#!/bin/sh
# Sobe o VoiceStudio numa tela virtual (o servidor não tem monitor).
# O backend fica em http://localhost:3900, que é o que a skill voicestudio usa.
# uso: voicestudio-headless [parar]
set -eu
LOG="$HOME/.config/VoiceStudio/headless.log"

if [ "${1:-}" = parar ]; then
    pkill -f '^/tmp/[.]mount_VoiceS' || true
    exit 0
fi

if curl -s -m 2 localhost:3900/health | grep -q '"ok"'; then
    echo "VoiceStudio já está no ar."; exit 0
fi

pgrep -x Xvfb >/dev/null || { setsid nohup Xvfb :99 -screen 0 1600x1000x24 -nolisten tcp >/dev/null 2>&1 </dev/null & sleep 2; }
rm -f "$HOME/.config/VoiceStudio/"Singleton*
DISPLAY=:99 setsid nohup "$HOME/.local/bin/VoiceStudio" --no-sandbox >"$LOG" 2>&1 </dev/null &

for i in $(seq 1 60); do
    curl -s -m 2 localhost:3900/health | grep -q '"ok"' && { curl -s localhost:3900/health; echo; exit 0; }
    sleep 3
done
echo "Backend não respondeu em 3 min; veja $LOG" >&2; exit 1
