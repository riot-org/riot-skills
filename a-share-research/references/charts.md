# 图表选型与渲染

所有图表由 `scripts/render_svg.py`（单图）或 `scripts/render_report.py`（整份报告自动配图）生成，底层是 `scripts/viz/` 零依赖 SVG 库。需要贴到微信/飞书/PPT 时用 `scripts/export_image.py` 转 PNG，整份报告可转 PDF。

## 先问“这张图回答什么问题”

| 想说明的问题 | 用这个 | 子命令 | 数据来自 |
| --- | --- | --- | --- |
| 今天拉了什么、砸了什么、意图是什么？ | 盘面复盘 | `daily` | `daily_moves.py` 输出 |
| 现在是什么市场？ | 市场状态卡 | `regime` | `market_regime.py` 输出 |
| 赚钱效应在扩散还是收缩？ | 广度与成交额走势 | `breadth` | market.json 的 `history` |
| 资金在哪些行业？轮动到哪了？ | 行业涨跌热力图 | `heatmap` | 行业收益 CSV |
| 候选股谁更值得研究？ | 综合评分堆叠条 | `scores` | `score.py --format json` |
| 候选股谁更强、谁回撤更深？ | 区间表现对比 + 回撤 | `perf` | 多只个股行情 CSV |
| 这只股票一眼看懂 | 个股卡片 | `card` | 候选 JSON（含指标、现金流、评分） |
| 趋势、量能、相对强度细节 | K 线三面板 | `kline` | 个股 + 基准行情 CSV |
| 现在贵不贵？ | 估值分位带 | `valuation` | 估值时间序列 CSV |
| 利润是不是真金白银？ | 利润与现金流 | `cashflow` | `cashflow_quality.py` 输出 |
| 回款/库存有没有恶化？ | 收入 vs 应收/存货增速 | `growth` | `cashflow_quality.py` 输出 |
| 主力成本在哪？获利盘多少？处在什么阶段？ | 筹码分布 + 主力阶段 | `chips` | 个股行情 CSV（+ 流通股本、事件） |
| 上证是不是被护住了？ | 国家队护盘痕迹 | `nteam` | 上证 + 对比指数 + 宽基 ETF |
| 组合是否过度集中？ | 权重分布与上限 | `allocation` | 持仓 CSV |

只有一个关键数字时，直接写在正文里，不要为它画图。

## 报告配图顺序（render_report.py 自动执行）

1. 开头「速览」：市场状态 + 各结论数量 + 今日盘面一句话（给了 `daily`）。
2. 市场状态：状态卡 → 广度走势（给了 `breadth_history`）→ 行业热力图（给了 `sectors`）→ 盘面复盘（给了 `daily`）→ 国家队护盘痕迹（给了 `national_team`）。
3. 候选股：评分堆叠条 → 区间表现对比（≥2 只有行情）。
4. 每只候选：个股卡片（含主力阶段与共振数）→ K 线 → 估值分位带（给了 `valuation_csv`）→ 利润与现金流（有 `cashflow` 且适用）→ 筹码分布与主力行为（给了 `main_force`）→ 共振检查表（给了 `resonance`）。
5. 风险计划：组合权重分布（给了 `holdings_csv`）。

缺哪项数据就跳过对应的图，不用占位图或编造数据补齐。

## 设计约定（改图时保持一致）

- **红涨绿跌**（A 股习惯）；涨跌颜色只用于价格/收益方向，不用作普通系列色。
- 分类系列色固定顺序：蓝、橙、青绿、黄、品红、紫；同一实体在不同图里颜色一致。超过 6 个系列请拆图或合并为“其他”。
- **不做双纵轴**：价格、成交量、相对强度、回撤分面板绘制，各自一条纵轴。
- 颜色之外总有第二种编码：数值标签、图标（★ ◷ ✕ ? ▲ ▼）、文字（“超限”“缺失”“不适用”）。
- 每张图都有标题 + 副标题说明口径（区间、复权、单位、分位定义）。
- 悬停原生提示显示明细；浅色/深色跟随系统，导出图片默认浅色。
- 估值分位带使用图中整个区间的分位，**只用于展示**；回测必须用滚动、点时的分位。

## 导出

```bash
python3 scripts/export_image.py reports/2026-10-14/charts --out-dir reports/2026-10-14/png   # 全部 SVG → 2x PNG
python3 scripts/export_image.py reports/2026-10-14/charts/card_600519.svg --theme dark        # 单张深色
python3 scripts/export_image.py reports/2026-10-14/report.html --pdf                          # 报告 → PDF
```

后端顺序：Chrome/Chromium/Edge/Brave 无头模式 → `rsvg-convert` → `cairosvg`。都没有时脚本会报错并提示安装方式，不会自动下载。
