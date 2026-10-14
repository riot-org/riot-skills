#!/usr/bin/env python3
"""把研究结果汇总成 SKILL.md 第 7 节格式的报告：report.md + 自包含的 report.html（内嵌 SVG）。

用法:
    python3 scripts/render_report.py report.json --out-dir reports/2026-10-14

report.json 结构见 templates/report.example.json。其中 market / scores 以及候选股的
indicators / cashflow 字段既可以直接写对象，也可以写 JSON 文件路径（相对 report.json）——
即 market_regime.py / score.py / indicators.py / cashflow_quality.py 的 --format json 输出。
候选股给了 kline_csv（可选 bench_csv）就会画 K 线图。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from html import escape
from pathlib import Path

import viz
from _common import fmt_pct, load_bars, load_series, read_json
from daily_moves import to_markdown as daily_md
from main_force import chip_distribution, to_markdown as main_force_md
from market_regime import to_markdown as regime_md
from national_team import load_etf, to_markdown as nteam_md
from resonance import to_markdown as resonance_md

CONCLUSIONS = ("优先研究", "观察等待", "回避", "无法判断")


def _load(value, base: Path):
    if isinstance(value, str):
        return read_json(base / value)
    return value


def _bullets(items, empty="（未提供）") -> list[str]:
    items = items or []
    return [f"- {i}" for i in items] if items else [f"- {empty}"]


def gate_conflicts(cands: list[dict], market: dict | None, scores: dict | None, base: Path) -> list[str]:
    """“优先研究”必须同时满足：市场不在风险收缩、通过现金流和趋势门槛、主力不在出货/下跌、四层共振。"""
    out = []
    excluded = {e.get("code"): e.get("reason") for e in (scores or {}).get("excluded", [])}
    trend_failed = {x["code"]: x["gate_failed"] for x in (scores or {}).get("trend_failed", [])}
    for c in cands:
        if c.get("conclusion") != "优先研究":
            continue
        name = f"{c.get('name', '')} {c['code']}"
        if market and market.get("regime") == "contraction":
            out.append(f"{name}：市场处于风险收缩，结论最高为“观察等待”")
        if c["code"] in excluded:
            out.append(f"{name}：已被排除（{excluded[c['code']]}），不应进入候选")
        if c["code"] in trend_failed:
            out.append(f"{name}：趋势门槛未通过（{'、'.join(trend_failed[c['code']])}）")
        mf = _load(c.get("main_force"), base)
        if mf and mf.get("phase") in ("distribution", "markdown"):
            out.append(f"{name}：主力行为判断为“{mf['phase_label']}”")
        res = _load(c.get("resonance"), base)
        if res is None:
            out.append(f"{name}：缺少共振检查（大盘/板块/个股/资金），无法确认可以给“优先研究”")
        elif res.get("max_conclusion") != "优先研究":
            out.append(f"{name}：共振不足（未共振：{'、'.join(res['missing'])}），结论上限为“{res['max_conclusion']}”")
    return out


def _slug(code: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", code)


def build(report: dict, base: Path, out: Path) -> str:
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)

    def chart(name: str, svg: str, alt: str) -> list[str]:
        (charts / name).write_text(svg, encoding="utf-8")
        return [f"![{alt}](charts/{name})", ""]

    cands = report.get("candidates") or []
    md: list[str] = [f"# {report.get('title', 'A 股研究报告')}", ""]
    # 速览：一行结论，先给读者答案
    glance = []
    market = _load(report.get("market"), base)
    if market:
        glance.append(f"市场：**{market['regime_label']}**（置信度 {market['confidence']}）")
    for verdict in CONCLUSIONS:
        n = sum(c.get("conclusion", "无法判断") == verdict for c in cands)
        if n:
            glance.append(f"{viz.base.VERDICT[verdict][0]} {verdict} {n} 只")
    if glance:
        md += ["> " + " · ".join(glance), ""]
    daily = _load(report.get("daily"), base)  # daily_moves.py 输出
    if daily:
        md += [f"> **今日盘面**：{daily['summary']}", ""]

    # 1. 日期与数据时点
    md += ["## 1. 分析日期与数据时点", "",
           f"- 分析日期：{report.get('analysis_date', '未注明')}",
           f"- 行情数据截止：{report.get('data_cutoff', '未注明')}",
           f"- 财报可用口径：{report.get('financials_as_of', '未注明')}"]
    sources = report.get("sources") or []
    if sources:
        md += ["", "| 数据项 | 来源 | 时点 |", "| --- | --- | --- |"]
        md += [f"| {s.get('item', '')} | {s.get('source', '')} | {s.get('as_of', '')} |" for s in sources]
    md.append("")

    # 2. 市场状态
    md += ["## 2. 市场状态", ""]
    if market:
        md += chart("regime.svg", viz.regime(market), "市场状态")
        md += regime_md(market).split("\n")[2:]  # 跳过脚本自带的标题行
        md.append("")
    else:
        md += ["无法判断：未提供市场状态数据。", ""]
    breadth = report.get("breadth_history")  # market.json（含 history）路径或数组
    if breadth:
        hist = _load(breadth, base)
        hist = hist.get("history", []) if isinstance(hist, dict) else hist
        if len(hist) >= 2:
            md += chart("breadth.svg", viz.breadth_history(hist), "市场广度与成交额")
    sectors = report.get("sectors")  # {"csv": 路径, "columns": {"ret_5d": "近5日", ...}, "sort": 列名}
    if sectors:
        cols = list(sectors["columns"].items())
        with open(base / sectors["csv"], newline="", encoding="utf-8-sig") as f:
            rows = [{"industry": r["industry"],
                     **{c: (float(r[c]) if (r.get(c) or "").strip() else None) for c, _ in cols}}
                    for r in csv.DictReader(f)]
        md += chart("sectors.svg", viz.sector_heatmap(rows, cols, sectors.get("sort"),
                                                     subtitle=sectors.get("subtitle", "")), "行业涨跌热力图")
    if daily:
        md += ["### 当日盘面：拉了什么、砸了什么、意图", ""]
        md += chart("daily_moves.svg", viz.daily_moves(daily), "盘面复盘")
        md += daily_md(daily).split("\n")[2:] + [""]
    nt_cfg = report.get("national_team")  # {"json": national_team.py 输出, "sh_csv", "compare": {名: csv}, "etf": {名: csv}}
    if nt_cfg:
        nt = _load(nt_cfg["json"], base)
        md += ["### 国家队行为", ""]
        if nt_cfg.get("sh_csv") and nt_cfg.get("compare"):
            compare = {n: load_bars(base / f) for n, f in nt_cfg["compare"].items()}
            etf = next(((n, load_etf(base / f)) for n, f in (nt_cfg.get("etf") or {}).items()), None)
            md += chart("national_team.svg", viz.national_team(load_bars(base / nt_cfg["sh_csv"]), compare, etf, nt,
                                                               nt["days"]), "国家队护盘痕迹")
        md += nteam_md(nt).split("\n")[2:] + [""]

    # 3. 股票池与排除
    uni = report.get("universe") or {}
    scores = _load(report.get("scores"), base)
    md += ["## 3. 股票池与排除规则", "", f"- 范围：{uni.get('scope', '未注明')}"]
    md += [f"- 过滤：{f}" for f in uni.get("filters", [])]
    excluded = (uni.get("excluded") or []) + ((scores or {}).get("excluded") or [])
    if excluded:
        md += ["", "| 代码 | 名称 | 排除原因 |", "| --- | --- | --- |"]
        md += [f"| {e.get('code', '')} | {e.get('name', '')} | {e.get('reason', '')} |" for e in excluded]
    md.append("")

    # 4. 候选股表格
    md += ["## 4. 候选股表格", ""]
    if scores:
        md += chart("scores.svg", viz.scores(scores, 15), "综合评分")
    with_bars = [c for c in cands if c.get("kline_csv")]
    if len(with_bars) >= 2:
        bench_c = next((c for c in with_bars if c.get("bench_csv")), None)
        bench = ("基准", load_bars(base / bench_c["bench_csv"])) if bench_c else None
        md += chart("performance.svg", viz.performance(
            [(c.get("name") or c["code"], load_bars(base / c["kline_csv"])) for c in with_bars[:6]], bench, 120,
            "候选股区间表现对比"), "区间表现对比")
    rank = {s["code"]: s for s in (scores or {}).get("ranked", []) + (scores or {}).get("trend_failed", [])}
    conflicts = gate_conflicts(cands, market, scores, base)
    md += ["| 代码 | 名称 | 行业 | 趋势 | 相对强度(60日) | 现金流质量 | 估值 | 供给/事件风险 | 综合评分 | 结论 |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in cands:
        ind = _load(c.get("indicators"), base) or {}
        cf = _load(c.get("cashflow"), base) or {}
        rs = (ind.get("vs_industry") or ind.get("vs_bench") or {}).get("excess_60d")
        trend = c.get("trend") or ("—" if not ind else
                                   ("MA60 上方" if ind.get("checks", {}).get("close_above_ma60") else "MA60 下方")
                                   + ("、MA60 向上" if ind.get("checks", {}).get("ma60_rising") else "、MA60 走平/向下"))
        cash = c.get("cashflow_text") or (f"{cf['label']}" + (f"（{cf['score']:.0f}）" if cf.get("score") is not None else "")
                                          if cf else "—")
        total = rank.get(c["code"], {}).get("total")
        md.append(f"| {c['code']} | {c.get('name', '')} | {c.get('industry', '')} | {trend} | "
                  f"{c.get('relative_strength') or fmt_pct(rs)} | {cash} | {c.get('valuation', '—')} | "
                  f"{c.get('supply_risk', '—')} | {'—' if total is None else f'{total:.0f}'} | "
                  f"**{c.get('conclusion', '无法判断')}** |")
    if scores and scores.get("notes"):
        md += [""] + [f"> {n}" for n in scores["notes"]]
    if conflicts:
        md += ["", "**⚠️ 结论与硬门槛冲突，需修正后再发布：**", ""] + [f"- {c}" for c in conflicts]
        for c in conflicts:
            print(f"警告: {c}", file=sys.stderr)
    md.append("")

    # 5 & 6. 候选逻辑、观察区间
    md += ["## 5. 候选逻辑", ""]
    for c in cands:
        md += [f"### {c.get('name', '')} {c['code']} — {c.get('conclusion', '无法判断')}", ""]
        slug, name = _slug(c["code"]), c.get("name", "")
        bars = load_bars(base / c["kline_csv"]) if c.get("kline_csv") else None
        ind, cf = _load(c.get("indicators"), base), _load(c.get("cashflow"), base)
        extra = {"main_force": _load(c.get("main_force"), base), "resonance": _load(c.get("resonance"), base)}
        md += chart(f"card_{slug}.svg", viz.stock_card({**c, **extra}, bars, ind, cf, rank.get(c["code"])), f"{name} 个股卡片")
        if bars:
            bench = load_bars(base / c["bench_csv"]) if c.get("bench_csv") else None
            md += chart(f"kline_{slug}.svg", viz.kline(bars, bench, c.get("chart_days", 120), f"{name} {c['code']}"),
                        f"{name} K 线")
        if c.get("valuation_csv"):
            col = c.get("valuation_column", "pe_ttm")
            md += chart(f"valuation_{slug}.svg", viz.valuation_band(load_series(base / c["valuation_csv"], col), col,
                                                                    f"{name} {col} 历史分位"), f"{name} 估值分位")
        if cf and cf.get("applicable"):
            md += chart(f"cashflow_{slug}.svg", viz.cashflow(cf), f"{name} 利润与现金流")
        mf = _load(c.get("main_force"), base)
        if mf:
            if bars:
                fs = c.get("float_shares")
                md += chart(f"chips_{slug}.svg", viz.chips(bars, chip_distribution(bars, fs), mf, f"{name} 筹码分布"),
                            f"{name} 筹码分布")
            md += [f"**主力行为：{mf['phase_label']}**（置信度 {mf['confidence']}）", ""] + main_force_md(mf, "").split("\n")[2:] + [""]
        res = _load(c.get("resonance"), base)
        if res:
            md += [f"**共振检查：{res['level']}（{res['yes_count']}/4）**", ""] + resonance_md(res, "").split("\n")[2:] + [""]
        for key, label in (("supports", "支持因素"), ("risks", "主要风险"),
                           ("to_verify", "待核实"), ("invalidation", "逻辑失效条件")):
            md += [f"**{label}**", ""] + _bullets(c.get(key)) + [""]
    md += ["## 6. 观察/买入研究区间", "",
           "> 仅在数据支持时给出技术条件或估值区间，不是确定性预测，不代表实时价格。", ""]
    md += [f"- {c.get('name', '')} {c['code']}：{c.get('watch_zone') or '数据不足，暂不给出'}" for c in cands]
    md.append("")

    # 7. 风险计划
    md += ["## 7. 风险计划", ""]
    plan = report.get("risk_plan") or {}
    labels = {"position_limits": "仓位限制", "correlation": "组合相关性", "liquidity": "流动性风险",
              "exit_triggers": "退出触发条件"}
    for k, label in labels.items():
        if plan.get(k):
            md += [f"**{label}**", ""] + _bullets(plan[k] if isinstance(plan[k], list) else [plan[k]]) + [""]
    if plan.get("sizing_md"):  # position_size.py 的 Markdown 输出，或其文件路径
        sizing = plan["sizing_md"]
        if sizing.endswith(".md") and (base / sizing).is_file():
            sizing = (base / sizing).read_text(encoding="utf-8")
        md += [sizing.replace("### ", "**", 1).replace("\n", "**\n", 1) if sizing.startswith("### ") else sizing, ""]
    if plan.get("holdings_csv"):  # 拟议/现有持仓 code,name,industry,weight
        with open(base / plan["holdings_csv"], newline="", encoding="utf-8-sig") as f:
            hold = [{**r, "weight": float(r["weight"])} for r in csv.DictReader(f)]
        md += chart("allocation.svg", viz.allocation(hold, plan.get("max_weight", 0.10), plan.get("max_industry", 0.25)),
                    "组合权重分布")

    # 8. 结论
    md += ["## 8. 结论", ""]
    for verdict in CONCLUSIONS:
        names = [f"{c.get('name', '')} {c['code']}" for c in cands if c.get("conclusion", "无法判断") == verdict]
        if names:
            md.append(f"- **{verdict}**：{'、'.join(names)}")
    if report.get("summary"):
        md += ["", report["summary"]]
    md += ["", "---", "",
           "*本报告仅用于研究与决策辅助，不构成投资建议，不保证收益；所有信号均为概率性证据。*"]
    return "\n".join(md) + "\n"


# ---------- 极简 Markdown → HTML（只覆盖本报告用到的语法） ----------

def _inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def md_to_html(md: str, out: Path) -> str:
    html, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if m := re.match(r"^(#{1,4}) (.*)", ln):
            n = len(m.group(1))
            html.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif m := re.match(r"^!\[(.*?)\]\((.+?\.svg)\)$", ln):
            svg = (out / m.group(2)).read_text(encoding="utf-8")
            html.append(f'<figure aria-label="{escape(m.group(1))}">{svg}</figure>')
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            html.append('<div class="tbl"><table><thead><tr>' + "".join(f"<th>{_inline(c)}</th>" for c in head)
                        + "</tr></thead><tbody>" + "".join(
                            "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
                        + "</tbody></table></div>")
            continue
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].startswith("> "):
                quote.append(_inline(lines[i][2:]))
                i += 1
            html.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            continue
        elif ln.strip() == "---":
            html.append("<hr>")
        elif ln.strip():
            html.append(f"<p>{_inline(ln)}</p>")
        i += 1
    title = re.search(r"^# (.*)", md, re.M)
    return HTML_SHELL.format(title=escape(title.group(1) if title else "研究报告"), body="\n".join(html))


HTML_SHELL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f6f5f2; --card:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --line:#e7e6e2; --accent:#2a78d6; }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --bg:#111110; --card:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --line:#2e2e2b; --accent:#3987e5; }}
}}
:root[data-theme="dark"] {{ --bg:#111110; --card:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --line:#2e2e2b; --accent:#3987e5; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); line-height:1.65;
  font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif; }}
main {{ max-width:880px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:26px; margin:0 0 20px; }}
h2 {{ font-size:19px; margin:40px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--line); }}
h3 {{ font-size:16px; margin:28px 0 8px; }}
p, li {{ color:var(--ink-2); }} strong {{ color:var(--ink); }}
figure {{ margin:12px 0; overflow-x:auto; }} figure svg {{ max-width:100%; height:auto; display:block; }}
.tbl {{ overflow-x:auto; margin:12px 0; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }}
th, td {{ border-bottom:1px solid var(--line); padding:7px 10px; text-align:left; white-space:nowrap; }}
th {{ color:var(--ink-2); font-weight:600; background:var(--card); }}
blockquote {{ margin:12px 0; padding:8px 14px; border-left:3px solid var(--accent); background:var(--card);
  color:var(--ink-2); font-size:13px; }}
hr {{ border:0; border-top:1px solid var(--line); margin:32px 0 12px; }}
em {{ color:var(--ink-2); font-size:13px; }}
</style></head>
<body><main>
{body}
</main></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    src = Path(a.report).resolve()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = build(read_json(src), src.parent, out)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.html").write_text(md_to_html(md, out), encoding="utf-8")
    html = (out / "report.html").resolve()
    print(f"已生成 {out / 'report.md'} 和 {out / 'report.html'}（图表在 {out / 'charts'}）")
    print(f"浏览器预览：{html.as_uri()}")


if __name__ == "__main__":
    main()
