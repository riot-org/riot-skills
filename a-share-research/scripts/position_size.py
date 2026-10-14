#!/usr/bin/env python3
"""基于风险预算的仓位测算（对应 SKILL.md 第 5 节）。只输出研究用的测算，不下单。

用法:
    python3 scripts/position_size.py --equity 1000000 --entry 42.5 --stop 39.0
    python3 scripts/position_size.py --equity 1000000 --entry 42.5 --atr 1.26 --atr-mult 2.5 \\
        --board gem --avg-amount 1.1e9 --industry-weight 0.12 [--format json|md]

逻辑:
    股数 = min(风险预算 / 每股风险, 单股权重上限, 行业剩余额度, 流动性上限)，按交易单位取整。
    每股风险 = 入场价 − 止损价 + 预估滑点 + 往返费用；另给出连续跌停情景下的亏损，提醒止损不一定能成交。
费用默认值（可覆盖）：佣金 0.025%（最低 5 元）、过户费 0.001%（双向）、印花税 0.05%（仅卖出）。
券商佣金和税费以实际为准。
"""
from __future__ import annotations

import argparse
import math

from _common import dump_json, fmt_num, fmt_pct

BOARDS = {  # 涨跌幅限制, 最小申报, 递增单位
    "main": (0.10, 100, 100, "沪深主板"),
    "gem": (0.20, 100, 100, "创业板"),
    "star": (0.20, 200, 1, "科创板"),
    "bse": (0.30, 100, 1, "北交所"),
    "st": (0.05, 100, 100, "ST 主板"),
}


def round_lot(shares: float, min_lot: int, step: int) -> int:
    if shares < min_lot:
        return 0
    return int(min_lot + math.floor((shares - min_lot) / step) * step)


def trade_cost(value: float, side: str, a) -> float:
    commission = max(value * a.commission, a.min_commission) if value > 0 else 0.0
    transfer = value * a.transfer_fee
    stamp = value * a.stamp_duty if side == "sell" else 0.0
    return commission + transfer + stamp


def compute(a) -> dict:
    limit, min_lot, step, board_name = BOARDS[a.board]
    stop = a.stop if a.stop is not None else a.entry - a.atr * a.atr_mult
    if stop >= a.entry:
        raise SystemExit("错误: 止损价必须低于入场价")
    slip = a.entry * a.slippage
    fee_per_share = (a.entry + stop) * (a.commission + a.transfer_fee) + stop * a.stamp_duty
    risk_per_share = a.entry - stop + slip + fee_per_share

    caps = {
        "风险预算": a.equity * a.risk_pct / risk_per_share,
        "单股权重上限": a.equity * a.max_weight / a.entry,
    }
    if a.industry_weight is not None:
        caps["行业剩余额度"] = max(0.0, a.max_industry - a.industry_weight) * a.equity / a.entry
    if a.avg_amount:
        caps["流动性上限"] = a.avg_amount * a.max_participation / a.entry
    binding = min(caps, key=caps.get)
    shares = round_lot(caps[binding], min_lot, step)
    value = shares * a.entry

    buy_cost = trade_cost(value, "buy", a)
    sell_at_stop = shares * stop
    loss_at_stop = value - sell_at_stop + buy_cost + trade_cost(sell_at_stop, "sell", a) + shares * slip
    # 情景：连续 N 个跌停后才能卖出
    gap_price = a.entry * (1 - limit) ** a.gap_days
    loss_gap = value - shares * gap_price + buy_cost + trade_cost(shares * gap_price, "sell", a)

    warnings = []
    if shares == 0:
        warnings.append(f"按约束计算不足最小申报数量 {min_lot} 股，测算结果为不建仓")
    if (a.entry - stop) / a.entry > limit:
        warnings.append(f"止损距离超过单日涨跌幅限制 {limit:.0%}，可能需要多个交易日才能触发")
    if binding == "流动性上限":
        warnings.append("仓位受成交额约束，冲击成本可能较大")
    if a.avg_amount and value > a.avg_amount * 0.01:
        warnings.append(f"拟建仓金额占 20 日均成交额 {value / a.avg_amount:.1%}，需分批执行")

    return {
        "board": board_name, "price_limit": limit, "entry": a.entry, "stop": stop,
        "stop_distance": (a.entry - stop) / a.entry, "risk_per_share": risk_per_share,
        "caps_shares": caps, "binding_constraint": binding,
        "shares": shares, "position_value": value, "weight": value / a.equity,
        "buy_cost": buy_cost, "loss_at_stop": loss_at_stop, "loss_at_stop_pct_equity": loss_at_stop / a.equity,
        "gap_scenario": {"limit_down_days": a.gap_days, "exit_price": gap_price,
                         "loss": loss_gap, "loss_pct_equity": loss_gap / a.equity},
        "round_trip_cost_pct": (buy_cost + trade_cost(value, "sell", a)) / value if value else None,
        "warnings": warnings,
        "disclaimer": "仅为风险预算测算，不构成交易指令；实际仓位需结合组合相关性和账户规则。",
    }


