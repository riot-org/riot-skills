#!/usr/bin/env python3
"""候选股标准化评分与排序（对应 SKILL.md 第 4 节）。

用法:
    python3 scripts/score.py candidates.csv [--config templates/score_config.json]
                             [--regime expansion|structural|choppy|contraction]
                             [--format md|json|csv]

candidates.csv 至少包含 code,name,industry 以及配置里的因子列（见 templates/candidates.example.csv）。
- 每个因子先转成 0~1 百分位（方向统一为越大越好）；quality/valuation 组在样本足够的行业内排名，
  避免跨行业直接比较；样本不足时回退到全样本并在 notes 中注明。
- 缺失值按 missing_percentile（默认 0，即最差）处理，并列入 missing，绝不当作良好。
- exclude_reason 非空的行不参与打分，单独列出排除原因。
- 风险收缩等状态下按 regime_weights 自动降低趋势权重。
总分仅用于排序，不等于上涨概率。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from _chart import save_chart
from _common import dump_json, percentile_rank, read_json

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "templates" / "score_config.json"
GROUP_LABELS = {"trend": "趋势/相对强度", "quality": "现金流/财务质量", "valuation": "估值",
                "liquidity": "流动性", "risk": "供给/事件风险"}


def _num(v):
    if v is None:
        return None
    v = str(v).strip().replace(",", "")
    if v in ("", "-", "—", "nan", "None", "null"):
        return None
    return float(v[:-1]) / 100 if v.endswith("%") else float(v)


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
       "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


def check_gates(row: dict, gates: list[dict]) -> dict[str, list[str]]:
    """返回 {门槛类型: [未通过项]}；缺失数据视为未通过。"""
    failed: dict[str, list[str]] = defaultdict(list)
    for g in gates:
        v = _num(row.get(g["column"]))
        if v is None or not OPS[g["op"]](v, g["value"]):
            failed[g["type"]].append(g["label"] + ("（缺失）" if v is None else ""))
    return failed


def score(rows: list[dict], cfg: dict, regime: str | None) -> dict:
    gates = cfg.get("gates", [])
    excluded, pool, gate_fail = [], [], {}
    for r in rows:
        if (r.get("exclude_reason") or "").strip():
            excluded.append(r)
            continue
        failed = check_gates(r, gates)
        if failed.get("cash"):  # 现金流门槛不过：直接排除
            details = [r.get(g["detail_column"]) for g in gates if g["type"] == "cash" and g.get("detail_column")]
            reason = "；".join(d.strip() for d in details if d and d.strip()) or "、".join(failed["cash"])
            excluded.append({**r, "exclude_reason": "未通过现金流门槛：" + reason})
            continue
        pool.append(r)
        if failed.get("trend"):  # 趋势门槛不过：参与计算但不排名
            gate_fail[r.get("code")] = failed["trend"]
    weights = cfg.get("regime_weights", {}).get(regime or "", cfg["weights"])
    neutral = cfg.get("industry_neutral_groups", [])
    min_size = cfg.get("min_industry_size", 5)
    miss_p = cfg.get("missing_percentile", 0.0)
    notes = []

    by_ind = defaultdict(list)
    for i, r in enumerate(pool):
        by_ind[(r.get("industry") or "未分类").strip()].append(i)

    na_rules = cfg.get("not_applicable_groups", {})
    na = [{g for kw, gs in na_rules.items() if kw in (r.get("industry") or "") for g in gs} for r in pool]

    pct = [dict() for _ in pool]          # factor column -> percentile
    missing = [list() for _ in pool]
    small_industries: set[str] = set()
    for f in cfg["factors"]:
        col, d = f["column"], f["direction"]
        if not pool or col not in pool[0]:
            notes.append(f"候选表无 {col} 列（{f.get('label', col)}），该因子对所有股票按缺失处理")
        raw = [None if f["group"] in na[i] or col not in r else _num(r.get(col)) for i, r in enumerate(pool)]
        vals = [None if v is None else v * d for v in raw]
        ranks: list = [None] * len(pool)
        if f["group"] in neutral:
            small = []
            for ind, idxs in by_ind.items():
                if len(idxs) >= min_size:
                    sub = percentile_rank([vals[i] for i in idxs])
                    for i, p in zip(idxs, sub):
                        ranks[i] = p
                else:
                    small.append(ind)
            if small:
                rest = [i for ind in small for i in by_ind[ind]]
                sub = percentile_rank([vals[i] for i in rest])
                for i, p in zip(rest, sub):
                    ranks[i] = p
                small_industries.update(small)
        else:
            ranks = percentile_rank(vals)
        for i, p in enumerate(ranks):
            if f["group"] in na[i]:
                continue
            if p is None:
                missing[i].append(f.get("label", col))
                p = miss_p
            pct[i][col] = p

    results = []
    for i, r in enumerate(pool):
        groups = {}
        for g in weights:
            cols = [f["column"] for f in cfg["factors"] if f["group"] == g]
            groups[g] = 100 * sum(pct[i][c] for c in cols) / len(cols) if cols and g not in na[i] else None
        total = sum(weights[g] * groups[g] for g in weights if groups[g] is not None) / \
            sum(weights[g] for g in weights if groups[g] is not None)
        applicable = [f for f in cfg["factors"] if f["group"] not in na[i]]
        results.append({"code": r.get("code"), "name": r.get("name"), "industry": r.get("industry"),
                        "total": total, "groups": groups, "missing": missing[i],
                        "gate_failed": gate_fail.get(r.get("code"), []),
                        "not_applicable": sorted(na[i]),
                        "data_coverage": 1 - len(missing[i]) / len(applicable)})
    results.sort(key=lambda x: x["total"], reverse=True)
    trend_failed = [x for x in results if x["gate_failed"]]
    results = [x for x in results if not x["gate_failed"]]
    for rank, x in enumerate(results, 1):
        x["rank"] = rank
    if gates:
        notes.insert(0, f"门槛：{len(results)} 只通过趋势与现金流门槛参与排名，{len(trend_failed)} 只趋势未确认（观察/回避），"
                        f"{sum('现金流门槛' in (e.get('exclude_reason') or '') for e in excluded)} 只现金流不达标已排除")

    if small_industries:
        notes.append(f"{'、'.join(sorted(small_industries))} 样本少于 {min_size}，"
                     f"{'/'.join(GROUP_LABELS[g] for g in neutral)} 在这些行业合并排名，行业中性不充分")
    if any(na):
        notes.append("标“不适用”的维度不计入该股总分（如金融业不用一般企业的现金流规则），需另用行业专用指标核查")
    if weights is not cfg["weights"]:
        notes.append(f"按 {regime} 状态调整权重：" + "，".join(f"{GROUP_LABELS[g]} {v:.0%}" for g, v in weights.items()))
    if regime == "contraction":
        notes.insert(0, "市场处于风险收缩：已降低趋势权重；排名靠前不代表应当买入")
    return {"regime": regime, "weights": weights, "ranked": results, "trend_failed": trend_failed,
            "excluded": [{"code": r.get("code"), "name": r.get("name"), "reason": r["exclude_reason"]} for r in excluded],
            "notes": notes}


def to_markdown(res: dict) -> str:
    gs = list(res["weights"])
    lines = ["| 排名 | 代码 | 名称 | 行业 | " + " | ".join(f"{GROUP_LABELS[g]}({res['weights'][g]:.0%})" for g in gs)
             + " | 综合 | 数据覆盖 |",
             "| --- " * (6 + len(gs)) + "|"]
    for x in res["ranked"]:
        cells = [("不适用" if g in x["not_applicable"] else "—") if x["groups"][g] is None
                 else f"{x['groups'][g]:.0f}" for g in gs]
        lines.append(f"| {x['rank']} | {x['code']} | {x['name']} | {x['industry']} | " + " | ".join(cells)
                     + f" | **{x['total']:.0f}** | {x['data_coverage']:.0%} |")
    if res.get("trend_failed"):
        lines += ["", "趋势门槛未通过（不排名，结论只能是观察等待或回避）："]
        lines += [f"- {x['code']} {x['name']}：{'、'.join(x['gate_failed'])}（综合 {x['total']:.0f}）"
                  for x in res["trend_failed"]]
    gaps = [x for x in res["ranked"] if x["missing"]]
    if gaps:
        lines += ["", "缺失数据（按最差分位计）："] + [f"- {x['code']} {x['name']}：{'、'.join(x['missing'])}" for x in gaps]
    if res["excluded"]:
        lines += ["", "排除："] + [f"- {e['code']} {e['name']}：{e['reason']}" for e in res["excluded"]]
    if res["notes"]:
        lines += [""] + [f"> {n}" for n in res["notes"]]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--regime", choices=("expansion", "structural", "choppy", "contraction", "unknown"))
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("md", "json", "csv"), default="md")
    a = ap.parse_args()
    res = score(load_rows(a.candidates), read_json(a.config), a.regime)
    if a.format == "md":
        print(to_markdown(res))
    elif a.format == "json":
        dump_json(res)
    else:
        gs = list(res["weights"])
        w = csv.writer(sys.stdout)
        w.writerow(["rank", "code", "name", "industry", *gs, "total", "missing"])
        for x in res["ranked"]:
            w.writerow([x["rank"], x["code"], x["name"], x["industry"],
                        *[None if x["groups"][g] is None else round(x["groups"][g], 1) for g in gs],
                        round(x["total"], 1), ";".join(x["missing"])])
    if a.chart:
        from viz import scores as scores_chart
        save_chart(scores_chart(res, 15), a.chart)


if __name__ == "__main__":
    main()
