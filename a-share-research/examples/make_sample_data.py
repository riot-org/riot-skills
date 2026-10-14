#!/usr/bin/env python3
"""生成**合成**示例行情，仅用于测试脚本，不代表任何真实证券。

    python3 examples/make_sample_data.py   # 输出到 examples/data/
"""
import csv
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "data"


def trading_days(n: int, end: date = date(2026, 9, 30)) -> list[str]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return days[::-1]


def series(seed: int, start: float, drift: float, vol: float, days: list[str], base_vol: float) -> list[dict]:
    rnd = random.Random(seed)
    rows, price = [], start
    for d in days:
        r = rnd.gauss(drift, vol)
        o = price * (1 + rnd.gauss(0, vol / 3))
        c = price * math.exp(r)
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        v = base_vol * (1 + (2.5 if r > 0 else 1.0) * abs(r) / vol * 0.3) * rnd.uniform(0.7, 1.3)
        rows.append({"date": d, "open": round(o, 2), "high": round(h, 2), "low": round(lo, 2),
                     "close": round(c, 2), "volume": int(v), "amount": round(v * c, 0)})
        price = c
    return rows


def main() -> None:
    OUT.mkdir(exist_ok=True)
    days = trading_days(300)
    specs = {
        "bench_synthetic": (1, 3800, 0.0002, 0.011, 1e9),
        "industry_synthetic": (2, 2100, 0.0006, 0.014, 3e8),
        "DEMO01_trend_up": (9, 24.0, 0.0035, 0.016, 2e7),
        "DEMO02_downtrend": (4, 41.0, -0.0012, 0.022, 1.5e7),
        "DEMO03_range": (5, 12.5, 0.0, 0.018, 3e7),
    }
    for name, (seed, start, drift, vol, bv) in specs.items():
        rows = series(seed, start, drift, vol, days, bv)
        with open(OUT / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    # 国家队演示：上证（护盘日被拉回）、中证1000（更弱）、沪深300ETF（护盘日放量申购）
    rnd = random.Random(41)
    sh, cs, shares = 3350.0, 6400.0, 1.0e10
    rows_sh, rows_cs, rows_etf = [], [], []
    for k, d in enumerate(days):
        shock = rnd.gauss(-0.0004, 0.011)
        defend = shock < -0.014 and k > len(days) - 120  # 近期急跌日触发护盘
        cs_r = shock * 1.5 + rnd.gauss(-0.0008, 0.006)
        sh_r = shock * (0.35 if defend else 1.0)
        o = sh * (1 + rnd.gauss(0, 0.002))
        c = sh * (1 + sh_r)
        low = min(o, c, sh * (1 + shock * 1.3)) if defend else min(o, c) * (1 - abs(rnd.gauss(0, 0.003)))
        high = max(o, c) * (1 + abs(rnd.gauss(0, 0.003)))
        rows_sh.append({"date": d, "open": round(o, 2), "high": round(high, 2), "low": round(low, 2),
                        "close": round(c, 2), "volume": int(rnd.uniform(3e10, 5e10))})
        cs_c = cs * (1 + cs_r)
        rows_cs.append({"date": d, "open": round(cs, 2), "high": round(max(cs, cs_c) * 1.003, 2),
                        "low": round(min(cs, cs_c) * 0.997, 2), "close": round(cs_c, 2), "volume": int(rnd.uniform(1e10, 2e10))})
        amt = rnd.uniform(3e9, 5e9) * (3.2 if defend else 1)
        shares *= 1.035 if defend else 1 + rnd.gauss(0, 0.002)
        rows_etf.append({"date": d, "amount": round(amt, -6), "shares": round(shares, -4)})
        sh, cs = c, cs_c
    for name, rows in (("sh_synthetic", rows_sh), ("csi1000_synthetic", rows_cs), ("etf300_synthetic", rows_etf)):
        with open(OUT / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    # 分时演示（1 分钟，240 根）：上证早盘冲高、午后回落、尾盘拉升；中证1000 冲高后一路走弱
    rnd = random.Random(51)
    times = [f"{9 + (m + 30) // 60:02d}:{(m + 30) % 60:02d}" for m in range(120)] + \
            [f"{13 + m // 60:02d}:{m % 60:02d}" for m in range(120)]
    for name, path_fn in (("sh_1min", lambda t: 0.006 * math.sin(t * math.pi / 0.35) * (t < 0.35)
                            - 0.009 * min(max(t - 0.35, 0) / 0.5, 1) + 0.012 * max(t - 0.875, 0) / 0.125),
                          ("csi1000_1min", lambda t: 0.005 * math.sin(t * math.pi / 0.3) * (t < 0.3)
                           - 0.026 * min(max(t - 0.3, 0) / 0.7, 1))):
        rows = [{"time": tm, "price": round(1000 * (1 + path_fn(i / 239) + rnd.gauss(0, 0.0004)), 2)}
                for i, tm in enumerate(times)]
        with open(OUT / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["time", "price"])
            w.writeheader()
            w.writerows(rows)

    # 估值序列（约 3 年日频 PE/PB）
    rnd = random.Random(21)
    pe, rows = 32.0, []
    for d in trading_days(750):
        pe = max(12.0, pe * math.exp(rnd.gauss(-0.0002, 0.012)))
        rows.append({"date": d, "pe_ttm": round(pe, 2), "pb": round(pe / 6.5, 2)})
    with open(OUT / "DEMO01_valuation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # 市场广度历史（附加到 market 模板上）
    market = json.loads((Path(__file__).parent.parent / "templates" / "market.example.json").read_text("utf-8"))
    rnd = random.Random(31)
    a20, a60, hist = 0.55, 0.58, []
    for d in days[-120:]:
        a20 = min(0.95, max(0.05, a20 + rnd.gauss(-0.002, 0.05)))
        a60 = min(0.95, max(0.05, a60 * 0.9 + a20 * 0.1 + rnd.gauss(-0.001, 0.01)))
        hist.append({"date": d, "pct_above_ma20": round(a20, 3), "pct_above_ma60": round(a60, 3),
                     "turnover": round(rnd.uniform(0.8, 1.4) * 1e12, -8)})
    market["history"] = hist
    (OUT / "market_with_history.json").write_text(json.dumps(market, ensure_ascii=False, indent=1), "utf-8")
    print(f"已生成 {len(specs)} 个合成行情文件及估值、广度历史 → {OUT}")


if __name__ == "__main__":
    main()
