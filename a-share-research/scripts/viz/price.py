"""价格类图表：K 线、多股业绩对比（含回撤）、估值分位带。"""
from __future__ import annotations

from html import escape

from _common import Bar, sma

from .base import (SERIES, area, date_ticks, fmt_axis, header, legend, nice_ticks, polyline,
                   svg_doc, text_width)


def kline(bars: list[Bar], bench: list[Bar] | None, days: int, title: str) -> str:
    ma_full = {n: sma([b.close for b in bars], n) for n in (20, 60, 120)}
    view = bars[-days:]
    off = len(bars) - len(view)
    W, L, R = 760, 16, 64
    top, price_h, gap, vol_h = 58, 250, 22, 70
    rs_h = 70 if bench else 0
    H = top + price_h + gap + vol_h + (gap + rs_h if bench else 0) + 34
    pw = W - L - R
    step = pw / len(view)
    bw = max(1.0, min(8.0, step * 0.65))
    x = lambda i: L + step * (i + 0.5)

    lo = min(b.low for b in view)
    hi = max(b.high for b in view)
    for n in ma_full:
        vals = [v for v in ma_full[n][off:] if v is not None]
        if vals:
            lo, hi = min(lo, min(vals)), max(hi, max(vals))
    pad = (hi - lo) * 0.05
    lo, hi = lo - pad, hi + pad
    py = lambda v: top + price_h * (1 - (v - lo) / (hi - lo))

    last = view[-1]
    chg = last.close / view[-2].close - 1 if len(view) > 1 else 0
    body = [f'<text x="{L}" y="24" class="title">{escape(title)}</text>',
            f'<text x="{L}" y="42" class="sub">{escape(view[0].date)} → {escape(last.date)} · 收盘 '
            f'{last.close:.2f}（{chg:+.2%}） · 价格需为同一复权口径</text>']

    # 图例
    lx = W - R - 250
    for i, (n, c) in enumerate(((20, "var(--s1)"), (60, "var(--s2)"), (120, "var(--s7)"))):
        body.append(f'<line x1="{lx + i * 70}" y1="38" x2="{lx + i * 70 + 16}" y2="38" stroke="{c}" stroke-width="2"/>'
                    f'<text x="{lx + i * 70 + 21}" y="42">MA{n}</text>')

    for t in nice_ticks(lo, hi, 5):
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                    f'<text x="{W - R + 6}" y="{py(t) + 4:.1f}">{fmt_axis(t)}</text>')

    for i, b in enumerate(view):
        up = b.close >= b.open
        c = "var(--up)" if up else "var(--down)"
        y1, y2 = py(max(b.open, b.close)), py(min(b.open, b.close))
        body.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{py(b.high):.1f}" y2="{py(b.low):.1f}" stroke="{c}" stroke-width="1"/>'
                    f'<rect x="{x(i) - bw / 2:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(1.0, y2 - y1):.1f}" '
                    f'fill="{c if not up else "var(--surface)"}" stroke="{c}" stroke-width="1"/>')

    for n, c in ((20, "var(--s1)"), (60, "var(--s2)"), (120, "var(--s7)")):
        pts = [None if v is None else (x(i), py(v)) for i, v in enumerate(ma_full[n][off:])]
        body.append(polyline(pts, c, 1.6))

    # 成交量
    vt = top + price_h + gap
    vmax = max(b.volume for b in view) or 1
    body.append(f'<text x="{L}" y="{vt - 6}" class="sub">成交量</text>'
                f'<text x="{W - R + 6}" y="{vt + 8}">{fmt_axis(vmax)}</text>'
                f'<line class="grid" x1="{L}" x2="{W - R}" y1="{vt + vol_h}" y2="{vt + vol_h}"/>')
    for i, b in enumerate(view):
        h = vol_h * b.volume / vmax
        c = "var(--up)" if b.close >= b.open else "var(--down)"
        body.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{vt + vol_h - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                    f'fill="{c}" fill-opacity=".55"/>')

    # 相对强度：个股 / 基准，归一到视窗首日 = 1
    rs_vals: list[float | None] = []
    if bench:
        bmap = {b.date: b.close for b in bench}
        rt = vt + vol_h + gap
        base = next(((b.close, bmap[b.date]) for b in view if b.date in bmap), None)
        rs_vals = [(b.close / base[0]) / (bmap[b.date] / base[1]) if base and b.date in bmap else None for b in view]
        present = [v for v in rs_vals if v is not None]
        if present:
            rlo, rhi = min(present + [1.0]), max(present + [1.0])
            rpad = (rhi - rlo) * 0.08 or 0.01
            rlo, rhi = rlo - rpad, rhi + rpad
            ry = lambda v: rt + rs_h * (1 - (v - rlo) / (rhi - rlo))
            body.append(f'<text x="{L}" y="{rt - 6}" class="sub">相对强度（个股 ÷ 基准，首日 = 1.00，'
                        f'当前 {present[-1]:.2f}）</text>'
                        f'<line x1="{L}" x2="{W - R}" y1="{ry(1):.1f}" y2="{ry(1):.1f}" stroke="var(--muted)" '
                        f'stroke-dasharray="3 3"/><text x="{W - R + 6}" y="{ry(1) + 4:.1f}">1.00</text>')
            body.append(polyline([None if v is None else (x(i), ry(v)) for i, v in enumerate(rs_vals)], "var(--s3)", 2))

    # 日期刻度
    body += date_ticks([b.date for b in view], x, H - 12, L, W - R)

    # 悬停：每根 K 线一个全高透明命中区域 + <title>
    for i, b in enumerate(view):
        j = off + i
        tip = (f"{b.date}\n开 {b.open:.2f}  高 {b.high:.2f}\n低 {b.low:.2f}  收 {b.close:.2f}\n"
               f"成交量 {fmt_axis(b.volume)}" + (f"  成交额 {fmt_axis(b.amount)}" if b.amount else ""))
        mas = [f"MA{n} {ma_full[n][j]:.2f}" for n in (20, 60, 120) if ma_full[n][j] is not None]
        if mas:
            tip += "\n" + "  ".join(mas)
        if rs_vals and rs_vals[i] is not None:
            tip += f"\n相对强度 {rs_vals[i]:.3f}"
        body.append(f'<rect class="hit" x="{L + step * i:.1f}" y="{top}" width="{step:.2f}" '
                    f'height="{H - top - 30}"><title>{escape(tip)}</title></rect>')
    return svg_doc(W, H, body, f"{title} K 线图")




