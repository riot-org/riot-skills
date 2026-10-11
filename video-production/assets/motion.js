/*
 * motion.js —— 视频动画库
 *
 * 所有函数都是「纯」的：同样的时间 t 一定画出同样的画面，所以可以逐帧渲染、任意跳转。
 * 用法见 assets/template.html 和 references/motion-api.md。
 *
 * 铁律：一个 DOM 元素在一帧里只能交给一个函数控制（M.animate / M.kenBurns / M.tween ...）。
 *       两个函数控制同一个元素，后一个会把前一个的 transform 整个覆盖掉。
 *       需要「入场 + 镜头推拉」同时作用时，套两层：外层入场，内层推拉。
 */
(function () {
  const M = (window.M = {});
  M.RENDER = /[?&]render/.test(location.search);

  // ================= 数学与缓动 =================
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  M.clamp = clamp;
  M.lerp = lerp;
  // 接受单个元素、NodeList、数组、选择器字符串
  const toArray = (x) => (typeof x === "string" ? [...document.querySelectorAll(x)] : x instanceof Element ? [x] : [...x]);

  M.ease = {
    linear: (k) => k,
    in: (k) => k * k * k, // 加速：用于退场
    out: (k) => 1 - Math.pow(1 - k, 3), // 减速：默认，用于入场
    inOut: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2), // 两头慢：移动、转场、镜头
    outQuint: (k) => 1 - Math.pow(1 - k, 5), // 更急的减速：大元素快速到位
    back: (k) => 1 + 2.5 * Math.pow(k - 1, 3) + 1.5 * Math.pow(k - 1, 2), // 轻微过冲回弹：弹出
  };
  const easeFn = (e) => (typeof e === "function" ? e : M.ease[e] || M.ease.out);

  // t 在 [at, at+dur] 内从 0 走到 1（已缓动）；之前是 0，之后是 1
  M.prog = (t, at, dur, ease = "out") => easeFn(ease)(clamp((t - at) / Math.max(dur, 1e-6)));
  // 是否已经过了某个时刻
  M.after = (t, at) => t >= at;

  // ================= 状态 → 样式 =================
  // 状态字段：o 透明度, x/y 像素位移, xp/yp 百分比位移, s 缩放, sx/sy, r 旋转, rx/ry 3D 旋转,
  //          persp 透视, blur 模糊, bright 亮度, clip 裁切, origin 变换原点
  function apply(el, st) {
    if (!el) return;
    const s = el.style;
    s.opacity = st.o ?? 1;
    let tf = "";
    if (st.persp) tf += `perspective(${st.persp}px) `;
    if (st.xp || st.yp) tf += `translate(${st.xp || 0}%, ${st.yp || 0}%) `;
    tf += `translate(${st.x || 0}px, ${st.y || 0}px)`;
    if (st.rx) tf += ` rotateX(${st.rx}deg)`;
    if (st.ry) tf += ` rotateY(${st.ry}deg)`;
    if (st.r) tf += ` rotate(${st.r}deg)`;
    const sc = st.s ?? 1;
    tf += ` scale(${sc * (st.sx ?? 1)}, ${sc * (st.sy ?? 1)})`;
    s.transform = tf;
    const f = [];
    if (st.blur > 0.05) f.push(`blur(${st.blur.toFixed(2)}px)`);
    if (st.bright != null && Math.abs(st.bright - 1) > 0.001) f.push(`brightness(${st.bright})`);
    s.filter = f.length ? f.join(" ") : "none";
    s.clipPath = st.clip || "none";
    if (st.origin) s.transformOrigin = st.origin;
  }
  function combine(a, b) {
    return {
      ...a,
      ...b,
      o: (a.o ?? 1) * (b.o ?? 1),
      x: (a.x || 0) + (b.x || 0),
      y: (a.y || 0) + (b.y || 0),
      xp: (a.xp || 0) + (b.xp || 0),
      yp: (a.yp || 0) + (b.yp || 0),
      s: (a.s ?? 1) * (b.s ?? 1),
      r: (a.r || 0) + (b.r || 0),
      rx: (a.rx || 0) + (b.rx || 0),
      ry: (a.ry || 0) + (b.ry || 0),
      blur: (a.blur || 0) + (b.blur || 0),
      bright: (a.bright ?? 1) * (b.bright ?? 1),
      clip: b.clip && b.clip !== "none" ? b.clip : a.clip,
      persp: a.persp || b.persp,
      origin: b.origin || a.origin,
    };
  }
  M.set = apply;
  M.combine = combine;

  // ================= 元素入场 / 退场预设 =================
  // 每个预设：k=0 完全隐藏，k=1 完全到位。[默认时长, 默认缓动]
  const PRESET = {
    none: () => ({}), // 不做动画，直接显示（配合 at 使用时：at 之前隐藏）
    fade: (k) => ({ o: k }),
    rise: (k, o) => ({ o: k, y: (1 - k) * (o.dist ?? 48), blur: (1 - k) * 8 }), // 从下往上浮现
    drop: (k, o) => ({ o: k, y: -(1 - k) * (o.dist ?? 48), blur: (1 - k) * 8 }), // 从上往下落
    left: (k, o) => ({ o: k, x: (1 - k) * (o.dist ?? 80), blur: (1 - k) * 6 }), // 从右侧滑入（向左运动）
    right: (k, o) => ({ o: k, x: -(1 - k) * (o.dist ?? 80), blur: (1 - k) * 6 }), // 从左侧滑入（向右运动）
    scale: (k) => ({ o: k, s: lerp(0.9, 1, k) }), // 轻微放大淡入
    pop: (k) => ({ o: clamp(k * 1.6), s: lerp(0.6, 1, k) }), // 弹出（配 back 缓动有回弹）
    slam: (k) => ({ o: clamp(k * 1.4), s: lerp(1.25, 1, k), blur: (1 - k) * 14 }), // 大字从大缩小「砸」下来
    blur: (k) => ({ o: k, blur: (1 - k) * 20 }), // 从模糊变清晰
    wipe: (k) => (k >= 1 ? {} : { clip: `inset(-5% ${(1 - k) * 105}% -5% -5%)` }), // 从左往右擦出
    wipeUp: (k) => (k >= 1 ? {} : { clip: `inset(${(1 - k) * 105}% -5% -5% -5%)` }), // 从下往上擦出
    tilt: (k, o) => ({ o: clamp(k * 1.5), persp: 2400, y: (1 - k) * (o.dist ?? 320), rx: (1 - k) * 28, s: lerp(0.92, 1, k) }), // 3D 翻起
  };
  const PRESET_DEF = {
    none: [0.001, "linear"],
    fade: [0.5, "out"],
    rise: [0.7, "out"],
    drop: [0.7, "out"],
    left: [0.7, "out"],
    right: [0.7, "out"],
    scale: [0.6, "out"],
    pop: [0.6, "back"],
    slam: [0.9, "out"],
    blur: [0.8, "out"],
    wipe: [0.8, "inOut"],
    wipeUp: [0.8, "inOut"],
    tilt: [1.3, "out"],
  };
  // 退场：默认把入场倒放，方向继续往前走（rise 入场是往上，退场也往上走）
  const OUT_SPECIAL = {
    wipe: (k) => ({ clip: `inset(-5% -5% -5% ${k * 105}%)` }),
    wipeUp: (k) => ({ clip: `inset(-5% -5% ${k * 105}% -5%)` }),
  };
  function outState(name, k, o) {
    if (OUT_SPECIAL[name]) return OUT_SPECIAL[name](k, o);
    const st = (PRESET[name] || PRESET.fade)(1 - k, o);
    return { ...st, x: -(st.x || 0), y: -(st.y || 0) };
  }
  M.PRESETS = Object.keys(PRESET);

  /*
   * M.animate(el, t, {
   *   at,            入场开始时刻（不写 = 一直可见）
   *   preset,        入场预设，默认 "rise"
   *   dur, ease,     入场时长/缓动，不写用预设默认值
   *   dist,          位移距离（rise/drop/left/right/tilt）
   *   out,           退场开始时刻（不写 = 不退场，交给转场带走）
   *   outPreset,     退场预设，默认 "fade"
   *   outDur, outEase 退场时长（默认 0.4）/缓动（默认 "in"）
   *   extra,         额外叠加的状态，比如 M.drift(t) 的结果
   * })  返回入场进度 0..1
   */
  M.animate = function (el, t, o = {}) {
    const name = o.preset || "rise";
    if (!PRESET[name]) throw new Error(`未知的入场预设：${name}，可选：${M.PRESETS.join(", ")}`);
    const [d0, e0] = PRESET_DEF[name];
    const kIn = o.at == null ? 1 : M.prog(t, o.at, o.dur ?? d0, o.ease ?? e0);
    let st = PRESET[name](kIn, o);
    if (o.at != null && t < o.at) st = { ...st, o: 0 }; // 入场前一定隐藏
    if (o.out != null) {
      const kOut = M.prog(t, o.out, o.outDur ?? 0.4, o.outEase ?? "in");
      if (kOut > 0) st = combine(st, outState(o.outPreset || "fade", kOut, o));
    }
    if (o.extra) st = combine(st, o.extra);
    apply(el, st);
    return kIn;
  };
  // 快捷写法：M.enter(el, t, 1.2, "pop")
  M.enter = (el, t, at, preset = "rise", o = {}) => M.animate(el, t, { ...o, at, preset });

  // 一组元素依次入场。gap 是相邻元素的间隔（秒）。o.out 给了的话，按 o.outGap 依次退场
  M.stagger = function (els, t, at, gap = 0.09, o = {}) {
    els = toArray(els);
    els.forEach((el, i) =>
      M.animate(el, t, { ...o, at: at + i * gap, out: o.out != null ? o.out + i * (o.outGap ?? 0) : undefined }),
    );
  };

  /*
   * 轮播：同一个位置上依次展示多组内容（功能列表、步骤、照片）。
   * items: 元素数组，或「元素数组的数组」（每组内部再错峰）
   * start: 第一组开始时刻；step: 每组停留时长
   * o: { preset 入场, outPreset 退场, outDur 退场时长(0.35), gap 组内错峰(0.07), outLast 最后一组是否退场 }
   * 返回当前组的序号
   */
  M.cycle = function (items, t, start, step, o = {}) {
    const n = items.length;
    const outDur = o.outDur ?? 0.35;
    items.forEach((item, i) => {
      const at = start + i * step;
      const out = i < n - 1 || o.outLast ? at + step - outDur : undefined;
      const group = Array.isArray(item) ? item : [item];
      group.forEach((el, j) =>
        M.animate(el, t, {
          preset: o.preset || "rise",
          outPreset: o.outPreset || o.preset || "rise",
          dist: o.dist,
          dur: o.dur,
          at: at + j * (o.gap ?? 0.07),
          out,
          outDur,
        }),
      );
    });
    return clamp(Math.floor((t - start) / step), 0, n - 1);
  };

  // 进度条（每段一格）：container 里自动生成 n 个 <span><i></i></span>
  M.ticks = function (container, n, t, start, step) {
    if (container.children.length !== n) {
      container.innerHTML = "<span><i></i></span>".repeat(n);
      container.classList.add("m-ticks");
    }
    [...container.children].forEach((sp, i) => {
      sp.firstChild.style.width = `${clamp((t - start - i * step) / step) * 100}%`;
    });
  };

  // ================= 文字 =================
  // 把元素里的文字拆成一个个 <span>，用于逐字/逐词动画。mode: "char"（中文用）| "word"（英文用）
  M.split = function (el, mode = "char") {
    if (el.dataset.split) return [...el.querySelectorAll(":scope > .m-piece")];
    const text = el.textContent;
    el.textContent = "";
    const parts = mode === "word" ? text.split(/(\s+)/) : Array.from(text);
    for (const p of parts) {
      if (/^\s+$/.test(p)) {
        el.appendChild(document.createTextNode(p));
        continue;
      }
      const sp = document.createElement("span");
      sp.className = "m-piece";
      sp.textContent = p;
      el.appendChild(sp);
    }
    el.dataset.split = mode;
    return [...el.querySelectorAll(":scope > .m-piece")];
  };
  // 打字机：cps 每秒字数；caret 显示光标
  M.typewriter = function (el, text, t, at, cps = 16, caret = true) {
    const n = Math.floor(clamp((t - at) * cps, 0, text.length));
    const typing = t >= at && t < at + text.length / cps + 0.8;
    const blink = Math.floor(t * 2.5) % 2 === 0;
    el.textContent = text.slice(0, n) + (caret && typing && blink ? "▍" : "");
  };
  // 数字滚动
  M.countUp = function (el, t, at, dur, from, to, o = {}) {
    const v = lerp(from, to, M.prog(t, at, dur, o.ease || "out"));
    const d = o.decimals ?? 0;
    const num = o.sep === false ? v.toFixed(d) : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
    el.textContent = (o.prefix || "") + num + (o.suffix || "");
  };

  // ================= 镜头 =================
  // Ken Burns：整个 dur 内匀速缓慢放大+平移，让静态图片有生命。相邻镜头把 x 方向反过来
  M.kenBurns = function (el, t, dur, o = {}) {
    const k = clamp(t / dur);
    const [x0, x1] = o.x || [-1.5, 1.5];
    const [y0, y1] = o.y || [0, 0];
    apply(el, { s: lerp(o.from ?? 1.0, o.to ?? 1.08, k), xp: lerp(x0, x1, k), yp: lerp(y0, y1, k), origin: o.origin || "50% 50%" });
  };
  // 推镜头：在 [at, at+dur] 内从 1 推到 to 倍，origin 设在要看的区域（如 "30% 40%"）
  M.pushIn = function (el, t, at, dur, o = {}) {
    const k = M.prog(t, at, dur, o.ease || "inOut");
    apply(el, { s: lerp(o.from ?? 1, o.to ?? 1.4, k), origin: o.origin || "50% 50%" });
  };
  // 缓慢漂移，返回状态，用作 M.animate 的 extra
  M.drift = (t, amp = 6, speed = 0.25, seed = 0) => ({
    x: amp * Math.sin(t * speed * 2 * Math.PI + seed),
    y: amp * 0.6 * Math.cos(t * speed * 1.7 * Math.PI + seed),
  });
  // 呼吸值 0..1（光晕、背景亮度的缓慢起伏）
  M.breathe = (t, speed = 0.22, seed = 0) => 0.5 + 0.5 * Math.sin(t * speed * 2 * Math.PI + seed);

  // 两个状态之间补间（常驻元素用：比如 Logo 从屏幕中央缩到角落）
  M.tween = function (el, t, at, dur, from, to, ease = "inOut") {
    const k = M.prog(t, at, dur, ease);
    const st = {};
    for (const key of new Set([...Object.keys(from), ...Object.keys(to)])) {
      const a = from[key] ?? to[key];
      const b = to[key] ?? from[key];
      st[key] = typeof a === "number" ? lerp(a, b, k) : k < 1 ? a : b;
    }
    apply(el, st);
    return k;
  };

  // SVG 描边生长：path/line/circle 等带 stroke 的元素
  M.draw = function (el, t, at, dur, ease = "inOut") {
    const len = Number(el.dataset.len || (el.dataset.len = el.getTotalLength()));
    el.style.strokeDasharray = len;
    el.style.strokeDashoffset = len * (1 - M.prog(t, at, dur, ease));
  };

  // ================= 演示交互 =================
  /*
   * 假光标。el 需要 position:absolute; left:0; top:0。
   * keys: [[时刻, x, y], ...] 光标依次经过的位置（舞台像素坐标）
   * clicks: [时刻, ...] 点击时刻，点击时缩小一下
   */
  M.cursor = function (el, t, keys, clicks = []) {
    let x = keys[0][1];
    let y = keys[0][2];
    for (let i = 0; i < keys.length - 1; i++) {
      const [ta, xa, ya] = keys[i];
      const [tb, xb, yb] = keys[i + 1];
      if (t >= ta) {
        const k = M.prog(t, ta, tb - ta, "inOut");
        x = lerp(xa, xb, k);
        y = lerp(ya, yb, k);
      }
    }
    const pressed = clicks.some((c) => t >= c && t < c + 0.16);
    apply(el, { o: M.prog(t, keys[0][0] - 0.3, 0.3), x, y, s: pressed ? 0.82 : 1, origin: "0 0" });
    return { x, y };
  };
  // 点击涟漪：el 是一个圆（border-radius:50%），放在点击位置，自动以中心对齐
  M.ripple = function (el, t, at) {
    const k = M.prog(t, at, 0.6, "out");
    apply(el, { xp: -50, yp: -50, o: t >= at && k < 1 ? 0.55 * (1 - k) : 0, s: lerp(0.2, 2.6, k) });
  };

  // ================= 字幕 =================
  // list: [[开始, 结束, "文本"], ...]
  M.captions = function (box, t, list) {
    const c = list.find(([a, b]) => t >= a && t < b);
    if (!c) {
      box.innerHTML = "";
      return;
    }
    if (box.dataset.cur !== c[2]) {
      box.innerHTML = `<span>${c[2]}</span>`;
      box.dataset.cur = c[2];
    }
    box.firstChild.style.opacity = Math.min(M.prog(t, c[0], 0.15, "linear"), 1 - M.prog(t, c[1] - 0.15, 0.15, "linear"));
  };

  // ================= 视频素材 =================
  // <video> 逐帧同步。localTime = 这段素材该播到第几秒。渲染时精确 seek 并等解码；预览时自然播放
  M._pending = [];
  M.syncVideo = function (v, localTime) {
    const target = clamp(localTime, 0, (v.duration || 1e9) - 0.001);
    if (M.RENDER) {
      v.pause();
      if (Math.abs(v.currentTime - target) < 1e-3) return; // 时间没变时 seeked 事件不会触发
      M._pending.push(new Promise((r) => v.addEventListener("seeked", r, { once: true })));
      v.currentTime = target;
    } else {
      if (Math.abs(v.currentTime - target) > 0.25) v.currentTime = target;
      if (v.paused) v.play().catch(() => {});
    }
  };

  // ================= 场景转场 =================
  /*
   * 每种转场：dur 默认时长，ease 缓动，in(进入的场景)，out(离开的场景)，overlay(盖在上面的色层)，bar(擦除边缘的色条)
   * dir：left = 内容向左走（新场景从右边进来），right / up / down 同理
   */
  const dirShift = (dir, v) =>
    dir === "right" ? { xp: -v } : dir === "up" ? { yp: v } : dir === "down" ? { yp: -v } : { xp: v };
  const wipeClip = (dir, p) => {
    const r = (1 - p) * 100;
    return dir === "left" ? `inset(0 0 0 ${r}%)` : dir === "up" ? `inset(${r}% 0 0 0)` : dir === "down" ? `inset(0 0 ${r}% 0)` : `inset(0 ${r}% 0 0)`;
  };
  M.TRANSITIONS = {
    cut: { dur: 0 },
    crossfade: { dur: 0.5, ease: "inOut", in: (p) => ({ o: p }) },
    fadeThrough: {
      dur: 0.8,
      ease: "linear",
      in: (p) => ({ o: p >= 0.5 ? 1 : 0 }),
      out: (p) => ({ o: p < 0.5 ? 1 : 0 }),
      overlay: (p, tr) => ({ o: 1 - Math.abs(2 * p - 1), color: tr.color || "#000" }),
    },
    flash: {
      dur: 0.36,
      ease: "linear",
      in: (p) => ({ o: p >= 0.5 ? 1 : 0 }),
      out: (p) => ({ o: p < 0.5 ? 1 : 0 }),
      overlay: (p, tr) => ({ o: 1 - Math.abs(2 * p - 1), color: tr.color || "var(--accent, #fff)" }),
    },
    push: {
      dur: 0.7,
      ease: "inOut",
      in: (p, tr) => dirShift(tr.dir, (1 - p) * 100),
      out: (p, tr) => dirShift(tr.dir, -p * 100),
    },
    slideOver: {
      dur: 0.7,
      ease: "inOut",
      in: (p, tr) => dirShift(tr.dir, (1 - p) * 100),
      out: (p) => ({ s: 1 - 0.06 * p, bright: 1 - 0.45 * p }),
    },
    wipe: { dur: 0.7, ease: "inOut", in: (p, tr) => ({ clip: wipeClip(tr.dir || "right", p) }), bar: true },
    zoom: {
      dur: 0.6,
      ease: "inOut",
      // 新场景从 1.15 倍缩回 1（始终比画面大，不会露出底下的旧场景边缘），旧场景放大、模糊、淡出
      in: (p) => ({ o: p, s: 1.15 - 0.15 * p }),
      out: (p) => ({ o: 1 - p, s: 1 + 0.35 * p, blur: 10 * p }),
    },
    blur: {
      dur: 0.6,
      ease: "inOut",
      in: (p) => ({ o: p, blur: 24 * (1 - p) }),
      out: (p) => ({ o: 1 - p, blur: 24 * p }),
    },
    iris: { dur: 0.8, ease: "inOut", in: (p, tr) => ({ clip: `circle(${(p * 72).toFixed(2)}% at ${tr.at || "50% 50%"})` }) },
  };
  function normTr(x) {
    if (!x) x = "crossfade";
    if (typeof x === "string") {
      const [type, dir] = x.split("-");
      x = { type, dir };
    }
    const def = M.TRANSITIONS[x.type];
    if (!def) throw new Error(`未知的转场：${x.type}，可选：${Object.keys(M.TRANSITIONS).join(", ")}`);
    return { ...x, dur: x.dur ?? def.dur };
  }

  /*
   * 时间轴。
   * scenes: [{ id, dur 或 bars, transition, render(lt, s) }, ...]
   *   id         场景 <section> 的 id
   *   dur        这一场景占的时长（秒）；或者用 bars 按小节数算（需要 opts.bar）
   *   transition 进入这一场景用的转场："crossfade" | "fadeThrough" | "flash" | "push-left" | "wipe-right" | "zoom" ...
   *              或 { type, dir, dur, color, at }。第一个场景的 transition 无效
   *   render     画这一场景的函数。lt = 场景内时间（0 = 本场景的分界点），s = { dur, inStart, outStart }
   * opts: { bar 一小节的秒数, transition 默认转场 }
   *
   * 时间规则：场景 i 的分界点 = 前面所有 dur 之和。转场以分界点为中心，前后各占一半。
   *          所以 dur 设成小节的整数倍时，每个分界点（转场的正中间）都落在强拍上。
   */
  M.timeline = function (scenes, opts = {}) {
    const stage = document.getElementById("stage");
    let ov = document.getElementById("m-overlay");
    if (!ov) {
      ov = Object.assign(document.createElement("div"), { id: "m-overlay" });
      stage.appendChild(ov);
    }
    let bar = document.getElementById("m-bar");
    if (!bar) {
      bar = Object.assign(document.createElement("div"), { id: "m-bar" });
      stage.appendChild(bar);
    }
    let b = 0;
    const list = scenes.map((sc, i) => {
      const el = document.getElementById(sc.id);
      if (!el) throw new Error(`找不到场景元素 #${sc.id}`);
      const dur = sc.bars != null ? sc.bars * opts.bar : sc.dur;
      if (!(dur > 0)) throw new Error(`场景 ${sc.id} 缺少 dur（或 bars + opts.bar）`);
      const tr = i === 0 ? { type: "cut", dur: 0 } : normTr(sc.transition ?? opts.transition);
      const item = { ...sc, el, dur, start: b, tr };
      b += dur;
      return item;
    });
    list.forEach((s, i) => {
      const next = list[i + 1];
      s.trOut = next ? next.tr : { type: "cut", dur: 0 };
      s.visFrom = s.start - s.tr.dur / 2;
      s.visTo = s.start + s.dur + s.trOut.dur / 2;
      const needed = s.tr.dur / 2 + s.trOut.dur / 2 + 0.8;
      if (s.dur < needed) console.warn(`场景 ${s.id} 只有 ${s.dur}s，扣掉转场后不到 0.8s 静止时间，观众看不清`);
    });
    const total = b;

    function render(t) {
      ov.style.opacity = 0;
      bar.style.opacity = 0;
      list.forEach((s, i) => {
        const last = i === list.length - 1;
        const on = t >= s.visFrom && (t < s.visTo || (last && t >= s.start));
        s.el.style.display = on ? "" : "none"; // 写 "" 不写 "block"：不要覆盖样式表里的 flex
        if (!on) return;
        s.el.style.zIndex = i + 1; // 后面的场景盖在前面的上面
        let st = {};
        const hin = s.tr.dur / 2;
        if (s.tr.dur > 0 && t < s.start + hin) {
          const def = M.TRANSITIONS[s.tr.type];
          const p = easeFn(def.ease)(clamp((t - s.start + hin) / s.tr.dur));
          if (def.in) st = combine(st, def.in(p, s.tr));
        }
        const hout = s.trOut.dur / 2;
        if (s.trOut.dur > 0 && t >= s.start + s.dur - hout) {
          const def = M.TRANSITIONS[s.trOut.type];
          const raw = clamp((t - (s.start + s.dur - hout)) / s.trOut.dur);
          const p = easeFn(def.ease)(raw);
          if (def.out) st = combine(st, def.out(p, s.trOut));
          if (def.overlay) {
            const o = def.overlay(p, s.trOut);
            ov.style.opacity = o.o;
            ov.style.background = o.color;
          }
          if (def.bar && raw > 0 && raw < 1) {
            const dir = s.trOut.dir || "right";
            const vertical = dir === "up" || dir === "down";
            const pos = dir === "left" || dir === "up" ? 1 - p : p;
            Object.assign(bar.style, {
              opacity: 1,
              width: vertical ? "100%" : "14px",
              height: vertical ? "14px" : "100%",
              left: vertical ? "0" : `calc(${pos * 100}% - 7px)`,
              top: vertical ? `calc(${pos * 100}% - 7px)` : "0",
            });
          }
        }
        apply(s.el, st);
        if (s.render) {
          s.render(t - s.start, { dur: s.dur, inStart: -hin, outStart: s.dur - hout, start: s.start });
        }
      });
    }

    const info = {
      duration: total,
      scenes: list.map((s) => ({ id: s.id, start: s.start, end: s.start + s.dur, settle: s.start + s.dur - s.trOut.dur / 2 - 0.1 })),
      transitions: list.slice(1).map((s, i) => ({ at: s.start, from: list[i].id, to: s.id, type: s.tr.type + (s.tr.dir ? "-" + s.tr.dir : ""), dur: s.tr.dur })),
    };
    return {
      render,
      duration: total,
      at: (id) => {
        const s = list.find((x) => x.id === id);
        if (!s) throw new Error(`时间轴里没有场景 ${id}`);
        return s.start;
      },
      // t 时刻「主要」在哪个场景（以分界点为准）
      current: (t) => [...list].reverse().find((s) => t >= s.start)?.id ?? list[0].id,
      info,
    };
  };

  // ================= 启动 =================
  /*
   * M.run({ size: [1920, 1080], duration, render(t), timeline })
   * 设置渲染接口（window.__seek 等）；直接用浏览器打开时循环预览：
   *   空格 暂停/继续，← → 前后 1 秒，Shift+← → 前后 0.1 秒；地址加 ?t=12 从第 12 秒开始
   */
  M.run = function ({ size = [1920, 1080], duration, render, timeline }) {
    const stage = document.getElementById("stage");
    stage.style.width = size[0] + "px";
    stage.style.height = size[1] + "px";
    const dur = duration ?? timeline?.duration;
    window.__duration = dur;
    window.__size = size;
    window.__timeline = timeline?.info;
    window.__seek = async (t) => {
      M._pending.length = 0;
      render(t);
      await Promise.all(M._pending);
    };
    window.__ready = Promise.all([
      document.fonts.ready,
      ...[...document.images].map((im) => (im.complete ? 0 : new Promise((r) => (im.onload = im.onerror = r)))),
      ...[...document.querySelectorAll("video")].map((v) =>
        v.readyState >= 1 ? 0 : new Promise((r) => (v.onloadedmetadata = v.onerror = r)),
      ),
    ]);
    if (M.RENDER) {
      render(0);
      return;
    }
    const fit = () => {
      const s = Math.min(innerWidth / size[0], innerHeight / size[1]);
      stage.style.transform = `translate(${(innerWidth - size[0] * s) / 2}px, ${(innerHeight - size[1] * s) / 2}px) scale(${s})`;
    };
    addEventListener("resize", fit);
    fit();
    const label = Object.assign(document.createElement("div"), { id: "m-time" });
    document.body.appendChild(label);
    let cur = Number(new URLSearchParams(location.search).get("t") || 0);
    let paused = false;
    let last = null;
    addEventListener("keydown", (e) => {
      if (e.code === "Space") paused = !paused;
      if (e.code === "ArrowRight") cur += e.shiftKey ? 0.1 : 1;
      if (e.code === "ArrowLeft") cur -= e.shiftKey ? 0.1 : 1;
      cur = ((cur % dur) + dur) % dur;
    });
    window.__ready.then(() => {
      const loop = (now) => {
        if (last != null && !paused) cur = (cur + (now - last) / 1000) % dur;
        last = now;
        render(cur);
        label.textContent = `${cur.toFixed(2)}s / ${dur.toFixed(2)}s${paused ? "  ⏸" : ""}  空格暂停 ←→ 跳转`;
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    });
  };

  // ================= 必需的基础样式 =================
  const css = document.createElement("style");
  css.textContent = `
    #stage { position: absolute; left: 0; top: 0; overflow: hidden; transform-origin: 0 0; }
    #stage > section { position: absolute; inset: 0; overflow: hidden; }
    #m-overlay { position: absolute; inset: 0; z-index: 900; opacity: 0; pointer-events: none; }
    #m-bar { position: absolute; z-index: 901; opacity: 0; background: var(--accent, #fff); pointer-events: none;
             box-shadow: 0 0 24px var(--accent, #fff); }
    .m-piece { display: inline-block; white-space: pre; }
    .m-ticks { display: flex; gap: 10px; }
    .m-ticks span { width: 54px; height: 6px; border-radius: 3px; background: rgb(128 128 128 / 0.25); overflow: hidden; }
    .m-ticks span i { display: block; height: 100%; width: 0; background: var(--accent, #fff); }
    #m-time { position: fixed; left: 8px; bottom: 8px; z-index: 9999; font: 12px/1.4 Menlo, monospace;
              color: #fff; background: rgb(0 0 0 / 0.6); padding: 4px 8px; border-radius: 6px; }
  `;
  document.head.appendChild(css);
})();
