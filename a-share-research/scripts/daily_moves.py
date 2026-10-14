#!/usr/bin/env python3
"""盘面复盘：当天拉了什么、砸了什么、资金意图是什么（对应 SKILL.md 阶段 A3）。

用法:
    python3 scripts/daily_moves.py --sectors 板块当日.csv [--indices 指数当日.csv] [--stocks 个股当日.csv]
        [--intraday 上证指数=sh_1min.csv --intraday 中证1000=csi1000_1min.csv] [--date 2026-10-14]
        [--top 8] [--format json|md]

输入（百分比一律用小数，0.023 = +2.3%；缺的列留空）:
    板块 CSV  name,pct,open_pct,high_pct,low_pct,amount_ratio[,limit_up,limit_down,ret_20d,style]
              amount_ratio = 当日成交额 / 近 20 日均值；ret_20d 用来识别高位主线和低位补涨；
              style 可填 权重/题材/成长/周期，不填时按名称关键词识别权重板块
    指数 CSV  name,pct[,open_pct,high_pct,low_pct,amount_ratio]（上证指数、中证1000、创业板指等）
    个股 CSV  code,name,sector,pct[,open_pct,high_pct,low_pct,amount_ratio,status]（status：涨停/跌停/炸板/N连板）
    资金身份（可选列，板块/个股/ETF 通用）：mktcap 市值（亿）、turnover_rate 换手率、max_board 最高连板、
              big_net / small_net 大单（超大+大）/小单净额（元，供应商口径）、lhb_inst_net / lhb_hot_net 龙虎榜
              机构/游资净买（元）、northbound_net 北向净买（元）、share_change ETF 份额变化（宽基 ETF 放在指数 CSV）
    分时 CSV  time,price[,volume]（1 分钟或 5 分钟）

每个板块/个股先按当天走势贴标签（放量拉升、冲高回落、低开低走、探底回升、无量阴跌等），
再按“拉权重砸题材”“高低切换”“主线分歧”“尾盘拉指数”等模式推断意图。
意图是基于公开盘面数据的推断，必须同时给出其它可能的解释。
"""
from __future__ import annotations

import argparse
import csv
import statistics

from _chart import save_chart
from _common import dump_json, fmt_pct, read_json

PULL = 0.02            # 板块涨幅 ≥ 2% 算“拉”
DUMP = -0.02           # 板块跌幅 ≤ -2% 算“砸”
STOCK_PULL, STOCK_DUMP = 0.05, -0.05
VOL_UP, VOL_DOWN = 1.2, 0.9
FADE = 0.02            # 冲高回落 / 探底回升：收盘离最高/最低 ≥ 2 个百分点
WEIGHT_KEYWORDS = ("银行", "保险", "证券", "石油", "石化", "煤炭", "电力", "公用", "白酒", "通信服务", "运营商", "中字头")
SMALL_INDEX_KEYWORDS = ("1000", "2000", "创业", "科创", "微盘", "北证")


def _f(v):
    v = (v or "").strip().replace(",", "")
    if v in ("", "-", "—"):
        return None
    return float(v[:-1]) / 100 if v.endswith("%") else float(v)


def load_rows(path: str, numeric: tuple[str, ...]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{**r, **{k: _f(r.get(k)) for k in numeric}} for r in csv.DictReader(f)]


