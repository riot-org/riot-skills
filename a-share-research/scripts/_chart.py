"""分析脚本共用的出图出口：--chart xxx.svg 写 SVG；--chart xxx.png 同时写 SVG 并导出 PNG。"""
from __future__ import annotations

import sys
from pathlib import Path


def save_chart(svg: str, path: str | None, theme: str = "light") -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    svg_path = out.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    if out.suffix.lower() == ".png":
        from export_image import find_browser, svg_to_png
        try:
            svg_to_png(svg_path, out, 2.0, theme, find_browser())
        except (RuntimeError, SystemExit) as e:  # 导出失败不影响分析结果，SVG 仍可用
            print(f"PNG 导出失败（{e}），已保留 {svg_path}", file=sys.stderr)
            return
    print(f"图表：{out.resolve()}", file=sys.stderr)
