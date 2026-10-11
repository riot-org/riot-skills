---
name: video-production
description: 用代码做视频的完整方法：定目标、写分镜、动效与转场、配乐卡点、旁白字幕、渲染质检。画面用 HTML 时间轴动画逐帧渲染，或用 ffmpeg 剪辑已有素材；配乐可代码合成。宣传片、产品介绍、演示教程、数据动画、竖屏短视频、照片回顾、片头 Logo、文字动画、GIF，以及剪辑拼接、加字幕配乐、改比例、压缩视频都用它；用户只说「做个视频」「剪一下」「弄成动图」也算。
---

# 视频制作

这份 skill 是一套**按步骤执行就能做出好视频**的方法。每一步都有明确的产出和检查方式。不要跳步，尤其不要跳过第 6 步的转场检查——转场和过渡是最容易做坏、也最影响观感的地方。

## 原理（先读懂这一段）

视频 = 一个以时间 t 为输入的网页。页面上的每个元素在时刻 t 长什么样，完全由 t 算出来。渲染器把 t 从 0 走到结尾，每 1/30 秒截一张图，交给 ffmpeg 合成 MP4。

所以：
- **不能用 CSS animation / transition、`setTimeout`、`Math.random()`**，它们和 t 无关，逐帧截图时会乱。所有动画都用 `assets/motion.js` 里的函数，它们都以 t 为输入。
- 任何一秒都能单独截出来检查，改完重渲一次即可。

## 文件

| 文件 | 是什么 | 什么时候读 |
|---|---|---|
| `scripts/setup.sh` | 安装依赖到 `~/.cache/video-production` | 第一次用时运行 |
| `scripts/new.sh <目录>` | 新建视频工程：`video.html`（模板）、`motion.js`、`cues.json`（和模板对应的配乐编排）、两份风格示例 | 第 4 步 |
| `assets/template.html` | **完整可运行的示例**：7 个场景、6 种转场、所有常用动画。新视频在它上面改 | 第 4 步前**必须完整读一遍** |
| `assets/motion.js` | 动画与转场函数库 | 一般不用改 |
| `scripts/render.cjs` | 渲染：`--check` 转场对照图、`--stills` 静帧、`--timeline` 时间表、默认出 MP4 | 第 6、8 步 |
| `scripts/music.cjs` | 按配置合成配乐 | 第 7 步 |
| `references/motion-api.md` | motion.js 每个函数的参数和例子 | 写动画时查 |
| `references/transitions.md` | **转场手册**：怎么选、每种转场里元素该什么时候进场、常见错误 | 第 3、5 步**必读** |
| `references/motion-design.md` | 时长、缓动、错峰、排版、配色、安全区的具体数值 | 第 5 步 |
| `references/formats.md` | 各类视频的结构模板和推荐转场 | 第 3 步 |
| `references/checklist.md` | 逐项检查清单 | 第 6、8 步**必读** |
| `references/audio.md` | 配乐、卡点、旁白、字幕、响度 | 第 7 步 |
| `references/ffmpeg-recipes.md` | 剪辑已有素材、转码、各平台导出参数 | 需要时 |
| `references/pitfalls.md` | 踩过的坑 | 出现奇怪现象时 |

下面命令里的 `${SKILL_DIR}` 是本 skill 目录的绝对路径，Riot 加载时已经替换好。这个路径里有空格，所以命令里一律用引号把它括起来，别去掉引号。

## 第 1 步：确认需求

弄清下面四件事。能从上下文推断就不问，推断不出再问用户：

1. **在哪播** → 决定尺寸和时长（见 `references/formats.md` 和 `ffmpeg-recipes.md` 的平台表）。不确定就做 1920×1080、30–45 秒。
2. **核心信息**：观众看完要记住的那一句话。写下来，后面每个场景都要为它服务。
3. **素材**：Logo、品牌色、字体、截图、照片、录屏、文案。去项目里找（官网源码、README、assets 目录、CSS 变量）。**视频里的事实必须来自这些素材，不要编造功能和数字。**
4. **结尾要观众做什么**：访问网址、下载、关注。

## 第 2 步：选路线

- 只有文字、截图、图表、界面 → **HTML 时间轴**（第 3–8 步）。
- 只是剪辑已有视频（切、拼、加字幕、加音乐、转比例）→ 直接用 `references/ffmpeg-recipes.md`，不用写 HTML。
- 已有素材 + 需要动态文字和包装 → 素材放进 HTML 时间轴（`<video>` 用 `M.syncVideo`，图片用 `M.kenBurns`）。

