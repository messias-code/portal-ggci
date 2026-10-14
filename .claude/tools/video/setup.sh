#!/usr/bin/env bash
# Instala o que o fazer_video.py precisa DENTRO desta pasta (.venv/, .venv-kokoro/, voz/
# e .cache/ ficam fora do git). Idempotente: rodar de novo só completa o que falta.
#   uso: .claude/tools/video/setup.sh [voz-piper]   (padrão: pt_BR-faber-medium)
#
#   .venv         Python do sistema: playwright, ffmpeg, Whisper (conferência), Piper e edge-tts.
#   .venv-kokoro  Python 3.12 via uv: Kokoro-82M, a voz principal (torch só de CPU).
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
VOZ="${1:-pt_BR-faber-medium}"

[ -x "$AQUI/.venv/bin/python" ] || python3 -m venv "$AQUI/.venv"
#  playwright na mesma versão do venv do projeto, para reaproveitar o Chromium já baixado.
"$AQUI/.venv/bin/pip" install -q piper-tts edge-tts imageio-ffmpeg playwright==1.61.0 faster-whisper pillow
"$AQUI/.venv/bin/python" -m playwright install chromium

#  Kokoro não roda no Python 3.14 do sistema; o uv baixa um 3.12 só para ele.
if [ ! -x "$AQUI/.venv-kokoro/bin/python" ]; then
  uv venv -q --python 3.12 "$AQUI/.venv-kokoro"
fi
VIRTUAL_ENV="$AQUI/.venv-kokoro" uv pip install -q --index-url https://download.pytorch.org/whl/cpu torch
#  Sem o piso do transformers, o resolvedor volta a uma versão de 2021 que não compila.
VIRTUAL_ENV="$AQUI/.venv-kokoro" uv pip install -q "kokoro>=0.9.4" "transformers>=4.45" "tokenizers>=0.20" \
  soundfile espeakng-loader phonemizer-fork numpy

#  Voz Piper (alternativa). pt_BR-faber-medium → pt/pt_BR/faber/medium/
IFS=- read -r LOCAL NOME QUALIDADE <<< "$VOZ"
mkdir -p "$AQUI/voz"
for ext in onnx onnx.json; do
  [ -s "$AQUI/voz/$VOZ.$ext" ] || curl -fsSL -o "$AQUI/voz/$VOZ.$ext" \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/${LOCAL%%_*}/$LOCAL/$NOME/$QUALIDADE/$VOZ.$ext"
done
echo "ok: .venv, .venv-kokoro e voz $VOZ em $AQUI"
