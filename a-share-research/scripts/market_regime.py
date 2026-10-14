#!/usr/bin/env python3
"""市场状态识别（对应 SKILL.md 阶段 A）。

用法:
    python3 scripts/market_regime.py --bench HS300.csv --input market.json [--format json|md]

market.json 字段见 templates/market.example.json；缺的字段写 null 或省略，脚本会降低置信度，
不会把缺失当作中性或利好。--bench 可省略，但此时趋势维度记为缺失。

规则是透明的打分，阈值在 THRESHOLDS 中，可按回测结果调整。输出包括分类、每个维度的证据、
置信度、反证条件，供写入研究报告；最终表述仍需结合数据来源和时点。
"""
from __future__ import annotations

import argparse

from _chart import save_chart
from _common import dump_json, fmt_num, fmt_pct, load_bars, pct_change, read_json, sma

THRESHOLDS = {
    "breadth_strong": 0.55,   # 站上 MA60 比例
    "breadth_weak": 0.35,
    "adv_dec_strong": 1.3,    # 上涨/下跌家数比
    "adv_dec_weak": 0.7,
    "turnover_expand": 1.1,   # 成交额 / 20 日均值
    "turnover_shrink": 0.85,
    # 涨跌停看绝对数量（A 股常态：涨停约 50~80 家，跌停个位数到十几家）
    "limit_up_hot": 80,       # 涨停 ≥ 80：赚钱效应强
    "limit_up_cold": 40,      # 涨停 < 40：情绪偏冷
    "limit_down_stress": 30,  # 跌停 ≥ 30：亏钱效应扩散
    "board_hot": 6,           # 最高连板 ≥ 6：投机高度打开
    "board_cold": 3,          # 最高连板 ≤ 3：高度被压制
    "breadth_cap": -0.5,      # 广度信号 ≤ 此值（普跌）时，风险偏好最多判中性
}

# 数据合理性：A 股全市场约 5000+ 只股票，日成交额通常在万亿量级
SANITY = {"min_stock_count": 3000, "min_turnover": 5e11}

REGIMES = {
    "expansion": "趋势扩散/风险偏好改善",
    "structural": "结构性行情/存量博弈倾向",
    "choppy": "震荡分化",
    "contraction": "风险收缩/趋势恶化",
    "unknown": "无法确认",
}


def trend_signal(bench_path: str | None) -> dict:
    if not bench_path:
        return {"score": None, "evidence": "未提供基准行情"}
    bars = load_bars(bench_path)
    closes = [b.close for b in bars]
    if len(closes) < 130:
        return {"score": None, "evidence": f"基准仅 {len(closes)} 根 K 线，不足以计算 120 日均线"}
    ma20, ma60, ma120 = (sma(closes, n)[-1] for n in (20, 60, 120))
    ma60_series = sma(closes, 60)
    slope60 = pct_change(ma60_series[-11], ma60_series[-1])
    c = closes[-1]
    score = 0
    score += 1 if c > ma60 else -1
    score += 1 if slope60 > 0 else -1
    score += 1 if ma20 > ma60 > ma120 else (-1 if ma20 < ma60 < ma120 else 0)
    return {
        "score": max(-1.0, min(1.0, score / 3)),
        "date": bars[-1].date,
        "evidence": f"基准收盘 {fmt_num(c)}，MA20/60/120 = {fmt_num(ma20)}/{fmt_num(ma60)}/{fmt_num(ma120)}，"
                    f"MA60 10 日斜率 {fmt_pct(slope60, 2)}",
        "raw": {"close": c, "ma20": ma20, "ma60": ma60, "ma120": ma120, "ma60_slope": slope60},
    }


