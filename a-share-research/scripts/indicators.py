#!/usr/bin/env python3
"""个股趋势与相对强度指标（对应 SKILL.md 阶段 D）。

用法:
    python3 scripts/indicators.py STOCK.csv [--bench HS300.csv] [--industry IND.csv]
                                  [--name 贵州茅台] [--code 600519] [--format json|md]

输出:
    均线与斜率、20/60/120 日收益、相对基准/行业超额收益、回撤、波动率、ATR、
    量能比、上涨放量/回调缩量比、偏离度以及几条示例趋势条件。
    数值都是事实计算，不含买卖判断；参数需回测验证。
"""
from __future__ import annotations

import argparse

from _chart import save_chart
from _common import (Bar, ann_volatility, atr, dump_json, fmt_num, fmt_pct, load_bars,
                     max_drawdown, pct_change, ret_n, sma)

PERIODS = (20, 60, 120)
SLOPE_LOOKBACK = 10  # 均线斜率：当前均线相对 N 日前均线的变化


def _align(stock: list[Bar], other: list[Bar]) -> tuple[list[float], list[float]]:
    """按日期对齐两条序列的收盘价（取交集）。"""
    other_map = {b.date: b.close for b in other}
    pairs = [(b.close, other_map[b.date]) for b in stock if b.date in other_map]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def relative_strength(stock: list[Bar], bench: list[Bar]) -> dict:
    s, b = _align(stock, bench)
    out = {"aligned_days": len(s)}
    for n in PERIODS:
        rs, rb = ret_n(s, n), ret_n(b, n)
        out[f"excess_{n}d"] = None if rs is None or rb is None else rs - rb
    # 相对强度线：stock / bench，取 60 日均线方向
    if len(s) > 60 + SLOPE_LOOKBACK:
        rs_line = [x / y for x, y in zip(s, b)]
        ma = sma(rs_line, 60)
        out["rs_line_ma60_slope"] = pct_change(ma[-1 - SLOPE_LOOKBACK], ma[-1])
        out["rs_line_new_high_120d"] = rs_line[-1] >= max(rs_line[-120:])
    return out


def volume_profile(bars: list[Bar], n: int = 60) -> dict:
    window = bars[-n - 1:]
    up_vol, down_vol = [], []
    for i in range(1, len(window)):
        (up_vol if window[i].close >= window[i - 1].close else down_vol).append(window[i].volume)
    vols = [b.volume for b in bars]
    amounts = [b.amount for b in bars[-20:] if b.amount is not None]
    v5 = sum(vols[-5:]) / 5 if len(vols) >= 5 else None
    v20 = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
    return {
        "volume_ratio_5_20": None if not v5 or not v20 else v5 / v20,
        # >1 表示上涨日平均成交量大于下跌日（上涨放量、回调缩量）
        "up_down_volume_ratio_60d": (sum(up_vol) / len(up_vol)) / (sum(down_vol) / len(down_vol))
        if up_vol and down_vol and sum(down_vol) > 0 else None,
        "avg_amount_20d": sum(amounts) / len(amounts) if amounts else None,
    }


def compute(bars: list[Bar], bench: list[Bar] | None = None, industry: list[Bar] | None = None) -> dict:
    closes = [b.close for b in bars]
    last = bars[-1]
    res: dict = {"date": last.date, "close": last.close, "bars": len(bars)}

    for n in PERIODS:
        ma = sma(closes, n)
        res[f"ma{n}"] = ma[-1]
        res[f"ma{n}_slope"] = pct_change(ma[-1 - SLOPE_LOOKBACK], ma[-1]) if len(ma) > SLOPE_LOOKBACK else None
        res[f"ret_{n}d"] = ret_n(closes, n)

    res["dist_ma60"] = pct_change(res["ma60"], last.close)
    hi250 = max(closes[-250:])
    res["dist_250d_high"] = pct_change(hi250, last.close)
    res["max_drawdown_120d"] = max_drawdown(closes[-120:])
    res["volatility_60d_ann"] = ann_volatility(closes, 60)
    res["atr14"] = atr(bars, 14)
    res["atr14_pct"] = res["atr14"] / last.close if res["atr14"] else None
    res.update(volume_profile(bars))

    if bench:
        res["vs_bench"] = relative_strength(bars, bench)
    if industry:
        res["vs_industry"] = relative_strength(bars, industry)

    # 示例条件（SKILL.md 阶段 D），仅用于初筛，不是买入规则
    ref = res.get("vs_industry") or res.get("vs_bench") or {}
    res["checks"] = {
        "close_above_ma60": res["ma60"] is not None and last.close > res["ma60"],
        "ma60_rising": (res["ma60_slope"] or 0) > 0,
        "excess_60d_positive": (ref.get("excess_60d") or 0) > 0 if ref else None,
        "up_volume_dominant": (res["up_down_volume_ratio_60d"] or 0) > 1,
        "overextended": res["dist_ma60"] is not None and res["dist_ma60"] > 0.25,
    }
    warnings = []
    if len(bars) < 130:
        warnings.append(f"仅 {len(bars)} 根 K 线，120 日指标可能缺失或不稳定")
    if res["checks"]["overextended"]:
        warnings.append("收盘价偏离 60 日均线超过 25%，追高风险较大")
    res["warnings"] = warnings
    return res


