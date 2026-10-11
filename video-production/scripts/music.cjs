#!/usr/bin/env node
// 按 cue 配置合成视频配乐（44.1kHz 立体声 WAV）。纯代码合成，无需素材，结果可复现。
// 用法：node music.cjs <cues.json> [out.wav]
// 示例：assets/cues.promo.json（有冲劲的宣传片）、assets/cues.calm.json（温暖回顾）；字段与段落风格说明见 references/audio.md
//
// cues.json 字段：
//   duration    总时长（秒）
//   bar         一小节多长（秒）。设成画面里最常见的切换间隔，切换就会落在强拍上
//   anchor      某个强拍（小节开头）的时刻，通常取画面里最规律那段切换开始的时刻
//   progression 和弦循环，如 ["Am","F","C","G"]，按小节轮换
//   endChord    结尾停留的和弦（默认 progression[0]）
//   sections    [{from, to, style}]，style ∈ intro | groove | break | drop | calm | outro
//   hits        [{t, type, gain}]，type ∈ impact | crash | click | chime；
//               riser 用 {type:"riser", from, to}
const fs = require("fs");
const path = require("path");

const cfgPath = process.argv[2];
if (!cfgPath) {
  console.error("用法：node music.cjs <cues.json> [out.wav]");
  process.exit(1);
}
const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
const outPath = path.resolve(process.argv[3] || path.join(path.dirname(cfgPath), "music.wav"));

const SR = 44100;
const DUR = cfg.duration;
const N = Math.round(SR * DUR);
const BAR = cfg.bar;
const BEAT = BAR / 4;
const STEP = BEAT / 4;
const ORIGIN = cfg.anchor - (Math.floor(cfg.anchor / BAR) + 1) * BAR; // anchor 往前推到 0 之前的那个强拍
const sections = cfg.sections;
const styleAt = (t) => (sections.find((s) => t >= s.from && t < s.to) || {}).style;

const drums = [new Float32Array(N), new Float32Array(N)];
const music = [new Float32Array(N), new Float32Array(N)];
const send = new Float32Array(N);

let seed = 1;
const noise = () => ((seed = (seed * 16807) % 2147483647) / 1073741823.5) - 1;
const hz = (m) => 440 * Math.pow(2, (m - 69) / 12);
const lpCoef = (fc) => 1 - Math.exp((-2 * Math.PI * Math.min(fc, SR * 0.45)) / SR);

function write(bus, t0, len, pan, rev, fn) {
  const s0 = Math.round(t0 * SR);
  const gl = Math.cos(((pan + 1) * Math.PI) / 4);
  const gr = Math.sin(((pan + 1) * Math.PI) / 4);
  for (let i = 0; i < len * SR; i++) {
    const j = s0 + i;
    if (j < 0) continue;
    if (j >= N) break;
    const v = fn(i / SR);
    bus[0][j] += v * gl;
    bus[1][j] += v * gr;
    if (rev) send[j] += v * rev;
  }
}

