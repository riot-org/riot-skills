# 数据来源与工具规范

## 9.1 主数据源：扶摇（fuyao）MCP

本 Skill 依赖以下 4 个 MCP 服务器：

| id | 地址 | 用途 |
| --- | --- | --- |
| `fuyao-a-share` | `https://fuyao.aicubes.cn/mcp/a-share` | 个股行情、财务、公告等 |
| `fuyao-a-share-index` | `https://fuyao.aicubes.cn/mcp/a-share-index` | 指数行情、成分股、市场广度 |
| `fuyao-fund` | `https://fuyao.aicubes.cn/mcp/fund` | 基金、ETF 份额与申赎 |
| `fuyao-meta` | `https://fuyao.aicubes.cn/mcp/meta` | 代码表、交易日历、字段说明 |

各服务器的具体工具和字段以连接后的工具清单为准（工具名形如 `mcp__fuyao-a-share__<工具名>`），不要凭记忆假设工具名或参数。

**每次分析开始前先检查：** 当前工具清单（或 ToolSearch 搜 `fuyao`）里是否 4 个服务器都有 `mcp__fuyao-*__*` 工具。都有就直接用；缺任何一个，按下面步骤安装：

1. **收集 API key。** 调 `RequestEnv`，变量名 `FUYAO_API_KEY`，reason 写「连接扶摇 A 股数据 MCP 需要 API key」。不要让用户把 key 贴进对话，也不要让用户自己 `export`。已配好时不会再弹表单。
2. **写入 MCP 配置。** 注意：设置 → 环境变量里的值**不会**自动传给 MCP 服务器，key 必须写进每个服务器自己的 `env`。用 Bash 跑一个脚本，从 `$FUYAO_API_KEY` 读出值，只修改 `<配置目录>/config.json` 里的 `mcpServers` 数组（配置目录的位置和数组的形状见 `add-mcp` 技能），不要整份重写文件，也不要把 key 的明文输出到对话里。缺哪几个就补哪几个，已有的同 id 条目原样保留。每个条目的形状：

   ```json
   {
     "id": "fuyao-a-share",
     "command": "npx",
     "args": ["-y", "mcp-remote", "https://fuyao.aicubes.cn/mcp/a-share",
              "--header", "X-api-key:${FUYAO_API_KEY}"],
     "env": { "FUYAO_API_KEY": "<从 $FUYAO_API_KEY 读出的值>" },
     "enabled": true
   }
   ```

   另外 3 个只把 `id` 和 URL 末段换成 `a-share-index`、`fund`、`meta`。`--header` 和 `X-api-key:${FUYAO_API_KEY}` 是 `args` 里的两个元素，冒号两边不加空格；`${FUYAO_API_KEY}` 由 `mcp-remote` 从 `env` 替换，Riot 不展开。
3. **生效与验证。** 调 `ReloadConfig`，按返回的结果核对 4 个服务器的状态。返回「还在连接」通常是 `npx` 第一次下载包较慢，等一会儿再调一次。返回 401/403 说明 key 有误，请用户到设置 → 环境变量里更正 `FUYAO_API_KEY`，然后重跑第 2、3 步。如果 `ReloadConfig` 报配置文件不合法，必须当场修好，再调一次直到成功。
4. 安装仍失败，或用户不同意安装时，告诉用户原因，然后转用下文 9.2 的兜底数据源，不要停下不做。

## 9.2 兜底数据源：内置浏览器访问东方财富

MCP 不可用、MCP 缺某项数据，或需要和 MCP 交叉核对时，用内置浏览器（`BrowserNavigate` 打开页面，再用 `BrowserSnapshot` / `BrowserReadTab` 读取文本；只有需要看图表时才用 `BrowserScreenshot`）从东方财富取数。常用入口如下，页面结构以实际打开为准：

| 数据 | 页面 |
| --- | --- |
| 个股行情 | `https://quote.eastmoney.com/sh600519.html`（深市用 `sz`，北交所用 `bj`） |
| 财务报表、主要指标（F10） | `https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=SH600519` |
| 沪深京 A 股列表（涨跌、成交额，用于统计广度） | `https://quote.eastmoney.com/center/gridlist.html#hs_a_board` |
| 指数行情 | `https://quote.eastmoney.com/center/hszs.html` |
| 融资融券 | `https://data.eastmoney.com/rzrq/` |
| 限售解禁 | `https://data.eastmoney.com/dxf/` |
| 股东增减持 | `https://data.eastmoney.com/executive/gdzjc.html` |
| 资金流向（超大单/大单/中单/小单，用于资金身份识别的弱证据） | `https://data.eastmoney.com/zjlx/`；板块资金流 `https://data.eastmoney.com/bkzj/hy.html` |
| 公司公告 | `https://data.eastmoney.com/notices/` |
| 行业/概念板块当日涨跌、成交额（盘面复盘） | `https://quote.eastmoney.com/center/boardlist.html#industry_board`（概念板块用 `#concept_board`）；开高低需进入单个板块页 |
| 指数/个股分时 | 指数或个股行情页的分时图（如 `https://quote.eastmoney.com/zs000001.html`）；读不到分时数据时省略 `--intraday` |
| 涨停板池（按板块统计涨停家次、连板高度） | `https://quote.eastmoney.com/ztb/` |
| 龙虎榜（机构席位、游资营业部） | `https://data.eastmoney.com/stock/lhb.html` |
| 股东户数 | `https://data.eastmoney.com/gdhs/` |
| 大宗交易 | `https://data.eastmoney.com/dzjy/` |
| 机构持仓（基金、北向等） | 个股 F10「主力持仓」「股东研究」页 |
| 宽基 ETF 行情与份额（510050、510300 等） | `https://quote.eastmoney.com/sh510300.html`；份额以基金公司/交易所披露为准 |
| 中证1000、创业板指、中证2000 等对比指数 | `https://quote.eastmoney.com/center/hszs.html` |

使用兜底数据源时：

- 只读页面，不登录、不填表、不点广告或下载，遇到登录墙或验证码就停下，标为「数据缺失」，不要尝试绕过。
- 控制访问量：按需打开单页，不批量翻页爬取全市场。全市场广度这类统计需要大量页面时，先说明成本，改用抽样或只给出可得部分，并标注口径。
- 记录页面 URL 和读取时间作为来源。东方财富的「主力资金」等指标是供应商口径，按SKILL.md 第 2 节第 6 条的要求处理。
- 兜底数据和 MCP 数据冲突时，标出差异，并以交易所或公司原始披露为准。

## 9.3 通用规范

- 优先使用交易所公告、上市公司定期报告、监管机构披露及可信行情/财务数据供应商。
- 在输出的「分析日期与数据时点」里写明每项数据来自 MCP 还是东方财富兜底。
- 每个关键数值记录数据日期、单位、复权方式和来源。
- 对实时行情、资金流、估值或公告无法获取的情况，明确标注缺失；不得用旧数据冒充实时数据。
- 对不同供应商之间的冲突，指出口径差异并优先核对原始披露。
- 对新闻和公告先核验日期，避免引用过期消息解释当前行情。
