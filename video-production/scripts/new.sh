#!/usr/bin/env bash
# 新建一个视频工程：把模板、动画库、配乐示例复制到指定目录。
# 用法：bash new.sh <目录>        例如 bash new.sh video
set -euo pipefail
DIR="${1:?用法：bash new.sh <目录>}"
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DIR"
for f in template.html motion.js cues.template.json cues.promo.json cues.calm.json; do
  dest="$DIR/$f"
  [ "$f" = template.html ] && dest="$DIR/video.html"
  [ "$f" = cues.template.json ] && dest="$DIR/cues.json"
  if [ -e "$dest" ]; then echo "已存在，跳过：$dest"; else cp "$SKILL/assets/$f" "$dest"; echo "创建：$dest"; fi
done
echo
echo "下一步："
echo "  1. 浏览器打开 \"$DIR/video.html\" 预览（空格暂停，←→ 跳转）"
echo "  2. 按分镜表改 video.html 里的场景 HTML 和 M.timeline"
echo "  3. node \"$SKILL/scripts/render.cjs\" \"$DIR/video.html\" --check   检查转场"
