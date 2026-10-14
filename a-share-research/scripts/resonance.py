#!/usr/bin/env python3
"""共振检查：大盘 · 板块 · 个股 · 资金（机构 + 游资）四层是否同向（对应 SKILL.md 阶段 F）。

用法:
    python3 scripts/resonance.py --regime regime.json --stock 个股指标.json --industry 行业指标.json \\
        [--main-force 主力行为.json] [--national-team 国家队.json] [--format json|md]

输入都是其它脚本的 JSON 输出：
    --regime         market_regime.py
    --stock          indicators.py 个股（建议带 --bench 和 --industry）
    --industry       indicators.py 行业指数（带 --bench，用来判断板块趋势和相对强弱）
    --main-force     main_force.py（提供阶段与机构/游资参与）
    --national-team  national_team.py（判断指数稳定是否来自护盘）

原则：机构和游资都参与的方向才有持续性；和大盘共振才有搞头。
四层全部为“是”才算完整共振，才允许“优先研究”；任何一层为“否”或“未知”，结论最高为“观察等待”。
"""
from __future__ import annotations

import argparse

from _common import dump_json, fmt_pct, read_json

LAYERS = (("market", "大盘"), ("sector", "板块"), ("stock", "个股"), ("capital", "资金"))


def market_layer(regime: dict | None, nt: dict | None) -> dict:
    if not regime:
        return {"state": "未知", "why": ["未提供市场状态"]}
    key, label = regime["regime"], regime["regime_label"]
    why = [f"市场状态：{label}（置信度 {regime['confidence']}）"]
    if regime.get("data_warnings"):
        why.append("市场数据口径存疑")
    if key == "expansion":
        state = "是"
    elif key == "structural":
        state = "是"
        why.append("结构性行情：只有主线板块与大盘共振，非主线不算")
    elif key == "choppy":
        state = "否"
        why.append("震荡分化，大盘方向不明")
    elif key == "contraction":
        state = "否"
    else:
        state = "未知"
    if nt and nt.get("support_level") == "明显":
        why.append("上证有明显护盘迹象：指数平稳来自托底，不代表大盘趋势向上")
        if state == "是" and key != "expansion":
            state = "否"
    return {"state": state, "why": why}


def trend_layer(ind: dict | None, name: str) -> dict:
    if not ind:
        return {"state": "未知", "why": [f"未提供{name}指标"]}
    ck = ind.get("checks", {})
    rs = (ind.get("vs_industry") or ind.get("vs_bench") or {}).get("excess_60d")
    why = [f"收盘{'在' if ck.get('close_above_ma60') else '不在'} MA60 上方",
           f"MA60 {'向上' if ck.get('ma60_rising') else '走平/向下'}",
           f"60 日超额 {fmt_pct(rs)}" + ("（相对行业）" if ind.get("vs_industry") else "（相对基准）")]
    ok = ck.get("close_above_ma60") and ck.get("ma60_rising") and rs is not None and rs > 0
    return {"state": "是" if ok else "否", "why": why}


def capital_layer(mf: dict | None) -> dict:
    if not mf:
        return {"state": "未知", "why": ["未提供主力行为分析"]}
    pa = mf.get("participation") or {}
    why = [f"机构 {pa.get('institution', '未知')} · 游资 {pa.get('hot_money', '未知')}：{pa.get('verdict', '')}"]
    phase = mf.get("phase")
    if phase in ("distribution", "markdown"):
        why.append(f"主力行为判断为“{mf['phase_label']}”，与做多方向冲突")
        return {"state": "否", "why": why}
    if pa.get("both"):
        return {"state": "是", "why": why}
    if "未知" in (pa.get("institution"), pa.get("hot_money")):
        return {"state": "未知", "why": why + ["补充龙虎榜（机构席位/游资营业部）与机构持仓变化数据"]}
    return {"state": "否", "why": why}


def analyze(regime, stock, industry, mf, nt) -> dict:
    layers = {"market": market_layer(regime, nt), "sector": trend_layer(industry, "板块"),
              "stock": trend_layer(stock, "个股"), "capital": capital_layer(mf)}
    states = [layers[k]["state"] for k, _ in LAYERS]
    n_yes = states.count("是")
    if n_yes == 4:
        level, cap = "完整共振", "优先研究"
    elif "否" in states:
        level, cap = "共振不足", "观察等待" if layers["stock"]["state"] == "是" else "回避"
    else:
        level, cap = "共振待确认", "观察等待"
    missing = [label for k, label in LAYERS if layers[k]["state"] != "是"]
    return {"level": level, "yes_count": n_yes, "layers": layers, "max_conclusion": cap,
            "missing": missing,
            "principle": "机构和游资都参与的方向才有持续性；和大盘共振才有搞头。"}


def to_markdown(r: dict, title: str) -> str:
    mark = {"是": "✅", "否": "❌", "未知": "❓"}
    lines = [f"### {title} 共振检查：{r['level']}（{r['yes_count']}/4）", "",
             "| 层级 | 共振 | 依据 |", "| --- | --- | --- |"]
    for k, label in LAYERS:
        L = r["layers"][k]
        lines.append(f"| {label} | {mark[L['state']]} {L['state']} | {'；'.join(L['why'])} |")
    lines += ["", f"结论上限：**{r['max_conclusion']}**"
              + (f"（未共振：{'、'.join(r['missing'])}）" if r["missing"] else ""), "", f"> {r['principle']}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regime")
    ap.add_argument("--stock")
    ap.add_argument("--industry")
    ap.add_argument("--main-force")
    ap.add_argument("--national-team")
    ap.add_argument("--title", default="")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    load = lambda p: read_json(p) if p else None
    stock = load(a.stock)
    r = analyze(load(a.regime), stock, load(a.industry), load(a.main_force), load(a.national_team))
    title = a.title or (f"{stock.get('name', '')} {stock.get('code', '')}".strip() if stock else "")
    print(to_markdown(r, title)) if a.format == "md" else dump_json(r)


if __name__ == "__main__":
    main()