def to_markdown(r: dict, title: str) -> str:
    lines = [f"### {title} 趋势指标（截至 {r['date']}）", "",
             "| 指标 | 20 日 | 60 日 | 120 日 |", "| --- | --- | --- | --- |",
             "| 均线 | " + " | ".join(fmt_num(r[f"ma{n}"]) for n in PERIODS) + " |",
             "| 均线斜率(10日) | " + " | ".join(fmt_pct(r[f"ma{n}_slope"], 2) for n in PERIODS) + " |",
             "| 收益率 | " + " | ".join(fmt_pct(r[f"ret_{n}d"]) for n in PERIODS) + " |"]
    for key, label in (("vs_bench", "相对基准超额"), ("vs_industry", "相对行业超额")):
        if key in r:
            lines.append(f"| {label} | " + " | ".join(fmt_pct(r[key][f"excess_{n}d"]) for n in PERIODS) + " |")
    lines += ["", f"- 收盘 {fmt_num(r['close'])}，偏离 MA60 {fmt_pct(r['dist_ma60'])}，"
                  f"距 250 日高点 {fmt_pct(r['dist_250d_high'])}",
              f"- 120 日最大回撤 {fmt_pct(r['max_drawdown_120d'])}，60 日年化波动 {fmt_pct(r['volatility_60d_ann'], signed=False)}，"
              f"ATR14 {fmt_num(r['atr14'])}（{fmt_pct(r['atr14_pct'], signed=False)}）",
              f"- 5/20 日量比 {fmt_num(r['volume_ratio_5_20'])}，60 日上涨/下跌日均量比 "
              f"{fmt_num(r['up_down_volume_ratio_60d'])}，20 日均成交额 {fmt_num(r['avg_amount_20d'], 0)}"]
    labels = {"close_above_ma60": "收盘在 MA60 上方", "ma60_rising": "MA60 向上",
              "excess_60d_positive": "60 日超额为正", "up_volume_dominant": "上涨放量/回调缩量",
              "overextended": "严重偏离均线"}
    lines.append("- 示例条件：" + "；".join(
        f"{labels[k]} {'✓' if v else ('—' if v is None else '✗')}" for k, v in r["checks"].items()))
    for w in r["warnings"]:
        lines.append(f"- ⚠️ {w}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stock")
    ap.add_argument("--bench", help="基准指数行情 CSV，如沪深 300")
    ap.add_argument("--industry", help="行业指数行情 CSV")
    ap.add_argument("--code", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()

    r = compute(load_bars(a.stock),
                load_bars(a.bench) if a.bench else None,
                load_bars(a.industry) if a.industry else None)
    r = {"code": a.code, "name": a.name, **r}
    if a.format == "md":
        print(to_markdown(r, f"{a.name} {a.code}".strip() or a.stock))
    else:
        dump_json(r)
    if a.chart:
        from viz import kline as kline_chart
        save_chart(kline_chart(load_bars(a.stock), load_bars(a.bench) if a.bench else None, 120,
                               f"{a.name} {a.code}".strip() or a.stock), a.chart)


if __name__ == "__main__":
    main()
