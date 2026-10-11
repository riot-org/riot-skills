# motion.js 函数手册

页面里先引入 `<script src="motion.js"></script>`，所有函数挂在全局 `M` 上。参数里的 `t` 一律是**时间（秒）**：在场景的 `render(lt, s)` 里传 `lt`，在全局 `render(t)` 里传 `t`。

## 目录
- 启动与时间轴：M.run、M.timeline
- 元素入场退场：M.enter、M.animate、M.stagger、M.cycle
- 入场预设一览
- 文字：M.split、M.typewriter、M.countUp
- 镜头：M.kenBurns、M.pushIn、M.drift、M.breathe
- 常驻元素：M.tween
- 图形：M.draw、M.ticks
- 演示交互：M.cursor、M.ripple
- 字幕：M.captions
- 视频素材：M.syncVideo
- 底层工具：M.prog、M.set、M.ease、M.lerp、M.clamp、M.after

---

## M.run({ size, timeline, render, duration })

启动。必须是页面脚本的最后一行。

- `size`：`[宽, 高]`，默认 `[1920, 1080]`。
- `timeline`：`M.timeline(...)` 的返回值，总时长从这里取。
- `render(t)`：每帧调用的函数，里面先调 `tl.render(t)`，再画常驻元素和字幕。
- `duration`：不用 timeline 时手动给总时长。

浏览器直接打开时自动循环预览：空格暂停，← → 跳 1 秒，Shift+← → 跳 0.1 秒，URL 加 `?t=12` 从第 12 秒开始。

## M.timeline(scenes, opts) → tl

```js
const tl = M.timeline([
  { id: "s-a", bars: 2, render(lt, s) { ... } },
  { id: "s-b", dur: 4.5, transition: "push-left", render(lt, s) { ... } },
], { bar: 2.45, transition: "crossfade" });
```

场景字段：
- `id`：对应 `<section id>`。
- `dur`（秒）或 `bars`（小节数，需要 `opts.bar`）。
- `transition`：进入本场景的转场，不写用 `opts.transition`，再不写用 `crossfade`。见 transitions.md。
- `render(lt, s)`：`lt` 是场景内时间（0 = 分界点）；`s = { dur, inStart, outStart, start }`。

返回值：
- `tl.render(t)`：在总 render 里调用。
- `tl.duration`：总时长。
- `tl.at("s-b")`：场景 s-b 的分界点（全局秒数），用来安排字幕、常驻元素、配乐。
- `tl.current(t)`：t 时刻主要在哪个场景（返回 id）。

场景太短（扣掉两头转场后不足 0.8 秒）时，控制台会给出警告。

## M.enter(el, t, at, preset = "rise", opts = {})

在 `at` 秒开始入场。`at` 之前元素隐藏。返回入场进度（0–1）。

```js
M.enter($("#title"), lt, 0.3, "slam");
M.enter($("#title"), lt, 0.3, "rise", { dist: 80, dur: 0.9 });
M.enter($("#box"), lt, s.inStart, "none");            // 从转场开始就显示，不做动画
M.enter($("#c"), lt, 0.2, "rise", { extra: { yp: -50 } }); // 保留元素原本的 translateY(-50%)
```

`opts`：`dur` 时长、`ease` 缓动、`dist` 位移距离、`out` 退场时刻、`outPreset`、`outDur`、`outEase`、`extra` 叠加状态。

## M.animate(el, t, { at, preset, dur, ease, dist, out, outPreset, outDur, outEase, extra })

`M.enter` 的完整形式。要同时写入场和退场时用它：

```js
M.animate(el, lt, { at: 0.2, preset: "rise", out: 3.0, outPreset: "fade", outDur: 0.4 });
```

- 不写 `at`：一直显示（只应用 `extra`）。
- 不写 `out`：不退场，场景转场时整体带走（**大多数情况就该这样**）。
- 退场默认把入场倒放，方向继续前进：`rise` 退场往上走，`left` 退场继续往左走。

## M.stagger(els, t, at, gap = 0.09, opts = {})

一组元素依次入场，第 i 个在 `at + i * gap` 开始。`els` 可以是数组、NodeList 或选择器字符串。

