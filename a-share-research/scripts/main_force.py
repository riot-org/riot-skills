#!/usr/bin/env python3
"""主力行为分析：筹码分布 + 吸筹/洗盘/拉升/出货阶段推断（对应 SKILL.md 阶段 D2）。

用法:
    python3 scripts/main_force.py 个股.csv [--float-shares 流通股本(股)] [--events events.json]
                                  [--name 名称] [--code 代码] [--format json|md]

思路：主力（机构、游资、大户）的核心诉求是“以尽量低的成本拿到足够筹码”，再“在高位把筹码换给别人”。
这些行为会在量价和筹码结构上留下痕迹：
    吸筹  低位、波动收敛、上涨放量下跌缩量、OBV 走强而价格不涨、筹码向低位集中、股东户数减少
    洗盘  上升趋势中的缩量回调，不破 MA60，筹码结构稳定
    拉升  均线多头、放量突破、上涨日成交显著大于下跌日
    出货  高位放量滞涨、长上影、OBV 背离走弱、筹码向上发散、股东户数增加、大宗折价/减持
    下跌  MA60 向下且价格在其下方，筹码套牢盘为主

筹码分布按换手率衰减模型估算：每日旧筹码按换手率衰减，新筹码按当日高低价三角分布加入。
提供 --float-shares 时用真实换手率（成交量需与股本同单位，单位为股）；否则用相对量能近似，结果标注为近似。
所有结论都是基于公开数据的概率性推断，无法确认“主力”身份和真实意图。
"""
from __future__ import annotations

import argparse

from _chart import save_chart
from _common import Bar, dump_json, fmt_num, fmt_pct, load_bars, pct_change, read_json, sma

BINS = 120
CHIP_WINDOW = 250
PHASES = {"accumulation": "吸筹", "shakeout": "洗盘", "markup": "拉升", "distribution": "出货/派发",
          "markdown": "下跌", "unclear": "不明确"}


# ---------- 筹码分布 ----------

def chip_distribution(bars: list[Bar], float_shares: float | None, upto: int | None = None) -> dict:
    """返回 {prices, weights, avg_cost, profit_ratio, p5, p95, concentration90, peak, approx}。"""
    upto = len(bars) if upto is None else upto
    window = bars[max(0, upto - CHIP_WINDOW):upto]
    lo, hi = min(b.low for b in window), max(b.high for b in window)
    if hi <= lo:
        hi = lo * 1.01
    step = (hi - lo) / BINS
    prices = [lo + step * (i + 0.5) for i in range(BINS)]
    chips = [0.0] * BINS
    avg_vol = sum(b.volume for b in window) / len(window) or 1.0
    for b in window:
        if float_shares:
            t = min(b.volume / float_shares, 1.0)
        else:  # 近似：平均日换手按 2% 计，按相对量能缩放
            t = min(0.02 * b.volume / avg_vol, 0.5)
        chips = [c * (1 - t) for c in chips]
        mid = (b.high + b.low + b.close) / 3
        lo_i = max(0, int((b.low - lo) / step))
        hi_i = min(BINS - 1, int((b.high - lo) / step))
        span = []
        for i in range(lo_i, hi_i + 1):  # 三角分布：越接近均价权重越大
            half = max(mid - b.low, b.high - mid, step)
            span.append(max(0.0, 1 - abs(prices[i] - mid) / half) + 1e-6)
        total = sum(span)
        for k, i in enumerate(range(lo_i, hi_i + 1)):
            chips[i] += t * span[k] / total
    s = sum(chips) or 1.0
    w = [c / s for c in chips]
    close = window[-1].close
    cum, p5, p95, p50 = 0.0, prices[0], prices[-1], prices[0]
    for p, x in zip(prices, w):
        prev = cum
        cum += x
        if prev < 0.05 <= cum:
            p5 = p
        if prev < 0.5 <= cum:
            p50 = p
        if prev < 0.95 <= cum:
            p95 = p
    return {
        "prices": prices, "weights": w,
        "avg_cost": sum(p * x for p, x in zip(prices, w)),
        "median_cost": p50,
        "profit_ratio": sum(x for p, x in zip(prices, w) if p <= close),
        "p5": p5, "p95": p95,
        "concentration90": (p95 - p5) / (p95 + p5),  # 越小越集中
        "peak": prices[max(range(BINS), key=lambda i: w[i])],
        "approx": not float_shares,
    }


# ---------- 量价特征 ----------

