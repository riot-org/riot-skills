#!/usr/bin/env python3
"""国家队护盘行为识别（对应 SKILL.md 阶段 A2）。

用法:
    python3 scripts/national_team.py --sh 上证指数.csv \\
        --compare 中证1000=csi1000.csv --compare 创业板指=cyb.csv [--compare 中证2000=...] \\
        [--etf 沪深300ETF=510300.csv --etf 上证50ETF=510050.csv] [--days 60] [--format json|md]

国家队（汇金、证金及相关资金）的主要目标是维护上证指数平稳，常见手法是在急跌时买入宽基 ETF
（上证50、沪深300 等）和权重股（银行、保险、石油、中字头），对中小盘和题材股基本不管。
这些行为会留下可观测的痕迹，脚本逐日检查：
    1 指数分化   对比指数（中小盘）跌 ≥1% 时，上证跌幅少 ≥0.8 个百分点
    2 深V 拉回   盘中下探 ≥1.5% 后收回下影线的 60% 以上
    3 点位防守   盘中下探 ≥1% 且跌破整百点位或近 60 日低点后收回
    4 ETF 异动   市场下跌日，宽基 ETF 成交额 ≥ 20 日均值 2 倍，或份额单日增加 ≥2%（申购）
同一天 ≥2 项视为“护盘迹象强”。ETF CSV 需含 date、amount（成交额），可选 shares（份额）。
这是基于公开日线数据的推断，国家队是否入场以官方披露（季报、公告）为准。
"""
from __future__ import annotations

import argparse
import csv
import statistics

from _chart import save_chart
from _common import Bar, dump_json, fmt_pct, load_bars

DIVERGE_SMALL_DROP = -0.01   # 对比指数中位数跌幅门槛
DIVERGE_GAP = 0.008          # 上证少跌的百分点
V_DIP = 0.015                # 盘中下探幅度
V_RECOVER = 0.6              # 收回下影的比例
POINT_DIP = 0.01             # 点位防守：盘中至少下探 1%
ETF_AMOUNT_MULT = 2.0
ETF_SHARE_JUMP = 0.02


def _pair(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"需要 名称=路径：{s}")
    k, v = s.split("=", 1)
    return k.strip(), v.strip()


