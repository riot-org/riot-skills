# ffmpeg 配方

`ffmpeg` 找不到时，用 `~/.cache/video-production/node_modules/@ffmpeg-installer/*/ffmpeg`（setup.sh 装的）。

## 目录
- 查看信息
- 剪切与拼接
- 尺寸与比例
- 速度与帧率
- 文字、字幕、水印
- 音频
- 照片幻灯片
- GIF 与封面
- 检查拼图
- 平台导出参数

## 查看信息

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of compact in.mp4
```

## 剪切与拼接

```bash
# 精确剪切（重新编码，切点准）
ffmpeg -ss 00:00:05.2 -to 00:00:12.8 -i in.mp4 -c:v libx264 -crf 18 -c:a aac out.mp4
# 快速剪切（不重编码，切点会落到最近的关键帧）
ffmpeg -ss 5 -to 12 -i in.mp4 -c copy out.mp4
# 拼接同规格片段（编码、分辨率、帧率一致）
printf "file '%s'\n" a.mp4 b.mp4 c.mp4 > list.txt && ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4
# 拼接不同规格的片段：先统一成 1920x1080 30fps，再用上面的方法拼
ffmpeg -i x.mov -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30" -c:v libx264 -crf 18 -c:a aac -ar 44100 x.mp4
# 两段之间交叉淡化（a 时长 10s，在 9.5s 处开始 0.5s 的溶解）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=9.5[v];[0:a][1:a]acrossfade=d=0.5[a]" -map "[v]" -map "[a]" out.mp4
```

## 尺寸与比例

```bash
# 横屏转竖屏：模糊放大的自身做背景，原画面居中
ffmpeg -i in.mp4 -filter_complex "[0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];[0]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2" -c:a copy vertical.mp4
# 居中裁切成竖屏（主体在中间时）
ffmpeg -i in.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" -c:a copy vertical.mp4
# 裁出录屏的某块区域（宽:高:x:y）并放大
ffmpeg -i rec.mp4 -vf "crop=1280:720:400:200,scale=1920:1080:flags=lanczos" zoom.mp4
```

## 速度与帧率

```bash
# 2 倍速（画面和声音一起）
ffmpeg -i in.mp4 -filter_complex "[0:v]setpts=PTS/2[v];[0:a]atempo=2[a]" -map "[v]" -map "[a]" fast.mp4
# 慢动作 0.5 倍（插帧更顺滑，但较慢）
ffmpeg -i in.mp4 -vf "minterpolate=fps=60,setpts=2*PTS" -an slow.mp4
# 去掉录屏里静止不动的片段
ffmpeg -i rec.mp4 -vf "mpdecimate,setpts=N/FRAME_RATE/TB" -an trimmed.mp4
```

## 文字、字幕、水印

```bash
# 烧录 SRT 字幕（中文要指定字体）
ffmpeg -i in.mp4 -vf "subtitles=subs.srt:force_style='FontName=PingFang SC,FontSize=22,Outline=1,MarginV=40'" -c:a copy out.mp4
# 软字幕（封装进去，播放器可以开关）
ffmpeg -i in.mp4 -i subs.srt -c copy -c:s mov_text out.mp4
# 右下角叠 Logo（宽 160px，留 40px 边距）
ffmpeg -i in.mp4 -i logo.png -filter_complex "[1]scale=160:-1[l];[0][l]overlay=W-w-40:H-h-40" -c:a copy out.mp4
```

需要动画文字、复杂排版时，别用 drawtext 硬凑，把视频放进 HTML 时间轴做（`M.syncVideo` 逐帧同步）。

## 音频

```bash
# 给视频配乐（视频原声丢弃），音乐比视频长时以视频为准
ffmpeg -i video.mp4 -i music.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest out.mp4
# 音乐淡入淡出（视频 30s：开头 1s 淡入，最后 2s 淡出）
ffmpeg -i music.wav -af "afade=t=in:d=1,afade=t=out:st=28:d=2" music_faded.wav
# 旁白 + 音乐，音乐被旁白自动压低（侧链）
ffmpeg -i vo.wav -i music.wav -filter_complex "[1][0]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];[0][duck]amix=inputs=2:duration=longest:normalize=0" mix.wav
# 把多句旁白排到指定时刻（毫秒），再合并
ffmpeg -i l1.aiff -i l2.aiff -filter_complex "[0]adelay=1200|1200[a];[1]adelay=6500|6500[b];[a][b]amix=inputs=2:normalize=0,apad" -t 30 vo.wav
# 响度统一到 -14 LUFS（单遍；两遍法先用 print_format=json 测，再填 measured_* 参数）
ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1:LRA=11 -ar 44100 final.wav
```

## 照片幻灯片

简单的直接用 ffmpeg；要做 Ken Burns、文字卡、卡拍的话，用 HTML 模板更好控。

```bash
# 每张 2.5 秒，统一成 1920x1080
ffmpeg -framerate 1/2.5 -pattern_type glob -i 'photos/*.jpg' -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p" -c:v libx264 slides.mp4
```

## GIF 与封面

```bash
# 高质量 GIF：两遍调色板，12fps，宽 960
ffmpeg -i in.mp4 -vf "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" out.gif
# 取第 3.5 秒做封面
ffmpeg -ss 3.5 -i in.mp4 -frames:v 1 -q:v 2 cover.jpg
# 透明背景（片头、Logo 叠加用）：HTML 背景设成透明，截 PNG 序列后编码 VP9 带 alpha
ffmpeg -framerate 30 -i frames/%05d.png -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 2M logo.webm
```

## 检查拼图

```bash
# 抽 4 帧（按帧号）拼 2x2，用 Read 看
ffmpeg -i out.mp4 -vf "select='eq(n\,90)+eq(n\,300)+eq(n\,600)+eq(n\,900)',scale=640:-1,tile=2x2" -frames:v 1 check.jpg
# 每 5 秒一帧的缩略图墙
ffmpeg -i out.mp4 -vf "fps=1/5,scale=480:-1,tile=4x3" -frames:v 1 contact.jpg
```

## 平台导出参数

通用设置：`-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 192k -ar 44100`。不加 `yuv420p` 和 `faststart`，部分播放器和网页放不了或要整个下载完才能播。

| 平台 | 尺寸 | 帧率 | 建议时长 | 备注 |
|---|---|---|---|---|
| 官网 / 落地页 | 1920×1080 | 30 | 30–60s | 再出一个无声循环版 `-an`，控制在 5–10MB，用作背景 |
| B 站 / YouTube | 1920×1080 或 3840×2160 | 30/60 | 不限 | 码率可以给高（`-crf 16`） |
| 抖音 / 视频号 / Reels / Shorts | 1080×1920 | 30 | 15–60s | Shorts ≤ 60s；注意 UI 安全区 |
| 小红书 | 1080×1440 或 1080×1920 | 30 | 15–60s | 3:4 在信息流里更占地方 |
| X / Twitter | 1920×1080 或 1080×1080 | 30 | ≤ 140s | 文件 ≤ 512MB |
| 微信消息 / 朋友圈 | 1080×1920 或 1920×1080 | 30 | 朋友圈 ≤ 15s 预览 | 压到 20MB 以内更稳：`-crf 23 -maxrate 4M -bufsize 8M` |
| GitHub README | GIF 或 MP4 | 12–15（GIF） | 3–10s | GIF ≤ 5MB；MP4 可以直接拖进 issue / README |

压缩到指定大小：目标码率（kbps）≈ 目标大小（MB）× 8000 / 时长（秒）- 音频码率，然后 `-b:v <码率>k -maxrate <码率>k -bufsize <2倍>k`。
