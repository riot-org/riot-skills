#!/usr/bin/env node
// 把时间轴动画页面逐帧截图并编码成视频。
// 页面需要暴露：window.__seek(t)（可返回 Promise）、window.__duration（秒）、window.__ready（Promise），
// 可选 window.__size = [宽, 高]（默认 1920×1080）。见 assets/template.html。
//
// 用法：
//   node render.cjs <video.html> [--out out.mp4] [--fps 30] [--audio music.wav]
//   node render.cjs <video.html> --stills 2,9,20     只截这几秒到 <html 所在目录>/stills/
//   node render.cjs <video.html> --frames dir/       输出 PNG 序列（页面背景透明时保留透明通道）
//   node render.cjs <video.html> --check             每个场景的静止帧 + 每个转场 5 帧，拼成 check.png（需用 M.timeline）
//   node render.cjs <video.html> --timeline          打印场景、转场的时间点（写配乐和字幕时用）
const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawn, spawnSync } = require("child_process");

const DEPS = process.env.VIDEO_DEPS || path.join(os.homedir(), ".cache", "video-production");
const need = (name) => {
  try {
    return require(path.join(DEPS, "node_modules", name));
  } catch {
    console.error(`缺少 ${name}，先运行 ${path.join(__dirname, "setup.sh")}`);
    process.exit(1);
  }
};
const puppeteer = need("puppeteer-core");

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(name);
  return i > -1 ? args[i + 1] : def;
};
const html = path.resolve(args.find((a, i) => !a.startsWith("--") && !(args[i - 1] || "").startsWith("--")) || "");
if (!fs.existsSync(html)) {
  console.error("用法：node render.cjs <video.html> [--out x.mp4] [--fps 30] [--audio x.wav] [--stills 1,2,3] [--frames dir] [--check] [--timeline]");
  process.exit(1);
}
const FPS = Number(opt("--fps", 30));
const out = path.resolve(opt("--out", path.join(path.dirname(html), "out.mp4")));
const audio = opt("--audio");
const framesDir = opt("--frames");

