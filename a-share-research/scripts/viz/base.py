"""图表公共部分：主题色、SVG 外壳、刻度和折线工具。

颜色全部写成 CSS 变量，SVG 跟随系统深浅色；根元素加 data-theme="light|dark" 可强制主题
（export_png.py 导出图片时用）。分类色顺序固定：s1 蓝、s2 橙、s3 青绿、s4 黄、s5 品红、s7 紫。
A 股习惯红涨绿跌：--up / --down。
"""
from __future__ import annotations

import math
from html import escape

_LIGHT = ("--surface:#fcfcfb; --surface-2:#f3f2ef; --ink:#0b0b0b; --ink-2:#52514e; --muted:#8a8984; "
          "--grid:#e7e6e2; --up:#d03b3b; --down:#0ca30c; --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; "
          "--s4:#eda100; --s5:#e87ba4; --s7:#4a3aa7; --good:#0ca30c; --warn:#fab219; --bad:#d03b3b; "
          "--neutral:#a8a7a1; --band:#2a78d6;")
_DARK = ("--surface:#1a1a19; --surface-2:#242422; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#8f8e88; "
         "--grid:#2e2e2b; --up:#e66767; --down:#0ca30c; --s1:#3987e5; --s2:#d95926; --s3:#199e70; "
         "--s4:#c98500; --s5:#d55181; --s7:#9085e9; --neutral:#6d6c67; --band:#3987e5;")

STYLE = f"""
<style>
  svg {{ {_LIGHT} }}
  @media (prefers-color-scheme: dark) {{ svg:not([data-theme="light"]) {{ {_DARK} }} }}
  svg[data-theme="dark"] {{ {_DARK} }}
  text {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
         fill: var(--ink-2); font-size: 11px; }}
  .title {{ fill: var(--ink); font-size: 15px; font-weight: 600; }}
  .sub {{ fill: var(--muted); font-size: 11px; }}
  .val {{ fill: var(--ink); font-variant-numeric: tabular-nums; }}
  .big {{ fill: var(--ink); font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .halo {{ paint-order: stroke; stroke: var(--surface); stroke-width: 4px; stroke-linejoin: round; }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .hit {{ fill: transparent; }}
  .hit:hover {{ fill: var(--grid); fill-opacity: .5; }}
</style>"""

# 固定顺序的分类色；第 9 个以后不再生成新色
SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s7)"]

# 结论徽章：图标 + 文字 + 颜色，不只靠颜色区分
VERDICT = {"优先研究": ("★", "var(--good)"), "观察等待": ("◷", "var(--warn)"),
           "回避": ("✕", "var(--bad)"), "无法判断": ("?", "var(--neutral)")}


def svg_doc(w: int, h: int, body: list[str], label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{escape(label)}">{STYLE}'
            f'<rect width="{w}" height="{h}" fill="var(--surface)" rx="8"/>' + "".join(body) + "</svg>")


def nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.ceil(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step + 1e-9) + 1)]


def fmt_axis(v: float) -> str:
    if abs(v) >= 1e12:
        return f"{v / 1e12:.2f}万亿"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.1f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.2f}" if abs(v) < 100 else f"{v:.0f}"


def polyline(points: list[tuple[float, float] | None], color: str, width: float = 2, dash: str = "") -> str:
    """缺失点（None）处断开折线。"""
    segs, cur = [], []
    for p in points + [None]:
        if p is None:
            if len(cur) > 1:
                segs.append(cur)
            cur = []
        else:
            cur.append(p)
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return "".join(
        f'<polyline fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" '
        f'stroke-linecap="round"{extra} points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in s)}"/>' for s in segs)


def area(points: list[tuple[float, float]], base_y: float, color: str, opacity: float = 0.15) -> str:
    if len(points) < 2:
        return ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (f'<polygon fill="{color}" fill-opacity="{opacity}" stroke="none" '
            f'points="{points[0][0]:.1f},{base_y:.1f} {pts} {points[-1][0]:.1f},{base_y:.1f}"/>')


def header(title: str, subtitle: str = "", x: int = 16) -> list[str]:
    out = [f'<text x="{x}" y="26" class="title">{escape(title)}</text>']
    if subtitle:
        out.append(f'<text x="{x}" y="44" class="sub">{escape(subtitle)}</text>')
    return out


def legend(items: list[tuple[str, str]], x: float, y: float, kind: str = "line") -> list[str]:
    """items: [(标签, 颜色)]；kind=line 画短线，box 画色块。返回元素列表。"""
    out, cx = [], x
    for label, color in items:
        if kind == "line":
            out.append(f'<line x1="{cx:.1f}" y1="{y - 4}" x2="{cx + 16:.1f}" y2="{y - 4}" stroke="{color}" stroke-width="2"/>')
            tx = cx + 21
        else:
            out.append(f'<rect x="{cx:.1f}" y="{y - 10}" width="10" height="10" rx="2" fill="{color}"/>')
            tx = cx + 14
        out.append(f'<text x="{tx:.1f}" y="{y}">{escape(label)}</text>')
        cx = tx + text_width(label) + 16
    return out


def text_width(s: str, size: float = 11) -> float:
    """粗略估算文本宽度：中文按 1 em，其它按 0.6 em。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.6 for ch in s)


def date_ticks(dates: list[str], x, y: float, left: float, right: float, n: int = 5) -> list[str]:
    """首尾对齐边缘，中间均匀取 n 个日期标签。"""
    if not dates:
        return []
    k = len(dates)
    idx = sorted({0, k - 1, *range(0, k, max(1, k // n))})
    if len(idx) > 2 and idx[-1] - idx[-2] < k // (2 * n):
        idx.pop(-2)
    out = []
    for i in idx:
        anchor, tx = ("start", left) if i == 0 else ("end", right) if i == k - 1 else ("middle", x(i))
        out.append(f'<text x="{tx:.1f}" y="{y}" text-anchor="{anchor}">{escape(dates[i][2:])}</text>')
    return out


def signed_color(v: float | None) -> str:
    if v is None:
        return "var(--neutral)"
    return "var(--up)" if v > 0 else "var(--down)" if v < 0 else "var(--neutral)"
