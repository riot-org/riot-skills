#!/usr/bin/env bash
# 安装渲染依赖到 ~/.cache/video-production（可用 VIDEO_DEPS 覆盖），不碰用户项目。
set -euo pipefail

DEPS="${VIDEO_DEPS:-$HOME/.cache/video-production}"
mkdir -p "$DEPS"
cd "$DEPS"

# nvm 装的 node 在非交互 shell 里可能没加载
if ! command -v node >/dev/null 2>&1 && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
  # shellcheck disable=SC1091
  source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
fi
command -v node >/dev/null || { echo "需要 Node.js 18+"; exit 1; }

[ -f package.json ] || npm init -y >/dev/null

if [ ! -d node_modules/puppeteer-core ]; then
  npm i --no-audit --no-fund puppeteer-core@23.11.1
fi

if command -v ffmpeg >/dev/null 2>&1 && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264; then
  echo "ffmpeg：使用系统的 $(command -v ffmpeg)"
else
  # ffmpeg-static 会去 GitHub 下载二进制，经常超时；这个包把二进制直接放在 npm 包里
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) PKG=@ffmpeg-installer/darwin-arm64 ;;
    Darwin-x86_64) PKG=@ffmpeg-installer/darwin-x64 ;;
    Linux-x86_64) PKG=@ffmpeg-installer/linux-x64 ;;
    Linux-aarch64) PKG=@ffmpeg-installer/linux-arm64 ;;
    *) echo "没有现成的 ffmpeg 包，请自行安装 ffmpeg"; exit 1 ;;
  esac
  [ -x "node_modules/$PKG/ffmpeg" ] || npm i --no-audit --no-fund "$PKG"
  echo "ffmpeg：$DEPS/node_modules/$PKG/ffmpeg"
fi

echo "依赖就绪：$DEPS"
