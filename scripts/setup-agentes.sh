#!/usr/bin/env bash
# ==============================================================================
# setup-agentes.sh — configura Claude Code CLI e Antigravity CLI numa máquina nova
# ==============================================================================
#
# POR QUE ESTE SCRIPT EXISTE
#   A configuração dos dois agentes vive espalhada em cinco lugares diferentes
#   (~/.claude, ~/.gemini, ~/.agents, o repo, e o PATH do npm global). Reproduzir
#   isso na mão erra. Este script torna a configuração idempotente e auditável.
#
# O QUE ELE **NÃO** FAZ
#   Os comandos `/plugin` do Claude Code (claude-mem, claude-code-setup) são
#   slash commands do próprio CLI: nenhum script os executa. O script imprime a
#   lista no fim para você colar. Mesma coisa para logins interativos.
#
# USO
#   ./scripts/setup-agentes.sh                 # tudo
#   ./scripts/setup-agentes.sh --dry-run       # mostra sem executar
#   ./scripts/setup-agentes.sh --only skills   # uma seção só
#   Seções: path | regras | skills | mcp | hooks | omniroute | plugins
#
# IDEMPOTÊNCIA
#   Rodar duas vezes não duplica nada. Todo arquivo sobrescrito ganha backup
#   em <arquivo>.bak-<timestamp>.
# ==============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NPM_PREFIX_BIN="$HOME/.local/lib/nodejs/bin"
CARIMBO="$(date +%Y%m%d-%H%M%S)"
DRY=0
SECAO="tudo"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --only) SECAO="${2:?--only exige uma seção}"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 1 ;;
  esac
  shift
done

# O prefix do npm global entra no PATH deste processo SEMPRE, mesmo com --only,
# porque as seções skills/hooks dependem de achar npx, npm e playwright-cli.
# A gravação no .bashrc continua sendo trabalho da seção 'path'.
[ -d "$NPM_PREFIX_BIN" ] && export PATH="$NPM_PREFIX_BIN:$PATH"

