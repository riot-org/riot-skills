"""组合与排序图表：综合评分堆叠条、行业/个股持仓分布。"""
from __future__ import annotations

from html import escape

from .base import SERIES, header, legend, svg_doc, text_width


GROUP_ORDER = [("trend", "趋势", "var(--s1)"), ("quality", "现金流质量", "var(--s2)"),
               ("valuation", "估值", "var(--s3)"), ("liquidity", "流动性", "var(--s4)"),
               ("risk", "供给/事件风险", "var(--s5)")]


def scores(res: dict, top: int) -> str:
    ranked = res["ranked"][:top]
    w = res["weights"]
    W, L, R, row = 760, 150, 70, 30
    top_y = 78
    H = top_y + row * len(ranked) + 58
    pw = W - L - R
    body = [f'<text x="16" y="24" class="title">候选股综合评分</text>',
            f'<text x="16" y="42" class="sub">每段 = 子项得分 × 权重，总长 = 综合分（0~100，仅用于排序）'
            f'{" · 状态：" + escape(res["regime"]) if res.get("regime") else ""}</text>']
    lx = 16
    for g, label, c in GROUP_ORDER:
        if g not in w:
            continue
        text = f"{label} {w[g]:.0%}"
        body.append(f'<rect x="{lx}" y="54" width="10" height="10" rx="2" fill="{c}"/>'
                    f'<text x="{lx + 14}" y="63">{escape(text)}</text>')
        lx += 26 + len(text) * 9
    for t in (0, 25, 50, 75, 100):
        gx = L + pw * t / 100
        body.append(f'<line class="grid" x1="{gx:.1f}" x2="{gx:.1f}" y1="{top_y - 4}" y2="{H - 48}"/>'
                    f'<text x="{gx:.1f}" y="{H - 32}" text-anchor="middle">{t}</text>')
    for k, s in enumerate(ranked):
        y = top_y + k * row
        body.append(f'<text x="{L - 10}" y="{y + 17}" text-anchor="end" class="val">{k + 1}. '
                    f'{escape(str(s["name"]))} {escape(str(s["code"]))}</text>')
        total_w = sum(w[g] for g, _, _ in GROUP_ORDER if g in w and s["groups"].get(g) is not None)
        cx = L
        tip = [f'{s["name"]} {s["code"]}（{s.get("industry") or ""}）综合 {s["total"]:.1f}']
        for g, label, c in GROUP_ORDER:
            v = s["groups"].get(g)
            if g not in w:
                continue
            if v is None:
                tip.append(f"{label}：不适用/缺失")
                continue
            seg = pw * v / 100 * w[g] / total_w
            if seg > 0.5:
                body.append(f'<rect x="{cx:.1f}" y="{y + 5}" width="{max(seg - 2, 0.5):.1f}" height="16" rx="2" fill="{c}"/>')
            cx += seg
            tip.append(f"{label}：{v:.0f} 分 × {w[g] / total_w:.0%}")
        if s.get("missing"):
            tip.append("缺失：" + "、".join(s["missing"]))
        body.append(f'<text x="{cx + 6:.1f}" y="{y + 17}" class="val">{s["total"]:.0f}'
                    f'{" *" if s.get("missing") else ""}</text>')
        body.append(f'<rect class="hit" x="0" y="{y}" width="{W}" height="{row}"><title>{escape(chr(10).join(tip))}</title></rect>')
    if any(s.get("missing") for s in ranked):
        body.append(f'<text x="16" y="{H - 10}" class="sub">* 有缺失数据，缺失项按最差分位计；悬停查看明细</text>')
    return svg_doc(W, H, body, "候选股综合评分")




def allocation(holdings: list[dict], max_weight: float, max_industry: float,
               title: str = "组合权重分布") -> str:
    """holdings: [{code, name, industry, weight}]，weight 为小数。超过上限的条目标红并写“超限”。"""
    by_ind: dict[str, float] = {}
    for h in holdings:
        by_ind[h.get("industry") or "未分类"] = by_ind.get(h.get("industry") or "未分类", 0) + h["weight"]
    sections = [("按行业", sorted(by_ind.items(), key=lambda kv: -kv[1]), max_industry),
                ("按个股", sorted(((f"{h['name']} {h['code']}", h["weight"]) for h in holdings), key=lambda kv: -kv[1]),
                 max_weight)]
    W, L, R, row = 760, 150, 90, 24
    H = 70 + sum(36 + row * len(items) for _, items, _ in sections) + 20
    pw = W - L - R
    vmax = max([v for _, items, _ in sections for _, v in items] + [max_industry, max_weight]) * 1.1
    total = sum(h["weight"] for h in holdings)
    body = header(title, f"合计 {total:.1%}，现金 {max(0.0, 1 - total):.1%} · 虚线 = 上限（行业 {max_industry:.0%}，"
                         f"单股 {max_weight:.0%}）")
    y = 70
    for label, items, cap in sections:
        body.append(f'<text x="16" y="{y + 14}" class="val" style="font-weight:600">{label}</text>')
        y += 30
        cap_x = L + pw * cap / vmax
        body.append(f'<line x1="{cap_x:.1f}" x2="{cap_x:.1f}" y1="{y}" y2="{y + row * len(items)}" '
                    f'stroke="var(--muted)" stroke-dasharray="4 3"/>'
                    f'<text x="{cap_x:.1f}" y="{y - 4}" text-anchor="middle" class="sub">上限 {cap:.0%}</text>')
        for name, v in items:
            over = v > cap + 1e-9
            c = "var(--bad)" if over else "var(--s1)"
            body.append(f'<text x="{L - 10}" y="{y + 15}" text-anchor="end" class="val">{escape(name)}</text>'
                        f'<rect x="{L}" y="{y + 4}" width="{max(pw * v / vmax, 1):.1f}" height="14" rx="3" fill="{c}"/>'
                        f'<text x="{L + pw * v / vmax + 6:.1f}" y="{y + 15}" class="val halo">{v:.1%}{" ⚠ 超限" if over else ""}</text>')
            y += row
        y += 6
    return svg_doc(W, H, body, title)
