"""市场类图表：市场状态卡、行业涨跌热力图、广度与成交额走势。"""
from __future__ import annotations

from html import escape

from .base import date_ticks, fmt_axis, header, legend, polyline, svg_doc


def regime(r: dict) -> str:
    W, H = 760, 210
    tone = {"expansion": "var(--good)", "structural": "var(--warn)", "choppy": "var(--neutral)",
            "contraction": "var(--bad)", "unknown": "var(--neutral)"}[r["regime"]]
    icon = {"expansion": "▲", "structural": "◆", "choppy": "≈", "contraction": "▼", "unknown": "?"}[r["regime"]]
    body = [f'<rect x="16" y="16" width="6" height="52" rx="3" fill="{tone}"/>',
            f'<text x="34" y="38" class="title" style="font-size:18px">{icon} {escape(r["regime_label"])}</text>',
            f'<text x="34" y="60" class="sub">置信度：{escape(r["confidence"])} · 数据时点：{escape(str(r.get("date") or "未注明"))}</text>']
    if r.get("data_warnings"):
        body.append(f'<text x="{W - 16}" y="38" text-anchor="end" style="fill:var(--warn);font-weight:600">'
                    f'⚠ 数据口径存疑 {len(r["data_warnings"])} 项<title>{escape(chr(10).join(r["data_warnings"]))}</title></text>')
    names = (("trend", "大盘趋势"), ("breadth", "市场广度"), ("volume", "量能"), ("risk", "风险偏好"))
    cw = (W - 32 - 3 * 12) / 4
    for k, (key, label) in enumerate(names):
        s = r["signals"][key]
        v = s["score"]
        cx = 16 + k * (cw + 12)
        mark, col = (("缺失", "var(--neutral)") if v is None else ("偏多 ▲", "var(--good)") if v > 0.2
                     else ("偏空 ▼", "var(--bad)") if v < -0.2 else ("中性 ■", "var(--neutral)"))
        body.append(f'<rect x="{cx:.1f}" y="86" width="{cw:.1f}" height="104" rx="8" fill="none" stroke="var(--grid)"/>'
                    f'<text x="{cx + 12:.1f}" y="110">{label}</text>'
                    f'<text x="{cx + 12:.1f}" y="136" class="val" style="font-size:16px;font-weight:600">{mark}</text>')
        # 刻度条：-1 ~ +1
        bx, bwid = cx + 12, cw - 24
        body.append(f'<line x1="{bx:.1f}" x2="{bx + bwid:.1f}" y1="158" y2="158" stroke="var(--grid)" stroke-width="4" stroke-linecap="round"/>'
                    f'<line x1="{bx + bwid / 2:.1f}" x2="{bx + bwid / 2:.1f}" y1="152" y2="164" stroke="var(--muted)"/>')
        if v is not None:
            body.append(f'<circle cx="{bx + bwid * (v + 1) / 2:.1f}" cy="158" r="6" fill="{col}" stroke="var(--surface)" stroke-width="2"/>')
        body.append(f'<text x="{bx:.1f}" y="180" class="sub">空</text><text x="{bx + bwid:.1f}" y="180" class="sub" text-anchor="end">多</text>')
        body.append(f'<rect class="hit" x="{cx:.1f}" y="86" width="{cw:.1f}" height="104" rx="8">'
                    f'<title>{escape(label + "：" + s["evidence"])}</title></rect>')
    return svg_doc(W, H, body, f"市场状态：{r['regime_label']}")