function findChrome() {
  // 优先 Google Chrome：Chromium 不带 H.264 解码，页面里的 mp4 会放不出来
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  ];
  const hit = candidates.find((p) => p && fs.existsSync(p));
  if (!hit) throw new Error("找不到 Chrome，设置 CHROME_PATH");
  return hit;
}
function findFfmpeg() {
  if (process.env.FFMPEG_PATH) return process.env.FFMPEG_PATH;
  if (spawnSync("ffmpeg", ["-version"]).status === 0) return "ffmpeg";
  const dir = path.join(DEPS, "node_modules", "@ffmpeg-installer");
  for (const sub of fs.existsSync(dir) ? fs.readdirSync(dir) : []) {
    const bin = path.join(dir, sub, "ffmpeg");
    if (fs.existsSync(bin)) return bin;
  }
  throw new Error("找不到 ffmpeg，先运行 setup.sh");
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: findChrome(),
    headless: true,
    args: ["--allow-file-access-from-files", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required"],
  });
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("页面报错：", e.message));
  await page.goto("file://" + html + "?render", { waitUntil: "networkidle0", timeout: 60000 });
  const [w, h] = await page.evaluate(() => window.__size || [1920, 1080]);
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  await page.evaluate(() => window.__ready);
  const duration = await page.evaluate(() => window.__duration);
  const seek = (t) => page.evaluate((t) => window.__seek(t), t);

  const tlInfo = await page.evaluate(() => window.__timeline || null);

  // --timeline：打印场景和转场的时间点（写配乐 cues、字幕时间时用）
  if (args.includes("--timeline")) {
    if (!tlInfo) throw new Error("页面没有用 M.timeline，没有时间轴信息");
    console.log(`总时长 ${tlInfo.duration.toFixed(2)}s\n\n场景（start = 分界点，转场正中间）:`);
    for (const s of tlInfo.scenes) console.log(`  ${s.start.toFixed(2).padStart(7)}s  ${s.id}`);
    console.log("\n转场:");
    for (const tr of tlInfo.transitions)
      console.log(`  ${tr.at.toFixed(2).padStart(7)}s  ${tr.from} → ${tr.to}  ${tr.type} ${tr.dur}s`);
    await browser.close();
    return;
  }

  // --check：每个场景的「静止帧」+ 每个转场 5 帧（开始、25%、50%、75%、结束），拼成一张对照图
  if (args.includes("--check")) {
    if (!tlInfo) throw new Error("页面没有用 M.timeline，没法自动检查转场；改用 --stills");
    const shots = [];
    const grab = async (t, label) => {
      t = Math.max(0, Math.min(duration - 1 / FPS, t));
      await seek(t);
      const b64 = await page.screenshot({ type: "jpeg", quality: 70, encoding: "base64" });
      shots.push({ label: `${label}  ${t.toFixed(2)}s`, src: `data:image/jpeg;base64,${b64}` });
    };
    const rows = [];
    shots.length = 0;
    for (const s of tlInfo.scenes) await grab(s.settle, `${s.id} 静止`);
    rows.push({ title: "各场景静止帧（离场转场开始前一刻）：所有元素都应已到位、完整、没有重叠和溢出", shots: [...shots] });
    for (const tr of tlInfo.transitions) {
      shots.length = 0;
      const half = Math.max(tr.dur / 2, 0.05);
      for (const k of [0, 0.25, 0.5, 0.75, 1]) await grab(tr.at - half + k * 2 * half, `${Math.round(k * 100)}%`);
      rows.push({ title: `转场 ${tr.from} → ${tr.to}（${tr.type}，${tr.dur}s）`, shots: [...shots] });
    }
    const cell = 360;
    const sheet = `<!doctype html><meta charset="utf-8"><style>
      body{margin:0;padding:20px;background:#222;color:#eee;font:14px -apple-system,"PingFang SC",sans-serif}
      h3{margin:18px 0 8px;font-size:15px} .row{display:flex;flex-wrap:wrap;gap:8px}
      figure{margin:0;width:${cell}px} img{width:100%;display:block;border:1px solid #444}
      figcaption{font-size:12px;color:#aaa;margin-top:3px}</style>
      ${rows.map((r) => `<h3>${r.title}</h3><div class="row">${r.shots.map((s) => `<figure><img src="${s.src}"><figcaption>${s.label}</figcaption></figure>`).join("")}</div>`).join("")}`;
    const sp = await browser.newPage();
    await sp.setViewport({ width: cell * 5 + 8 * 4 + 40, height: 800 });
    await sp.setContent(sheet, { waitUntil: "load" });
    const file = path.join(path.dirname(html), "check.png");
    await sp.screenshot({ path: file, fullPage: true });
    await browser.close();
    console.log(`对照图：${file}（${tlInfo.scenes.length} 个场景，${tlInfo.transitions.length} 个转场）`);
    return;
  }

  const stills = opt("--stills");
  if (stills) {
    const dir = path.join(path.dirname(html), "stills");
    fs.mkdirSync(dir, { recursive: true });
    for (const t of stills.split(",").map(Number)) {
      await seek(t);
      const file = path.join(dir, `t${t.toFixed(2).padStart(6, "0")}.jpg`);
      await page.screenshot({ path: file, type: "jpeg", quality: 85 });
      console.log(file);
    }
    await browser.close();
    return;
  }

  const total = Math.round(duration * FPS);
  const t0 = Date.now();
  const progress = (i) => i % FPS === 0 && process.stdout.write(`\r${i}/${total} 帧`);

  if (framesDir) {
    fs.mkdirSync(framesDir, { recursive: true });
    for (let i = 0; i < total; i++) {
      await seek(i / FPS);
      await page.screenshot({ path: path.join(framesDir, `${String(i).padStart(5, "0")}.png`), omitBackground: true });
      progress(i);
    }
    await browser.close();
    console.log(`\n完成：${total} 帧 → ${path.resolve(framesDir)}`);
    return;
  }

  const audioArgs = audio ? ["-i", path.resolve(audio), "-c:a", "aac", "-b:a", "192k", "-shortest"] : [];
  const ff = spawn(findFfmpeg(), [
    "-y", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-", ...audioArgs,
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    out,
  ], { stdio: ["pipe", "ignore", "pipe"] });
  let ffErr = "";
  ff.stderr.on("data", (d) => (ffErr = (ffErr + d).slice(-4000)));
  const closed = new Promise((r) => ff.on("close", r));

  for (let i = 0; i < total; i++) {
    await seek(i / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    progress(i);
  }
  ff.stdin.end();
  const code = await closed;
  await browser.close();
  if (code !== 0) {
    console.error(ffErr);
    process.exit(1);
  }
  console.log(`\n完成：${out}（${((Date.now() - t0) / 1000).toFixed(0)} 秒）`);
})();
