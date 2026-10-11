---
name: moss-tts
description: 要把文字转成语音时用：视频旁白、有声内容、播报、客服话术。Moss API 的 TTS，音质远好过系统 say。需要合成旁白、批量生成多句语音、挑选音色、控制停顿时加载。
---

# Moss 语音合成

文字转语音。做视频旁白时和 `video-production` 技能配合用：这个技能负责出人声，
那边负责画面、配乐和混音。

## 先查 API Key

Key 放环境变量，**不要写进代码或提交到仓库**。没配先让用户去
<https://platform.mosi.cn/app/api-keys/> 建一个。

```bash
export MOSS_API_KEY=...          # 写进 ~/.zshrc 才持久
test -n "$MOSS_API_KEY" && echo ok   # 用之前先确认这一条过了
```

## 接口

```
POST https://api.mosi.cn/v1/audio/speech
Authorization: Bearer $MOSS_API_KEY
Content-Type: application/json
```

三个必填参数：

| 参数 | 说明 |
|---|---|
| `model` | `moss-tts-1.5-flash` 是首选（支持停顿语法、`language`、流式）。另有 `moss-tts-1.0-pro`，**不支持停顿语法** |
| `input` | 待合成文本 |
| `voice_id` | 音色 ID，见下面「音色」一节 |

常用可选参数：

- `response_format`：`mp3`（推荐）/ `wav` / `flac` 适合后期处理；`pcm` 只在流式时用。
- `delivery_method`：**不传或 `audio` = 响应体直接是音频二进制**，`curl -o out.mp3` 存下来就行；
  `url` = 返回 JSON 带结果 URL，适合服务端异步流。
- `language`：要写**英文全称**，中文是 `"Chinese"`、英文是 `"English"`。
  写 `zh` / `en` 不认。省略则由模型自己判断——中文文本建议显式写，跨语言音色尤其要写。
- `expected_duration_sec`：期望时长（秒，> 0），需要卡节奏或对齐画面时有用。
- `async: true`：创建异步任务立即返回 `task_id`，用
  `GET /v1/audio/tasks/{task_id}` 查结果；`webhook_url` 只收终态通知。
  **`async` 不能和 `stream` 同时用。**

注意：TTS **只认 `voice_id`**，不支持 `voice_url` / `voice_data`、内联音频或参考音频。

## 停顿：控制节奏的主要手段

只有 `moss-tts-1.5-flash` 支持，范围 `[pause 0.1s]` 到 `[pause 10.0s]`。

旁白节奏靠它，别用逗号或省略号去凑——那只会让语气变怪。写脚本时按语义断：

```json
{ "input": "先在海量文本上预训练。[pause 0.5s]再用指令微调，学会听懂你的要求。",
  "voice_id": "133bd03b-d717-4a55-8974-7ffc9afc1b51",
  "language": "Chinese", "response_format": "mp3" }
```

## 音色

15 个开箱音色，`voice_id` 直接可用。**旁白类**（做视频优先在这几个里挑）：

| 音色 | voice_id | 感觉 | 语言 |
|---|---|---|---|
| 故宫纪录片 | `133bd03b-d717-4a55-8974-7ffc9afc1b51` | 沉稳、磁性、专业 | 中文 |
| 历史解说男声 | `0804710c-8e5e-4b67-acda-5785ef13c309` | 沉稳、磁性 | 中文 |
| 诗词朗读 | `2fdf194e-c16e-4587-9027-0d3464e09b4e` | 沉稳、磁性、专业 | 中文 |
| 三农农业旁白 | `944eb93b-3820-49f3-b2c0-4e37a31d1161` | 轻快、磁性、专业 | 中文 |
| 少年感人声（男） | `fe85a513-9bf3-4ef7-aa0b-8b2d11e4db93` | 温柔、磁性、自然 | 中文 |
| 旁白Jake | `f9a1416b-d006-4b77-9581-8f0e8ec1e401` | 沉稳、磁性、专业 | 英文·英式 |

其他（对话、角色、娱乐向）：

| 音色 | voice_id | 感觉 | 语言 |
|---|---|---|---|
| 明太祖 | `f80b6698-0066-430b-88a0-f0fb8796db34` | 高冷、沉稳、霸总 | 中文 |
| 李白 | `7662a8a1-700c-466a-b66b-57ece9e2e231` | 古风、热血 | 中文 |
| 经验女教师 | `faf7f550-0627-4fc6-8db0-d3bfdad49358` | 高冷、自然 | 中文 |
| 轻快灵动女声 | `806c9695-6160-404e-8722-4f788d935af3` | 轻快、活泼 | 中文 |
| 忧伤的秋 | `19411508-8731-4b68-901d-7e4b8a98e23f` | 温柔、慵懒 | 中文 |
| 曼波有口音版 | `c6c0a40a-ea82-4468-9a21-333d3c4a76f6` | 轻快、可爱、搞笑 | 中文 |
| 东北虎哥 | `26838557-6890-4505-bc7c-e8198443a141` | 搞笑、慵懒 | 中文 |
| VOX AKUMA | `ddc6e38b-6f55-4415-b21b-a88cad2cc1d9` | 慵懒、磁性、专业 | 英文·英式 |
| 优雅英国女士 | `9d1e88e9-3b9c-4992-a414-7a1cb3ff7ab5` | 温柔、磁性、自然 | 英文·英式 |

