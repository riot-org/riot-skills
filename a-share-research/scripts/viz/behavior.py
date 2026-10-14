"""资金行为图表：筹码分布（主力行为）、国家队护盘痕迹。"""
from __future__ import annotations

from html import escape

from _common import Bar

from .base import SERIES, VERDICT, date_ticks, fmt_axis, header, legend, nice_ticks, polyline, svg_doc, text_width

PHASE_TONE = {"accumulation": "var(--s1)", "shakeout": "var(--warn)", "markup": "var(--good)",
              "distribution": "var(--bad)", "markdown": "var(--bad)", "unclear": "var(--neutral)"}


def chips(bars: list[Bar], dist: dict, result: dict | None = None, title: str = "", days: int = 120) -> str:
    """左：近 N 日收盘 + 平均成本 + 90% 筹码区间；右：筹码分布（红 = 获利盘，蓝 = 套牢盘）。"""
    view = bars[-days:]
    close = view[-1].close
    W, L, top, ph = 760, 16, 70, 300
    split = 470
    H = top + ph + 40
    prices, weights = dist["prices"], dist["weights"]
    lo = min(min(b.low for b in view), prices[0])
    hi = max(max(b.high for b in view), prices[-1])
    pad = (hi - lo) * 0.04
    lo, hi = lo - pad, hi + pad
    py = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    pw = split - L - 50
    x = lambda i: L + pw * i / (len(view) - 1)

    sub = f"截至 {view[-1].date} · 平均成本 {dist['avg_cost']:.2f} · 获利盘 {dist['profit_ratio']:.0%}"
    if dist.get("approx"):
        sub += " · 近似（未提供流通股本）"
    body = header(title or "筹码分布", sub)
    if result:
        lab = f"主力行为：{result['phase_label']}（{result['confidence']}）"
        tone = PHASE_TONE.get(result["phase"], "var(--neutral)")
        bw = text_width(lab, 12) + 24
        body.append(f'<rect x="{W - 16 - bw:.1f}" y="12" width="{bw:.1f}" height="26" rx="13" fill="{tone}" '
                    f'fill-opacity=".16" stroke="{tone}"/><text x="{W - 16 - bw / 2:.1f}" y="30" text-anchor="middle" '
                    f'class="val" style="font-size:12px;font-weight:600">{escape(lab)}</text>')
    body += legend([("收盘", "var(--s1)"), ("平均成本", "var(--s2)")], L, 62)

    for t in nice_ticks(lo, hi, 5):
        body.append(f'<line class="grid" x1="{L}" x2="{W - 16}" y1="{py(t):.1f}" y2="{py(t):.1f}"/>'
                    f'<text x="{split - 44}" y="{py(t) + 4:.1f}">{t:.2f}</text>')
    # 90% 筹码区间
    body.append(f'<rect x="{L}" y="{py(dist["p95"]):.1f}" width="{pw}" height="{py(dist["p5"]) - py(dist["p95"]):.1f}" '
                f'fill="var(--s2)" fill-opacity=".07"/>')
    body.append(polyline([(x(i), py(b.close)) for i, b in enumerate(view)], "var(--s1)", 2))
    body.append(f'<line x1="{L}" x2="{W - 16}" y1="{py(dist["avg_cost"]):.1f}" y2="{py(dist["avg_cost"]):.1f}" '
                f'stroke="var(--s2)" stroke-width="1.5" stroke-dasharray="5 3"/>')
    body.append(f'<line x1="{L}" x2="{W - 16}" y1="{py(close):.1f}" y2="{py(close):.1f}" stroke="var(--muted)" stroke-width="1"/>')
    body += date_ticks([b.date for b in view], x, H - 12, L, L + pw, n=3)

    # 右侧筹码柱
    hx, hw = split + 10, W - 16 - split - 10
    wmax = max(weights) or 1
    bh = max(1.0, ph / len(prices) * 0.85)
    for p, w in zip(prices, weights):
        if w <= 0 or not (lo <= p <= hi):
            continue
        col = "var(--up)" if p <= close else "var(--s1)"
        body.append(f'<rect x="{hx}" y="{py(p) - bh / 2:.1f}" width="{max(hw * w / wmax, 0.5):.1f}" height="{bh:.1f}" '
                    f'fill="{col}" fill-opacity=".75"><title>{p:.2f}：{w:.2%}</title></rect>')
    body.append(f'<text x="{hx}" y="{top - 6}" class="sub">筹码分布 · 红 获利盘 / 蓝 套牢盘</text>')
    body.append(f'<text x="{W - 16}" y="{py(dist["avg_cost"]) - 4:.1f}" text-anchor="end" class="val halo">成本 {dist["avg_cost"]:.2f}</text>')
    return svg_doc(W, H, body, title or "筹码分布")