def obv(bars: list[Bar]) -> list[float]:
    out, v = [], 0.0
    for i, b in enumerate(bars):
        if i:
            v += b.volume if b.close > bars[i - 1].close else -b.volume if b.close < bars[i - 1].close else 0
        out.append(v)
    return out


def slope_norm(vals: list[float], n: int) -> float | None:
    """最近 n 日线性回归斜率 / 区间均值绝对值，用于比较价格与 OBV 方向。"""
    if len(vals) < n:
        return None
    ys = vals[-n:]
    xm, ym = (n - 1) / 2, sum(ys) / n
    num = sum((i - xm) * (y - ym) for i, y in enumerate(ys))
    den = sum((i - xm) ** 2 for i in range(n))
    scale = (max(ys) - min(ys)) or 1.0
    return num / den * n / scale


def features(bars: list[Bar]) -> dict:
    closes = [b.close for b in bars]
    vols = [b.volume for b in bars]
    c = closes[-1]
    ma20, ma60 = sma(closes, 20), sma(closes, 60)
    win = bars[-250:]
    lo, hi = min(b.low for b in win), max(b.high for b in win)
    f = {
        "position_250d": (c - lo) / (hi - lo) if hi > lo else None,  # 0 = 年内低点，1 = 年内高点
        "ret_20d": pct_change(closes[-21], c) if len(closes) > 20 else None,
        "ret_60d": pct_change(closes[-61], c) if len(closes) > 60 else None,
        "ret_120d": pct_change(closes[-121], c) if len(closes) > 120 else None,
        "ma60_slope": pct_change(ma60[-11], ma60[-1]) if len(closes) > 70 else None,
        "above_ma60": ma60[-1] is not None and c > ma60[-1],
        "ma_bull": ma20[-1] is not None and ma60[-1] is not None and c > ma20[-1] > ma60[-1],
        "vol_ratio_5_20": (sum(vols[-5:]) / 5) / (sum(vols[-20:]) / 20) if len(vols) >= 20 and sum(vols[-20:]) else None,
        "price_slope_40": slope_norm(closes, 40),
        "obv_slope_40": slope_norm(obv(bars), 40),
    }
    up, dn = [], []
    for i in range(max(1, len(bars) - 40), len(bars)):
        (up if closes[i] >= closes[i - 1] else dn).append(vols[i])
    f["up_down_vol_40"] = (sum(up) / len(up)) / (sum(dn) / len(dn)) if up and dn and sum(dn) else None
    # 波动收敛：近 20 日振幅均值 / 近 120 日振幅均值
    amp = [(b.high - b.low) / b.close for b in bars]
    f["range_contraction"] = (sum(amp[-20:]) / 20) / (sum(amp[-120:]) / 120) if len(amp) >= 120 else None
    # 高位放量滞涨 / 长上影（近 20 日）
    avg20 = sum(vols[-40:-20]) / 20 if len(vols) >= 40 else (sum(vols) / len(vols))
    stall, shadow = 0, 0
    for i in range(max(1, len(bars) - 20), len(bars)):
        b, pc = bars[i], closes[i - 1]
        body = abs(b.close - b.open)
        if b.volume > 2 * avg20 and abs(b.close / pc - 1) < 0.01:
            stall += 1
        if (b.high - max(b.open, b.close)) > max(2 * body, 0.03 * b.close) and b.volume > 1.5 * avg20:
            shadow += 1
    f["high_vol_stall_20d"], f["long_upper_shadow_20d"] = stall, shadow
    f["new_high_120d_with_volume"] = (len(closes) > 120 and c >= max(closes[-120:])
                                      and f["vol_ratio_5_20"] is not None and f["vol_ratio_5_20"] > 1.2)
    return f


# ---------- 阶段推断 ----------

