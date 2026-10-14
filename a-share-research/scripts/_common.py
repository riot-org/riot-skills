"""共享工具：读取行情 CSV、基础统计。仅依赖 Python 标准库（3.9+）。

行情 CSV 约定（列名不区分大小写，中文列名也可）：
    date, open, high, low, close, volume[, amount]
按日期升序或降序均可，读取后统一升序。价格应为同一复权口径（建议前复权）。
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

COLUMN_ALIASES = {
    "date": {"date", "日期", "trade_date", "time"},
    "open": {"open", "开盘", "开盘价"},
    "high": {"high", "最高", "最高价"},
    "low": {"low", "最低", "最低价"},
    "close": {"close", "收盘", "收盘价"},
    "volume": {"volume", "vol", "成交量"},
    "amount": {"amount", "成交额", "turnover"},
}


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


def _normalize_header(name: str) -> str | None:
    key = name.strip().lower()
    for canonical, aliases in COLUMN_ALIASES.items():
        if key in aliases:
            return canonical
    return None


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value in ("", "-", "--", "nan", "None"):
        return None
    return float(value)


def load_bars(path: str | Path) -> list[Bar]:
    """读取行情 CSV，跳过停牌/缺价行，返回按日期升序的 Bar 列表。"""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        mapping = {h: _normalize_header(h) for h in reader.fieldnames or []}
        missing = {"date", "close"} - set(mapping.values())
        if missing:
            die(f"{path}: 缺少必需列 {sorted(missing)}，现有列 {reader.fieldnames}")
        bars = []
        for row in reader:
            r = {mapping[k]: v for k, v in row.items() if mapping.get(k)}
            close = _num(r.get("close"))
            if close is None or close <= 0:
                continue
            bars.append(Bar(
                date=r["date"].strip(),
                open=_num(r.get("open")) or close,
                high=_num(r.get("high")) or close,
                low=_num(r.get("low")) or close,
                close=close,
                volume=_num(r.get("volume")) or 0.0,
                amount=_num(r.get("amount")),
            ))
    bars.sort(key=lambda b: b.date)
    if not bars:
        die(f"{path}: 没有有效行情数据")
    return bars


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= n:
            running -= values[i - n]
        if i >= n - 1:
            out[i] = running / n
    return out


def pct_change(a: float | None, b: float | None) -> float | None:
    """(b / a - 1)，任一缺失返回 None。"""
    if a is None or b is None or a == 0:
        return None
    return b / a - 1


def ret_n(closes: list[float], n: int) -> float | None:
    if len(closes) <= n:
        return None
    return pct_change(closes[-n - 1], closes[-1])


def max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)
    return mdd


def ann_volatility(closes: list[float], n: int = 60) -> float | None:
    if len(closes) <= n:
        return None
    window = closes[-n - 1:]
    rets = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
    return statistics.stdev(rets) * math.sqrt(244)


def atr(bars: list[Bar], n: int = 14) -> float | None:
    if len(bars) <= n:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        b, prev = bars[i], bars[i - 1].close
        trs.append(max(b.high - b.low, abs(b.high - prev), abs(b.low - prev)))
    return sum(trs) / n


def percentile_rank(values: list[float | None]) -> list[float | None]:
    """0~1 百分位（越大越靠前），缺失值保持 None，并列取平均名次。"""
    present = sorted((v, i) for i, v in enumerate(values) if v is not None)
    out: list[float | None] = [None] * len(values)
    if not present:
        return out
    if len(present) == 1:
        out[present[0][1]] = 0.5
        return out
    j = 0
    while j < len(present):
        k = j
        while k + 1 < len(present) and present[k + 1][0] == present[j][0]:
            k += 1
        rank = (j + k) / 2 / (len(present) - 1)
        for m in range(j, k + 1):
            out[present[m][1]] = rank
        j = k + 1
    return out


def fmt_pct(v: float | None, digits: int = 1, signed: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.{digits}f}%" if signed else f"{v * 100:.{digits}f}%"


def fmt_num(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:,.{digits}f}"


def read_json(path: str | Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj) -> None:
    json.dump(round_floats(obj), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def round_floats(obj, digits: int = 4):
    if isinstance(obj, float):
        return None if math.isnan(obj) else round(obj, digits)
    if isinstance(obj, dict):
        return {k: round_floats(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, digits) for v in obj]
    return obj


def die(msg: str, code: int = 2) -> None:
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(code)


def load_series(path: str | Path, column: str) -> list[tuple[str, float]]:
    """读取 date + 任意数值列（如 pe_ttm、pb），返回 [(date, value)] 升序，跳过空值。"""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        date_col = next((h for h in fields if _normalize_header(h) == "date"), None)
        if not date_col or column not in fields:
            die(f"{path}: 需要日期列和 {column} 列，现有列 {fields}")
        out = [(row[date_col].strip(), v) for row in reader if (v := _num(row.get(column))) is not None]
    out.sort()
    return out
