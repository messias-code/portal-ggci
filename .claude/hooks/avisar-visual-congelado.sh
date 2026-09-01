#!/usr/bin/env bash
# PreToolUse — a regra número um do /senior é "o visual está congelado".
# Este hook não bloqueia: ele injeta o lembrete no momento da edição, junto com
# a armadilha do Tailwind purgado (não há build no repo, então classe utilitária
# nova não existe no output.css e falha em silêncio).
set -uo pipefail

payload="$(cat)"
caminho="$(printf '%s' "$payload" | python3 -c "
import json,sys
try: print(json.load(sys.stdin).get('tool_input',{}).get('file_path','') or '')
except Exception: pass
" 2>/dev/null)"

case "$caminho" in
  */static/*|*/templates/*|*.css|*.html)
    echo "AVISO — visual congelado: $caminho

1. Toda alteração de frontend precisa ser justificada como MANUTENÇÃO
   (bug, código morto, inconsistência) e você deve declarar por que não
   muda um pixel. Se não puder garantir, pare e pergunte.
2. O Tailwind deste repo é bundle purgado, sem build. Classe utilitária
   nova NÃO existe no output.css e falha silenciosamente." >&2
    ;;
esac

exit 0