def sector_heatmap(rows: list[dict], columns: list[tuple[str, str]], sort_by: str | None = None,
                   title: str = "行业涨跌热力图", subtitle: str = "") -> str:
    """rows: [{industry, <col>: 小数收益}]；columns: [(列名, 表头)]。红涨绿跌，格内写数值，不只靠颜色。"""
    sort_by = sort_by or columns[-1][0]
    rows = sorted(rows, key=lambda r: (r.get(sort_by) is None, -(r.get(sort_by) or 0)))
    W, L, top, rh = 760, 120, 84, 26
    H = top + rh * len(rows) + 40
    cw = (W - L - 16) / len(columns)
    vmax = max((abs(r[c]) for r in rows for c, _ in columns if r.get(c) is not None), default=0.01) or 0.01

    body = header(title, subtitle or f"按「{dict(columns)[sort_by]}」降序 · 颜色越深幅度越大（红涨绿跌）")
    for j, (c, lab) in enumerate(columns):
        body.append(f'<text x="{L + cw * (j + 0.5):.1f}" y="{top - 10}" text-anchor="middle" class="val">{escape(lab)}</text>')
    for i, r in enumerate(rows):
        y = top + i * rh
        body.append(f'<text x="{L - 10}" y="{y + 17}" text-anchor="end" class="val">{escape(str(r["industry"]))}</text>')
        for j, (c, lab) in enumerate(columns):
            v = r.get(c)
            cx = L + cw * j
            body.append(f'<rect x="{cx + 1:.1f}" y="{y + 1}" width="{cw - 2:.1f}" height="{rh - 2}" rx="3" fill="var(--surface-2)"/>')
            if v is None:
                body.append(f'<text x="{cx + cw / 2:.1f}" y="{y + 17}" text-anchor="middle" class="sub">—</text>')
                continue
            op = 0.12 + 0.6 * min(abs(v) / vmax, 1)
            tip = f"{r['industry']} {lab} {v:+.2%}"
            col = "var(--up)" if v > 0 else "var(--down)"
            body.append(f'<rect x="{cx + 1:.1f}" y="{y + 1}" width="{cw - 2:.1f}" height="{rh - 2}" rx="3" '
                        f'fill="{col}" fill-opacity="{op:.2f}"><title>{escape(tip)}</title></rect>'
                        f'<text x="{cx + cw / 2:.1f}" y="{y + 17}" text-anchor="middle" class="val">{v:+.1%}</text>')
    return svg_doc(W, H, body, title)


def breadth_history(hist: list[dict], title: str = "市场广度与成交额") -> str:
    """hist: [{date, pct_above_ma20, pct_above_ma60, turnover}]，两块面板各用各的纵轴。"""
    hist = sorted(hist, key=lambda h: h["date"])
    n = len(hist)
    if n < 2:
        raise SystemExit("错误: 广度历史少于 2 个点")
    W, L, R, top, ph, gap, vh = 760, 16, 64, 70, 200, 30, 90
    H = top + ph + gap + vh + 34
    pw = W - L - R
    x = lambda i: L + pw * i / (n - 1)
    py = lambda v: top + ph * (1 - v)
    body = header(title, f"{hist[0]['date']} → {hist[-1]['date']} · 50% 为多空分界参考")
    body += legend([("站上 MA20 比例", "var(--s1)"), ("站上 MA60 比例", "var(--s2)")], 16, 62)
    for t in (0, 0.25, 0.5, 0.75, 1):
        dash = ' stroke-dasharray="3 3"' if t == 0.5 else ""
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py(t):.1f}" y2="{py(t):.1f}"{dash}/>'
                    f'<text x="{W - R + 6}" y="{py(t) + 4:.1f}">{t:.0%}</text>')
    for key, c in (("pct_above_ma20", "var(--s1)"), ("pct_above_ma60", "var(--s2)")):
        body.append(polyline([None if h.get(key) is None else (x(i), py(h[key])) for i, h in enumerate(hist)], c, 2))
    vt = top + ph + gap
    tv = [h.get("turnover") for h in hist]
    tmax = max((v for v in tv if v), default=0)
    body.append(f'<text x="{L}" y="{vt - 8}" class="sub">全市场成交额</text>')
    if tmax:
        body.append(f'<text x="{W - R + 6}" y="{vt + 8}">{fmt_axis(tmax)}</text>')
        bw = max(1.0, pw / n * 0.7)
        for i, v in enumerate(tv):
            if v:
                h = vh * v / tmax
                body.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{vt + vh - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                            f'fill="var(--s1)" fill-opacity=".5"/>')
    body += date_ticks([h["date"] for h in hist], x, H - 12, L, W - R)
    step = pw / (n - 1)
    for i, h in enumerate(hist):
        parts = [h["date"]]
        for key, lab in (("pct_above_ma20", "站上 MA20"), ("pct_above_ma60", "站上 MA60")):
            if h.get(key) is not None:
                parts.append(f"{lab} {h[key]:.1%}")
        if h.get("turnover"):
            parts.append(f"成交额 {fmt_axis(h['turnover'])}")
        body.append(f'<rect class="hit" x="{x(i) - step / 2:.1f}" y="{top}" width="{step:.2f}" height="{ph + gap + vh}">'
                    f'<title>{escape(chr(10).join(parts))}</title></rect>')
    return svg_doc(W, H, body, title)