## 第 3 步：写分镜表（写代码之前）

按 `references/formats.md` 中对应类型的结构，写出这张表，**每一列都要填**：

| # | 场景 id | 时长 | 进入转场 | 背景 | 画面内容 | 文字（逐字写出） | 元素入场顺序 |
|---|---|---|---|---|---|---|---|
| 1 | s-title | 4.9s | — | 深 | Logo + 产品名 | 「Product.」「一句话定位」 | 小字 0.3 → 大字 0.6 → 副标题 1.4 |
| 2 | s-window | 4.9s | fadeThrough | 浅 | 界面截图 | … | 标题 0.1 → 截图 0.3 → 2.0 起推镜头 |

填表规则：
1. **时长**：每个场景 = 入场动画时间 + 至少 1.5 秒静止阅读时间 + 转场时间。文字阅读按中文 5 字/秒、英文 3 词/秒算。多数场景 3.5–5 秒；列表类每项 2.4–2.5 秒。
2. **要配乐时，时长取同一个「小节长度」的整数倍**（例如都是 2.45 秒的 2 倍），转场就会落在强拍上。详见 audio.md。
3. **进入转场**：按 `references/transitions.md` 的选择表选。全片最多 3–4 种转场；深浅背景切换时不要用 crossfade。
4. **背景**：深、浅交替，不要连续三个场景同色。
5. **文字**：一个场景一句标题 + 最多一句说明。
6. **元素入场顺序**：从主到次，间隔 0.1–0.3 秒，全部在 1.5 秒内入场完毕。进入转场是 push / slideOver / wipe / iris 时，主体元素要从转场开始就在画面里（见 transitions.md「空场景」）。

把分镜表给用户看。用户说直接做就不用等。

## 第 4 步：建工程、读模板

```bash
bash "${SKILL_DIR}/scripts/setup.sh"          # 第一次用时
bash "${SKILL_DIR}/scripts/new.sh" video      # 在当前项目里建 video/ 目录
```

然后**完整读一遍 `video/video.html`**。它是一个能直接渲染的 37 秒示例，几乎每一种常用写法都在里面：大字砸下、3D 翻起的窗口加推镜头、数字滚动、逐字入场、左文右图轮播加进度条、光标点击演示、常驻 Logo、字幕。新视频是在这个文件上改出来的：同类场景直接复制对应的 `<section>` 和 `render` 函数，再改文字和数值。

想看效果就用浏览器打开 `video/video.html`：空格暂停，← → 跳 1 秒，地址加 `?t=12` 从第 12 秒开始。

## 第 5 步：写场景

### 5.1 HTML

- 每个场景是 `#stage` 下的一个 `<section id="s-xxx" class="dark|light ...">`。场景的背景写在 section 上（class `dark` / `light` / `light-2`）。
- 需要动画的元素都给 id 或 class。
- 一直存在的元素（角落 Logo、字幕框）放在所有 section 之后。
- 图片放进项目目录，用相对路径。截图要用 2 倍分辨率的图。
- **不要给 section 本身写动画**：section 的位置、透明度由转场控制。

### 5.2 时间轴

```js
const tl = M.timeline([
  { id: "s-title", bars: 2, render(lt, s) { ... } },
  { id: "s-window", bars: 2, transition: "fadeThrough", render(lt, s) { ... } },
], { bar: 2.45 });
```

- `bars: 2` 表示占 2 小节；不配乐也可以直接写 `dur: 4.5`（秒）。
- `transition` 是**进入这个场景**的转场。写法见 transitions.md。
- `render(lt, s)` 里的 `lt` 是**场景内时间**：`lt = 0` 是这个场景的分界点（转场正中间）。`s.inStart` 是进入转场开始的时刻（负数），`s.outStart` 是离开转场开始的时刻，`s.dur` 是场景时长。

### 5.3 动画写法（详细参数见 motion-api.md）

```js
M.enter(el, lt, 0.3, "rise");                         // 0.3 秒时从下往上浮现
M.enter(el, lt, 0.6, "slam");                         // 大标题砸下来
M.stagger($$(".chip"), lt, 1.0, 0.1, { preset: "pop" }); // 一组依次弹出，间隔 0.1 秒
M.enter(el, lt, s.inStart, "none");                   // 从转场一开始就在（push/wipe 等转场的主体用）
M.countUp(el, lt, 0.5, 1.3, 0, 12800);                // 数字滚动
M.kenBurns(img, lt - s.inStart, s.dur);               // 图片缓慢推拉
M.cycle(groups, lt, s.inStart, step, { preset: "rise" }); // 同一位置轮换多组内容
```

