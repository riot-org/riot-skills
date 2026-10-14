#!/usr/bin/env python3
"""把研究数据渲染成独立 SVG 图表（零依赖；跟随系统深浅色，悬停有原生提示）。

子命令（都需要 -o 输出路径；--theme light|dark 可强制主题，默认跟随系统）:
    kline      个股.csv [--bench 指数.csv] [--days 120] [--title 名称]      K 线 + 均线 + 成交量 + 相对强度
    perf       --stock 名称=个股.csv ...（≤6）[--bench 名称=指数.csv] [--days 120]  归一化走势 + 回撤对比
    valuation  估值.csv --column pe_ttm [--title ...]                        估值走势 + 历史分位带
    cashflow   cashflow.json                                               净利润/CFO/FCF 柱 + 利润现金含量
    growth     cashflow.json                                               收入 vs 应收/存货增速
    heatmap    行业.csv --columns ret_5d=近5日,ret_20d=近20日 [--sort ret_20d]  行业涨跌热力图（红涨绿跌）
    breadth    market.json（需含 history 数组）                            站上均线比例 + 成交额
    regime     regime.json（market_regime.py 输出）                        市场状态卡
    scores     scores.json（score.py 输出）[--top 15]                      综合评分堆叠条
    allocation 持仓.csv（code,name,industry,weight）[--max-weight 0.1 --max-industry 0.25]  权重分布与超限
    card       候选.json [--scores scores.json]                           个股一页卡片
    chips      个股.csv [--float-shares N] [--events events.json] [--title ...]  筹码分布 + 主力行为阶段
    daily      daily.json（daily_moves.py 输出）                          盘面复盘：板块日内区间 + 指数分时 + 意图
    nteam      --sh 上证.csv --compare 名称=CSV ... [--etf 名称=CSV] [--days 60]  国家队护盘痕迹

候选.json 与 report.json 里 candidates 的单个元素同格式（kline_csv / indicators / cashflow 写相对路径）。
所有输入格式见 references/data-formats.md，图表选型见 references/charts.md。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import viz
from _common import load_bars, load_series, read_json
from main_force import analyze as main_force_analyze, chip_distribution
from national_team import analyze as nteam_analyze, load_etf


def _pair(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"需要 名称=路径 形式：{s}")
    k, v = s.split("=", 1)
    return k.strip(), v.strip()


def _load_rel(value, base: Path):
    return read_json(base / value) if isinstance(value, str) else value


def _num(v):
    v = (v or "").strip().replace(",", "")
    if v in ("", "-", "—"):
        return None
    return float(v[:-1]) / 100 if v.endswith("%") else float(v)


def theme(svg: str, mode: str) -> str:
    return svg if mode == "auto" else svg.replace("<svg ", f'<svg data-theme="{mode}" ', 1)


def card_from_candidate(path: str, scores_path: str | None) -> str:
    base = Path(path).resolve().parent
    c = read_json(path)
    bars = load_bars(base / c["kline_csv"]) if c.get("kline_csv") else None
    sc = read_json(scores_path) if scores_path else None
    entry = next((s for s in (sc or {}).get("ranked", []) if s["code"] == c.get("code")), None)
    return viz.stock_card(c, bars, _load_rel(c.get("indicators"), base), _load_rel(c.get("cashflow"), base), entry)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = {name: sub.add_parser(name) for name in
         ("kline", "perf", "valuation", "cashflow", "growth", "heatmap", "breadth", "regime", "scores",
          "allocation", "card", "chips", "nteam", "daily")}
    p["kline"].add_argument("csv")
    p["kline"].add_argument("--bench")
    p["kline"].add_argument("--days", type=int, default=120)
    p["kline"].add_argument("--title", default="")
    p["perf"].add_argument("--stock", type=_pair, action="append", required=True)
    p["perf"].add_argument("--bench", type=_pair)
    p["perf"].add_argument("--days", type=int, default=120)
    p["perf"].add_argument("--title", default="区间表现对比")
    p["valuation"].add_argument("csv")
    p["valuation"].add_argument("--column", default="pe_ttm")
    p["valuation"].add_argument("--title", default="")
    for k in ("cashflow", "growth", "regime", "scores", "breadth", "card", "daily"):
        p[k].add_argument("json")
    p["scores"].add_argument("--top", type=int, default=15)
    p["card"].add_argument("--scores")
    p["heatmap"].add_argument("csv")
    p["heatmap"].add_argument("--columns", required=True, help="列名=表头，逗号分隔")
    p["heatmap"].add_argument("--sort")
    p["heatmap"].add_argument("--title", default="行业涨跌热力图")
    p["allocation"].add_argument("csv")
    p["allocation"].add_argument("--max-weight", type=float, default=0.10)
    p["allocation"].add_argument("--max-industry", type=float, default=0.25)
    p["chips"].add_argument("csv")
    p["chips"].add_argument("--float-shares", type=float)
    p["chips"].add_argument("--events")
    p["chips"].add_argument("--title", default="")
    p["nteam"].add_argument("--sh", required=True)
    p["nteam"].add_argument("--compare", type=_pair, action="append", required=True)
    p["nteam"].add_argument("--etf", type=_pair, action="append", default=[])
    p["nteam"].add_argument("--days", type=int, default=60)
    for sp in p.values():
        sp.add_argument("-o", "--output", required=True)
        sp.add_argument("--theme", choices=("auto", "light", "dark"), default="auto")
    a = ap.parse_args()

    if a.cmd == "kline":
        svg = viz.kline(load_bars(a.csv), load_bars(a.bench) if a.bench else None, a.days, a.title or Path(a.csv).stem)
    elif a.cmd == "perf":
        svg = viz.performance([(n, load_bars(f)) for n, f in a.stock],
                              (a.bench[0], load_bars(a.bench[1])) if a.bench else None, a.days, a.title)
    elif a.cmd == "valuation":
        svg = viz.valuation_band(load_series(a.csv, a.column), a.column, a.title or f"{Path(a.csv).stem} 估值分位")
    elif a.cmd == "cashflow":
        svg = viz.cashflow(read_json(a.json))
    elif a.cmd == "growth":
        svg = viz.growth_gap(read_json(a.json))
    elif a.cmd == "heatmap":
        cols = [_pair(c) for c in a.columns.split(",")]
        with open(a.csv, newline="", encoding="utf-8-sig") as f:
            rows = [{"industry": r["industry"], **{c: _num(r.get(c)) for c, _ in cols}} for r in csv.DictReader(f)]
        svg = viz.sector_heatmap(rows, cols, a.sort, a.title)
    elif a.cmd == "breadth":
        svg = viz.breadth_history(read_json(a.json).get("history") or [])
    elif a.cmd == "regime":
        svg = viz.regime(read_json(a.json))
    elif a.cmd == "scores":
        svg = viz.scores(read_json(a.json), a.top)
    elif a.cmd == "allocation":
        with open(a.csv, newline="", encoding="utf-8-sig") as f:
            hold = [{**r, "weight": _num(r["weight"])} for r in csv.DictReader(f)]
        svg = viz.allocation(hold, a.max_weight, a.max_industry)
    elif a.cmd == "daily":
        svg = viz.daily_moves(read_json(a.json))
    elif a.cmd == "chips":
        bars = load_bars(a.csv)
        res = main_force_analyze(bars, a.float_shares, read_json(a.events) if a.events else {})
        svg = viz.chips(bars, chip_distribution(bars, a.float_shares), res, a.title or f"{Path(a.csv).stem} 筹码分布")
    elif a.cmd == "nteam":
        sh = load_bars(a.sh)
        compare = {n: load_bars(f) for n, f in a.compare}
        etfs = {n: load_etf(f) for n, f in a.etf}
        res = nteam_analyze(sh, compare, etfs, a.days)
        svg = viz.national_team(sh, compare, next(iter(etfs.items()), None), res, a.days)
    else:
        svg = card_from_candidate(a.json, a.scores)

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(theme(svg, a.theme), encoding="utf-8")
    print(f"已写入 {a.output}")


if __name__ == "__main__":
    main()
