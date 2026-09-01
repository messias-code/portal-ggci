#!/usr/bin/env bash
# PostToolUse — depois de editar um .py sob apps/, roda a suíte do app tocado.
# Só o app, nunca a suíte inteira: medido em 01/09/2026, apps.automacoes.analise_ia
# leva 42s com --parallel 4 (152 testes). A suíte completa é lenta demais para hook.
#
# Falha de teste NÃO bloqueia a edição (sai 0). O objetivo é dar o retorno na hora,
# não impedir trabalho em progresso.
set -uo pipefail

RAIZ="/home/labs/portal-ggci-dev"
payload="$(cat)"

caminho="$(printf '%s' "$payload" | python3 -c "
import json,sys
try: print(json.load(sys.stdin).get('tool_input',{}).get('file_path','') or '')
except Exception: pass
" 2>/dev/null)"

case "$caminho" in
  *.py) ;;
  *) exit 0 ;;
esac

# apps/<grupo>/<app>/... -> apps.<grupo>.<app>
rel="${caminho#$RAIZ/}"
case "$rel" in
  apps/*/*) ;;
  *) exit 0 ;;
esac
grupo="$(printf '%s' "$rel" | cut -d/ -f2)"
app="$(printf '%s' "$rel" | cut -d/ -f3)"
alvo="apps.${grupo}.${app}"

[ -d "$RAIZ/apps/$grupo/$app" ] || exit 0

cd "$RAIZ" || exit 0
# shellcheck disable=SC1091
[ -f venv/bin/activate ] && . venv/bin/activate

saida="$(timeout 180 python manage.py test "$alvo" --parallel 4 2>&1)"
resumo="$(printf '%s' "$saida" | grep -E '^(OK|FAILED|Ran [0-9]+ test)' | tr '\n' ' ')"

if printf '%s' "$saida" | grep -q '^FAILED'; then
  echo "Testes de ${alvo}: ${resumo}" >&2
  printf '%s' "$saida" | grep -E '^(FAIL|ERROR):' | head -10 >&2
else
  echo "Testes de ${alvo}: ${resumo:-sem testes}" >&2
fi

exit 0
