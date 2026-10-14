"""个股一页卡片：结论徽章、关键数字、走势缩略图、分项得分、支持/风险要点。适合贴到报告或群聊。"""
from __future__ import annotations

from html import escape

from _common import Bar, sma

from .base import VERDICT, area, header, polyline, svg_doc, signed_color, text_width
from .portfolio import GROUP_ORDER


def _clip(s: str, width: float) -> str:
    out, w = "", 0.0
    for ch in s:
        w += text_width(ch, 12)
        if w > width:
            return out + "…"
        out += ch
    return out


def stock_card(c: dict, bars: list[Bar] | None, ind: dict | None, cf: dict | None, score: dict | None,
               weights: dict | None = None) -> str:
    ind, cf = ind or {}, cf or {}
    n_items = max(1, *(min(len(c.get(k) or []), 4) for k in ("supports", "risks", "invalidation")))
    W, H = 760, 352 + 22 * n_items + 26
    verdict = c.get("conclusion", "无法判断")
    icon, vcol = VERDICT.get(verdict, VERDICT["无法判断"])
    mf, res = c.get("main_force") or {}, c.get("resonance") or {}
    bits = [c.get("industry"), f"数据截至 {ind['date']}" if ind.get("date") else "",
            f"主力：{mf['phase_label']}" if mf else "",
            f"共振 {res['yes_count']}/4（{res['level']}）" if res else ""]
    body = header(f"{c.get('name', '')} {c.get('code', '')}", " · ".join(x for x in bits if x))
    bw = text_width(verdict, 13) + 40
    body.append(f'<rect x="{W - 16 - bw:.1f}" y="12" width="{bw:.1f}" height="30" rx="15" fill="{vcol}" fill-opacity=".16" stroke="{vcol}"/>'
                f'<text x="{W - 16 - bw / 2:.1f}" y="32" text-anchor="middle" class="val" style="font-size:13px;font-weight:600">'
                f'{icon} {escape(verdict)}</text>')

    # 关键数字
    rs = (ind.get("vs_industry") or ind.get("vs_bench") or {}).get("excess_60d")
    tiles = [
        ("收盘", f"{ind['close']:.2f}" if ind.get("close") else "—",
         f"20 日 {ind['ret_20d']:+.1%}" if ind.get("ret_20d") is not None else "", signed_color(ind.get("ret_20d"))),
        ("60 日超额", f"{rs:+.1%}" if rs is not None else "—", "相对行业" if ind.get("vs_industry") else "相对基准",
         signed_color(rs)),
        ("距 MA60", f"{ind['dist_ma60']:+.1%}" if ind.get("dist_ma60") is not None else "—",
         "MA60 向上" if (ind.get("ma60_slope") or 0) > 0 else "MA60 走平/向下", signed_color(ind.get("dist_ma60"))),
        ("120 日最大回撤", f"{ind['max_drawdown_120d']:.1%}" if ind.get("max_drawdown_120d") is not None else "—",
         f"年化波动 {ind['volatility_60d_ann']:.0%}" if ind.get("volatility_60d_ann") else "", "var(--ink-2)"),
        ("现金流质量", cf.get("label", "—"), f"{cf['score']:.0f}/100" if cf.get("score") is not None else "",
         {"优": "var(--good)", "良": "var(--good)", "中": "var(--warn)", "差": "var(--bad)"}.get(cf.get("label"), "var(--ink-2)")),
    ]
    tw = (W - 32 - 4 * 10) / 5
    for i, (lab, val, note, col) in enumerate(tiles):
        tx = 16 + i * (tw + 10)
        body.append(f'<rect x="{tx:.1f}" y="58" width="{tw:.1f}" height="74" rx="8" fill="var(--surface-2)"/>'
                    f'<rect x="{tx:.1f}" y="58" width="3" height="74" rx="1.5" fill="{col}"/>'
                    f'<text x="{tx + 12:.1f}" y="78" class="sub">{escape(lab)}</text>'
                    f'<text x="{tx + 12:.1f}" y="106" class="big">{escape(val)}</text>'
                    f'<text x="{tx + 12:.1f}" y="124" class="sub">{escape(note)}</text>')

    # 走势缩略图（最近 120 日收盘 + MA60）
    sx, sy, sw, sh = 16, 150, 440, 140
    body.append(f'<text x="{sx}" y="{sy}" class="sub">近 120 日收盘与 MA60</text>')
    if bars and len(bars) > 2:
        closes = [b.close for b in bars]
        ma60 = sma(closes, 60)
        view, mv = closes[-120:], ma60[-120:]
        lo = min(view + [v for v in mv if v is not None])
        hi = max(view + [v for v in mv if v is not None])
        x = lambda i: sx + sw * i / (len(view) - 1)
        y = lambda v: sy + 10 + (sh - 10) * (1 - (v - lo) / ((hi - lo) or 1))
        pts = [(x(i), y(v)) for i, v in enumerate(view)]
        body.append(area(pts, sy + sh, "var(--s1)", 0.12))
        body.append(polyline(pts, "var(--s1)", 2))
        body.append(polyline([None if v is None else (x(i), y(v)) for i, v in enumerate(mv)], "var(--s2)", 1.5, "4 3"))
        body.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>')
        body.append(f'<text x="{sx + sw:.1f}" y="{sy + sh + 14}" text-anchor="end" class="sub">实线 收盘 · 虚线 MA60</text>')
    else:
        body.append(f'<text x="{sx}" y="{sy + 40}" class="sub">无行情数据</text>')

    # 分项得分
    gx, gy = 486, 150
    body.append(f'<text x="{gx}" y="{gy}" class="sub">分项得分（0~100）{" · 综合 " + format(score["total"], ".0f") if score else ""}</text>')
    if score:
        for k, (g, lab, col) in enumerate(GROUP_ORDER):
            v = score["groups"].get(g)
            yy = gy + 14 + k * 26
            body.append(f'<text x="{gx}" y="{yy + 12}">{escape(lab)}</text>'
                        f'<rect x="{gx + 92}" y="{yy + 2}" width="150" height="12" rx="3" fill="var(--surface-2)"/>')
            if v is None:
                body.append(f'<text x="{gx + 250}" y="{yy + 12}" class="sub">不适用</text>')
            else:
                body.append(f'<rect x="{gx + 92}" y="{yy + 2}" width="{max(1.5 * v, 1):.1f}" height="12" rx="3" fill="{col}"/>'
                            f'<text x="{gx + 250}" y="{yy + 12}" class="val">{v:.0f}</text>')
    else:
        body.append(f'<text x="{gx}" y="{gy + 30}" class="sub">未评分</text>')

    # 要点
    cols = [("支持因素", c.get("supports") or [], "var(--good)", "+"),
            ("主要风险", c.get("risks") or [], "var(--bad)", "−"),
            ("失效条件", c.get("invalidation") or [], "var(--warn)", "!")]
    cw = (W - 32 - 2 * 12) / 3
    for i, (lab, items, col, mark) in enumerate(cols):
        cx = 16 + i * (cw + 12)
        body.append(f'<text x="{cx:.1f}" y="330" class="val" style="font-weight:600">{escape(lab)}</text>')
        for k, it in enumerate(items[:4] or ["（未提供）"]):
            yy = 352 + k * 22
            body.append(f'<text x="{cx:.1f}" y="{yy}" style="fill:{col};font-weight:700">{mark}</text>'
                        f'<text x="{cx + 14:.1f}" y="{yy}" style="font-size:12px"><title>{escape(it)}</title>'
                        f'{escape(_clip(it, cw - 18))}</text>')
    body.append(f'<text x="16" y="{H - 12}" class="sub">研究辅助，不构成投资建议 · 指标由脚本计算，口径见报告</text>')
    return svg_doc(W, H, body, f"{c.get('name', '')} 个股卡片")
