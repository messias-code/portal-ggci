#!/usr/bin/env bash
# PreToolUse — barra acesso ao .env, que guarda SECRET_KEY, DB_PASSWORD e
# PWD_SERVER (senha de root do servidor). A regra em regras/seguranca-e-acessos.md
# pede confirmação antes de usar essas credenciais; este hook a torna executável
# em vez de depender da memória do agente.
#
# Contrato: recebe o JSON do tool call em stdin. Sai 2 para bloquear, com a
# justificativa em stderr (o agente lê e se adapta). Sai 0 para liberar.
set -uo pipefail

payload="$(cat)"

campo() {
  printf '%s' "$payload" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
cur=d
for k in '$1'.split('.'):
    cur = cur.get(k) if isinstance(cur, dict) else None
    if cur is None: break
print(cur or '')
" 2>/dev/null
}

ferramenta="$(campo tool_name)"
caminho="$(campo tool_input.file_path)"
comando="$(campo tool_input.command)"

bloquear() {
  echo "BLOQUEADO pelo hook proteger-env: $1

O .env contém SECRET_KEY, DB_PASSWORD e PWD_SERVER (senha de root).
Se você precisa mesmo desse valor, peça ao usuário — ele decide.
Para ver apenas os NOMES das chaves, sem valores:
  sed -E 's/=.*/=<oculto>/' .env" >&2
  exit 2
}

case "$ferramenta" in
  Read|Edit|Write|NotebookEdit)
    case "$caminho" in
      *.env|*.env.*|*/.env) [ "${caminho##*/}" = ".env.example" ] || bloquear "leitura/escrita de $caminho" ;;
    esac
    ;;
  Bash)
    # Só barra quando o .env é ALVO de leitura; não atrapalha grep no .gitignore
    # nem append (`>> .env`), que é escrita e não vaza nada.
    #
    # A checagem é LINHA A LINHA de propósito. A classe [^|;&] casa quebra de
    # linha, então num comando de várias linhas o regex emendava um `tail` de uma
    # linha com um `.env` de outra e bloqueava escrita legítima. Avaliar cada
    # linha isolada mantém o alcance no comando que realmente lê o arquivo.
    while IFS= read -r linha; do
      printf '%s' "$linha" | grep -qE '\.env\.example' && continue
      # O comando de leitura precisa estar em POSIÇÃO DE COMANDO: início da linha
      # ou logo após |, ; ou &. Sem essa âncora, a alternativa `\.` (que existe
      # para pegar o builtin `.` do source) casava qualquer ponto literal — um
      # simples "--- 7. CHAVE ---" dentro de uma string bloqueava a escrita.
      if printf '%s' "$linha" | grep -qE '(^|[|;&][[:space:]]*)(cat|less|more|head|tail|bat|nl|od|xxd|strings|source|\.)[[:space:]]+[^|;&]*\.env([[:space:]]|$)'; then
        bloquear "comando que lê o .env: $linha"
      fi
    done <<< "$comando"
    ;;
esac

exit 0
