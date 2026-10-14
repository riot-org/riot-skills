#!/usr/bin/env python3
"""现金流与财务质量检查（对应 SKILL.md 阶段 C）。

用法:
    python3 scripts/cashflow_quality.py FINANCIALS.json [--format json|md]

FINANCIALS.json 格式见 templates/financials.example.json：一个公司、多年（或多期）年报口径数据，
金额统一单位（建议：亿元）。字段缺失写 null，脚本会把缺失单独列出，不默认视为良好。

输出：逐年指标、红旗/亮点、0~100 的质量分（只用于排序）和标签。
金融业（银行/保险/券商等）现金流口径不同，脚本直接返回“不适用”，请改用行业专用指标。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _chart import save_chart
from _common import dump_json, fmt_num, fmt_pct, read_json

# 现金流硬门槛（SKILL.md 阶段 C），全部满足才算“现金流充足”
GATE_YEARS = 3
GATE_MIN_CFO_TO_NI = 0.8
GATE_MAX_NET_DEBT_TO_CFO = 3.0

FINANCIAL_INDUSTRIES = ("银行", "保险", "证券", "券商", "多元金融", "信托", "期货")
CYCLICAL_HINTS = ("房地产", "建筑", "基建", "钢铁", "煤炭", "有色", "化工", "航运", "水泥")


def _g(row: dict, key: str):
    v = row.get(key)
    return None if v is None else float(v)


def _growth(cur, prev):
    if cur is None or prev is None or prev <= 0:
        return None
    return cur / prev - 1


def per_year(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        prev = rows[i - 1] if i else {}
        rev, ni, cfo, capex = (_g(r, k) for k in ("revenue", "net_profit", "cfo", "capex"))
        recv = sum(x for x in (_g(r, "receivables"), _g(r, "contract_assets")) if x is not None) \
            if any(_g(r, k) is not None for k in ("receivables", "contract_assets")) else None
        prev_recv = sum(x for x in (_g(prev, "receivables"), _g(prev, "contract_assets")) if x is not None) \
            if prev and any(_g(prev, k) is not None for k in ("receivables", "contract_assets")) else None
        debt, cash = _g(r, "interest_debt"), _g(r, "cash")
        ebit, interest = _g(r, "ebit"), _g(r, "interest_expense")
        fcf = cfo - abs(capex) if cfo is not None and capex is not None else None
        out.append({
            "period": r.get("period"),
            "disclosed": r.get("disclosed"),
            "revenue": rev, "net_profit": ni, "cfo": cfo, "fcf": fcf,
            "cfo_to_ni": cfo / ni if cfo is not None and ni and ni > 0 else None,
            "fcf_margin": fcf / rev if fcf is not None and rev else None,
            "revenue_growth": _growth(rev, _g(prev, "revenue")) if prev else None,
            "receivables_growth": _growth(recv, prev_recv),
            "inventory_growth": _growth(_g(r, "inventory"), _g(prev, "inventory")) if prev else None,
            "net_debt": debt - cash if debt is not None and cash is not None else None,
            "net_debt_to_cfo": (debt - cash) / cfo if debt is not None and cash is not None and cfo and cfo > 0 else None,
            "short_debt_cover": cash / _g(r, "short_debt") if cash is not None and _g(r, "short_debt") else None,
            "interest_cover": ebit / interest if ebit is not None and interest and interest > 0 else None,
            "equity_raised": _g(r, "equity_raised"),
            "dividends": _g(r, "dividends"),
        })
    return out


def assess(data: dict) -> dict:
    industry = data.get("industry", "")
    base = {"code": data.get("code"), "name": data.get("name"), "industry": industry,
            "unit": data.get("unit", "亿元"), "source": data.get("source")}
    if any(k in industry for k in FINANCIAL_INDUSTRIES):
        return {**base, "applicable": False, "label": "不适用",
                "cash_gate": {"passed": False, "failed": ["金融企业现金流口径不适用，默认排除"]},
                "note": "金融企业现金流口径不同，请改看资本充足率、不良率、拨备覆盖、净息差或偿付能力等指标。"}

    rows = sorted(data["years"], key=lambda r: str(r.get("period")))
    ys = per_year(rows)
    last = ys[-1]
    flags, positives, missing = [], [], []

    for key, label in (("cfo", "经营现金流"), ("net_profit", "净利润"), ("revenue", "营业收入")):
        if last[key] is None:
            missing.append(label)
    if any(r.get("capex") is None for r in rows):
        missing.append("资本开支（FCF 无法完整计算）")

    cfos = [y["cfo"] for y in ys if y["cfo"] is not None]
    fcfs = [y["fcf"] for y in ys if y["fcf"] is not None]
    ratios = [y["cfo_to_ni"] for y in ys if y["cfo_to_ni"] is not None]
    score = 50.0

    if cfos:
        pos = sum(c > 0 for c in cfos)
        if pos == len(cfos):
            positives.append(f"近 {len(cfos)} 期经营现金流全部为正"); score += 12
        elif pos <= len(cfos) / 2:
            flags.append(f"近 {len(cfos)} 期中 {len(cfos) - pos} 期经营现金流为负"); score -= 15
    if ratios:
        avg = sum(ratios) / len(ratios)
        if avg >= 1.0:
            positives.append(f"CFO/净利润 平均 {avg:.2f}，利润兑现度高"); score += 12
        elif avg < 0.6:
            flags.append(f"CFO/净利润 平均仅 {avg:.2f}，利润现金含量低"); score -= 15
        if len(ratios) >= 3 and ratios[-1] < ratios[0] * 0.6:
            flags.append(f"CFO/净利润 从 {ratios[0]:.2f} 降到 {ratios[-1]:.2f}，回款恶化"); score -= 8
    if fcfs:
        pos = sum(f > 0 for f in fcfs)
        if pos == len(fcfs):
            positives.append(f"近 {len(fcfs)} 期自由现金流（近似）全部为正"); score += 10
        elif fcfs[-1] < 0:
            flags.append("最近一期自由现金流为负"); score -= 5

    rg, recg, invg = last["revenue_growth"], last["receivables_growth"], last["inventory_growth"]
    if rg is not None and recg is not None and recg - rg > 0.2:
        flags.append(f"应收+合同资产增速 {fmt_pct(recg)} 明显快于收入增速 {fmt_pct(rg)}"); score -= 8
    if rg is not None and invg is not None and invg - rg > 0.3:
        flags.append(f"存货增速 {fmt_pct(invg)} 明显快于收入增速 {fmt_pct(rg)}"); score -= 5

    if last["net_debt_to_cfo"] is not None and last["net_debt_to_cfo"] > 5:
        flags.append(f"净有息负债 / CFO = {last['net_debt_to_cfo']:.1f} 倍，偿债依赖再融资"); score -= 8
    elif last["net_debt"] is not None and last["net_debt"] < 0:
        positives.append("账面现金超过有息负债（净现金）"); score += 6
    if last["short_debt_cover"] is not None and last["short_debt_cover"] < 1:
        flags.append(f"货币资金仅覆盖短债 {last['short_debt_cover']:.2f} 倍"); score -= 8
    if last["interest_cover"] is not None and last["interest_cover"] < 3:
        flags.append(f"利息保障倍数 {last['interest_cover']:.1f}，偏低"); score -= 5

    raised = [y["equity_raised"] for y in ys if y["equity_raised"]]
    if len(raised) >= 2:
        flags.append(f"近 {len(ys)} 期有 {len(raised)} 期股权融资，关注稀释与融资依赖"); score -= 6
    divs = [(y["dividends"], y["fcf"]) for y in ys if y["dividends"] and y["fcf"] is not None]
    if divs and all(d > f for d, f in divs if f is not None):
        flags.append("分红持续高于自由现金流，可持续性存疑")
        score -= 4

    if any(k in industry for k in CYCLICAL_HINTS):
        flags.append(f"{industry} 属周期/重资产行业：需结合行业周期、预收款与资本开支阶段解读")

    score = max(0.0, min(100.0, score))
    gate = cash_gate(ys)
    if not gate["passed"]:
        flags.insert(0, "未通过现金流硬门槛：" + "；".join(gate["failed"]))
    if len(missing) >= 2:
        label = "数据不足"
    else:
        label = "优" if score >= 75 else "良" if score >= 60 else "中" if score >= 45 else "差"
    return {**base, "applicable": True, "score": score, "label": label,
            "cash_gate": gate, "positives": positives, "flags": flags, "missing": missing, "years": ys}


def cash_gate(ys: list[dict]) -> dict:
    recent = ys[-GATE_YEARS:]
    failed = []
    if len(recent) < GATE_YEARS:
        failed.append(f"不足 {GATE_YEARS} 个年度数据")
    cfos = [y["cfo"] for y in recent]
    if None in cfos:
        failed.append("经营现金流有缺失")
    elif any(c <= 0 for c in cfos):
        failed.append(f"近 {len(recent)} 年有经营现金流 ≤ 0")
    ratios = [y["cfo_to_ni"] for y in recent]
    if None in ratios:
        failed.append("CFO/净利润 无法计算（数据缺失或净利润 ≤ 0）")
    elif sum(ratios) / len(ratios) < GATE_MIN_CFO_TO_NI:
        failed.append(f"CFO/净利润 平均 {sum(ratios) / len(ratios):.2f} < {GATE_MIN_CFO_TO_NI}")
    fcfs = [y["fcf"] for y in recent]
    if None in fcfs:
        failed.append("自由现金流无法计算（资本开支缺失）")
    elif sum(fcfs) <= 0:
        failed.append(f"近 {len(recent)} 年自由现金流累计 {sum(fcfs):.2f} ≤ 0")
    last = recent[-1] if recent else {}
    nd, ndc = last.get("net_debt"), last.get("net_debt_to_cfo")
    if nd is None:
        failed.append("有息负债或货币资金缺失")
    elif nd > 0 and (ndc is None or ndc > GATE_MAX_NET_DEBT_TO_CFO):
        failed.append(f"净有息负债/CFO {'无法计算' if ndc is None else f'{ndc:.1f} 倍'} > {GATE_MAX_NET_DEBT_TO_CFO:g} 倍")
    return {"passed": not failed, "failed": failed}


def to_markdown(r: dict) -> str:
    gate = r.get("cash_gate") or {}
    head = (f"### {r.get('name') or ''} {r.get('code') or ''} 现金流质量：{r['label']}"
            f"（现金流门槛：{'✅ 通过' if gate.get('passed') else '❌ 未通过'}）")
    if not r["applicable"]:
        return f"{head}\n\n{r['note']}"
    u = r["unit"]
    lines = [f"{head}（{r['score']:.0f}/100，仅用于排序）", "",
             f"| 期间 | 收入({u}) | 净利润 | CFO | FCF≈CFO−Capex | CFO/净利 | 收入增速 | 应收增速 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for y in r["years"]:
        lines.append(f"| {y['period']} | {fmt_num(y['revenue'])} | {fmt_num(y['net_profit'])} | {fmt_num(y['cfo'])} | "
                     f"{fmt_num(y['fcf'])} | {fmt_num(y['cfo_to_ni'])} | {fmt_pct(y['revenue_growth'])} | "
                     f"{fmt_pct(y['receivables_growth'])} |")
    lines.append("")
    lines += [f"- ✅ {p}" for p in r["positives"]]
    lines += [f"- ⚠️ {f}" for f in r["flags"]]
    if r["missing"]:
        lines.append(f"- ❓ 缺失：{'、'.join(r['missing'])}")
    if r.get("source"):
        lines.append(f"- 来源：{r['source']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("financials")
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    data = read_json(a.financials)
    items = data if isinstance(data, list) else [data]
    results = [assess(d) for d in items]
    if a.format == "md":
        print("\n\n".join(to_markdown(r) for r in results))
    else:
        dump_json(results if isinstance(data, list) else results[0])
    if a.chart:
        from viz import cashflow as cashflow_chart
        for k, res in enumerate(r for r in results if r.get("applicable")):
            p = Path(a.chart)
            path = a.chart if k == 0 else str(p.with_name(f"{p.stem}_{res.get('code') or k}{p.suffix}"))
            save_chart(cashflow_chart(res), path)


if __name__ == "__main__":
    main()