上面的 ID 是某次查到的快照，**用前先查一次确认还有效**（也可能用户账号里没开这些）：

```bash
curl -s "https://api.mosi.cn/v1/audio/voices?limit=150" \
  -H "Authorization: Bearer $MOSS_API_KEY" | python3 -m json.tool
```

返回 `{object, data[], has_more, first_id, last_id, next_cursor}`，
每个元素是 `{id, object: "audio.voice", name, created_at}`。分页用 `limit` / `offset`
（默认 20，上限 150）或 `after=<上一页 next_cursor>`。

更多音色见 <https://mossland.studio/voice/library>（卡片上复制图标可取 ID）。
要克隆自己的音色用创建音色接口（`multipart` 传音频样本）。

## 批量合成旁白

`scripts/synthesize.py` 做这件事：逐句合成、打印时长表、支持跳过已生成的。

```bash
python3 "${SKILL_DIR}/scripts/synthesize.py" lines.txt \
  --voice 133bd03b-d717-4a55-8974-7ffc9afc1b51 \
  --language Chinese --outdir vo --pause 0.4
```

`lines.txt` 一行一句（空行和 `#` 开头跳过），输出 `vo/01.mp3`、`vo/02.mp3`…，
并打印每句时长和累计时间轴。

**为什么逐句合成而不是整篇一次**：做视频必须知道每句在时间轴上的起点，
逐句才有独立时长；某句念错也能只重生成那一句。代价是句子之间的语气不连贯——
所以用 `--pause` 在句尾补停顿，或在句子里用 `[pause Xs]` 手动调。

## 验证（别跳过）

**你听不到声音**，只能用测量代替耳朵，并且交付时要如实告诉用户这一点。

```bash
# 每句时长（macOS 自带）
afinfo vo/01.mp3 | awk '/estimated duration/ {print $3}'
# 响度与峰值
ffmpeg -hide_banner -nostats -i vo/01.mp3 -af ebur128=peak=true -f null - 2>&1 | tail -6
```

要查的：时长合理（中文约 4–5 字/秒，明显偏离说明文本或停顿写错了）、
没有削波、各句响度一致。听感、语气、多音字读法**必须让用户自己确认**。

## 错误码

| HTTP | code | 原因 | 怎么办 |
|---|---|---|---|
| 404 | `voice_not_found` | `voice_id` 不存在或不可用 | 查音色列表，换 ID |
| 400 | `unsupported_stream` | 模型不支持流式 | 用 `moss-tts-1.5-flash` |
| 400 | `unsupported_for_stream` | 流式请求带了不支持的字段 | 去掉 `sample_rate`、`delivery_method`、`file_id` |
| 400 | `unsupported_with_async` | `stream` 和 `async` 同时传 | 去掉 `async` |
| 400 | `unsupported_with_webhook` | 流式还传了 `webhook_url` | 去掉 `webhook_url` |

401/403 一般是 Key 没配或失效，先回「先查 API Key」那节。

## 连不上时先怀疑本地代理

报 **TLS 握手错误**（`WRONG_VERSION_NUMBER`、`tlsv1 alert protocol version`、`SSL routines:ST_CONNECT`），
而且 curl 和 Python 两种 TLS 栈结果一样时 —— **这不是 Key 的问题**，是本机代理把
`api.mosi.cn` 的路由带偏了。踩过：Clash Verge 开 TUN 模式 + DNS 用 fake-IP 时，
域名被映射到 `198.18.x.x` 的假地址，握手直接失败（同机 baidu/apple 正常，节点本身是通的）。

三步确认（都不要动用户的代理配置，改由用户自己决定）：

```bash
# 1) 解析到 198.18.0.0/15 假地址，且换公共 DNS 结果一样 → 本地代理在劫持 DNS
dscacheutil -q host -a name api.mosi.cn

# 2) 用 DoH 查真实地址（系统 DNS 已被劫持，查不到真的）
curl -s "https://223.5.5.5/resolve?name=api.mosi.cn&type=A"

# 3) 直连真实地址。能返回 200 → Key 和接口都好，问题百分之百在代理
curl -s -o /dev/null -w "%{http_code}\n" --max-time 20 \
  --resolve api.mosi.cn:443:<真实IP> \
  "https://api.mosi.cn/v1/audio/voices?limit=1" \
  -H "Authorization: Bearer $MOSS_API_KEY"
```

解法：把代理客户端切到**「规则」模式**（国内域名直连）最省事。注意 **Global/全局模式下规则被忽略**，
在 Global 模式下加直连规则没有任何作用 —— 必须先离开 Global。

## 和视频技能配合

做视频旁白时的顺序是**先旁白、后画面**：先逐句合成拿到每句实际起点，
再按这些起点排分镜——画面跟着旁白走，不要让旁白去迁就画面。
`video-production` 技能里有排轴和混音（旁白为主、配乐压低到 −16 LUFS）的配方。