def classify(f: dict, chips: dict, chips_prev: dict | None, ev: dict) -> dict:
    pts = {k: 0.0 for k in ("accumulation", "shakeout", "markup", "distribution", "markdown")}
    why = {k: [] for k in pts}

    def add(phase, w, text):
        pts[phase] += w
        why[phase].append(text)

    pos, r20, r60, r120 = f["position_250d"], f["ret_20d"], f["ret_60d"], f["ret_120d"]
    ps, os_ = f["price_slope_40"], f["obv_slope_40"]
    udv, vr, rc = f["up_down_vol_40"], f["vol_ratio_5_20"], f["range_contraction"]
    conc_chg = None if not chips_prev else chips["concentration90"] - chips_prev["concentration90"]

    # 吸筹
    if pos is not None and pos < 0.35:
        add("accumulation", 1, f"处于年内低位区（位置 {pos:.0%}）")
    if rc is not None and rc < 0.75:
        add("accumulation", 1, f"振幅收敛（近 20 日 / 近 120 日 = {rc:.2f}）")
    if udv is not None and udv > 1.15 and (r60 is None or abs(r60) < 0.15) and (r20 is None or r20 > -0.05):
        add("accumulation", 1, f"价格未大涨但上涨日量能是下跌日的 {udv:.2f} 倍")
    if ps is not None and os_ is not None and os_ > 0.3 and ps < 0.2:
        add("accumulation", 1.5, "OBV 走强而价格横盘/走弱（量价正背离）")
    if conc_chg is not None and conc_chg < -0.02 and pos is not None and pos < 0.5:
        add("accumulation", 1, "筹码在低位进一步集中")

    # 洗盘
    if f["ma60_slope"] and f["ma60_slope"] > 0 and f["above_ma60"] and r20 is not None and -0.15 < r20 < 0:
        add("shakeout", 1.5, f"上升趋势中回调 {r20:.1%} 但仍在 MA60 上方")
        if vr is not None and vr < 0.8:
            add("shakeout", 1.5, f"回调缩量（5/20 日量比 {vr:.2f}）")
        if conc_chg is not None and abs(conc_chg) < 0.02:
            add("shakeout", 0.5, "回调中筹码结构基本稳定")

    # 拉升
    if f["ma_bull"]:
        add("markup", 1, "均线多头排列（收盘 > MA20 > MA60）")
    if r60 is not None and r60 > 0.15:
        add("markup", 1, f"60 日上涨 {r60:.1%}")
    if udv is not None and udv > 1.2 and (r20 or 0) > 0:
        add("markup", 1, f"上涨放量（上涨/下跌日量比 {udv:.2f}）")
    if f["new_high_120d_with_volume"]:
        add("markup", 1, "放量创 120 日新高")

    # 出货
    if pos is not None and pos > 0.75 and (r120 or 0) > 0.3:
        add("distribution", 1, f"高位（位置 {pos:.0%}，120 日涨幅 {r120:.0%}）")
    if f["high_vol_stall_20d"] >= 2:
        add("distribution", 1.5, f"近 20 日 {f['high_vol_stall_20d']} 次放量滞涨")
    if f["long_upper_shadow_20d"] >= 2:
        add("distribution", 1, f"近 20 日 {f['long_upper_shadow_20d']} 次放量长上影")
    if ps is not None and os_ is not None and ps > 0 and os_ < -0.2 and (pos or 0) > 0.6:
        add("distribution", 1.5, "价格仍在高位而 OBV 走弱（量价顶背离）")
    if udv is not None and udv < 0.9 and (pos or 0) > 0.6:
        add("distribution", 1, f"高位下跌日量能大于上涨日（{udv:.2f}）")
    if conc_chg is not None and conc_chg > 0.03 and (pos or 0) > 0.6:
        add("distribution", 1, "高位筹码向上发散")
    if chips["profit_ratio"] > 0.9 and (pos or 0) > 0.75:
        add("distribution", 0.5, f"获利盘 {chips['profit_ratio']:.0%}，兑现压力大")

    # 下跌
    if f["ma60_slope"] is not None and f["ma60_slope"] < 0 and not f["above_ma60"]:
        add("markdown", 2, "MA60 向下且收盘在其下方")
    if r20 is not None and r20 < -0.08 and not f["above_ma60"]:
        add("markdown", 1, f"近 20 日继续下跌 {r20:.1%}")
    if chips["profit_ratio"] < 0.2:
        add("markdown", 1, f"获利盘仅 {chips['profit_ratio']:.0%}，上方套牢盘重")

    # 外部事件（可选）
    hc = ev.get("holder_count_change")  # 最近一期股东户数环比变化，小数
    if hc is not None:
        if hc < -0.05:
            add("accumulation" if (pos or 0) < 0.5 else "markup", 1, f"股东户数环比 {hc:+.1%}，筹码集中")
        elif hc > 0.08 and (pos or 0) > 0.6:
            add("distribution", 1, f"高位股东户数环比 {hc:+.1%}，筹码分散")
    if ev.get("block_trade_discount") is not None and ev["block_trade_discount"] > 0.05:
        add("distribution", 1, f"大宗交易平均折价 {ev['block_trade_discount']:.1%}")
    if ev.get("insider_reduction"):
        add("distribution", 1, f"重要股东减持：{ev['insider_reduction']}")
    lhb = [v for v in (ev.get("lhb_institution_net"), ev.get("lhb_hotmoney_net")) if v is not None]
    if lhb:  # 龙虎榜合计净买入，正为净买
        net = sum(lhb)
        add("markup" if net > 0 else "distribution", 0.5, f"龙虎榜合计净{'买入' if net > 0 else '卖出'} {abs(net) / 1e8:.2f} 亿")

    # 同分时偏保守：先认下跌/出货，最后才认吸筹
    caution = ["markdown", "distribution", "shakeout", "markup", "accumulation"]
    ranked = sorted(pts.items(), key=lambda kv: (-kv[1], caution.index(kv[0])))
    (top, top_pts), (second, second_pts) = ranked[0], ranked[1]
    if top_pts < 2:
        phase, conf = "unclear", "低"
    else:
        phase = top
        margin = top_pts - second_pts
        conf = "高" if margin >= 2 and top_pts >= 4 else "中" if margin >= 1 else "低"
    return {"phase": phase, "phase_label": PHASES[phase], "confidence": conf,
            "scores": pts, "evidence": why[phase] if phase != "unclear" else [],
            "competing": {PHASES[k]: why[k] for k, v in ranked[1:3] if v > 0}}


