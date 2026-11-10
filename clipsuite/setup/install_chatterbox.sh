#!/usr/bin/env bash
# Installs Chatterbox (natural, expressive narration) into its own environment, .venv-chatterbox,
# because it pins PyTorch/transformers versions that would clash with Kokoro and Whisper.
# Usage:  cd clipsuite && bash setup/install_chatterbox.sh      (downloads a few GB the first time)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname)" == "Darwin" ]]; then
  brew install python@3.11
  PY="$(brew --prefix python@3.11)/bin/python3.11"
else
  PY="$(command -v python3.11 || command -v python3)"
fi

"$PY" -m venv .venv-chatterbox
.venv-chatterbox/bin/pip install --upgrade pip
.venv-chatterbox/bin/pip install "chatterbox-tts==0.1.7"
# Chatterbox's audio watermarker (resemble-perth) still imports pkg_resources, which newer
# setuptools releases no longer ship. Without it the watermarker silently fails to load.
.venv-chatterbox/bin/pip install "setuptools<81"
.venv-chatterbox/bin/python -c "
import perth
assert perth.PerthImplicitWatermarker is not None, 'watermarker failed to load'
from chatterbox.tts import ChatterboxTTS
print('Chatterbox is installed.')"
echo "ClipSuite will now use Chatterbox automatically (or pass --tts chatterbox)."