C_OK=$'\033[32m'; C_INFO=$'\033[36m'; C_WARN=$'\033[33m'; C_OFF=$'\033[0m'
titulo() { printf '\n%s══ %s%s\n' "$C_INFO" "$1" "$C_OFF"; }
ok()     { printf '  %s✓%s %s\n' "$C_OK" "$C_OFF" "$1"; }
aviso()  { printf '  %s!%s %s\n' "$C_WARN" "$C_OFF" "$1"; }
rodar()  { if [ "$DRY" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
quero()  { [ "$SECAO" = "tudo" ] || [ "$SECAO" = "$1" ]; }

backup() {
  [ -e "$1" ] || return 0
  [ "$DRY" = 1 ] && { printf '  [dry-run] backup de %s\n' "$1"; return 0; }
  cp -a "$1" "$1.bak-$CARIMBO"
}

# ------------------------------------------------------------------ 1. PATH ---
# O Node deste servidor mora em ~/.local/lib/nodejs; o prefix do npm global NÃO
# entra no PATH sozinho, então todo `npm install -g` some. Sem isto, nada
# instalado por npx/npm global é encontrado.
secao_path() {
  titulo "PATH do npm global"
  if ! command -v node >/dev/null 2>&1 && [ ! -x "$NPM_PREFIX_BIN/node" ]; then
    aviso "Node não encontrado. Instale antes; sem ele nada de skills funciona."
    return 0
  fi
  local prefix; prefix="$( (command -v npm >/dev/null && npm config get prefix) 2>/dev/null || echo "$HOME/.local/lib/nodejs")"
  if grep -qF "$prefix/bin" "$HOME/.bashrc" 2>/dev/null; then
    ok "PATH já contém $prefix/bin"
  else
    backup "$HOME/.bashrc"
    rodar "printf '\n# Binarios globais do npm\nexport PATH=\"%s/bin:\$PATH\"\n' '$prefix' >> '$HOME/.bashrc'"
    ok "PATH acrescentado ao .bashrc ($prefix/bin)"
  fi
  export PATH="$prefix/bin:$PATH"
}

# ---------------------------------------------------------------- 2. REGRAS ---
# As regras do projeto são a fonte da verdade e viajam no git (.claude/regras/).
# Aqui elas são referenciadas pelos dois agentes, em vez de copiadas — assim uma
# correção na regra vale para Claude Code e Antigravity ao mesmo tempo.
secao_regras() {
  titulo "Regras globais (Claude Code + Antigravity)"
  rodar "mkdir -p '$HOME/.claude' '$HOME/.gemini/config'"

  if [ -f "$HOME/.claude/CLAUDE.md" ]; then
    ok "~/.claude/CLAUDE.md já existe (preservado)"
  else
    backup "$HOME/.claude/CLAUDE.md"
    rodar "printf '@RTK.md\n@karpathy-guidelines.md\n' > '$HOME/.claude/CLAUDE.md'"
    ok "~/.claude/CLAUDE.md criado"
  fi

  # Antigravity lê ~/.gemini/config/GEMINI.md. Apontamos para as MESMAS regras
  # versionadas do repo, para os dois agentes não divergirem de comportamento.
  local destino="$HOME/.gemini/config/GEMINI.md"
  if [ -d "$REPO/.claude/regras" ]; then
    backup "$destino"
    if [ "$DRY" = 1 ]; then
      printf '  [dry-run] gerar %s a partir de %s/.claude/regras/\n' "$destino" "$REPO"
    else
      {
        echo "# Regras globais — geradas por scripts/setup-agentes.sh em $CARIMBO"
        echo "# Fonte: $REPO/.claude/regras/ (não edite aqui; edite lá e rode o script)"
        echo
        for f in "$REPO"/.claude/regras/*.md; do
          # seguranca-e-acessos.md é gitignored e cita credenciais: nunca propagar
          [ "$(basename "$f")" = "seguranca-e-acessos.md" ] && continue
          echo "<!-- ${f##*/} -->"; cat "$f"; echo
        done
      } > "$destino"
    fi
    ok "GEMINI.md gerado a partir das regras versionadas (segurança excluída)"
  else
    aviso "$REPO/.claude/regras/ não encontrado — GEMINI.md não gerado"
  fi
}

# ---------------------------------------------------------------- 3. SKILLS ---
# ~/.agents/skills é o diretório UNIVERSAL: Claude Code e Antigravity leem os
# dois. Instalar aqui evita manter duas cópias.
# Formato: "<skill-sentinela>|<argumentos do npx skills add>"
# A sentinela é o nome de UMA skill que o pacote cria — é como sabemos que já
# está instalado. O pacote da Vercel instala 9 skills com nomes próprios, então
# derivar o nome da URL não funciona.
SKILLS_REMOTAS=(
  "design-taste-frontend|https://github.com/Leonxlnx/taste-skill --skill design-taste-frontend"
  "image-to-code|https://github.com/Leonxlnx/taste-skill --skill image-to-code"
  "web-design-guidelines|vercel-labs/agent-skills"
)
secao_skills() {
  titulo "Skills (globais — Claude Code + Antigravity)"
  if ! command -v npx >/dev/null 2>&1; then
    aviso "npx ausente; pulando skills remotas"; return 0
  fi
  rodar "mkdir -p '$HOME/.agents/skills'"
  local entrada nome args
  for entrada in "${SKILLS_REMOTAS[@]}"; do
    nome="${entrada%%|*}"; args="${entrada#*|}"
    if [ -d "$HOME/.agents/skills/$nome" ]; then
      ok "skill '$nome' já instalada"
    else
      # -g é obrigatório: sem ele o npx instala DENTRO do projeto e polui o repo
      # com symlinks para .agents/, que é gitignored.
      rodar "npx -y skills add $args -g </dev/null >/dev/null 2>&1 || true"
      ok "skill instalada: $nome"
    fi
  done

  if command -v playwright-cli >/dev/null 2>&1; then
    ok "playwright-cli já instalado"
  else
    rodar "npm install -g @playwright/cli@latest >/dev/null 2>&1 || true"
    ok "playwright-cli instalado"
  fi
}

# ------------------------------------------------------------------- 4. MCP ---
# O .mcp.json do repo é a fonte; aqui só espelhamos para o Antigravity, que usa
# ~/.gemini/config/mcp_config.json com o mesmo formato de "mcpServers".
secao_mcp() {
  titulo "MCP servers (espelhados para o Antigravity)"
  local origem="$REPO/.mcp.json" destino="$HOME/.gemini/config/mcp_config.json"
  if [ ! -f "$origem" ]; then aviso "$origem não existe"; return 0; fi
  rodar "mkdir -p '$HOME/.gemini/config'"
  backup "$destino"
  rodar "cp '$origem' '$destino'"
  ok "mcp_config.json do Antigravity sincronizado com o .mcp.json do repo"
}

# ----------------------------------------------------------------- 5. HOOKS ---
secao_hooks() {
  titulo "Hooks do projeto"
  if [ ! -d "$REPO/.claude/hooks" ]; then aviso "sem .claude/hooks/"; return 0; fi
  rodar "chmod +x '$REPO'/.claude/hooks/*.sh"
  for h in "$REPO"/.claude/hooks/*.sh; do ok "executável: ${h##*/}"; done
  [ -f "$REPO/.claude/settings.json" ] \
    && ok "settings.json do projeto presente (hooks ligados)" \
    || aviso "falta .claude/settings.json — os hooks não serão chamados"
}