# 板块级游资活跃度：个股没上龙虎榜时，用所属板块的涨停与连板判断游资是否在做这个方向
SECTOR_HOT_LIMIT_UP_5D = 5   # 板块近 5 日涨停家次 ≥ 5
SECTOR_HOT_BOARD = 3         # 板块最高连板 ≥ 3
SECTOR_COLD_LIMIT_UP_5D = 1  # ≤ 1 且连板 ≤ 2 视为游资缺席


def participation(ev: dict) -> dict:
    """机构与游资是否同时参与。只用有数据的口径，缺失为“未知”，不当作参与。

    机构：龙虎榜机构专用席位近 20 日净买（lhb_institution_net）、机构/基金/北向持股比例变化（inst_holding_change）
    游资：龙虎榜游资营业部近 20 日净买（lhb_hotmoney_net，个股级，优先）；
          没有时用所属板块近 5 日涨停家次（sector_limit_up_5d）与最高连板（sector_max_board）作板块级证据
    """
    def judge(vals: list[tuple[float | None, str]]) -> tuple[str, list[str]]:
        known = [(v, t) for v, t in vals if v is not None]
        if not known:
            return "未知", []
        pos = [t for v, t in known if v > 0]
        neg = [t for v, t in known if v < 0]
        state = "参与" if pos and not neg else "撤离" if neg and not pos else "分歧" if pos and neg else "缺席"
        return state, [t for _, t in known]

    inst, inst_ev = judge([
        (ev.get("lhb_institution_net"), f"龙虎榜机构净买 {(ev.get('lhb_institution_net') or 0) / 1e8:+.2f} 亿"),
        (ev.get("inst_holding_change"), f"机构持股比例变化 {(ev.get('inst_holding_change') or 0):+.2%}"),
    ])
    if ev.get("lhb_hotmoney_net") is not None:
        hot, hot_ev = judge([(ev["lhb_hotmoney_net"], f"龙虎榜游资净买 {ev['lhb_hotmoney_net'] / 1e8:+.2f} 亿（个股级）")])
    else:
        lu, board = ev.get("sector_limit_up_5d"), ev.get("sector_max_board")
        if lu is None and board is None:
            hot, hot_ev = "未知", []
        else:
            sector = ev.get("sector_name") or "所属板块"
            desc = "、".join(x for x in (f"近 5 日涨停 {lu} 家次" if lu is not None else "",
                                         f"最高 {board} 连板" if board is not None else "") if x)
            if (lu or 0) >= SECTOR_HOT_LIMIT_UP_5D or (board or 0) >= SECTOR_HOT_BOARD:
                hot = "参与"
            elif (lu is None or lu <= SECTOR_COLD_LIMIT_UP_5D) and (board is None or board <= 2):
                hot = "缺席"
            else:
                hot = "偏弱"
            hot_ev = [f"{sector}{desc}（板块级证据，个股未上龙虎榜）"]
    both = inst == "参与" and hot == "参与"
    if both:
        verdict = "机构与游资共同参与，持续性较好"
    elif "未知" in (inst, hot):
        verdict = "参与方数据不全，无法确认资金共振"
    elif "撤离" in (inst, hot):
        verdict = "有一方在撤离，持续性存疑"
    else:
        verdict = "只有单一类型资金参与或参与偏弱，持续性存疑"
    return {"institution": inst, "hot_money": hot, "both": both, "verdict": verdict,
            "evidence": inst_ev + hot_ev, "note": ev.get("lhb_note") or ev.get("participation_note")}