def to_markdown(r: dict) -> str:
    caps = "；".join(f"{k} {math.floor(v):,} 股" for k, v in r["caps_shares"].items())
    g = r["gap_scenario"]
    lines = [
        f"### 仓位测算（{r['board']}，涨跌幅限制 {r['price_limit']:.0%}）", "",
        "| 项目 | 数值 |", "| --- | --- |",
        f"| 入场 / 止损 | {fmt_num(r['entry'])} / {fmt_num(r['stop'])}（距离 {fmt_pct(r['stop_distance'], signed=False)}） |",
        f"| 每股风险（含滑点和费用） | {fmt_num(r['risk_per_share'], 3)} |",
        f"| 测算股数 | **{r['shares']:,}** 股（约束：{r['binding_constraint']}） |",
        f"| 持仓金额 / 占权益 | {fmt_num(r['position_value'], 0)} / {fmt_pct(r['weight'], signed=False)} |",
        f"| 止损成交时亏损 | {fmt_num(r['loss_at_stop'], 0)}（权益的 {fmt_pct(r['loss_at_stop_pct_equity'], 2, signed=False)}） |",
        f"| 连续 {g['limit_down_days']} 个跌停情景 | 亏损 {fmt_num(g['loss'], 0)}（权益的 {fmt_pct(g['loss_pct_equity'], 2, signed=False)}） |",
        f"| 往返交易成本 | {fmt_pct(r['round_trip_cost_pct'], 3, signed=False)} |",
        "", f"各约束对应股数：{caps}",
    ]
    lines += [f"- ⚠️ {w}" for w in r["warnings"]]
    lines += ["", f"> {r['disclaimer']}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--equity", type=float, required=True, help="账户/组合权益（元）")
    ap.add_argument("--entry", type=float, required=True, help="假设入场价")
    ap.add_argument("--stop", type=float, help="止损价；不给则用 entry − ATR × atr-mult")
    ap.add_argument("--atr", type=float)
    ap.add_argument("--atr-mult", type=float, default=2.0)
    ap.add_argument("--risk-pct", type=float, default=0.005, help="单笔风险预算占权益比例，默认 0.5%%")
    ap.add_argument("--max-weight", type=float, default=0.10, help="单股权重上限，默认 10%%")
    ap.add_argument("--industry-weight", type=float, help="组合中同行业已有权重")
    ap.add_argument("--max-industry", type=float, default=0.25, help="单行业权重上限，默认 25%%")
    ap.add_argument("--avg-amount", type=float, help="20 日均成交额（元）")
    ap.add_argument("--max-participation", type=float, default=0.05, help="建仓金额占日均成交额上限，默认 5%%")
    ap.add_argument("--board", choices=BOARDS, default="main")
    ap.add_argument("--slippage", type=float, default=0.002, help="单边滑点比例，默认 0.2%%")
    ap.add_argument("--gap-days", type=int, default=2, help="跌停情景天数，默认 2")
    ap.add_argument("--commission", type=float, default=0.00025)
    ap.add_argument("--min-commission", type=float, default=5.0)
    ap.add_argument("--transfer-fee", type=float, default=0.00001)
    ap.add_argument("--stamp-duty", type=float, default=0.0005)
    ap.add_argument("--format", choices=("json", "md"), default="md")
    a = ap.parse_args()
    if a.stop is None and a.atr is None:
        ap.error("需要 --stop 或 --atr")
    r = compute(a)
    print(to_markdown(r)) if a.format == "md" else dump_json(r)


if __name__ == "__main__":
    main()
