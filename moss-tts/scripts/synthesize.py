#!/usr/bin/env python3
"""逐句合成 Moss TTS 旁白，并打印时长/时间轴。

为什么逐句：做视频要知道每句在时间轴上的起点，逐句才有独立时长，
念错的一句也能单独重生成。

用法：
    python3 synthesize.py lines.txt --voice <voice_id> [选项]

lines.txt 一行一句；空行和 # 开头跳过。

选项：
    --voice ID        音色 ID（必填）
    --language NAME   发音语言英文全称，如 Chinese / English。中文建议显式写
    --model ID        默认 moss-tts-1.5-flash
    --format FMT      mp3（默认）/ wav / flac
    --outdir DIR      输出目录，默认 vo
    --pause SEC       每句末尾追加的停顿，写成 [pause Xs]（需要 1.5-flash）
    --expected SEC    期望时长，传给接口的 expected_duration_sec
    --resume          已有音频就跳过，不重新请求
    --timeline FILE   把时间轴写成 JSON，交给视频时间轴用
    --dry-run         只打印将要合成的内容，不调接口

Key 从环境变量 MOSS_API_KEY 读。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.mosi.cn/v1/audio/speech"


def die(msg: str, code: int = 1) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    raise SystemExit(code)


def parse_line(raw: str) -> tuple[float | None, str]:
    """一行可以是 ``@4.5 正文``，表示这句子目标时长 4.5 秒；没有前缀就返回 None。"""
    line = raw.strip()
    if not line.startswith("@"):
        return None, line
    head, _, rest = line[1:].partition(" ")
    try:
        return float(head), rest.strip()
    except ValueError:
        die(f"行首的 @{head} 不是秒数：{raw[:60]}")


def read_lines(path: Path) -> list[tuple[float | None, str]]:
    if not path.exists():
        die(f"找不到脚本文件 {path}")
    out: list[tuple[float | None, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(parse_line(line))
    if not out:
        die(f"{path} 里没有可合成的句子")
    return out


def synthesize(
    text: str,
    *,
    key: str,
    voice: str,
    model: str,
    language: str | None,
    fmt: str,
    expected: float | None,
) -> bytes:
    """调一次接口，返回音频二进制。"""
    body: dict[str, object] = {
        "model": model,
        "input": text,
        "voice_id": voice,
        "response_format": fmt,
        # 不传 delivery_method 就是直接返回音频二进制
    }
    if language:
        body["language"] = language
    if expected and expected > 0:
        body["expected_duration_sec"] = expected

    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "audio/*",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        code = ""
        try:
            code = json.loads(detail).get("error", {}).get("code", "")
        except Exception:  # noqa: BLE001 - 报错体不一定真的是 JSON
            pass
        if exc.code in (401, 403):
            die(f"HTTP {exc.code}，API Key 没配或失效。先确认 MOSS_API_KEY 已设置。\n{detail}")
        die(f"HTTP {exc.code}{f' [{code}]' if code else ''}：{detail}")
    except urllib.error.URLError as exc:
        die(f"连不上接口（{exc.reason}）。检查网络或代理。")

    # 传错 delivery_method 时可能回 JSON 而不是音频
    if data[:1] == b"{":
        die(f"接口返回了 JSON 而不是音频，检查参数：{data[:400].decode('utf-8', 'replace')}")
    if not data:
        die("接口返回了空音频")
    return data


def duration(path: Path) -> float | None:
    """音频时长（秒）。macOS 用 afinfo，其它平台退回 ffmpeg。

    坑：afinfo 对 mp3 会把 duration 那行写到 **stderr**（aiff 才在 stdout），
    所以两个流都要看，只读 stdout 会永远读不出 mp3 的时长。
    """
    try:
        r = subprocess.run(
            ["afinfo", str(path)], capture_output=True, text=True, timeout=30
        )
        for line in (r.stdout + "\n" + r.stderr).splitlines():
            if "estimated duration" in line:
                for token in line.replace(":", " ").split():
                    try:
                        return float(token)
                    except ValueError:
                        continue
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        ).stderr
        for line in out.splitlines():
            if "Duration:" in line:
                hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
                return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="逐句合成 Moss TTS 旁白")
    ap.add_argument("script", type=Path, help="一行一句的文本文件")
    ap.add_argument("--voice", required=True, help="音色 ID")
    ap.add_argument("--language", default=None, help="发音语言英文全称，如 Chinese")
    ap.add_argument("--model", default="moss-tts-1.5-flash")
    ap.add_argument("--format", default="mp3", choices=["mp3", "wav", "flac", "aac"])
    ap.add_argument("--outdir", type=Path, default=Path("vo"))
    ap.add_argument("--pause", type=float, default=0.0, help="每句末尾追加停顿秒数")
    ap.add_argument("--expected", type=float, default=None, help="expected_duration_sec")
    ap.add_argument("--resume", action="store_true", help="跳过已生成的")
    ap.add_argument("--timeline", type=Path, default=None, help="时间轴输出到 JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("MOSS_API_KEY", "").strip()
    if not key and not args.dry_run:
        die("环境变量 MOSS_API_KEY 没设置。去 https://platform.mosi.cn/app/api-keys/ "
            "建一个，然后 export MOSS_API_KEY=...（写进 ~/.zshrc 才持久）")

    lines = read_lines(args.script)
    if args.pause > 0 and args.model == "moss-tts-1.0-pro":
        die("moss-tts-1.0-pro 不支持 [pause] 语法，要么换 moss-tts-1.5-flash，要么去掉 --pause")

    args.outdir.mkdir(parents=True, exist_ok=True)
    width = max(2, len(str(len(lines))))
    print(f"音色 {args.voice} · 模型 {args.model} · {len(lines)} 句 → {args.outdir}/")
    if args.dry_run:
        for i, (want, text) in enumerate(lines, 1):
            tag = f"  @{want}s" if want else ""
            print(f"  {i:0{width}d}  {text}{tag}")
        return

    timeline: list[dict[str, object]] = []
    failed: list[tuple[int, str]] = []
    at = 0.0  # 累计时间，句间不留空隙（要空隙写进 --pause 或句子里的停顿标记）

    for i, (want, text) in enumerate(lines, 1):
        final = text
        if args.pause > 0:
            final = f"{text}[pause {args.pause:.1f}s]"
        target = args.outdir / f"{i:0{width}d}.{args.format}"
        # 行首 @N 优先，其次全局 --expected
        expected = want if want is not None else args.expected

        if args.resume and target.exists():
            note = "已存在，跳过"
        else:
            try:
                target.write_bytes(synthesize(
                    final, key=key, voice=args.voice, model=args.model,
                    language=args.language, fmt=args.format, expected=expected,
                ))
                note = "ok"
            except SystemExit as exc:  # 单句失败不该中断整批
                if exc.code == 0:
                    raise
                failed.append((i, text))
                note = "失败"
        secs = duration(target) if target.exists() else None
        if secs is None and note == "ok":
            failed.append((i, text))
            note = "生成成功但读不出时长"
            secs = 0.0
        secs = secs or 0.0
        timeline.append({
            "index": i, "file": target.name, "start": round(at, 2),
            "end": round(at + secs, 2), "duration": round(secs, 2), "text": text,
        })
        mark = "" if note in ("ok", "已存在，跳过") else f"  [{note}]"
        print(f"  {i:0{width}d}  {at:6.2f} → {at + secs:6.2f}s  {secs:5.2f}s  {text}{mark}")
        at += secs

    print(f"\n合计 {at:.2f} 秒")
    if args.timeline:
        args.timeline.write_text(
            json.dumps({"voice_id": args.voice, "model": args.model,
                        "total": round(at, 2), "lines": timeline},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"时间轴 → {args.timeline}")
    print("\n验证：时长合理（中文约 4–5 字/秒）；听感、语气、多音字要用户自己听。")
    if failed:
        print(f"\n{len(failed)} 句失败：{', '.join(str(i) for i, _ in failed)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