def breadth_signal(b: dict | None) -> dict:
    b = b or {}
    parts, scores = [], []
    above60 = b.get("pct_above_ma60")
    if above60 is not None:
        scores.append(1 if above60 >= THRESHOLDS["breadth_strong"] else -1 if above60 <= THRESHOLDS["breadth_weak"] else 0)
        parts.append(f"站上 MA60 比例 {fmt_pct(above60, signed=False)}")
    adv, dec = b.get("advancers"), b.get("decliners")
    if adv is not None and dec:
        ratio = adv / dec
        scores.append(1 if ratio >= THRESHOLDS["adv_dec_strong"] else -1 if ratio <= THRESHOLDS["adv_dec_weak"] else 0)
        parts.append(f"涨/跌家数 {adv}/{dec}（{ratio:.2f}）")
    nh, nl = b.get("new_highs"), b.get("new_lows")
    if nh is not None and nl is not None:
        scores.append(1 if nh > nl * 1.5 else -1 if nl > nh * 1.5 else 0)
        parts.append(f"新高/新低 {nh}/{nl}")
    if b.get("pct_above_ma20") is not None:
        parts.append(f"站上 MA20 比例 {fmt_pct(b['pct_above_ma20'], signed=False)}")
    if not scores:
        return {"score": None, "evidence": "缺少市场广度数据"}
    return {"score": sum(scores) / len(scores), "evidence": "，".join(parts)}


def volume_signal(t: dict | None, trend_score: float | None) -> dict:
    t = t or {}
    today, avg20 = t.get("today"), t.get("avg20")
    if not today or not avg20:
        return {"score": None, "evidence": "缺少成交额数据"}
    ratio = today / avg20
    expand = ratio >= THRESHOLDS["turnover_expand"]
    shrink = ratio <= THRESHOLDS["turnover_shrink"]
    # 量能本身无方向：放量配合上涨为正，放量下跌为负
    if trend_score is None:
        score = 0.0
    elif expand:
        score = 1.0 if trend_score > 0 else -1.0
    elif shrink:
        score = -0.5 if trend_score > 0 else 0.0
    else:
        score = 0.0
    return {"score": score, "evidence": f"成交额 {fmt_num(today / 1e8, 0)} 亿，为 20 日均值的 {ratio:.2f} 倍"}


def risk_signal(r: dict | None, breadth_score: float | None) -> dict:
    """涨跌停的绝对数量 + 连板高度，再用当日广度校正：普跌日的少量涨停不代表风险偏好改善。"""
    r = r or {}
    up, down, board = r.get("limit_up"), r.get("limit_down"), r.get("max_board_height")
    if up is None or down is None:
        return {"score": None, "evidence": "缺少涨跌停数据"}
    parts, notes = [], []
    if up >= THRESHOLDS["limit_up_hot"]:
        parts.append(1.0); notes.append("涨停家数多")
    elif up < THRESHOLDS["limit_up_cold"]:
        parts.append(-1.0); notes.append("涨停家数偏少")
    else:
        parts.append(0.0)
    if down >= THRESHOLDS["limit_down_stress"]:
        parts.append(-1.0); notes.append("跌停家数多")
    elif down > up:
        parts.append(-0.5); notes.append("跌停多于涨停")
    else:
        parts.append(0.0)
    if board is not None:
        if board >= THRESHOLDS["board_hot"]:
            parts.append(1.0); notes.append("连板高度打开")
        elif board <= THRESHOLDS["board_cold"]:
            parts.append(-0.5); notes.append("连板高度被压制")
        else:
            parts.append(0.0)
    score = sum(parts) / len(parts)
    ev = f"涨停 {up} / 跌停 {down}" + (f"，最高连板 {board}" if board is not None else "")
    if notes:
        ev += "（" + "、".join(notes) + "）"
    if breadth_score is not None and breadth_score <= THRESHOLDS["breadth_cap"] and score > 0:
        score = 0.0
        ev += "；当日普跌，局部涨停不视为风险偏好改善"
    return {"score": score, "evidence": ev}


def sanity_check(market: dict) -> list[str]:
    """输入口径检查：常见错误是把行业指数数量当个股家数、只取单个交易所的成交额。"""
    out = []
    b = market.get("breadth") or {}
    adv, dec = b.get("advancers"), b.get("decliners")
    if adv is not None and dec is not None and adv + dec + (b.get("unchanged") or 0) < SANITY["min_stock_count"]:
        out.append(f"涨跌家数合计仅 {adv + dec}，A 股全市场约 5000+ 只，疑似用了行业/指数数量或抽样，请改用全市场个股家数")
    t = (market.get("turnover") or {}).get("today")
    if t is not None and t < SANITY["min_turnover"]:
        out.append(f"成交额 {t / 1e8:,.0f} 亿明显低于全市场常见水平（万亿量级），疑似只取了沪市或深市，请改用沪深京合计")
    return out


