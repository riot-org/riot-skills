#!/usr/bin/env python3
"""把 SVG 图表导出为 PNG（便于贴到微信/飞书/PPT），或把 report.html 导出为 PDF。

用法:
    python3 scripts/export_image.py charts/*.svg [--out-dir png/] [--scale 2] [--theme light|dark]
    python3 scripts/export_image.py report/report.html --pdf [--out-dir .]

渲染后端按顺序自动选择：Chrome/Chromium/Edge/Brave 无头模式 → rsvg-convert → cairosvg（Python 包）。
都不可用时报错并说明安装方式；不会联网下载任何东西。导出主题默认 light（白底更适合转发）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str | None:
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    for c in BROWSER_CANDIDATES:
        path = c if os.path.isabs(c) else shutil.which(c)
        if path and os.path.exists(path):
            return path
    return None


def svg_size(svg: str) -> tuple[int, int]:
    m = re.search(r'<svg[^>]*\bwidth="(\d+(?:\.\d+)?)"[^>]*\bheight="(\d+(?:\.\d+)?)"', svg)
    if not m:
        m2 = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg)
        if not m2:
            raise SystemExit("错误: 无法从 SVG 读取尺寸")
        return int(float(m2.group(1))), int(float(m2.group(2)))
    return int(float(m.group(1))), int(float(m.group(2)))


def set_theme(svg: str, mode: str) -> str:
    svg = re.sub(r'(<svg[^>]*?)\sdata-theme="[^"]*"', r"\1", svg, count=1)
    return svg.replace("<svg ", f'<svg data-theme="{mode}" ', 1)


def run_browser(browser: str, args: list[str]) -> None:
    with tempfile.TemporaryDirectory() as profile:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--hide-scrollbars", f"--user-data-dir={profile}", *args]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip()[-500:])


def svg_to_png(src: Path, dst: Path, scale: float, mode: str, browser: str | None) -> str:
    svg = set_theme(src.read_text(encoding="utf-8"), mode)
    w, h = svg_size(svg)
    if browser:
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.html"
            page.write_text("<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:transparent}"
                            f"svg{{display:block}}</style>{svg}", encoding="utf-8")
            run_browser(browser, [f"--window-size={w},{h}", f"--force-device-scale-factor={scale}",
                                  "--default-background-color=00000000", f"--screenshot={dst.resolve()}",
                                  page.resolve().as_uri()])
        return "chrome"
    if shutil.which("rsvg-convert"):
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as f:
            f.write(svg)
        try:
            subprocess.run(["rsvg-convert", "-z", str(scale), "-o", str(dst), f.name], check=True)
        finally:
            os.unlink(f.name)
        return "rsvg-convert"
    try:
        import cairosvg  # type: ignore
    except ImportError:
        raise SystemExit("错误: 没有可用的渲染后端。请安装 Chrome/Chromium，或 `brew install librsvg`，"
                         "或 `pip install cairosvg`；也可设置环境变量 CHROME_PATH 指向浏览器可执行文件。")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(dst), scale=scale)
    return "cairosvg"


def html_to_pdf(src: Path, dst: Path, browser: str | None) -> None:
    if not browser:
        raise SystemExit("错误: 导出 PDF 需要 Chrome/Chromium/Edge（或设置 CHROME_PATH）")
    run_browser(browser, ["--no-pdf-header-footer", f"--print-to-pdf={dst.resolve()}", src.resolve().as_uri()])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="SVG 文件或目录；--pdf 时为 HTML 文件")
    ap.add_argument("--out-dir", help="输出目录，默认与输入同目录")
    ap.add_argument("--scale", type=float, default=2.0, help="像素倍率，默认 2（高清）")
    ap.add_argument("--theme", choices=("light", "dark"), default="light")
    ap.add_argument("--pdf", action="store_true", help="把 HTML 报告导出为 PDF")
    a = ap.parse_args()

    files: list[Path] = []
    for i in a.inputs:
        p = Path(i)
        files += sorted(p.glob("*.svg")) if p.is_dir() else [p]
    if not files:
        raise SystemExit("错误: 没有找到输入文件")
    browser = find_browser()
    for src in files:
        out_dir = Path(a.out_dir) if a.out_dir else src.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        if a.pdf:
            dst = out_dir / (src.stem + ".pdf")
            html_to_pdf(src, dst, browser)
            print(f"已导出 {dst}")
        else:
            dst = out_dir / (src.stem + ".png")
            try:
                backend = svg_to_png(src, dst, a.scale, a.theme, browser)
            except RuntimeError as e:
                print(f"浏览器渲染失败（{e}），改用其它后端", file=sys.stderr)
                backend = svg_to_png(src, dst, a.scale, a.theme, None)
            print(f"已导出 {dst}（{backend}）")


if __name__ == "__main__":
    main()