# ------------------------------------------------------------- 6. OMNIROUTE ---
# Roteador local de IA, usado como plano B quando a cota do Claude acaba.
# Tudo aqui é criado FORA do repositório: o binário global vai para o prefix do
# npm, o wrapper para ~/.local/bin e a chave para ~/.omniroute. Nada disso é
# código do projeto, então nada disso entra no git.
secao_omniroute() {
  titulo "OmniRoute (plano B quando a cota acaba)"
  if ! command -v npm >/dev/null 2>&1; then aviso "npm ausente; pulando"; return 0; fi

  if command -v omniroute >/dev/null 2>&1; then
    ok "omniroute já instalado ($(omniroute --version 2>/dev/null | tail -1))"
  else
    # --allow-scripts é necessário: sem ele os módulos nativos (keytar, sharp,
    # onnxruntime, koffi) não compilam e falham só em runtime.
    rodar "npm install -g --allow-scripts=omniroute,keytar,onnxruntime-node,tls-client-node,sharp,@parcel/watcher,@swc/core,protobufjs,koffi,esbuild omniroute >/dev/null 2>&1"
    ok "omniroute instalado com scripts nativos habilitados"
  fi

  # O .env que vem no pacote traz JWT_SECRET e API_KEY_SECRET FIXOS, idênticos em
  # toda instalação. Rotacionar é obrigatório, e só funciona ANTES do primeiro
  # boot: trocar API_KEY_SECRET depois quebra a descriptografia das chaves salvas.
  local pkg_env; pkg_env="$(npm root -g 2>/dev/null)/omniroute/.env"
  if [ -f "$pkg_env" ] && [ ! -d "$HOME/.omniroute" ]; then
    if [ "$DRY" = 1 ]; then
      printf '  [dry-run] rotacionar segredos de %s\n' "$pkg_env"
    else
      backup "$pkg_env"
      local jwt aks pwd_novo
      jwt="$(openssl rand -base64 48 | tr -d '\n')"
      aks="$(openssl rand -hex 32)"
      pwd_novo="$(openssl rand -base64 18 | tr -d '\n/+=' | cut -c1-20)"
      sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|; s|^API_KEY_SECRET=.*|API_KEY_SECRET=${aks}|; s|^INITIAL_PASSWORD=.*|INITIAL_PASSWORD=${pwd_novo}|" "$pkg_env"
      ok "segredos rotacionados — senha inicial do dashboard: ${pwd_novo}"
      aviso "anote a senha acima; ela não será exibida de novo"
    fi
  else
    ok "segredos já rotacionados (ou ~/.omniroute já existe)"
  fi

  # O wrapper. O IP do Tailscale é DESCOBERTO, não cravado — o valor é diferente
  # em cada máquina, e cravá-lo foi um erro da primeira versão deste setup.
  local wrapper="$HOME/.local/bin/claude-omni"
  rodar "mkdir -p '$HOME/.local/bin' '$HOME/.omniroute'"
  if [ "$DRY" = 1 ]; then
    printf '  [dry-run] gerar %s\n' "$wrapper"
  else
    backup "$wrapper"
    cat > "$wrapper" <<'WRAPPER'
#!/usr/bin/env bash
# Roda o Claude Code através do OmniRoute. Gerado por scripts/setup-agentes.sh.
#   claude-omni                     # local, cai para Tailscale se preciso
#   claude-omni --models [filtro]   # lista os modelos disponíveis
#   OMNI_MODEL=fallback-livre claude-omni
#   OMNI_HOST=<ip> claude-omni      # força um endpoint
set -euo pipefail
PORT=20128
[ -f "$HOME/.omniroute/cli.env" ] && . "$HOME/.omniroute/cli.env"
: "${OMNIROUTE_KEY:?defina OMNIROUTE_KEY em ~/.omniroute/cli.env}"

# Descoberta do IP do tailnet desta máquina (vazio se não houver Tailscale).
TS="$(tailscale ip -4 2>/dev/null | head -1 || true)"

pick_host() {
  [ -n "${OMNI_HOST:-}" ] && { echo "$OMNI_HOST"; return; }
  for h in 127.0.0.1 ${TS:-}; do
    curl -s -o /dev/null --max-time 3 "http://$h:$PORT/v1/models" \
      -H "Authorization: Bearer $OMNIROUTE_KEY" && { echo "$h"; return; }
  done
  echo "erro: OmniRoute inacessível (127.0.0.1${TS:+ e $TS}) na porta $PORT" >&2
  exit 1
}
HOST="$(pick_host)"

if [ "${1:-}" = "--models" ]; then
  curl -s --max-time 15 "http://$HOST:$PORT/v1/models" \
    -H "Authorization: Bearer $OMNIROUTE_KEY" \
  | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)['data']]" \
  | { [ -n "${2:-}" ] && grep -i -- "$2" || cat; }
  exit 0