def performance(series: list[tuple[str, list[Bar]]], bench: tuple[str, list[Bar]] | None,
                days: int, title: str = "区间表现对比") -> str:
    """多只股票归一到 100 的走势 + 回撤面板。最多 6 只，超过请拆图。"""
    series = series[:len(SERIES)]
    names = [n for n, _ in series] + ([bench[0]] if bench else [])
    all_bars = [b for _, b in series] + ([bench[1]] if bench else [])
    common = sorted(set.intersection(*(set(b.date for b in bars) for bars in all_bars)))[-days:]
    if len(common) < 2:
        raise SystemExit("错误: 各序列没有足够的共同交易日")
    maps = [{b.date: b.close for b in bars} for bars in all_bars]
    norm = [[100 * m[d] / m[common[0]] for d in common] for m in maps]
    dd = []
    for vals in norm:
        peak, row = vals[0], []
        for v in vals:
            peak = max(peak, v)
            row.append(v / peak - 1)
        dd.append(row)
    colors = SERIES[:len(series)] + (["var(--muted)"] if bench else [])

    W, L, R, top, ph, gap, dh = 760, 44, 110, 70, 240, 26, 90
    H = top + ph + gap + dh + 34
    pw = W - L - R
    x = lambda i: L + pw * i / (len(common) - 1)
    lo, hi = min(map(min, norm)), max(map(max, norm))
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    py = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    dlo = min(min(map(min, dd)), -0.05)
    dy = lambda v: top + ph + gap + dh * (v / dlo)

    body = header(title, f"{common[0]} → {common[-1]} · 首日 = 100 · 收盘价需同一复权口径")
    body += legend(list(zip(names, colors)), 16, 62)
    for t in nice_ticks(lo, hi, 5):
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                    f'<text x="{L - 6}" y="{py(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    body.append(f'<line x1="{L}" x2="{W - R}" y1="{py(100):.1f}" y2="{py(100):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>')
    for k, vals in enumerate(norm):
        is_bench = bench and k == len(norm) - 1
        body.append(polyline([(x(i), py(v)) for i, v in enumerate(vals)], colors[k], 1.6 if is_bench else 2,
                             "4 3" if is_bench else ""))
    # 右侧直接标注终值（按 y 排序后避让）
    ends = sorted(((py(vals[-1]), k) for k, vals in enumerate(norm)))
    last_y = -1e9
    for y, k in ends:
        y = max(y, last_y + 13)
        last_y = y
        ret = norm[k][-1] / 100 - 1
        body.append(f'<text x="{W - R + 6}" y="{y + 4:.1f}" class="val">{escape(names[k][:6])} {ret:+.1%}</text>')

    dt = top + ph + gap
    body.append(f'<text x="{L}" y="{dt - 8}" class="sub">回撤（距区间内高点）</text>')
    for t in nice_ticks(dlo, 0, 3):
        body.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{dy(t):.1f}" y2="{dy(t):.1f}"/>'
                    f'<text x="{L - 6}" y="{dy(t) + 4:.1f}" text-anchor="end">{t:.0%}</text>')
    for k, row in enumerate(dd):
        body.append(polyline([(x(i), dy(v)) for i, v in enumerate(row)], colors[k], 1.3))
    body += date_ticks(common, x, H - 12, L, W - R)

    step = pw / (len(common) - 1)
    for i, d in enumerate(common):
        tip = d + "".join(f"\n{names[k]}：{norm[k][i]:.1f}（回撤 {dd[k][i]:.1%}）" for k in range(len(norm)))
        body.append(f'<rect class="hit" x="{x(i) - step / 2:.1f}" y="{top}" width="{step:.2f}" '
                    f'height="{ph + gap + dh}"><title>{escape(tip)}</title></rect>')
    return svg_doc(W, H, body, title)