```js
M.stagger($$(".chip"), lt, 1.0, 0.1, { preset: "pop" });
M.stagger(".feature", lt, 0.5, 0.12, { preset: "rise", dist: 30 });
```

`gap` 取值：小元素（标签、字）0.05–0.08；中等（卡片、行）0.1–0.14；大块 0.15–0.2。总错峰时长不超过 0.6 秒。

## M.cycle(items, t, start, step, opts = {}) → 当前序号

同一位置轮换多组内容（功能轮播、步骤、照片）。

```js
// 每组是 [编号, 标题, 说明] 三个元素，组内错峰 0.07s
const groups = $$(".item").map((it) => [...it.children]);
M.cycle(groups, lt, s.inStart, 2.45, { preset: "rise" });
M.cycle($$(".pic"), lt, s.inStart - 0.1, 2.45, { preset: "scale", outPreset: "fade", outDur: 0.4 });
```

`opts`：`preset` 入场（默认 rise）、`outPreset` 退场（默认同入场）、`outDur`（0.35）、`gap` 组内错峰（0.07）、`dist`、`dur`、`outLast`（最后一组也退场，默认否）。

## 入场预设一览

| 预设 | 效果 | 默认时长 / 缓动 | 用在 |
|---|---|---|---|
| `none` | 到时刻直接出现 | — | 跟随 B 类转场进来的主体 |
| `fade` | 淡入 | 0.5s / out | 次要信息、网址、注释 |
| `rise` | 从下 48px 浮上来 + 去模糊 | 0.7s / out | **默认**：标题、正文、列表 |
| `drop` | 从上往下落 | 0.7s / out | 顶部标签 |
| `left` | 从右侧 80px 滑入 | 0.7s / out | 右侧栏、时间线上的下一项 |
| `right` | 从左侧 80px 滑入 | 0.7s / out | 左侧栏 |
| `scale` | 0.9 → 1 淡入 | 0.6s / out | 图片、卡片 |
| `pop` | 0.6 → 1 带回弹 | 0.6s / back | Logo、标签、按钮、图标、数据卡 |
| `slam` | 1.25 → 1 + 去模糊 | 0.9s / out | 产品名、金句等超大字（每片 1–3 次） |
| `blur` | 从模糊变清晰 | 0.8s / out | 副标题、柔和情绪 |
| `wipe` | 从左往右擦出 | 0.8s / inOut | 标题、横线、图片 |
| `wipeUp` | 从下往上擦出 | 0.8s / inOut | 柱子、竖条 |
| `tilt` | 3D 翻起（28° → 0，从下 320px） | 1.3s / out | 截图、窗口、大卡片 |

## M.split(el, mode = "char") → 元素数组

把文字拆成单个的 `<span>`，配合 `M.stagger` 做逐字/逐词入场。可以重复调用（只拆一次）。中文用 `"char"`，英文用 `"word"`。

```js
M.stagger(M.split($("#quote")), lt, 0.15, 0.06, { preset: "rise", dist: 30 });
```

逐字间隔：中文 0.04–0.07s，英文单词 0.08–0.12s。一句话的总错峰不超过 1.2 秒。

## M.typewriter(el, text, t, at, cps = 16, caret = true)

打字机效果。`cps` 每秒字数：代码、命令 18–24，正文 12–16。`caret` 显示闪烁光标。

## M.countUp(el, t, at, dur, from, to, opts)

数字滚动。`opts`：`decimals` 小数位、`prefix`、`suffix`（如 "%"、"×"）、`sep: false` 不加千分位、`ease`。时长 0.8–1.5 秒。

## M.kenBurns(el, t, dur, { from = 1, to = 1.08, x = [-1.5, 1.5], y = [0, 0], origin })

在 `0..dur` 内匀速缓慢放大并平移（x、y 是百分比）。图片、背景用。

- `t` 传「这张图开始显示以来的时间」，例如 `lt - s.inStart`。
- 相邻两张图把 `x` 反过来（`[1.5, -1.5]`），不要都往一个方向走。
- **必须作用在内层元素上**；外层元素负责入场，否则两者会互相覆盖。
- 放大幅度：3–8%。超过 10% 会让人晕。