// ---------- 和弦 ----------
const NOTE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
function chord(name) {
  const m = /^([A-G])([#b]?)(m?)$/.exec(name);
  if (!m) throw new Error(`看不懂的和弦：${name}`);
  const pc = (NOTE[m[1]] + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0) + 12) % 12;
  const third = m[3] ? 3 : 4;
  const pcs = [pc, (pc + third) % 12, (pc + 7) % 12];
  // 和声垫取 F3–A4 之间最低的 4 个和弦音，各和弦自然形成转位、声部靠拢
  const padNotes = [];
  for (let n = 53; padNotes.length < 4; n++) if (pcs.includes(n % 12)) padNotes.push(n);
  return { pad: padNotes, root: 28 + ((pc - 4 + 12) % 12) }; // 贝斯根音在 E1–D#2
}

// ---------- 音色 ----------
function kick(t0, g = 1) {
  let ph = 0;
  write(drums, t0, 0.5, 0, 0, (t) => {
    ph += (2 * Math.PI * (44 + 120 * Math.exp(-t * 28))) / SR;
    return g * 0.82 * (Math.sin(ph) * Math.exp(-t * 6.5) + 0.25 * Math.exp(-t * 300));
  });
}
function clap(t0, g = 1) {
  let lp = 0, lp2 = 0;
  const a = lpCoef(2600), b = lpCoef(900);
  write(drums, t0, 0.35, 0.05, 0.25, (t) => {
    const n = noise();
    lp += a * (n - lp);
    lp2 += b * (lp - lp2);
    const bursts = t < 0.03 ? Math.exp(-((t % 0.01) * 300)) : 1;
    return g * 0.5 * (lp - lp2) * bursts * Math.exp(-t * 16);
  });
}
function hat(t0, open = false, g = 1, pan = 0.25) {
  let lp = 0;
  const a = lpCoef(7000);
  write(drums, t0, open ? 0.3 : 0.06, pan, 0.08, (t) => {
    const n = noise();
    lp += a * (n - lp);
    return g * 0.24 * (n - lp) * Math.exp(-t * (open ? 14 : 70));
  });
}
function crash(t0, g = 1) {
  let lp = 0;
  const a = lpCoef(5000);
  write(drums, t0, 2.2, -0.2, 0.3, (t) => {
    const n = noise();
    lp += a * (n - lp);
    return g * 0.14 * (n - lp) * Math.exp(-t * 2.2);
  });
}
function bass(t0, dur, m, g = 1) {
  let ph = 0, ph2 = 0, lp = 0;
  const f = hz(m);
  write(music, t0, dur + 0.05, 0, 0, (t) => {
    ph = (ph + f / SR) % 1;
    ph2 += (2 * Math.PI * f) / 2 / SR;
    lp += lpCoef(260 + 1400 * Math.exp(-t * 14)) * (2 * ph - 1 - lp);
    const env = Math.min(1, t / 0.004) * (t > dur ? Math.max(0, 1 - (t - dur) / 0.05) : 1);
    return g * env * (0.32 * lp + 0.3 * Math.sin(ph2));
  });
}
function pad(t0, dur, notes, g = 1, cutoff = 1500) {
  notes.forEach((m, k) => {
    [-0.11, 0, 0.12].forEach((det, d) => {
      let ph = (k * 0.37 + d * 0.21) % 1, lp = 0;
      const f = hz(m + det);
      write(music, t0, dur + 1, (d - 1) * 0.6, 0.5, (t) => {
        ph = (ph + f / SR) % 1;
        lp += lpCoef(cutoff * (0.7 + 0.3 * Math.sin(t * 1.3 + k))) * (2 * ph - 1 - lp);
        const env = Math.min(1, t / 0.5) * (t > dur ? Math.max(0, 1 - (t - dur)) : 1);
        return g * 0.03 * env * lp;
      });
    });
  });
}
function pluck(t0, m, g = 1, pan = 0) {
  let ph = 0, lp = 0;
  const f = hz(m);
  write(music, t0, 0.5, pan, 0.45, (t) => {
    ph = (ph + f / SR) % 1;
    lp += lpCoef(800 + 4000 * Math.exp(-t * 25)) * ((ph < 0.5 ? 1 : -1) - lp);
    return g * 0.1 * lp * Math.exp(-t * 9);
  });
}
function impact(t0, g = 1) {
  let ph = 0, lp = 0;
  const a = lpCoef(1800);
  write(drums, t0, 2.5, 0, 0.6, (t) => {
    ph += (2 * Math.PI * (34 + 70 * Math.exp(-t * 10))) / SR;
    lp += a * (noise() - lp);
    return g * (0.9 * Math.sin(ph) * Math.exp(-t * 2.2) + 0.35 * lp * Math.exp(-t * 4));
  });
}
function riser(t0, t1, g = 1) {
  let lp = 0;
  const len = t1 - t0;
  write(drums, t0, len, 0, 0.3, (t) => {
    const k = t / len;
    lp += lpCoef(300 + 9000 * k * k) * (noise() - lp);
    return g * 0.22 * lp * k * k;
  });
}
function blip(t0, f, len, g = 1) {
  write(music, t0, len, 0.2, 0.5, (t) => g * 0.18 * Math.sin(2 * Math.PI * f * t) * Math.exp(-t * (6 / len)));
}

// ---------- 编排 ----------
const PROG = cfg.progression.map(chord);
const END = chord(cfg.endChord || cfg.progression[0]);
const ARP = [0, 1, 2, 3, 2, 1, 2, 3, 0, 2, 1, 3, 2, 1, 3, 2];
const barStart = (n) => ORIGIN + n * BAR;
const anchorBar = Math.round((cfg.anchor - ORIGIN) / BAR);
const outro = sections.find((s) => s.style === "outro");
const kickTimes = [];

for (let n = 0; barStart(n) < DUR; n++) {
  const t0 = barStart(n);
  const end = Math.min(t0 + BAR, DUR);
  const mid = styleAt(Math.max(0, t0 + BAR / 2));
  // 和弦以 anchor 所在小节为第一个，保证功能区从主和弦开始；结尾第二小节起停在 endChord 上
  const outroBar = outro ? Math.ceil((outro.from - ORIGIN) / BAR - 0.01) : Infinity;
  const c = n > outroBar ? END : PROG[(((n - anchorBar) % PROG.length) + PROG.length) % PROG.length];

  if (n === outroBar + 1) {
    pad(t0, DUR - t0 - 0.6, c.pad, 1.2, 1300);
  } else if (n <= outroBar) {
    const cutoff = mid === "calm" ? 800 : mid === "intro" || mid === "break" ? 1000 : 1700;
    pad(Math.max(t0, 0), end - Math.max(t0, 0), c.pad, 1, cutoff);
  }

  for (let s = 0; s < 16; s++) {
    const t = t0 + s * STEP;
    if (t < 0 || t >= DUR) continue;
    const st = styleAt(t);
    const beat = s % 4 === 0;
    const off8 = s % 4 === 2;
    const sinceStart = (sections.find((x) => x.style === st) || { from: 0 }).from;

    // 琶音
    const arpG = { intro: 0.55, groove: 1, drop: 1, calm: 0.7, outro: 0.8 }[st];
    const arpOn = arpG && !(st === "intro" && t < 2.4) && !(st === "outro" && outro && t > outro.from + BAR * 1.5);
    if (arpOn && (st !== "calm" || s % 2 === 0)) {
      pluck(t, c.pad[ARP[s]] + 12, arpG * (beat ? 1 : 0.7), s % 2 ? 0.35 : -0.35);
    }

    if (st === "groove") {
      if (beat) (kick(t), kickTimes.push(t));
      if (off8) hat(t, false, 1);
      if (t >= sinceStart + BAR * 2 && (s === 4 || s === 12)) clap(t, 0.8);
      if (s % 2 === 0) bass(t, STEP * 1.6, c.root + (s % 8 === 6 ? 12 : 0) + 12);
    } else if (st === "drop") {
      if (beat) (kick(t), kickTimes.push(t));
      if (s === 4 || s === 12) clap(t);
      hat(t, false, s % 2 ? 0.55 : 1, s % 2 ? 0.35 : 0.15);
      if (off8) hat(t, true, 0.6, -0.3);
      if (s % 2 === 0) bass(t, STEP * 1.6, c.root + (s % 8 === 6 ? 12 : 0) + 12, 1.1);
    } else if (st === "calm") {
      if (s === 0 || s === 8) (kick(t, 0.8), bass(t, BEAT * 1.8, c.root + 12, 0.9));
      if (off8) hat(t, false, 0.6);
    } else if (st === "break") {
      if (s === 0) bass(t, BAR * 0.9, c.root + 12, 0.8);
    }
  }
}

// break 段最后一小节：军鼓滚奏，八分到十六分，渐强
for (const b of sections.filter((s) => s.style === "break")) {
  const from = Math.max(b.from, b.to - BAR);
  for (let t = from; t < b.to - 0.01; ) {
    const k = (t - from) / (b.to - from);
    clap(t, 0.25 + 0.6 * k);
    t += k < 0.5 ? BEAT / 2 : BEAT / 4;
  }
}

for (const h of cfg.hits || []) {
  const g = h.gain ?? 1;
  if (h.type === "impact") impact(h.t, g);
  else if (h.type === "crash") crash(h.t, g);
  else if (h.type === "riser") riser(h.from, h.to, g);
  else if (h.type === "click") blip(h.t, 1800, 0.05, 0.8 * g);
  else if (h.type === "chime") (blip(h.t, hz(88), 0.9, 0.9 * g), blip(h.t + 0.12, hz(93), 1.2, 0.8 * g));
  else console.warn(`未知的 hit 类型：${h.type}`);
}

// ---------- 混响（Schroeder） ----------
function reverb(input, offset) {
  const out = new Float32Array(N);
  const combs = [1557, 1617, 1491, 1422].map((d) => ({ buf: new Float32Array(d + offset), i: 0, lp: 0 }));
  const aps = [556, 225].map((d) => ({ buf: new Float32Array(d + offset), i: 0 }));
  for (let j = 0; j < N; j++) {
    let s = 0;
    for (const c of combs) {
      const y = c.buf[c.i];
      c.lp += 0.45 * (y - c.lp);
      c.buf[c.i] = input[j] + c.lp * 0.86;
      c.i = (c.i + 1) % c.buf.length;
      s += y;
    }
    s *= 0.25;
    for (const a of aps) {
      const y = a.buf[a.i];
      a.buf[a.i] = s + y * 0.5;
      a.i = (a.i + 1) % a.buf.length;
      s = y - s * 0.5;
    }
    out[j] = s;
  }
  return out;
}
const revL = reverb(send, 0);
const revR = reverb(send, 23);

// ---------- 侧链 + 混音 ----------
const duck = new Float32Array(N).fill(1);
for (const tk of kickTimes) {
  const s0 = Math.round(tk * SR);
  for (let i = 0; i < 0.3 * SR && s0 + i < N; i++) {
    duck[s0 + i] = Math.min(duck[s0 + i], 1 - 0.55 * Math.exp((-i / SR) * 9));
  }
}
const mix = [new Float32Array(N), new Float32Array(N)];
let peak = 0;
for (let j = 0; j < N; j++) {
  const t = j / SR;
  const fade = Math.min(1, t / 0.05) * Math.min(1, (DUR - t) / 2.2);
  for (let ch = 0; ch < 2; ch++) {
    const v = drums[ch][j] + music[ch][j] * duck[j] + (ch ? revR[j] : revL[j]) * 0.55;
    mix[ch][j] = Math.tanh(v * 1.1) * fade;
    peak = Math.max(peak, Math.abs(mix[ch][j]));
  }
}

// ---------- 写 WAV ----------
const norm = 0.89 / peak; // 峰值约 -1 dBFS
const data = Buffer.alloc(N * 4);
for (let j = 0; j < N; j++) {
  data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, mix[0][j] * norm)) * 32767), j * 4);
  data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, mix[1][j] * norm)) * 32767), j * 4 + 2);
}
const header = Buffer.alloc(44);
header.write("RIFF", 0);
header.writeUInt32LE(36 + data.length, 4);
header.write("WAVEfmt ", 8);
header.writeUInt32LE(16, 16);
header.writeUInt16LE(1, 20);
header.writeUInt16LE(2, 22);
header.writeUInt32LE(SR, 24);
header.writeUInt32LE(SR * 4, 28);
header.writeUInt16LE(4, 32);
header.writeUInt16LE(16, 34);
header.write("data", 36);
header.writeUInt32LE(data.length, 40);
fs.writeFileSync(outPath, Buffer.concat([header, data]));
console.log(`完成：${outPath}（${DUR}s，${(60 / BEAT).toFixed(1)} BPM）`);