fi

export ANTHROPIC_BASE_URL="http://$HOST:$PORT"
export ANTHROPIC_AUTH_TOKEN="$OMNIROUTE_KEY"
# O Claude Code manda `claude-opus-5` puro e o OmniRoute recusa nome sem prefixo
# de provedor ("400 Ambiguous model"), por isso o modelo é fixado aqui.
export ANTHROPIC_MODEL="${OMNI_MODEL:-auto/best-coding}"
export ANTHROPIC_SMALL_FAST_MODEL="${OMNI_FAST_MODEL:-auto/best-fast}"
echo "→ OmniRoute: $ANTHROPIC_BASE_URL  (modelo: $ANTHROPIC_MODEL)" >&2
exec claude "$@"
WRAPPER
    chmod +x "$wrapper"
  fi
  ok "wrapper criado em ~/.local/bin/claude-omni (IP do Tailscale descoberto em runtime)"

  if grep -q 'omniroute/cli.env' "$HOME/.bashrc" 2>/dev/null; then
    ok "~/.bashrc já carrega a chave do OmniRoute"
  else
    rodar "printf '\n# Chave do OmniRoute para o wrapper claude-omni\n[ -f \"\$HOME/.omniroute/cli.env\" ] && . \"\$HOME/.omniroute/cli.env\"\n' >> '$HOME/.bashrc'"
    ok "~/.bashrc passa a carregar ~/.omniroute/cli.env"
  fi

  if [ -f "$HOME/.omniroute/cli.env" ]; then
    ok "chave do OmniRoute já configurada"
  else
    aviso "falta a chave. Suba o servidor e crie uma:"
    printf '      omniroute serve --daemon --no-open\n'
    printf '      # logue no dashboard (http://localhost:20128) e crie uma API key,\n'
    printf '      # depois grave com permissão restrita:\n'
    printf '      umask 077; echo "export OMNIROUTE_KEY=<chave>" > ~/.omniroute/cli.env\n'
  fi
}

# --------------------------------------------------------------- 7. PLUGINS ---
secao_plugins() {
  titulo "Plugins — AÇÃO MANUAL NECESSÁRIA"
  cat <<'TXT'
  Estes são slash commands do Claude Code. Nenhum script consegue executá-los.
  Cole no prompt do Claude Code, um por vez:

    /plugin marketplace add thedotmack/claude-mem
    /plugin install claude-mem
    /plugin marketplace add anthropics/claude-plugins-official
    /plugin install claude-code-setup@claude-plugins-official

  Opcional (proxy de compressão de tokens — substitui o binário do claude):
    uv tool install --python 3.13 "headroom-ai[all]"
    headroom wrap claude
TXT
}

# ------------------------------------------------------------------ EXECUÇÃO --
printf '%ssetup-agentes.sh%s — repo: %s%s\n' "$C_INFO" "$C_OFF" "$REPO" \
  "$([ "$DRY" = 1 ] && echo '  [DRY-RUN]')"

quero path      && secao_path
quero regras    && secao_regras
quero skills    && secao_skills
quero mcp       && secao_mcp
quero hooks     && secao_hooks
quero omniroute && secao_omniroute
quero plugins   && secao_plugins

titulo "Verificação"
printf '  Claude Code : %s\n' "$(command -v claude || echo 'AUSENTE')"
printf '  Antigravity : %s\n' "$(command -v agy || echo 'AUSENTE')"
printf '  Skills universais: %s em ~/.agents/skills\n' "$(ls -1 "$HOME/.agents/skills" 2>/dev/null | wc -l)"
printf '  claude-omni : %s\n' "$(command -v claude-omni || echo AUSENTE)"
printf '\n%sPronto.%s Abra um terminal novo para o PATH valer.\n' "$C_OK" "$C_OFF"
