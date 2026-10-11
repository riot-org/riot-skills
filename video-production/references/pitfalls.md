# 踩过的坑

## 画面

- **场景切换覆盖了 flex 布局**：用 `display = on ? "block" : "none"` 控制场景显隐，会把 `display:flex` 的居中布局冲掉，内容挤到左上角。显示时写 `""`，让样式表决定。`M.timeline` 已经这样处理。
- **CSS animation / transition 不能用**：它们按真实时间跑，逐帧 seek 截不到正确状态。所有运动都在 `render(t)` 里由 t 算。GIF、Lottie、`<video>` 自动播放同理，要么手动按 t 控制，要么别用。
- **随机数会闪**：`Math.random()` 每帧都不一样。用带种子的伪随机，或者预先生成好存起来。
- **字体和图片没加载完就截图**：渲染前要等 `window.__ready`（`M.run` 会等 `document.fonts.ready`、所有 `<img>` 和 `<video>` 的元数据）。
- **`<video>` 帧同步**：渲染时视频必须暂停，每帧设 `currentTime` 并等 `seeked` 事件；目标时间和当前时间相同时 `seeked` 不会触发，要先判断。`M.syncVideo` 已经处理。Chromium 不支持 H.264，用 Google Chrome 渲染，或者先把素材转成 VP9 WebM。
- **中文字体回落**：Geist、Inter 这类西文字体没有中文字形，会回落到 PingFang SC。粗细 800/900 在 PingFang 里会显得细一些；行高也不同，胶囊标签里中英混排要设 `line-height: 1.2` 才对齐。
- **file:// 读本地素材**：渲染器启动 Chrome 时带了 `--allow-file-access-from-files`，相对路径（如 `../assets/x.png`）才能读到。
- **`filter: blur()` 和大面积阴影很慢**：全屏模糊会让渲染速度降好几倍。模糊只给小元素，或者只在入场的几帧里用（`M.set` 在模糊接近 0 时自动去掉）。
- **转场时新场景是空的**：push、slideOver、wipe、iris 会把整个新场景搬进来，元素等到分界点之后才入场，观众就会看到一块空背景滑进来。主体要从 `s.inStart` 起就显示。详见 transitions.md。
- **深浅场景 crossfade 发灰**：深色和浅色半透明叠加是一片脏灰。深浅切换用 `fadeThrough`。
- **缩放入场露边**：新场景从小于 1 的缩放放大进来时，四周会露出底下的旧场景。缩放入场要从大于 1 缩回 1。
- **元素被动画后跳位**：motion.js 会覆盖元素整个 transform。原本靠 `translateY(-50%)` 居中的元素，要改用 flex 居中，或者在 `extra` 里补 `{ yp: -50 }`。
- **两个函数控制同一个元素**：后调用的会覆盖先调用的，表现为入场动画不见了或推镜头不动。套两层元素，各管一个。
- **字幕手写 `<br>`**：照「一行最多十几个字」的习惯在字幕文本里插 `<br>`，结果 1920 宽画面上一行放得下的句子也被拆成两行，左右大片空着。字幕换行交给 CSS（`max-width` + `text-wrap: balance`，见模板 `#captions`），文本里不写断行。
- **截图要用高清素材**：1080p 画面里放大 1.5 倍的截图，原图至少要 2 倍分辨率；能用 SVG 就用 SVG。

## 依赖

- **ffmpeg-static 安装超时**：它在 postinstall 时从 GitHub 下载二进制，国内网络常超时，镜像可能 404。改装 `@ffmpeg-installer/<平台>-<架构>`，二进制就在 npm 包里，走 npm registry。`setup.sh` 已经这样处理；系统里有带 libx264 的 ffmpeg 就直接用系统的。
- **输出放不了**：没加 `-pix_fmt yuv420p` 时，部分播放器（QuickTime、微信、浏览器）打不开；没加 `-movflags +faststart` 时，网页要下载完才能播。

## 音频

- **手写 WAV 头漏了 `data` 标签**：`RIFF`、`WAVEfmt `、`data` 三处都要写，漏了 ffmpeg 会报 `no 'data' tag found`。
- **bandpass 默认按 Q 值算带宽**：`bandpass=f=500:w=600` 是 Q=600 的极窄带，测出 -60 dB 会误以为中频没声。测倍频程写 `width_type=o:w=1`。
- **一个大音量的鼓压扁整首歌**：按峰值归一化时，底鼓和冲击音决定峰值，其余声部被相对压低。先看各总线 RMS（鼓和乐器相差 3 dB 以内比较健康），再看频段斜率。
- **`-shortest` 和淡出**：音乐比视频长时 `-shortest` 会硬切，结尾要提前淡出，或者按视频时长生成音乐。