def national_team(sh: list[Bar], compare: dict[str, list[Bar]], etf_rows: tuple[str, dict] | None,
                  result: dict, days: int = 60, title: str = "国家队护盘痕迹") -> str:
    view = sh[-(days + 1):]
    dates = [b.date for b in view]
    ev = {e["date"]: e for e in result.get("events", [])}
    W, L, R, top, ph, gap, rh, eh = 760, 16, 120, 100, 200, 34, 120, 70
    has_etf = etf_rows is not None
    H = top + ph + gap + rh + (gap + eh if has_etf else 0) + 34
    pw = W - L - R
    x = lambda i: L + pw * i / (len(view) - 1)

    sub = (f"{result['window']} · 护盘迹象{result['support_level']}：{len(result['events'])} 天（强 {result['strong_days']} 天）"
           + (f" · 上证跑赢对比指数 {result['index_distortion']:+.1%}" if result.get("index_distortion") is not None else ""))
    body = header(title, sub)
    body.append(f'<text x="{L}" y="62" class="sub">▲ 强信号（≥2 项）  △ 弱信号 · 悬停查看迹象</text>')

    # 面板 1：上证 + 整百点位 + 信号
    lo, hi = min(b.low for b in view), max(b.high for b in view)
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad
    py = lambda v: top + ph * (1 - (v - lo) / (hi - lo))
    for lv in range(int(lo // 100 + 1) * 100, int(hi) + 1, 100):
        body.append(f'<line x1="{L}" x2="{W - R}" y1="{py(lv):.1f}" y2="{py(lv):.1f}" stroke="var(--muted)" stroke-dasharray="3 4"/>'
                    f'<text x="{W - R + 6}" y="{py(lv) + 4:.1f}">{lv}</text>')
    for i, b in enumerate(view):  # 日内高低线，体现深V下影
        body.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{py(b.high):.1f}" y2="{py(b.low):.1f}" stroke="var(--grid)" stroke-width="3"/>')
    body.append(polyline([(x(i), py(b.close)) for i, b in enumerate(view)], "var(--s1)", 2))
    for i, b in enumerate(view):
        e = ev.get(b.date)
        if not e:
            continue
        yy = py(b.low) + 12
        strong = e["strength"] == "强"
        body.append(f'<path d="M{x(i):.1f},{yy - 6:.1f} l5,9 h-10 z" fill="{"var(--bad)" if strong else "none"}" '
                    f'stroke="var(--bad)" stroke-width="1.5"><title>{escape(b.date + chr(10) + chr(10).join(e["signals"]))}</title></path>')
    body.append(f'<text x="{L}" y="{top - 4}" class="sub">上证指数（灰条 = 日内高低）</text>')

    # 面板 2：相对走势
    rt = top + ph + gap
    series = [("上证指数", {b.date: b.close for b in view})] + [(n, {b.date: b.close for b in bars}) for n, bars in compare.items()]
    norm = []
    for name, m in series:
        base = next((m[d] for d in dates if d in m), None)
        norm.append((name, [None if d not in m or not base else 100 * m[d] / base for d in dates]))
    vals = [v for _, s in norm for v in s if v is not None]
    rlo, rhi = min(vals + [100]), max(vals + [100])
    rpad = (rhi - rlo) * 0.08 or 1
    ry = lambda v: rt + rh * (1 - (v - rlo + rpad) / (rhi - rlo + 2 * rpad))
    body.append(f'<text x="{L}" y="{rt - 8}" class="sub">相对走势（窗口首日 = 100）</text>')
    body.append(f'<line x1="{L}" x2="{W - R}" y1="{ry(100):.1f}" y2="{ry(100):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>')
    colors = SERIES
    for k, (name, s) in enumerate(norm):
        body.append(polyline([None if v is None else (x(i), ry(v)) for i, v in enumerate(s)], colors[k % len(colors)], 2))
        last = next((v for v in reversed(s) if v is not None), None)
        if last is not None:
            body.append(f'<text x="{W - R + 6}" y="{ry(last) + 4:.1f}" class="val halo">{escape(name[:6])} {last - 100:+.1f}%</text>')

    # 面板 3：ETF 成交额
    if has_etf:
        name, rows = etf_rows
        et = rt + rh + gap
        amts = [(rows.get(d) or {}).get("amount") for d in dates]
        amax = max((a for a in amts if a), default=0) or 1
        bw = max(1.0, pw / len(dates) * 0.7)
        body.append(f'<text x="{L}" y="{et - 8}" class="sub">{escape(name)} 成交额（红 = 护盘信号日）</text>'
                    f'<text x="{W - R + 6}" y="{et + 8}">{fmt_axis(amax)}</text>')
        for i, (d, a) in enumerate(zip(dates, amts)):
            if not a:
                continue
            h = eh * a / amax
            col = "var(--bad)" if d in ev else "var(--s1)"
            body.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{et + eh - h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{col}" '
                        f'fill-opacity="{0.85 if d in ev else 0.45}"><title>{d} {fmt_axis(a)}</title></rect>')
    body += date_ticks(dates, x, H - 12, L, W - R)
    return svg_doc(W, H, body, title)


def daily_moves(r: dict, max_rows: int = 16, title: str = "") -> str:
    """盘面复盘：左侧板块日内区间（最低—最高，| 开盘，● 收盘），右侧指数分时；顶部是意图推断。"""
    sectors = sorted(r.get("sectors", []), key=lambda s: -s["pct"])
    if len(sectors) > max_rows:  # 保留两端：拉得最多和砸得最多的
        half = max_rows // 2
        sectors = sectors[:half] + sectors[-half:]
    intents = r.get("intents", [])[:3]
    has_intra = bool(r.get("intraday"))
    W, L = 760, 16
    top = 74 + 24 * len(intents)
    row = 22
    H = top + 30 + row * len(sectors) + 30
    left_w = 470 if has_intra else W - 32
    name_w, val_w = 96, 170
    bx0, bx1 = L + name_w, L + left_w - val_w
    vals = [v for s in sectors for v in (s.get("high_pct"), s.get("low_pct"), s["pct"]) if v is not None] + [0]
    vmax = max(abs(min(vals)), abs(max(vals))) * 1.08 or 0.01
    sx = lambda v: bx0 + (bx1 - bx0) * (v + vmax) / (2 * vmax)

    body = header(title or f"盘面复盘 {r.get('date') or ''}".strip(), "拉了什么、砸了什么、资金意图（推断）")
    for k, it in enumerate(intents):
        y = 62 + k * 24
        tone = "var(--warn)" if it["confidence"] != "低" else "var(--neutral)"
        txt = f"意图 {k + 1}：{it['intent']} · 主导 {it.get('actor', '不明')}（{it['confidence']}）"
        body.append(f'<rect x="{L}" y="{y}" width="{text_width(txt, 12) + 20:.1f}" height="20" rx="10" fill="{tone}" fill-opacity=".14" stroke="{tone}"/>'
                    f'<text x="{L + 10}" y="{y + 14}" class="val" style="font-size:12px">{escape(txt)}'
                    f'<title>{escape("；".join(it["evidence"]) + chr(10) + "其它可能：" + "；".join(it["alternatives"]))}</title></text>')

    # 左：板块区间条
    body.append(f'<text x="{L}" y="{top + 14}" class="sub">板块日内区间：灰线 最低→最高 · 竖线 开盘 · 圆点 收盘 · 〔权〕权重 · 右侧为形态与主导资金</text>')
    y0 = top + 30
    body.append(f'<line x1="{sx(0):.1f}" x2="{sx(0):.1f}" y1="{y0 - 4}" y2="{y0 + row * len(sectors)}" stroke="var(--muted)"/>')
    for k, s in enumerate(sectors):
        y = y0 + k * row + row / 2
        col = "var(--up)" if s["pct"] > 0 else "var(--down)" if s["pct"] < 0 else "var(--neutral)"
        nm = s["name"] + ("〔权〕" if s.get("is_weight") else "")
        body.append(f'<text x="{bx0 - 8}" y="{y + 4:.1f}" text-anchor="end" class="val">{escape(nm)}</text>')
        if s.get("high_pct") is not None and s.get("low_pct") is not None:
            body.append(f'<line x1="{sx(s["low_pct"]):.1f}" x2="{sx(s["high_pct"]):.1f}" y1="{y:.1f}" y2="{y:.1f}" '
                        f'stroke="var(--neutral)" stroke-width="4" stroke-linecap="round" stroke-opacity=".6"/>')
        if s.get("open_pct") is not None:
            body.append(f'<line x1="{sx(s["open_pct"]):.1f}" x2="{sx(s["open_pct"]):.1f}" y1="{y - 6:.1f}" y2="{y + 6:.1f}" stroke="var(--ink-2)" stroke-width="1.5"/>')
        body.append(f'<circle cx="{sx(s["pct"]):.1f}" cy="{y:.1f}" r="5" fill="{col}" stroke="var(--surface)" stroke-width="2"/>')
        prio = ("冲高回落", "探底回升", "放量拉升", "放量砸盘", "无量阴跌")  # 形态比量能更能说明意图
        short = sorted((t.replace("（放量）", "") for t in s.get("tags", []) if t.startswith(prio)),
                       key=lambda t: next(i for i, p in enumerate(prio) if t.startswith(p)))
        ar = s.get("amount_ratio")
        driver = (s.get("actor") or {}).get("driver", "")
        note = " · ".join(x for x in (short[0] if short else (f"量 {ar:.1f}x" if ar else ""),
                                      driver if driver and driver != "不明" else "") if x)
        body.append(f'<text x="{bx1 + 8}" y="{y + 4:.1f}" class="val">{s["pct"]:+.1%}</text>'
                    f'<text x="{bx1 + 52}" y="{y + 4:.1f}" class="sub">{escape(note)}</text>')
        tip = f"{s['name']} 收 {s['pct']:+.2%}" + (f"，高 {s['high_pct']:+.2%} 低 {s['low_pct']:+.2%}" if s.get("high_pct") is not None else "") \
              + (f"，量能 {ar:.2f} 倍" if ar else "") + (f"\n{'、'.join(s['tags'])}" if s.get("tags") else "") \
              + (f"\n主导：{s['actor']['driver']}（{s['actor']['confidence']}）" + (f"，{s['actor']['counterparty']}" if s['actor'].get('counterparty') else "")
                 + f"\n" + "；".join(s["actor"]["evidence"]) if s.get("actor") else "")
        body.append(f'<rect class="hit" x="{L}" y="{y - row / 2:.1f}" width="{left_w}" height="{row}"><title>{escape(tip)}</title></rect>')
    for t in (-vmax / 1.08, 0, vmax / 1.08):
        body.append(f'<text x="{sx(t):.1f}" y="{y0 + row * len(sectors) + 16}" text-anchor="middle" class="sub">{t:+.0%}</text>')

    # 右：指数分时
    if has_intra:
        rx0, rx1 = L + left_w + 24, W - 100
        ry0, ry1 = y0, y0 + min(row * len(sectors), 260)
        series = []
        for name, prof in r["intraday"].items():
            pts = prof.get("series") or []
            if len(pts) >= 2:
                base = pts[0][1]
                series.append((name, [p / base - 1 for _, p in pts], pts))
        allv = [v for _, s, _ in series for v in s] + [0]
        lo_v, hi_v = min(allv), max(allv)
        pad = (hi_v - lo_v) * 0.08 or 0.002
        lo_v, hi_v = lo_v - pad, hi_v + pad
        yy = lambda v: ry0 + (ry1 - ry0) * (1 - (v - lo_v) / (hi_v - lo_v))
        body.append(f'<text x="{rx0}" y="{top + 14}" class="sub">指数分时（开盘 = 0）</text>'
                    f'<line x1="{rx0}" x2="{rx1}" y1="{yy(0):.1f}" y2="{yy(0):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>')
        for k, (name, vs, pts) in enumerate(series):
            c = SERIES[k % len(SERIES)]
            xx = lambda i, n=len(vs): rx0 + (rx1 - rx0) * i / (n - 1)
            body.append(polyline([(xx(i), yy(v)) for i, v in enumerate(vs)], c, 1.8))
            body.append(f'<text x="{rx1 + 6}" y="{yy(vs[-1]) + 4:.1f}" class="val halo">{escape(name[:6])} {vs[-1]:+.1%}</text>')
        if series:
            pts = series[0][2]
            for i in (0, len(pts) // 2, len(pts) - 1):
                anchor = "start" if i == 0 else "end" if i == len(pts) - 1 else "middle"
                xx = rx0 + (rx1 - rx0) * i / (len(pts) - 1)
                body.append(f'<text x="{xx:.1f}" y="{ry1 + 16}" text-anchor="{anchor}" class="sub">{escape(str(pts[i][0]))}</text>')
        if r.get("summary"):
            body.append(f'<text x="{rx0}" y="{ry1 + 40}" class="sub">悬停意图标签查看依据和其它可能</text>')
    return svg_doc(W, H, body, title or "盘面复盘")
