#!/usr/bin/env bash
# 用合成数据跑通整条流水线：行情 → 指标 → 市场状态 → 现金流 → 评分 → 仓位 → 报告
set -euo pipefail
cd "$(dirname "$0")"
S=../scripts
mkdir -p out

python3 make_sample_data.py
python3 $S/market_regime.py --bench data/bench_synthetic.csv --input ../templates/market.example.json > out/regime.json
for c in DEMO01_trend_up DEMO02_downtrend; do
  python3 $S/indicators.py data/$c.csv --bench data/bench_synthetic.csv --industry data/industry_synthetic.csv \
    --code "${c%%_*}" > "out/${c%%_*}_indicators.json"
done
python3 $S/indicators.py data/industry_synthetic.csv --bench data/bench_synthetic.csv > out/industry_indicators.json
python3 $S/national_team.py --sh data/sh_synthetic.csv --compare 中证1000=data/csi1000_synthetic.csv \
  --etf 沪深300ETF=data/etf300_synthetic.csv > out/national_team.json
python3 $S/main_force.py data/DEMO01_trend_up.csv --events ../templates/events.example.json > out/DEMO01_main_force.json
python3 $S/main_force.py data/DEMO02_downtrend.csv > out/DEMO02_main_force.json
for c in DEMO01 DEMO02; do
  python3 $S/resonance.py --regime out/regime.json --stock "out/${c}_indicators.json" --industry out/industry_indicators.json \
    --main-force "out/${c}_main_force.json" --national-team out/national_team.json > "out/${c}_resonance.json"
done
python3 $S/daily_moves.py --sectors ../templates/sectors_day.example.csv --indices ../templates/indices_day.example.csv \
  --stocks ../templates/stocks_day.example.csv --intraday 上证指数=data/sh_1min.csv --intraday 中证1000=data/csi1000_1min.csv \
  --national-team out/national_team.json --date 2026-09-30 > out/daily.json
python3 $S/cashflow_quality.py ../templates/financials.example.json > out/DEMO01_cashflow.json
python3 $S/score.py ../templates/candidates.example.csv --regime "$(python3 -c 'import json;print(json.load(open("out/regime.json"))["regime"])')" \
  --format json > out/scores.json
ATR=$(python3 -c 'import json;print(json.load(open("out/DEMO01_indicators.json"))["atr14"])')
ENTRY=$(python3 -c 'import json;print(json.load(open("out/DEMO01_indicators.json"))["close"])')
AMT=$(python3 -c 'import json;print(json.load(open("out/DEMO01_indicators.json"))["avg_amount_20d"])')
python3 $S/position_size.py --equity 1000000 --entry "$ENTRY" --atr "$ATR" --atr-mult 2.5 \
  --avg-amount "$AMT" --industry-weight 0.10 > out/DEMO01_sizing.md
python3 $S/render_report.py demo_report.json --out-dir out/report

# 可选：导出 PNG（需要 Chrome/Chromium、rsvg-convert 或 cairosvg）
if [[ "${1:-}" == "--png" ]]; then
  python3 $S/export_image.py out/report/charts --out-dir out/report/png
fi