## M.pushIn(el, t, at, dur, { to = 1.4, from = 1, origin = "50% 50%", ease = "inOut" })

推镜头：从全貌推到细节。`origin` 设在要看的区域（例如对话框在左上，就写 `"35% 25%"`）。同样作用在内层元素上。推近倍数：1.3–1.6。

## M.drift(t, amp = 6, speed = 0.25, seed = 0) → 状态

返回一个缓慢漂移的位移，放进 `extra` 叠加：`M.enter(el, lt, 0.2, "rise", { extra: M.drift(lt, 8) })`。多个元素用不同 `seed`，不要同步漂。

## M.breathe(t, speed = 0.22, seed = 0) → 0..1

缓慢起伏的值，用于光晕、背景亮度：`M.set(glow, { o: 0.6 + 0.4 * M.breathe(lt) })`。

## M.tween(el, t, at, dur, from, to, ease = "inOut")

在两个状态之间补间，用于跨场景的常驻元素（见 transitions.md「共享元素」）。状态字段同 `M.set`。

## M.draw(el, t, at, dur, ease = "inOut")

SVG 描边生长。`el` 是带 stroke 的 `<path>`、`<line>`、`<circle>` 等。用于折线图、图标、签名、Logo 描边。

## M.ticks(container, n, t, start, step)

进度条：在 container 里生成 n 格，每格在 `start + i*step` 到 `start + (i+1)*step` 间填满。配合 `M.cycle` 用，`start`、`step` 和 cycle 保持一致。

## M.cursor(el, t, keys, clicks = []) → { x, y }

假光标。`el` 用一个箭头 SVG，CSS 设 `position:absolute; left:0; top:0; width:44px`。

- `keys`：`[[时刻, x, y], ...]` 光标依次到达的位置（舞台像素坐标，指尖位置）。
- `clicks`：点击时刻数组。点击时光标缩小 0.16 秒。
- 第一个关键帧前 0.3 秒淡入。

移动规则：每段移动 0.8–1.4 秒；到达目标后停 0.2–0.4 秒再点击；点击后 0.2–0.3 秒界面给反馈。

## M.ripple(el, t, at)

点击涟漪。`el` 是一个圆（`border-radius:50%; border:3px solid #fff; width:80px; height:80px; position:absolute`），把它的 `left/top` 设在点击点，函数会自动居中。

## M.captions(box, t, list)

字幕。`list = [[开始, 结束, "文本"], ...]`。在总 `render(t)` 里调用，传全局 `t`。时间可以用 `tl.at("s-xxx") + 0.4` 来写，场景时长改了也不会错位。

## M.syncVideo(v, localTime)

把 `<video>` 定到第 `localTime` 秒。渲染时逐帧精确 seek；预览时自然播放。

```html
<video id="clip" class="media" src="clip.mp4" muted playsinline preload="auto"></video>
```
```js
M.syncVideo($("#clip"), lt - s.inStart);   // 场景一开始就从素材第 0 秒播
M.syncVideo($("#clip"), (lt - s.inStart) * 0.5); // 半速
```

素材先用 ffmpeg 转成 H.264 MP4 或 VP9 WebM；渲染用 Google Chrome（Chromium 不支持 H.264）。

## 底层工具

- `M.prog(t, at, dur, ease = "out")`：t 在 `[at, at+dur]` 内 0→1 的进度（已缓动）。自己写特殊动画时用。
- `M.set(el, state)`：直接设置状态。字段：`o` 透明度、`x/y` 像素位移、`xp/yp` 百分比位移、`s` 缩放、`sx/sy`、`r` 旋转、`rx/ry` 3D 旋转、`persp` 透视、`blur`、`bright` 亮度、`clip` 裁切、`origin` 变换原点。**会覆盖元素整个 transform/filter/clip-path。**
- `M.ease`：`linear`、`in`、`out`、`inOut`、`outQuint`、`back`。
- `M.lerp(a, b, k)`、`M.clamp(v, a, b)`、`M.after(t, at)`。

自己写动画的模板：

```js
const k = M.prog(lt, 1.2, 0.8, "inOut");      // 1.2s 开始，0.8s 完成
M.set(el, { o: k, x: M.lerp(-200, 0, k) });   // 从左边 200px 移到原位
```
