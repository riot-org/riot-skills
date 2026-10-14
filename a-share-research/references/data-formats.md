# 脚本输入数据格式

所有脚本只读本地文件。从 fuyao MCP 或东方财富取到数据后，先按下面格式落盘（建议放在本次分析的工作目录，如 `work/2026-10-14/`），再运行脚本。字段缺失就留空或写 `null`，**不要填 0 或估计值**——脚本会把缺失单独标出。

## 1. 行情 CSV（indicators / market_regime / render_svg / render_report）

```csv
date,open,high,low,close,volume,amount
2026-09-29,41.80,42.90,41.55,42.61,18234500,772310000
```

- 必需列：`date`、`close`；其余缺失时以收盘价代替 OHLC、成交量记 0。也认中文列名（日期/开盘/最高/最低/收盘/成交量/成交额）。
- 日期升序降序均可；停牌日不要写入（或留空收盘价，会被跳过）。
- **个股和基准必须同一复权口径**（建议前复权），在报告里注明。
- 至少 130 根 K 线才能算 120 日指标；画图默认显示最近 120 根。
- 指数、行业指数用同一格式；相对强度按日期交集对齐。
- 成交量单位（股/手）保持全表一致；成交额单位为元。

## 2. 市场数据 JSON（market_regime.py --input）

见 `templates/market.example.json`。

| 字段 | 含义 |
| --- | --- |
| `breadth.pct_above_ma20/ma60` | 站上 20/60 日均线的股票比例，0~1 |
| `breadth.advancers/decliners` | 上涨/下跌家数 |
| `breadth.new_highs/new_lows` | 创 N 日新高/新低家数（注明 N） |
| `turnover.today/avg20` | 全市场成交额与过去 20 日均值，元 |
| `risk.limit_up/limit_down/max_board_height` | 涨停、跌停家数、最高连板 |
| `supply` | 融资余额、IPO/再融资、解禁、减持等，自由键值，仅作背景展示，不参与打分 |
| `sources` | 每项数据的来源与读取时间 |

## 3. 财务 JSON（cashflow_quality.py）

见 `templates/financials.example.json`。一个对象一家公司，或多个对象组成数组。

| 字段 | 含义 |
| --- | --- |
| `industry` | 行业名；含“银行/保险/证券”等关键词时直接判“不适用” |
| `unit` | 金额单位，全表统一（建议亿元） |
| `years[].period` / `disclosed` | 报告期 / 实际披露日期（回测按披露日生效） |
| `revenue`, `net_profit` | 营业收入、归母净利润 |
| `cfo`, `capex` | 经营活动现金流净额、购建固定/无形/长期资产支付的现金（正数） |
| `receivables`, `contract_assets`, `inventory` | 应收账款（可含应收票据，需注明）、合同资产、存货 |
| `interest_debt`, `cash`, `short_debt` | 有息负债、货币资金、短期借款+一年内到期非流动负债 |
| `ebit`, `interest_expense` | 息税前利润、利息费用 |
| `equity_raised`, `dividends` | 当期股权融资金额、现金分红 |

用年报口径做多年比较；季报数据单独成表，不要和年报混在同一序列里。

## 4. 候选表 CSV（score.py）

见 `templates/candidates.example.csv`。必需 `code,name,industry`，其余列名对应 `templates/score_config.json` 的 `gates[].column` 和 `factors[].column`。门槛先于评分：现金流门槛不过直接排除，趋势门槛不过不排名：

| 列 | 来源 |
| --- | --- |
| `cash_gate`, `cash_gate_detail` | `cashflow_quality.py` 的 `cash_gate.passed`（通过填 1，否则 0）和 `cash_gate.failed`（用分号连接）；**缺失视为未通过并排除** |
| `dist_ma60` | `indicators.py` 输出，趋势门槛之一 |
| `excess_60d`, `excess_120d`, `ma60_slope`, `max_drawdown_120d` | `indicators.py` 输出（`vs_industry` 优先，否则 `vs_bench`） |
| `cashflow_score`, `cfo_to_ni`, `net_debt_to_cfo` | `cashflow_quality.py` 输出（最近一期） |
| `pe_pct_5y`, `peg` | 估值分位、PEG（数据源提供或自行计算，注明口径） |
| `avg_amount_20d` | `indicators.py` 输出 |
| `supply_risk`, `event_risk` | 研究员基于解禁/减持/再融资、诉讼/问询/治理等给出的 0~1 主观评估，需在报告中写明依据 |
| `exclude_reason` | 非空即排除，不参与打分，原因会出现在报告“排除”表中 |

百分比字段用小数（0.12 表示 12%）；写成 `12%` 也会自动换算成 0.12。

## 5. 图表专用输入（render_svg.py）