ACTION = {
    "accumulation": "趋势尚未成立：按本 Skill 只做趋势的原则，不提前埋伏，等放量突破、趋势门槛通过后再研究。",
    "shakeout": "若趋势门槛仍通过，可视为持有/观察；跌破 MA60 或放量下跌则洗盘判断失效。",
    "markup": "与趋势门槛一致，是本 Skill 重点研究的阶段；警惕加速段的放量滞涨。",
    "distribution": "即使趋势门槛暂时通过，也应回避或降级为观察；持仓按失效条件退出。",
    "markdown": "趋势已破坏，回避。",
    "unclear": "信号不足，以趋势和现金流门槛为准，不用主力行为结论加减分。",
}


def analyze(bars: list[Bar], float_shares: float | None, ev: dict) -> dict:
    chips = chip_distribution(bars, float_shares)
    prev = chip_distribution(bars, float_shares, len(bars) - 20) if len(bars) > 80 else None
    f = features(bars)
    cls = classify(f, chips, prev, ev)
    close = bars[-1].close
    return {
        "date": bars[-1].date, "close": close, **cls,
        "action_hint": ACTION[cls["phase"]],
        "participation": participation(ev or {}),
        "chips": {k: v for k, v in chips.items() if k not in ("prices", "weights")}
        | {"close_vs_avg_cost": close / chips["avg_cost"] - 1,
           "concentration90_20d_ago": prev["concentration90"] if prev else None},
        "features": f,
        "events": ev or None,
        "caveat": "基于公开量价与披露数据的概率性推断，无法确认主力身份与真实意图；"
                  + ("筹码分布未提供流通股本，按相对量能近似。" if chips["approx"] else "筹码分布按真实换手率估算。"),
    }


def to_markdown(r: dict, title: str) -> str:
    ch = r["chips"]
    lines = [f"### {title} 主力行为：{r['phase_label']}（置信度：{r['confidence']}，截至 {r['date']}）", ""]
    lines += [f"- {e}" for e in r["evidence"]] or ["- 各阶段信号都不充分"]
    if r["competing"]:
        lines += ["", "其它可能："] + [f"- {k}：{'；'.join(v)}" for k, v in r["competing"].items()]
    lines += ["", "| 筹码指标 | 数值 |", "| --- | --- |",
              f"| 平均成本 / 中位成本 | {fmt_num(ch['avg_cost'])} / {fmt_num(ch['median_cost'])} |",
              f"| 收盘相对平均成本 | {fmt_pct(ch['close_vs_avg_cost'])} |",
              f"| 获利盘比例 | {fmt_pct(ch['profit_ratio'], signed=False)} |",
              f"| 90% 筹码区间 | {fmt_num(ch['p5'])} ~ {fmt_num(ch['p95'])}（集中度 {ch['concentration90']:.1%}，"
              f"20 日前 {'—' if ch['concentration90_20d_ago'] is None else format(ch['concentration90_20d_ago'], '.1%')}；越小越集中） |",
              f"| 筹码密集峰 | {fmt_num(ch['peak'])} |",
              "", f"**对策**：{r['action_hint']}"]
    pa = r["participation"]
    lines += ["", f"**资金参与**：机构 {pa['institution']} · 游资 {pa['hot_money']} → {pa['verdict']}"]
    lines += [f"- {e}" for e in pa["evidence"]]
    if pa.get("note"):
        lines.append(f"- {pa['note']}")
    lines += ["", f"> {r['caveat']}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock")
    ap.add_argument("--float-shares", type=float, help="流通股本（股），与成交量单位一致")
    ap.add_argument("--events", help="可选事件 JSON：股东户数变化、龙虎榜、大宗交易、减持，见 templates/events.example.json")
    ap.add_argument("--code", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    bars = load_bars(a.stock)
    if len(bars) < 130:
        raise SystemExit(f"错误: 需要至少 130 根 K 线，当前 {len(bars)}")
    r = {"code": a.code, "name": a.name, **analyze(bars, a.float_shares, read_json(a.events) if a.events else {})}
    print(to_markdown(r, f"{a.name} {a.code}".strip() or a.stock)) if a.format == "md" else dump_json(r)
    if a.chart:
        from viz import chips as chips_chart
        title = f"{a.name} {a.code}".strip() or a.stock
        save_chart(chips_chart(bars, chip_distribution(bars, a.float_shares), r, f"{title} 筹码分布"), a.chart)


if __name__ == "__main__":
    main()