def classify(sig: dict) -> tuple[str, str, list[str]]:
    t, b, v, r = (sig[k]["score"] for k in ("trend", "breadth", "volume", "risk"))  # r 只影响置信度
    available = [s for s in (t, b, v, r) if s is not None]
    if t is None or b is None:
        return "unknown", "低", ["补齐基准趋势和市场广度数据后重新判断"]

    if t > 0.3 and b > 0.3 and (v is None or v >= 0):
        key = "expansion"
        counter = ["基准收盘跌破 MA60 且 MA60 拐头向下", "站上 MA60 比例回落到 45% 以下", "放量下跌或跌停家数显著增加"]
    elif t < -0.3 and b < 0:
        key = "contraction"
        counter = ["基准重新站上 MA60 且 MA60 走平/向上", "站上 MA60 比例回升到 50% 以上", "上涨放量、涨停数量明显多于跌停"]
    elif t >= 0 and b <= 0:
        key = "structural"
        counter = ["广度改善（站上 MA60 比例 > 55%）则转向趋势扩散", "基准跌破 MA60 则转向风险收缩"]
    else:
        key = "choppy"
        counter = ["趋势、广度、量能三者同向时再确认方向"]

    # 置信度：维度齐全且方向一致越高
    signs = [1 if s > 0.2 else -1 if s < -0.2 else 0 for s in available]
    agreement = abs(sum(signs)) / len(signs)
    coverage = len(available) / 4
    level = agreement * 0.6 + coverage * 0.4
    conf = "高" if level >= 0.75 else "中" if level >= 0.5 else "低"
    return key, conf, counter


def analyze(bench: str | None, market: dict) -> dict:
    sig = {"trend": trend_signal(bench), "breadth": breadth_signal(market.get("breadth"))}
    sig["volume"] = volume_signal(market.get("turnover"), sig["trend"]["score"])
    sig["risk"] = risk_signal(market.get("risk"), sig["breadth"]["score"])
    warnings = sanity_check(market)
    key, conf, counter = classify(sig)
    if warnings and conf != "低":
        conf = "低" if len(warnings) > 1 else "中"
    return {
        "date": market.get("date") or sig["trend"].get("date"),
        "regime": key,
        "regime_label": REGIMES[key],
        "confidence": conf,
        "signals": sig,
        "counter_conditions": counter,
        "data_warnings": warnings,
        "supply_and_flows": market.get("supply"),
        "sources": market.get("sources"),
        "note": "资金/供给指标仅作背景，未计入分类打分；不可简单相加后断言资金净流入/流出。",
    }


def to_markdown(r: dict) -> str:
    names = {"trend": "大盘趋势", "breadth": "市场广度", "volume": "量能", "risk": "风险偏好"}
    lines = [f"### 市场状态：{r['regime_label']}（置信度：{r['confidence']}）", "",
             f"数据时点：{r['date'] or '未注明'}", "", "| 维度 | 信号 | 证据 |", "| --- | --- | --- |"]
    for k, label in names.items():
        s = r["signals"][k]["score"]
        mark = "缺失" if s is None else ("偏多" if s > 0.2 else "偏空" if s < -0.2 else "中性")
        lines.append(f"| {label} | {mark} | {r['signals'][k]['evidence']} |")
    if r.get("supply_and_flows"):
        lines += ["", "资金与供给（背景，不计分）："]
        lines += [f"- {k}: {v}" for k, v in r["supply_and_flows"].items()]
    if r.get("data_warnings"):
        lines += ["", "⚠️ 数据口径存疑（已下调置信度）："] + [f"- {w}" for w in r["data_warnings"]]
    lines += ["", "反证条件："] + [f"- {c}" for c in r["counter_conditions"]]
    lines += ["", f"> {r['note']}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", help="基准指数行情 CSV")
    ap.add_argument("--input", help="市场广度/量能/风险 JSON")
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    r = analyze(a.bench, read_json(a.input) if a.input else {})
    print(to_markdown(r)) if a.format == "md" else dump_json(r)
    from viz import regime as regime_chart
    save_chart(regime_chart(r), a.chart)


if __name__ == "__main__":
    main()