必须遵守的规则：
1. **一个元素在一帧里只交给一个函数**。要「入场 + 推拉」就套两层：外层 `M.enter`，内层 `M.kenBurns`。
2. **元素原本的 CSS transform 会被覆盖**。如果靠 `transform: translateY(-50%)` 居中，要么改用 flex 居中，要么写 `M.enter(el, lt, at, "rise", { extra: { yp: -50 } })`。
3. 场景的最后一个元素要在 `s.outStart - 1.0` 之前入场完毕，留出至少 1 秒静止时间让人看清。
4. 不写退场动画：离开场景时由转场整体带走。只有同一场景内轮换内容时才写退场（`M.cycle` 会自动处理）。
5. 每个静止超过 2 秒的场景都要有一个慢速运动：背景光晕呼吸（`M.breathe`）、图片推拉（`M.kenBurns`）、截图推镜头（`M.pushIn`），否则画面会「死」。

### 5.4 启动

最后一行保持：`M.run({ size: [1920, 1080], timeline: tl, render });`。竖屏改成 `[1080, 1920]`，并重新排版（左右分栏改上下堆叠），不能只改尺寸。

## 第 6 步：检查（每改一轮都要做）

```bash
node "${SKILL_DIR}/scripts/render.cjs" video/video.html --check
```

生成 `video/check.png`，上半部分是每个场景的静止帧，下半部分是每个转场 0% / 25% / 50% / 75% / 100% 五帧。**用 Read 工具打开它，对照 `references/checklist.md` 逐项检查**。最常见的问题：
- 转场 75% 那一帧是空背景 → 新场景的主体入场太晚，改成从 `s.inStart` 开始（transitions.md「空场景」）。
- 静止帧里元素还是半透明或模糊 → 入场太晚，或者场景太短。
- 深浅切换的 50% 帧是一片灰 → 换掉 crossfade。
- 文字溢出、被裁、和别的元素重叠 → 改 CSS。

要看某几秒的大图：`--stills 3.2,7,12.5`（输出到 `video/stills/`）。

**发现问题就改，改完重新 `--check`，直到清单全部通过。**

## 第 7 步：声音

按 `references/audio.md` 来。合成配乐的流程：

```bash
node "${SKILL_DIR}/scripts/render.cjs" video/video.html --timeline   # 打印每个场景、转场的时刻
# new.sh 已经建好 video/cues.json，它和模板的时间轴一一对应（每条都注明了对应哪个场景、哪个动作）。
# 按 --timeline 的输出改它：duration、sections 的起止、hits 的时刻。温和风格参考 cues.calm.json
node "${SKILL_DIR}/scripts/music.cjs" video/cues.json video/music.wav
```

然后按 audio.md「不靠耳朵的检查」测响度和波形。你听不到声音，交付时要如实告诉用户。

## 第 8 步：渲染与交付

```bash
node "${SKILL_DIR}/scripts/render.cjs" video/video.html --audio video/music.wav --out video/out.mp4
```

1080p30 每秒视频约需 1.5–2 秒渲染。渲染完：
1. `ffmpeg -i video/out.mp4` 确认时长、1920x1080、30 fps，以及有音频流。
2. 按 checklist.md 的「成片」部分再抽查一遍。
3. 需要其他平台版本（竖屏、GIF、压缩）时，按 ffmpeg-recipes.md 处理。
4. 把成片交给用户：回复里用 `![](video/out.mp4)` 内嵌，Riot 在对话里直接给播放器（音频 `![](music.wav)` 同理，配乐、旁白试听都这样给）；封面帧、GIF 也用 `![](路径)`。内嵌播放的文件上限 32 MB，成片更大时改给链接 `[打开 video/out.mp4](video/out.mp4)`，或另出一个压缩版（ffmpeg-recipes）内嵌。回复里写：分镜表（时间 / 画面 / 转场 / 声音）、怎么改（改哪个文件、哪条命令重渲）、你没法验证的部分（听感），以及一两个后续选项（竖屏版、短版、换配乐）。
5. 不要擅自提交 git。`check.png`、`stills/`、`music.wav` 是中间产物，问用户要不要保留。