def load_etf(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = {}
        for r in csv.DictReader(f):
            d = (r.get("date") or r.get("日期") or "").strip()
            amt = (r.get("amount") or r.get("成交额") or "").replace(",", "").strip()
            sh = (r.get("shares") or r.get("份额") or "").replace(",", "").strip()
            rows[d] = {"amount": float(amt) if amt else None, "shares": float(sh) if sh else None}
    return dict(sorted(rows.items()))


def analyze(sh: list[Bar], compare: dict[str, list[Bar]], etfs: dict[str, dict], days: int) -> dict:
    cmap = {n: {b.date: b.close for b in bars} for n, bars in compare.items()}
    closes = [b.close for b in sh]
    events = []
    start = max(1, len(sh) - days)
    for i in range(start, len(sh)):
        b, pc = sh[i], sh[i - 1].close
        d, prev_d = b.date, sh[i - 1].date
        pct = b.close / pc - 1
        sig = []
        # 1 指数分化
        rets = [m[d] / m[prev_d] - 1 for m in cmap.values() if d in m and prev_d in m]
        small = statistics.median(rets) if rets else None
        if small is not None and small <= DIVERGE_SMALL_DROP and pct - small >= DIVERGE_GAP:
            sig.append(f"指数分化：上证 {pct:+.2%}，对比指数中位 {small:+.2%}")
        # 2 深 V 拉回
        dip = b.low / pc - 1
        if dip <= -V_DIP and (b.close - b.low) / (pc - b.low) >= V_RECOVER:
            sig.append(f"深V拉回：盘中 {dip:+.2%}，收于 {pct:+.2%}")
        # 3 点位防守
        level = int(b.close // 100) * 100
        low60 = min(closes[max(0, i - 60):i])
        stressed = dip <= -POINT_DIP  # 只在盘中明显下探的日子判断点位防守，避免平淡日的噪声
        if stressed and b.low < level <= b.close:
            sig.append(f"守住 {level} 点：最低 {b.low:.0f}")
        elif stressed and b.low < low60 <= b.close:
            sig.append(f"跌破近 60 日低点 {low60:.0f} 后收回")
        # 4 ETF 异动（只看市场下跌日）
        market_down = (small is not None and small < 0) or pct < 0 or dip <= -V_DIP
        if market_down:
            for name, rows in etfs.items():
                keys = list(rows)
                if d not in rows:
                    continue
                k = keys.index(d)
                hist = [rows[x]["amount"] for x in keys[max(0, k - 20):k] if rows[x]["amount"]]
                amt = rows[d]["amount"]
                if amt and hist and amt >= ETF_AMOUNT_MULT * (sum(hist) / len(hist)):
                    sig.append(f"{name} 成交额为 20 日均值的 {amt / (sum(hist) / len(hist)):.1f} 倍")
                if k and rows[d]["shares"] and rows[keys[k - 1]]["shares"]:
                    chg = rows[d]["shares"] / rows[keys[k - 1]]["shares"] - 1
                    if chg >= ETF_SHARE_JUMP:
                        sig.append(f"{name} 份额单日 {chg:+.1%}（大额申购）")
        if sig:
            events.append({"date": d, "sh_pct": pct, "compare_median_pct": small, "signals": sig,
                           "strength": "强" if len(sig) >= 2 else "弱"})

    window = sh[start - 1:]
    sh_ret = window[-1].close / window[0].close - 1
    comp_ret = {}
    for n, m in cmap.items():
        ds = [b.date for b in window if b.date in m]
        if len(ds) >= 2:
            comp_ret[n] = m[ds[-1]] / m[ds[0]] - 1
    strong = [e for e in events if e["strength"] == "强"]
    gap = sh_ret - statistics.median(comp_ret.values()) if comp_ret else None
    if len(strong) >= 3 or (len(strong) >= 1 and gap is not None and gap > 0.05):
        level = "明显"
    elif events:
        level = "零星"
    else:
        level = "未见"
    return {
        "window": f"{window[0].date} → {window[-1].date}",
        "days": len(window) - 1,
        "support_level": level,
        "sh_return": sh_ret, "compare_returns": comp_ret, "index_distortion": gap,
        "events": events, "strong_days": len(strong),
        "last_signal": events[-1]["date"] if events else None,
        "implications": implications(level, gap),
        "caveat": "基于公开日线数据的推断；国家队持仓以季报、公告等官方披露为准。",
    }


def implications(level: str, gap: float | None) -> list[str]:
    out = []
    if gap is not None and gap > 0.03:
        out.append(f"上证跑赢中小盘指数 {gap:.1%}：上证被权重托住，不能代表多数股票的真实状态，"
                   "市场状态应以中证全指/中证1000 与全市场广度为准。")
    if level == "明显":
        out += ["护盘集中在宽基 ETF 和权重股，护的是指数点位，不护个股；中小盘、题材股趋势坏了照样跌。",
                "指数被托住的同时若全市场广度很差，说明存量资金在流出，属于风险收缩特征，不是买入信号。",
                "护盘资金托住的权重股波动小、趋势弱，不符合本 Skill 的趋势门槛时同样不做。"]
    elif level == "零星":
        out.append("有零星护盘迹象，关注是否在关键点位密集出现。")
    else:
        out.append("窗口内未见明显护盘痕迹，指数走势主要由市场资金决定。")
    return out


def to_markdown(r: dict) -> str:
    lines = [f"### 国家队行为：护盘迹象{r['support_level']}（{r['window']}，{r['days']} 个交易日）", "",
             f"- 上证区间 {fmt_pct(r['sh_return'])}；" + "；".join(f"{n} {fmt_pct(v)}" for n, v in r["compare_returns"].items()),
             f"- 指数失真度（上证 − 对比指数中位）：{fmt_pct(r['index_distortion'])}",
             f"- 护盘迹象：{len(r['events'])} 天，其中强信号 {r['strong_days']} 天；最近一次 {r['last_signal'] or '—'}"]
    if r["events"]:
        lines += ["", "| 日期 | 上证 | 对比指数中位 | 迹象 | 强度 |", "| --- | --- | --- | --- | --- |"]
        for e in r["events"][-12:]:
            lines.append(f"| {e['date']} | {fmt_pct(e['sh_pct'], 2)} | {fmt_pct(e['compare_median_pct'], 2)} | "
                         f"{'；'.join(e['signals'])} | {e['strength']} |")
    lines += ["", "**含义**", ""] + [f"- {x}" for x in r["implications"]] + ["", f"> {r['caveat']}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sh", required=True, help="上证指数行情 CSV（需含 open/high/low/close）")
    ap.add_argument("--compare", type=_pair, action="append", default=[], help="对比指数 名称=CSV，建议中证1000/创业板指/中证2000")
    ap.add_argument("--etf", type=_pair, action="append", default=[], help="宽基 ETF 名称=CSV（date,amount[,shares]）")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    if not a.compare:
        ap.error("至少提供一个 --compare 对比指数，否则无法判断指数分化")
    r = analyze(load_bars(a.sh), {n: load_bars(p) for n, p in a.compare},
                {n: load_etf(p) for n, p in a.etf}, a.days)
    print(to_markdown(r)) if a.format == "md" else dump_json(r)
    if a.chart:
        from viz import national_team as nteam_chart
        etf = next(((n, load_etf(p)) for n, p in a.etf), None)
        save_chart(nteam_chart(load_bars(a.sh), {n: load_bars(p) for n, p in a.compare}, etf, r, a.days), a.chart)


if __name__ == "__main__":
    main()