def _quantile(sorted_vals: list[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


METRIC_LABELS = {"pe_ttm": "市盈率 PE(TTM)", "pe": "市盈率 PE", "pb": "市净率 PB", "ps_ttm": "市销率 PS(TTM)",
                 "ev_ebitda": "EV/EBITDA", "dividend_yield": "股息率"}


def valuation_band(rows: list[tuple[str, float]], metric: str, title: str) -> str:
    """估值（PE/PB 等）走势 + 历史分位带。负值（亏损期 PE）不参与分位计算并断线显示。
    分位基于图中整个区间（含当日之后的数据），只用于展示，回测时必须改用滚动分位。"""
    metric = METRIC_LABELS.get(metric, metric)
    valid = sorted(v for _, v in rows if v > 0)
    if len(valid) < 20:
        raise SystemExit("错误: 有效估值数据不足 20 个点")
    qs = {q: _quantile(valid, q) for q in (0.1, 0.3, 0.5, 0.7, 0.9)}
    cur = rows[-1][1]
    cur_pct = sum(v <= cur for v in valid) / len(valid) if cur > 0 else None

    W, L, R, top, ph = 760, 16, 120, 66, 260
    H = top + ph + 40
    pw = W - L - R
    n = len(rows)
    x = lambda i: L + pw * i / max(n - 1, 1)
    lo, hi = min(valid[0], qs[0.1]) * 0.92, max(valid[-1], qs[0.9]) * 1.05
    py = lambda v: top + ph * (1 - (min(max(v, lo), hi) - lo) / (hi - lo))

    sub = f"{rows[0][0]} → {rows[-1][0]} · 当前 {cur:.2f}"
    sub += f"，处于历史 {cur_pct:.0%} 分位" if cur_pct is not None else "（为负，亏损期不计分位）"
    body = header(title, sub)
    body.append(f'<rect x="{L}" y="{py(qs[0.9]):.1f}" width="{pw}" height="{py(qs[0.1]) - py(qs[0.9]):.1f}" '
                f'fill="var(--band)" fill-opacity=".08"/>'
                f'<rect x="{L}" y="{py(qs[0.7]):.1f}" width="{pw}" height="{py(qs[0.3]) - py(qs[0.7]):.1f}" '
                f'fill="var(--band)" fill-opacity=".12"/>')
    labels = {0.1: "10% 分位", 0.3: "30%", 0.5: "中位数", 0.7: "70%", 0.9: "90% 分位"}
    for q, v in qs.items():
        body.append(f'<line x1="{L}" x2="{W - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="var(--muted)" '
                    f'stroke-dasharray="{"" if q == 0.5 else "3 3"}"/>'
                    f'<text x="{W - R + 6}" y="{py(v) + 4:.1f}">{labels[q]} {v:.1f}</text>')
    body.append(polyline([(x(i), py(v)) if v > 0 else None for i, (_, v) in enumerate(rows)], "var(--s1)", 2))
    if cur > 0:
        body.append(f'<circle cx="{x(n - 1):.1f}" cy="{py(cur):.1f}" r="5" fill="var(--s1)" '
                    f'stroke="var(--surface)" stroke-width="2"/>')
    body.append(f'<text x="{L}" y="{top - 8}" class="sub">{escape(metric)}；浅色带 = 10%~90% 分位，深色带 = 30%~70%</text>')
    body += date_ticks([d for d, _ in rows], x, H - 12, L, W - R)
    step = pw / max(n - 1, 1)
    for i, (d, v) in enumerate(rows):
        pct = f"，分位 {sum(u <= v for u in valid) / len(valid):.0%}" if v > 0 else "（亏损）"
        body.append(f'<rect class="hit" x="{x(i) - step / 2:.1f}" y="{top}" width="{step:.2f}" height="{ph}">'
                    f'<title>{escape(f"{d}  {metric} {v:.2f}{pct}")}</title></rect>')
    return svg_doc(W, H, body, title)
