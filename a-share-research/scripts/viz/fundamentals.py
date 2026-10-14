"""财务类图表：利润与现金流对比、利润现金含量、收入与应收增速对比。"""
from __future__ import annotations

from html import escape

from .base import SERIES, header, legend, nice_ticks, polyline, svg_doc


def cashflow(r: dict, title: str = "") -> str:
    """输入 cashflow_quality.py 的 JSON 输出（单个公司）。"""
    years = r["years"]
    unit = r.get("unit", "")
    title = title or f"{r.get('name') or ''} {r.get('code') or ''} 利润与现金流".strip()
    keys = [("net_profit", "净利润"), ("cfo", "经营现金流 CFO"), ("fcf", "自由现金流 FCF≈CFO−资本开支")]
    colors = SERIES[:3]

    W, L, R, top, ph, gap, rh = 760, 56, 24, 76, 210, 40, 90
    H = top + ph + gap + rh + 40
    pw = W - L - R
    vals = [y[k] for y in years for k, _ in keys if y[k] is not None] + [0]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = (lo - pad if lo < 0 else 0), hi + pad
    py = lambda v: top + ph * (1 - (v - lo) / (hi - lo))

    sub = f"单位：{unit} · 质量评级：{r.get('label', '—')}"
    if r.get("score") is not None:
        sub += f"（{r['score']:.0f}/100）"
    body = header(title, sub)
    body += legend([(lab, c) for (_, lab), c in zip(keys, colors)], 16, 64, kind="box")

    for t in nice_ticks(lo, hi, 4):
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                    f'<text x="{L - 6}" y="{py(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    body.append(f'<line x1="{L}" x2="{W - R}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="var(--muted)"/>')

    gw = pw / len(years)
    bw = min(26.0, (gw - 18) / 3)
    for i, y in enumerate(years):
        gx = L + gw * i + (gw - 3 * bw - 4) / 2
        for k, ((key, lab), c) in enumerate(zip(keys, colors)):
            v = y[key]
            bx = gx + k * (bw + 2)
            if v is None:
                body.append(f'<text x="{bx + bw / 2:.1f}" y="{py(0) - 4:.1f}" text-anchor="middle" class="sub">缺</text>')
                continue
            y0, y1 = sorted((py(0), py(v)))
            tip = f"{y['period']} {lab}：{v:,.2f} {unit}"
            body.append(f'<rect x="{bx:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(y1 - y0, 1):.1f}" rx="3" fill="{c}">'
                        f'<title>{escape(tip)}</title></rect>')
        body.append(f'<text x="{L + gw * (i + 0.5):.1f}" y="{top + ph + 16}" text-anchor="middle">{escape(str(y["period"]))}</text>')

    # 利润现金含量：CFO / 净利润，参考线 1.0
    rt = top + ph + gap
    ratios = [y.get("cfo_to_ni") for y in years]
    present = [v for v in ratios if v is not None]
    body.append(f'<text x="{L}" y="{rt - 4}" class="sub">利润现金含量 CFO ÷ 净利润（≥1 表示利润基本收到现金）</text>')
    if present:
        rlo, rhi = min(min(present), 0.8) - 0.1, max(max(present), 1.1) + 0.1
        ry = lambda v: rt + 8 + (rh - 8) * (1 - (v - rlo) / (rhi - rlo))
        body.append(f'<line x1="{L}" x2="{W - R}" y1="{ry(1):.1f}" y2="{ry(1):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
                    f'<text x="{L - 6}" y="{ry(1) + 4:.1f}" text-anchor="end">1.0</text>')
        pts = [None if v is None else (L + gw * (i + 0.5), ry(v)) for i, v in enumerate(ratios)]
        body.append(polyline(pts, "var(--s7)", 2))
        for p, v in zip(pts, ratios):
            if p is None:
                continue
            col = "var(--good)" if v >= 1 else "var(--warn)" if v >= 0.6 else "var(--bad)"
            body.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="5" fill="{col}" stroke="var(--surface)" stroke-width="2"/>'
                        f'<text x="{p[0]:.1f}" y="{p[1] - 9:.1f}" text-anchor="middle" class="val">{v:.2f}</text>')
    else:
        body.append(f'<text x="{L}" y="{rt + 30}" class="sub">数据不足</text>')
    return svg_doc(W, H, body, title)


def growth_gap(r: dict, title: str = "") -> str:
    """收入增速 vs 应收+合同资产增速：应收显著跑赢收入是回款恶化信号。"""
    years = [y for y in r["years"] if y.get("revenue_growth") is not None]
    title = title or f"{r.get('name') or ''} 收入与应收增速".strip()
    W, L, R, top, ph = 760, 56, 24, 76, 200
    H = top + ph + 40
    pw = W - L - R
    keys = [("revenue_growth", "收入增速"), ("receivables_growth", "应收+合同资产增速"),
            ("inventory_growth", "存货增速")]
    vals = [y[k] for y in years for k, _ in keys if y.get(k) is not None] + [0]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.1 or 0.05
    lo, hi = min(lo - pad, 0), hi + pad
    py = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    body = header(title, "应收/存货增速持续明显快于收入，需核查回款和库存")
    body += legend([(lab, c) for (_, lab), c in zip(keys, SERIES)], 16, 64)
    for t in nice_ticks(lo, hi, 4):
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                    f'<text x="{L - 6}" y="{py(t) + 4:.1f}" text-anchor="end">{t:.0%}</text>')
    if not years:
        body.append(f'<text x="{L}" y="{top + 40}" class="sub">数据不足</text>')
        return svg_doc(W, H, body, title)
    gw = pw / len(years)
    for k, ((key, lab), c) in enumerate(zip(keys, SERIES)):
        pts = [None if y.get(key) is None else (L + gw * (i + 0.5), py(y[key])) for i, y in enumerate(years)]
        body.append(polyline(pts, c, 2))
        for p, y in zip(pts, years):
            if p:
                tip = f"{y['period']} {lab} {y[key]:+.1%}"
                body.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="4" fill="{c}" stroke="var(--surface)" stroke-width="2">'
                            f'<title>{escape(tip)}</title></circle>')
    for i, y in enumerate(years):
        body.append(f'<text x="{L + gw * (i + 0.5):.1f}" y="{H - 14}" text-anchor="middle">{escape(str(y["period"]))}</text>')
    return svg_doc(W, H, body, title)