| 图 | 格式 |
| --- | --- |
| 估值分位带 `valuation` | CSV：`date` + 估值列（如 `pe_ttm`、`pb`，`--column` 指定）；亏损期 PE 为负值会断线且不计分位。建议 ≥3 年日频或 ≥5 年周频 |
| 行业热力图 `heatmap` | CSV：`industry` + 若干收益列（小数），见 `templates/sectors.example.csv`；`--columns ret_5d=近5日,...` 指定列和表头 |
| 广度走势 `breadth` | market.json 中加 `history: [{date, pct_above_ma20, pct_above_ma60, turnover}]` |
| 持仓分布 `allocation` | CSV：`code,name,industry,weight`（weight 为小数），见 `templates/holdings.example.csv` |
| 区间表现 `perf` | 多个行情 CSV，`--stock 名称=路径` 重复传入，最多 6 只 |
| 个股卡片 `card` | 与报告 JSON 中单个候选对象相同的 JSON |

## 6. 主力行为与国家队输入

| 脚本 | 输入 |
| --- | --- |
| `main_force.py` | 个股行情 CSV（≥130 根，建议 250 根以上）；`--float-shares` 流通股本（股，成交量也须为股）；`--events` 见 `templates/events.example.json`：`holder_count_change`（股东户数环比，小数）、`lhb_institution_net` / `lhb_hotmoney_net`（近 20 日龙虎榜机构/游资净买，元）、`inst_holding_change`（机构持股比例变化，小数）、`sector_name` / `sector_limit_up_5d` / `sector_max_board`（所属板块近 5 日涨停家次、最高连板；个股没上龙虎榜时作为游资参与的板块级证据）、`block_trade_discount`（大宗平均折价，小数）、`insider_reduction`（减持说明） |
| `national_team.py` | `--sh` 上证指数 OHLC CSV；`--compare` 对比指数 CSV（建议中证1000、创业板指、中证2000）；`--etf` 宽基 ETF CSV：`date,amount[,shares]`（成交额元，份额份） |
| `resonance.py` | 均为其它脚本的 JSON：`market_regime`、个股和行业指数的 `indicators`（行业指数也用 indicators.py 计算）、`main_force`、`national_team` |

## 7. 盘面复盘输入（daily_moves.py）

百分比一律用小数；缺的列留空。示例见 `templates/sectors_day.example.csv`、`indices_day.example.csv`、`stocks_day.example.csv`。

| 文件 | 列 |
| --- | --- |
| 板块 | `name,pct,open_pct,high_pct,low_pct,amount_ratio[,limit_up,limit_down,ret_20d,style]`；`amount_ratio` = 当日成交额 / 近 20 日均值；`ret_20d` 用于识别高低切换和主线分歧；`style` 填“权重”可显式标记权重板块 |
| 指数 | `name,pct[,open_pct,high_pct,low_pct,amount_ratio]`，至少包含上证指数和一个中小盘指数（中证1000/创业板指） |
| 个股 | `code,name,sector,pct[,open_pct,high_pct,low_pct,amount_ratio,status]`，`status` 填涨停/跌停/炸板 |
| 分时 | `time,price`，1 或 5 分钟；`--intraday 名称=路径` 可传多条 |
| 国家队 | `--national-team` 传 national_team.py 的 JSON，当日有护盘迹象时提高权重板块归因为国家队的权重 |

资金身份识别的可选列（板块、个股、ETF 通用，有就填）：

| 列 | 含义 | 用于识别 |
| --- | --- | --- |
| `mktcap` | 市值（亿元） | 国家队（千亿权重）、游资（< 100 亿小票） |
| `turnover_rate` | 换手率（小数） | 游资（≥ 10%）、国家队（< 1% 稳步拉升） |
| `max_board` | 最高连板 | 游资 |
| `lhb_inst_net` / `lhb_hot_net` | 龙虎榜机构专用 / 游资营业部净买（元） | 机构 / 游资 |
| `northbound_net` | 北向净买（元，若数据源仍提供） | 机构 |
| `big_net` / `small_net` | 大单（超大+大）/ 小单净额（元，供应商口径） | 机构、散户与对手方（弱证据） |
| `share_change` | ETF 份额单日变化（小数），宽基 ETF 行放在指数 CSV | 国家队 |

板块数量建议覆盖全部一级或二级行业（≥ 20 个），太少时高低切换等模式无法识别。

## 8. 报告 JSON（render_report.py）

见 `examples/demo_report.json`。`market`、`scores`、候选股的 `indicators`、`cashflow` 可以内嵌对象，也可以写相对路径指向各脚本 `--format json` 的输出；`risk_plan.sizing_md` 可以是 `position_size.py` 的 Markdown 文本或文件路径。`conclusion` 只能取：优先研究 / 观察等待 / 回避 / 无法判断。

可选字段：`daily`（daily_moves.py 输出路径）、`national_team`（`{json, sh_csv, compare: {名: csv}, etf: {名: csv}}`）、候选的 `main_force` / `resonance`（JSON 路径）和 `float_shares`、`breadth_history`（含 history 的 market.json 路径）、`sectors`（`{csv, columns, sort}`）、候选的 `valuation_csv` / `valuation_column`、`risk_plan.holdings_csv` / `max_weight` / `max_industry`。