def load_intraday(path: str) -> list[tuple[str, float]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [(r.get("time") or r.get("时间"), float(r.get("price") or r.get("价格")))
                for r in csv.DictReader(f) if (r.get("price") or r.get("价格"))]


def shape_tags(r: dict, pull: float, dump: float) -> list[str]:
    """按当日 OHLC 与量能给走势贴标签。"""
    pct, o, h, lo, ar = (r.get(k) for k in ("pct", "open_pct", "high_pct", "low_pct", "amount_ratio"))
    tags = []
    if pct is None:
        return tags
    vol_up = ar is not None and ar >= VOL_UP
    vol_dn = ar is not None and ar < VOL_DOWN
    if pct >= pull:
        tags.append("放量拉升" if vol_up else "缩量上涨" if vol_dn else "拉升")
        if h is not None and h - pct < 0.005:
            tags.append("收在最高附近")
        if o is not None and o < 0 < pct:
            tags.append("低开高走")
    if pct <= dump:
        tags.append("放量砸盘" if vol_up else "无量阴跌" if vol_dn else "下跌")
        if lo is not None and pct - lo < 0.005:
            tags.append("收在最低附近")
        if o is not None and o <= -0.01 and pct <= o:
            tags.append("低开低走")
    if h is not None and h >= 0.02 and h - pct >= FADE:
        tags.append("冲高回落" + ("（放量）" if vol_up else ""))
    if lo is not None and lo <= -0.02 and pct - lo >= FADE:
        tags.append("探底回升" + ("（放量）" if vol_up else ""))
    if r.get("status"):
        tags.append(r["status"])
    return tags


def intraday_profile(series: list[tuple[str, float]], prev_close: float | None = None) -> dict:
    """分时形态：以第一笔为基准（或给定昨收），计算早盘 30 分钟、尾盘 30 分钟、日内最大回落/反弹。"""
    prices = [p for _, p in series]
    base = prev_close or prices[0]
    n = len(prices)
    k = max(1, n // 8)  # 约 30 分钟（按 4 小时交易计）
    hi_i = max(range(n), key=lambda i: prices[i])
    lo_i = min(range(n), key=lambda i: prices[i])
    prof = {
        "first_30m": prices[k] / prices[0] - 1,
        "last_30m": prices[-1] / prices[-k - 1] - 1,
        "high": prices[hi_i] / base - 1, "high_time": series[hi_i][0],
        "low": prices[lo_i] / base - 1, "low_time": series[lo_i][0],
        "close": prices[-1] / base - 1,
    }
    desc = []
    if prof["first_30m"] >= 0.005:
        desc.append(f"早盘 30 分钟拉升 {prof['first_30m']:+.2%}")
    elif prof["first_30m"] <= -0.005:
        desc.append(f"早盘 30 分钟下砸 {prof['first_30m']:+.2%}")
    if hi_i < n * 0.4 and prof["high"] - prof["close"] >= 0.008:
        desc.append(f"{prof['high_time']} 冲到 {prof['high']:+.2%} 后回落")
    if lo_i < n * 0.8 and prof["close"] - prof["low"] >= 0.008:
        desc.append(f"{prof['low_time']} 探到 {prof['low']:+.2%} 后拉回")
    if prof["last_30m"] >= 0.004:
        desc.append(f"尾盘 30 分钟拉升 {prof['last_30m']:+.2%}")
    elif prof["last_30m"] <= -0.004:
        desc.append(f"尾盘 30 分钟跳水 {prof['last_30m']:+.2%}")
    prof["desc"] = desc
    return prof


def is_weight(r: dict) -> bool:
    style = (r.get("style") or "").strip()
    if style:
        return style == "权重"
    return any(k in r["name"] for k in WEIGHT_KEYWORDS)


ACTORS = ("国家队", "游资", "机构", "散户")
BROAD_ETF_KEYWORDS = ("50", "300", "500", "1000", "A50", "科创50", "创业板")


def attribute(r: dict, ctx: dict) -> dict:
    """判断一次拉升/砸盘的主导资金，以及（有资金流数据时）对手方。全部是指纹式推断，不是身份确认。

    指纹：
      国家队  权重/宽基 ETF、上证强于中小盘的护盘日、ETF 放量或份额大增、尾盘拉指数；只买不砸，不碰小票
      游资    题材、中小市值、涨停/连板/炸板、高换手、龙虎榜游资席位、日内急拉急砸
      机构    中大市值成长/白马、不涨停的稳步放量、与 20 日趋势同向、龙虎榜机构席位、北向/大单同向
      散户    小单与价格同向而大单反向（接盘或推高被出货）、高开低走追高被套、无龙头的后排跟风、缩量阴跌
    """
    pct = r.get("pct") or 0
    up = pct > 0
    sign = 1 if up else -1
    pts = {a: 0.0 for a in ACTORS}
    ev = {a: [] for a in ACTORS}

    def add(actor, w, text):
        pts[actor] += w
        ev[actor].append(text)

    name = r.get("name", "")
    mc, tr, ar = r.get("mktcap"), r.get("turnover_rate"), r.get("amount_ratio")
    status = r.get("status") or ""
    tags = r.get("tags", [])
    is_etf = "ETF" in name.upper()
    # 国家队
    if is_etf and any(k in name for k in BROAD_ETF_KEYWORDS) and up:
        if (ar or 0) >= 2:
            add("国家队", 3, f"宽基 ETF 放量 {ar:.1f} 倍")
        if (r.get("share_change") or 0) >= 0.02:
            add("国家队", 2, f"ETF 份额 {r['share_change']:+.1%}（大额申购）")
    if r.get("is_weight") and up:
        if ctx.get("index_gap") is not None and ctx["index_gap"] >= 0.008:
            add("国家队", 2, f"权重上涨且上证强于中小盘 {ctx['index_gap']:+.2%}")
        if ctx.get("nt_today"):
            add("国家队", 1, "国家队脚本当日识别到护盘迹象")
        if ctx.get("tail_pull"):
            add("国家队", 1, "上证尾盘拉升")
    if mc is not None and mc >= 1000 and up and (tr or 1) < 0.01 and "收在最高附近" in tags:
        add("国家队", 1, f"千亿市值、低换手（{tr:.2%}）稳步拉升")
    if r.get("is_weight") and not up:
        add("机构", 0.5, "权重下跌：国家队通常不砸盘，更可能是机构/外资卖出")
    # 游资
    lu, board = r.get("limit_up"), r.get("max_board")
    if lu is not None and lu >= 3 and up:
        add("游资", 2, f"板块 {int(lu)} 家涨停")
    if board is not None and board >= 3:
        add("游资", 1, f"最高 {int(board)} 连板")
    if any(k in status for k in ("涨停", "炸板", "连板")):
        add("游资", 2, f"个股{status}")
    if (r.get("limit_down") or 0) >= 3 and not up:
        add("游资", 1, f"板块 {int(r['limit_down'])} 家跌停（短线资金踩踏）")
    if r.get("lhb_hot_net") is not None and r["lhb_hot_net"] * sign > 0:
        bigger = abs(r["lhb_hot_net"]) > abs(r.get("lhb_inst_net") or 0)
        add("游资", 2.5 if bigger else 2, f"龙虎榜游资净{'买' if up else '卖'} {abs(r['lhb_hot_net']) / 1e8:.2f} 亿")
    if tr is not None and tr >= 0.10:
        add("游资", 1, f"换手率 {tr:.1%}")
    if mc is not None and mc < 100:
        add("游资", 1, f"小市值 {mc:.0f} 亿")
    if any(t.startswith("冲高回落（放量）") for t in tags) and not r.get("is_weight"):
        add("游资", 1, "题材放量冲高回落（短线资金拉高兑现）")
    # 机构
    if r.get("lhb_inst_net") is not None and r["lhb_inst_net"] * sign > 0:
        bigger = abs(r["lhb_inst_net"]) >= abs(r.get("lhb_hot_net") or 0)
        add("机构", 2.5 if bigger else 2, f"龙虎榜机构净{'买' if up else '卖'} {abs(r['lhb_inst_net']) / 1e8:.2f} 亿")
    if r.get("northbound_net") is not None and r["northbound_net"] * sign > 0:
        add("机构", 1, f"北向净{'买' if up else '卖'} {abs(r['northbound_net']) / 1e8:.2f} 亿")
    if (mc is None or mc >= 300) and not r.get("is_weight") and not any(k in status for k in ("涨停", "跌停", "炸板")) \
            and (lu or 0) < 3 and ar is not None and 1.2 <= ar <= 2.5 and abs(pct) >= 0.02:
        add("机构", 1, f"不涨跌停的稳步放量（{ar:.1f} 倍）")
    if r.get("ret_20d") is not None and r["ret_20d"] * sign > 0.05 and not any(t.startswith("冲高回落") for t in tags):
        add("机构", 1, f"与 20 日趋势同向（{r['ret_20d']:+.1%}），有持续性")
    if r.get("big_net") is not None and r["big_net"] * sign > 0:
        add("机构", 0.5, f"大单净{'流入' if up else '流出'} {abs(r['big_net']) / 1e8:.2f} 亿（供应商口径）")
    # 散户
    big, small = r.get("big_net"), r.get("small_net")
    if big is not None and small is not None and big * small < 0 and small * sign > 0:
        add("散户", 2, f"小单净{'买' if small > 0 else '卖'} {abs(small) / 1e8:.2f} 亿、大单反向（供应商口径）")
    o = r.get("open_pct")
    if o is not None and o >= 0.02 and pct <= o - 0.02:
        add("散户", 1, f"高开 {o:+.1%} 后低走（追高被套）")
    if up and (lu or 0) == 0 and not status and ar is not None and ar < 1.0 and abs(pct) < 0.04:
        add("散户", 1, "无涨停龙头、缩量上涨（后排跟风）")
    if not up and "无量阴跌" in tags:
        add("散户", 1, "无量阴跌（散户慢慢卖、无人承接）")

    ranked = sorted(pts.items(), key=lambda kv: -kv[1])
    (a1, p1), (a2, p2) = ranked[0], ranked[1]
    if p1 < 1.5:
        driver, conf = "不明", "低"
    elif p2 >= 1.5 and p1 - p2 < 1:
        driver, conf = f"{a1}+{a2}", "中"
    else:
        driver, conf = a1, "高" if p1 >= 4 and p1 - p2 >= 2 else "中"
    counter = None
    if big is not None and small is not None and big * small < 0:
        counter = "散户接盘" if big < 0 < small else "散户在卖、大单承接" if small < 0 < big else None
    return {"driver": driver, "confidence": conf, "counterparty": counter,
            "evidence": [e for a, _ in ranked if pts[a] > 0 for e in ev[a]][:5], "scores": pts}


def infer_intents(sectors: list[dict], indices: list[dict], intraday: dict) -> list[dict]:
    out = []

    def add(name, conf, evidence, alternatives, involved=(), hint=None):
        out.append({"intent": name, "confidence": conf, "evidence": evidence, "alternatives": alternatives,
                    "involved": [x["name"] for x in involved], "actor_hint": hint})

    valid = [s for s in sectors if s.get("pct") is not None]
    if not valid:
        return out
    up = sum(s["pct"] > 0 for s in valid) / len(valid)
    med_ar = statistics.median([s["amount_ratio"] for s in valid if s.get("amount_ratio") is not None] or [1.0])
    weights = [s["pct"] for s in valid if is_weight(s)]
    others = [s["pct"] for s in valid if not is_weight(s)]
    w_avg = statistics.mean(weights) if weights else None
    t_avg = statistics.mean(others) if others else None
    sh = next((i["pct"] for i in indices if "上证" in i["name"] and i.get("pct") is not None), None)
    smalls = [i["pct"] for i in indices if any(k in i["name"] for k in SMALL_INDEX_KEYWORDS) and i.get("pct") is not None]
    small = statistics.mean(smalls) if smalls else None
    breadth = f"上涨板块占比 {up:.0%}"

    # 1 拉权重护指数 / 2 拉题材砸权重
    if w_avg is not None and t_avg is not None:
        gap = w_avg - t_avg
        idx_gap = None if sh is None or small is None else sh - small
        if gap >= 0.01 or (idx_gap is not None and idx_gap >= 0.008):
            ev = [f"权重板块平均 {w_avg:+.2%}，其它板块平均 {t_avg:+.2%}"]
            if idx_gap is not None:
                ev.append(f"上证 {sh:+.2%}，中小盘指数平均 {small:+.2%}")
            ev.append(breadth)
            name = "拉权重护指数"
            if up < 0.4:
                name += "，掩护个股下跌"
            add(name, "高" if gap >= 0.02 and up < 0.5 else "中", ev,
                ["避险资金切向高股息/低估值权重（不一定是护盘）", "权重板块自身有利好催化"],
                [x for x in valid if is_weight(x) and x["pct"] > 0], "国家队")
        elif gap <= -0.01:
            add("拉题材砸权重：活跃资金做题材", "中",
                [f"权重板块平均 {w_avg:+.2%}，其它板块平均 {t_avg:+.2%}", breadth],
                ["权重资金在撤出（风格切换而非风险偏好上升）", "题材有消息催化，持续性待验证"],
                [x for x in valid if not is_weight(x) and x["pct"] >= PULL], "游资")

    # 3/4 普涨普跌
    if up >= 0.7:
        add("普涨" + ("放量：增量资金进场" if med_ar >= 1.1 else "缩量：存量资金反弹"), "中",
            [breadth, f"板块成交额中位数为 20 日均值的 {med_ar:.2f} 倍"], ["超跌反弹，未必是趋势反转"],
            hint="机构" if med_ar >= 1.1 else "混合")
    elif up <= 0.3:
        add("普跌" + ("放量：集中出逃" if med_ar >= 1.1 else "缩量：无承接阴跌"), "中",
            [breadth, f"板块成交额中位数为 20 日均值的 {med_ar:.2f} 倍"],
            ["外部利空冲击后的一次性释放", "节前/周末前的避险减仓"],
            hint="机构" if med_ar >= 1.1 else "散户")

    # 5 高低切换 / 6 主线分歧
    ranked = sorted([s for s in valid if s.get("ret_20d") is not None], key=lambda s: -s["ret_20d"])
    if len(ranked) >= 8:
        q = max(2, len(ranked) // 4)
        hi_grp, lo_grp = ranked[:q], ranked[-q:]
        hi_avg = statistics.mean(s["pct"] for s in hi_grp)
        lo_avg = statistics.mean(s["pct"] for s in lo_grp)
        if hi_avg <= -0.015 and lo_avg >= 0.01:
            add("高低切换：高位主线兑现，资金去低位补涨", "中",
                [f"近 20 日涨幅前 {q} 板块今日平均 {hi_avg:+.2%}（{'、'.join(s['name'] for s in hi_grp[:4])}）",
                 f"近 20 日涨幅后 {q} 板块今日平均 {lo_avg:+.2%}（{'、'.join(s['name'] for s in lo_grp[:4])}）"],
                ["单日轮动，主线未必结束，需看后续 2~3 日是否回流"], hi_grp + lo_grp, "机构")
        faded = [s for s in hi_grp if any(t.startswith("冲高回落") for t in s["tags"])]
        if faded:
            add("主线分歧：高位板块冲高回落", "中" if any("放量" in t for s in faded for t in s["tags"]) else "低",
                [f"{s['name']}：最高 {fmt_pct(s.get('high_pct'))}，收 {fmt_pct(s['pct'])}，"
                 f"量能 {s.get('amount_ratio') or 0:.2f} 倍" for s in faded],
                ["正常换手，分歧后可能转一致", "盘中利空导致回落"], faded)

    # 7 拉高出货 / 8 砸盘承接
    fades = [s for s in valid if any(t.startswith("冲高回落（放量）") for t in s["tags"])]
    if len(fades) >= 3:
        add("盘中拉高出货：多个板块放量冲高回落", "中", [f"{s['name']} 最高 {fmt_pct(s.get('high_pct'))} 收 {fmt_pct(s['pct'])}" for s in fades[:6]],
            ["大盘盘中跳水拖累，不一定是主动出货"], fades)
    dips = [s for s in valid if any(t.startswith("探底回升（放量）") for t in s["tags"])]
    if len(dips) >= 2:
        add("砸出低点后被承接：洗盘或低吸", "低", [f"{s['name']} 最低 {fmt_pct(s.get('low_pct'))} 收 {fmt_pct(s['pct'])}" for s in dips[:6]],
            ["超跌反抽，承接未必持续"], dips)

    # 9 分时：尾盘拉指数 / 早盘冲高回落
    sh_prof = next((v for k, v in intraday.items() if "上证" in k), None)
    small_prof = [v for k, v in intraday.items() if any(x in k for x in SMALL_INDEX_KEYWORDS)]
    if sh_prof:
        sm_last = statistics.mean(p["last_30m"] for p in small_prof) if small_prof else None
        if sh_prof["last_30m"] >= 0.004 and (sm_last is None or sh_prof["last_30m"] - sm_last >= 0.003):
            add("尾盘拉上证：做收盘价/护盘", "中",
                [f"上证尾盘 30 分钟 {sh_prof['last_30m']:+.2%}"]
                + ([f"中小盘尾盘 30 分钟 {sm_last:+.2%}"] if sm_last is not None else []),
                ["尾盘有利好消息", "机构调仓集中在尾盘"], hint="国家队")
        if sh_prof["high"] - sh_prof["close"] >= 0.008 and sh_prof["first_30m"] > 0:
            add("早盘拉高、盘中回落：冲高出货或护盘力度不足", "低", sh_prof["desc"], ["外盘或消息面盘中转弱"], hint="混合")
    return out


def analyze(sectors, indices, stocks, intraday_series, date, top, nt: dict | None = None) -> dict:
    for s in sectors:
        s["tags"] = shape_tags(s, PULL, DUMP)
        s["is_weight"] = is_weight(s)
    for s in stocks:
        s["tags"] = shape_tags(s, STOCK_PULL, STOCK_DUMP)
        s["is_weight"] = is_weight({"name": s.get("sector") or "", "style": s.get("style")})
    for i in indices:
        i["tags"] = shape_tags(i, 0.01, -0.01)
    intraday = {name: intraday_profile(series) for name, series in intraday_series.items()}
    valid = [s for s in sectors if s.get("pct") is not None]
    sh = next((i["pct"] for i in indices if "上证" in i["name"] and i.get("pct") is not None), None)
    smalls = [i["pct"] for i in indices if any(k in i["name"] for k in SMALL_INDEX_KEYWORDS) and i.get("pct") is not None]
    sh_prof = next((v for k, v in intraday.items() if "上证" in k), None)
    ctx = {"index_gap": sh - statistics.mean(smalls) if sh is not None and smalls else None,
           "nt_today": bool(nt and any(e["date"] == date for e in nt.get("events", []))),
           "tail_pull": bool(sh_prof and sh_prof["last_30m"] >= 0.004)}
    etf_rows = [i for i in indices if "ETF" in i["name"].upper()]  # 普通指数是结果不是参与者，只识别 ETF
    for row in valid + stocks + etf_rows:
        if row.get("pct") is not None:
            row["actor"] = attribute(row, ctx)
    pulled = sorted([s for s in valid if s["pct"] >= PULL], key=lambda s: -s["pct"])[:top]
    dumped = sorted([s for s in valid if s["pct"] <= DUMP], key=lambda s: s["pct"])[:top]
    st_valid = [s for s in stocks if s.get("pct") is not None]
    st_pulled = sorted([s for s in st_valid if s["pct"] >= STOCK_PULL], key=lambda s: -s["pct"])[:top]
    st_dumped = sorted([s for s in st_valid if s["pct"] <= STOCK_DUMP], key=lambda s: s["pct"])[:top]
    intents = infer_intents(sectors, indices, intraday)
    by_name = {x["name"]: x for x in valid}
    for it in intents:
        drivers = [by_name[n]["actor"]["driver"] for n in it["involved"] if n in by_name]
        known = [d for d in drivers if d != "不明"]
        if known:
            top_d = max(set(known), key=known.count)
            it["actor"] = top_d if known.count(top_d) * 2 > len(known) or not it["actor_hint"] else it["actor_hint"]
        else:
            it["actor"] = it["actor_hint"] or "不明"
    counters = None  # 在确定拉/砸名单后计算
    counters = [f"{x['name']}（{x['actor']['counterparty']}）" for x in pulled + dumped + st_pulled + st_dumped
                if x.get("actor", {}).get("counterparty")]
    intent_labels = [f"{it['intent']}（{it['actor']}）" for it in intents[:3]]
    summary = (f"拉了：{'、'.join(s['name'] for s in pulled[:5]) or '无明显拉升板块'}；"
               f"砸了：{'、'.join(s['name'] for s in dumped[:5]) or '无明显砸盘板块'}；"
               f"意图推断：{'；'.join(intent_labels) or '无明确模式'}")
    return {
        "date": date, "summary": summary,
        "indices": indices, "intraday": {k: {**v, "series": intraday_series[k][::max(1, len(intraday_series[k]) // 120)]}
                                         for k, v in intraday.items()},
        "pulled_sectors": pulled, "dumped_sectors": dumped,
        "pulled_stocks": st_pulled, "dumped_stocks": st_dumped,
        "intents": intents, "sectors": valid, "counterparties": counters,
        "actor_summary": actor_summary(pulled, dumped, st_pulled, st_dumped),
        "caveat": "资金身份与意图都是基于盘面指纹的推断，无法确认真实身份；大单/小单资金流为数据供应商口径，只作弱证据。",
    }


def actor_summary(*groups) -> dict:
    """按主导资金汇总当天拉了/砸了哪些。"""
    out = {a: {"拉": [], "砸": []} for a in (*ACTORS, "不明")}
    for g in groups:
        for x in g:
            d = x.get("actor", {}).get("driver", "不明")
            for a in d.split("+"):
                out.setdefault(a, {"拉": [], "砸": []})["拉" if x["pct"] > 0 else "砸"].append(x["name"])
    return {a: v for a, v in out.items() if v["拉"] or v["砸"]}


def to_markdown(r: dict) -> str:
    def row(s, with_sector=False):
        name = f"{s.get('name', '')}" + (f"（{s.get('sector')}）" if with_sector and s.get("sector") else "")
        ar = s.get("amount_ratio")
        act = s.get("actor") or {}
        who = "—" if not act else f"{act['driver']}（{act['confidence']}）" + (f"，{act['counterparty']}" if act.get("counterparty") else "")
        return (f"| {name}{' 〔权重〕' if s.get('is_weight') else ''} | {fmt_pct(s.get('pct'), 2)} | "
                f"{fmt_pct(s.get('high_pct'), 2)} / {fmt_pct(s.get('low_pct'), 2)} | "
                f"{'—' if ar is None else f'{ar:.2f}'} | {'、'.join(s['tags']) or '—'} | {who} | "
                f"{'；'.join(act.get('evidence', [])[:3]) or '—'} |")

    head = ("| 名称 | 涨跌 | 最高 / 最低 | 量能(倍) | 走势 | 主导资金 | 依据 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |")
    lines = [f"### 盘面复盘（{r['date'] or '日期未注明'}）", "", f"**一句话**：{r['summary']}", ""]
    if r["indices"]:
        lines += ["**指数**", "", head] + [row(i) for i in r["indices"]] + [""]
    for k, v in r["intraday"].items():
        if v["desc"]:
            lines.append(f"- {k} 分时：" + "；".join(v["desc"]))
    if r["intraday"]:
        lines.append("")
    for key, label in (("pulled_sectors", "拉了什么（板块）"), ("dumped_sectors", "砸了什么（板块）")):
        lines += [f"**{label}**", ""] + ([head] + [row(s) for s in r[key]] if r[key] else ["无"]) + [""]
    for key, label in (("pulled_stocks", "拉升个股"), ("dumped_stocks", "砸盘个股")):
        if r[key]:
            lines += [f"**{label}**", "", head] + [row(s, True) for s in r[key]] + [""]
    if r.get("actor_summary"):
        lines += ["**谁在拉、谁在砸**", "", "| 资金 | 拉 | 砸 |", "| --- | --- | --- |"]
        for a, v in r["actor_summary"].items():
            lines.append(f"| {a} | {'、'.join(v['拉']) or '—'} | {'、'.join(v['砸']) or '—'} |")
        if r.get("counterparties"):
            lines += ["", f"对手方：{'；'.join(r['counterparties'])}"]
        lines.append("")
    lines += ["**意图推断**", ""]
    if not r["intents"]:
        lines.append("- 没有识别出明确模式，按普通轮动看待。")
    for it in r["intents"]:
        lines.append(f"- **{it['intent']}**（主导：{it.get('actor', '不明')}，置信度 {it['confidence']}）：{'；'.join(it['evidence'])}")
        lines.append(f"  - 其它可能：{'；'.join(it['alternatives'])}")
    lines += ["", f"> {r['caveat']}"]
    return "\n".join(lines)


def _pair(s: str) -> tuple[str, str]:
    k, v = s.split("=", 1)
    return k.strip(), v.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sectors", required=True)
    ap.add_argument("--indices")
    ap.add_argument("--stocks")
    ap.add_argument("--intraday", type=_pair, action="append", default=[], help="名称=分时CSV")
    ap.add_argument("--national-team", help="national_team.py 的 JSON 输出，用于确认当日护盘迹象")
    ap.add_argument("--date", default="")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--chart", help="同时出图：路径以 .png 结尾则导出 PNG（另存同名 SVG），.svg 只出 SVG")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    num = ("pct", "open_pct", "high_pct", "low_pct", "amount_ratio", "limit_up", "limit_down", "ret_20d", "max_board",
           "mktcap", "turnover_rate", "big_net", "small_net", "lhb_inst_net", "lhb_hot_net", "northbound_net", "share_change")
    sectors = load_rows(a.sectors, num)
    indices = load_rows(a.indices, num) if a.indices else []
    stocks = load_rows(a.stocks, num) if a.stocks else []
    nt = read_json(a.national_team) if a.national_team else None
    r = analyze(sectors, indices, stocks, {n: load_intraday(p) for n, p in a.intraday}, a.date, a.top, nt)
    print(to_markdown(r)) if a.format == "md" else dump_json(r)
    from viz import daily_moves as daily_chart
    save_chart(daily_chart(r), a.chart)


if __name__ == "__main__":
    main()
