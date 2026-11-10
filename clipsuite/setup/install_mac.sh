#!/usr/bin/env bash
# One-shot ClipSuite setup for macOS (Apple Silicon recommended).
# Usage:  cd clipsuite && bash setup/install_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf "\n\033[1;33m==> %s\033[0m\n" "$*"; }

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script is for macOS. On Linux: apt install ffmpeg nodejs; pip install -e '.[cpu]'"; exit 1
fi

# 1. Homebrew
if ! command -v brew >/dev/null; then
  say "Installing Homebrew (you'll be asked for your Mac password)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi

# 2. Command-line tools: yt-dlp, Node 22+, Python, and FFmpeg WITH libass (burned-in captions).
#    Homebrew's standard ffmpeg formula dropped libass, so use the official FFmpeg tap instead.
say "Installing yt-dlp, node, python"
brew install yt-dlp node python@3.12 espeak-ng   # espeak-ng helps the Kokoro voice with rare words
if ! ffmpeg -hide_banner -filters 2>/dev/null | awk '{print $2}' | grep -qx ass; then
  say "Installing FFmpeg with caption support (homebrew-ffmpeg tap; may build for a while)"
  brew uninstall --ignore-dependencies ffmpeg 2>/dev/null || true
  brew tap homebrew-ffmpeg/ffmpeg
  brew install homebrew-ffmpeg/ffmpeg/ffmpeg
fi

# 3. Python environment + Whisper (mlx-whisper runs on the Apple GPU)
say "Creating Python venv in .venv"
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
if [[ "$(uname -m)" == "arm64" ]]; then
  pip install -e '.[mac,dev]'
else
  pip install -e '.[cpu,dev]'   # Intel Mac: faster-whisper on CPU
fi

# 4. Remotion template
say "Installing Remotion template dependencies"
(cd remotion && npm install)

# 5. HyperFrames (runs via npx; this pre-fetches it and checks Chrome/FFmpeg/Node)
say "Checking HyperFrames"
npx --yes hyperframes doctor || echo "  (HyperFrames doctor reported issues - see above; optional)"

say "Done. Next steps:"
cat <<'EOF'
  source .venv/bin/activate
  clipsuite doctor                         # see what's installed
  clipsuite auto "https://youtu.be/..."    # make shorts from a link
  clipsuite serve                          # open the editor on your phone

Manual installs (apps, not scriptable):
  * DaVinci Resolve (free): https://www.blackmagicdesign.com/products/davinciresolve
  * ChatCut: https://chatcut.io (web app or desktop app)
  * Wan2GP: needs an NVIDIA GPU for real speed. On a Mac, try it via Pinokio (https://pinokio.co,
    experimental Apple Silicon support) or run it on a cloud GPU. See README "Wan2GP".
Prompt-to-video (clipsuite create): get a free Pexels key at https://www.pexels.com/api/ then run
  clipsuite config pexels_api_key YOUR_KEY
Optional: export ANTHROPIC_API_KEY=... to let Claude pick clips and write scripts for you.
EOF
