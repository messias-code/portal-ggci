#!/bin/bash

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# ==========================================================================
# 🌌 PORTAL GGCI - INTERFACE DE COMANDO SÊNIOR (ULTRA UX V8 - BULLETPROOF)
# ==========================================================================
# Autor: Ihan Messias (GGCI/OVG)
# Finalidade: Gestão Total de Infraestrutura e Ambiente com Live Logs
# ==========================================================================

# --------------------------------------------------------------------------
# 1. CORES E VARIÁVEIS (ANSI 256)
# --------------------------------------------------------------------------
if [ -t 1 ]; then
    C_CYAN='\033[38;5;45m'    # Ciano Brilhante (Primária)
    C_BLUE='\033[38;5;33m'    # Azul OVG
    C_PURP='\033[38;5;135m'   # Roxo Suave
    C_GREE='\033[38;5;46m'    # Verde Sucesso
    C_YELL='\033[38;5;220m'   # Amarelo Alerta
    C_REDD='\033[38;5;196m'   # Vermelho Erro
    C_GRAY='\033[38;5;244m'   # Cinza Secundário
    C_WHIT='\033[38;5;253m'   # Branco Neve
    C_BOLD='\033[1m'
    C_RESET='\033[0m'
else
    C_CYAN=''
    C_BLUE=''
    C_PURP=''
    C_GREE=''
    C_YELL=''
    C_REDD=''
    C_GRAY=''
    C_WHIT=''
    C_BOLD=''
    C_RESET=''
fi

# --------------------------------------------------------------------------
# 2. MOTOR DE INTERFACE (UI), LIVE LOGS E UTILITÁRIOS
# --------------------------------------------------------------------------
function draw_line() {
    printf "${C_GRAY}%.s─${C_RESET}" $(seq 1 80)
    echo ""
}

function print_ovg_logo() {
    clear
    echo -e "${C_CYAN}${C_BOLD}"
    echo "      ██████╗ ██╗   ██╗ ██████╗ "
    echo "     ██╔═══██╗██║   ██║██╔════╝ "
    echo "     ██║   ██║██║   ██║██║  ███╗"
    echo "     ██║   ██║╚██╗ ██╔╝██║   ██║"
    echo "     ╚██████╔╝ ╚████╔╝ ╚██████╔╝"
    echo -e "      ╚═════╝   ╚═══╝   ╚═════╝ ${C_RESET}"
    echo -e "${C_BLUE}${C_BOLD}      GERÊNCIA DE GESTÃO E CONTROLE DE INFORMAÇÕES - GGCI${C_RESET}"
    echo ""
    draw_line
}

function print_phase() {
    echo ""
    echo -e " ${C_PURP}╭────────────────────────────────────────────────────────────────────────╮${C_RESET}"
    printf " ${C_PURP}│${C_RESET} ${C_CYAN}${C_BOLD}%-70s${C_RESET} ${C_PURP}│${C_RESET}\n" "$1"
    echo -e " ${C_PURP}╰────────────────────────────────────────────────────────────────────────╯${C_RESET}"
}

function log_msg() {
    local type="$1"
    local msg="$2"
    case $type in
        "ok")    echo -e "   ${C_GREE}✔${C_RESET} ${C_WHIT}$msg${C_RESET}" ;;
        "warn")  echo -e "   ${C_YELL}[!]${C_RESET} ${C_YELL}$msg${C_RESET}" ;;
        "err")   echo -e "   ${C_REDD}✖${C_RESET} ${C_REDD}$msg${C_RESET}" ;;
        "info")  echo -e "   ${C_PURP}ℹ${C_RESET} ${C_GRAY}$msg${C_RESET}" ;;
    esac
}

# 💡 A MÁGICA: STREAM À PROVA DE BALAS COM PIPEFAIL
function run_with_stream() {
    local cmd="$1"
    local msg="$2"
    
    echo -e "   ${C_CYAN}➤${C_RESET} ${C_WHIT}${msg}${C_RESET}"
    echo -e "   ${C_GRAY}╭─────────────────────────────────────────────────────────────────╮${C_RESET}"
    
    # pipefail garante que se o Python der erro, o 'awk' não mascara o código de saída
    set -o pipefail
    eval "PYTHONUNBUFFERED=1 $cmd" 2>&1 | awk -v c_gray="${C_GRAY}" -v c_reset="${C_RESET}" -v c_whit="${C_WHIT}" '{print "   " c_gray "│" c_reset " " c_whit $0 c_reset}'
    local status=$?
    set +o pipefail
    
    echo -e "   ${C_GRAY}╰─────────────────────────────────────────────────────────────────╯${C_RESET}"
    if [ $status -eq 0 ]; then
        echo -e "   ${C_GREE}✔ Concluído com Sucesso${C_RESET}\n"
    else
        echo -e "   ${C_REDD}✖ Operação abortada com falhas (Código: $status)${C_RESET}\n"
    fi
    return $status
}

# 💡 TRADUTOR DE CAMINHOS LINUX -> WINDOWS (WSL2)
function show_output_folder() {
    local folder_path="$1"
    mkdir -p "$folder_path" 
    local abs_path=$(realpath "$folder_path")
    
    echo -e "   ${C_CYAN}➤${C_RESET} ${C_WHIT}Acesso Rápido aos Arquivos Gerados:${C_RESET}"
    
    # Detecção nativa do WSL e tradução de caminho
    if command -v wslpath > /dev/null 2>&1; then
        local win_path=$(wslpath -w "$abs_path")
        echo -e "   ${C_PURP}📂 Caminho Windows (Copie e cole no Explorer):${C_RESET}"
        printf "   ${C_WHIT}%s${C_RESET}\n" "$win_path"
        
        # Tenta abrir o explorer
        explorer.exe "$win_path" > /dev/null 2>&1 &
        echo -e "   ${C_GREE}✔ Windows Explorer acionado via WSL2${C_RESET}"
        
    elif command -v xdg-open > /dev/null 2>&1; then
        echo -e "   ${C_PURP}📂 Caminho Linux:${C_RESET} ${C_WHIT}${abs_path}${C_RESET}"
        xdg-open "$abs_path" > /dev/null 2>&1 &
        echo -e "   ${C_GREE}✔ Explorador de Arquivos acionado${C_RESET}"
        
    elif command -v open > /dev/null 2>&1; then
        echo -e "   ${C_PURP}📂 Caminho MacOS:${C_RESET} ${C_WHIT}${abs_path}${C_RESET}"
        open "$abs_path" > /dev/null 2>&1 &
        echo -e "   ${C_GREE}✔ Finder acionado${C_RESET}"
    else
        echo -e "   ${C_PURP}📂 Caminho Universal:${C_RESET} ${C_WHIT}${abs_path}${C_RESET}"
    fi
}

function wait_key() {
    echo -ne "\n   ${C_GRAY}Pressione [ENTER] para retornar ao menu principal...${C_RESET} "
    read -r
}

function check_sudo() {
    log_msg "info" "Solicitando credenciais de administrador..."
    local pass=""
    if [ -f .env ]; then
        pass=$(grep -E '^PWD_SERVER=' .env | cut -d '=' -f2 | tr -d "'\"")
    fi
    
    if [ -n "$pass" ]; then
        echo "$pass" | sudo -S -v >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log_msg "warn" "Senha do .env falhou, solicitando manualmente..."
            sudo -v
        fi
    else
        sudo -v
    fi
    
    (while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null) &
}

# --------------------------------------------------------------------------
# WATCHDOG DO ACESSO PÚBLICO (ggci-watchdog.timer)
# --------------------------------------------------------------------------
# POR QUE EXISTE: o Tailscale Funnel mantém dois estados — o local, nas prefs
# do tailscaled, e o anúncio de ingress no plano de controle. Nesta rede o
# netmap cai com frequência (NAT simétrico: netcheck acusa
# MappingVariesByDestIP, sem conexão direta, tudo via relay DERP) e, ao
# reconectar, o anúncio remoto NÃO volta sozinho. O estado local segue dizendo
# "Funnel on", então nada parece errado no servidor, mas quem está fora da
# tailnet recebe ERR_CONNECTION_CLOSED. Antes do watchdog, a única cura era
# rodar a opção 3 ou 5 na mão, que reanuncia o Funnel de passagem.
#
# COMO FUNCIONA: um timer do systemd roda /usr/local/bin/ggci-watchdog.sh a
# cada 60s, testa o caminho público real e cura em degraus. As funções abaixo
# são o contrato do portal.sh com ele, via dois arquivos de estado.
#
# QUEM CHAMA: opção 1 (instala), opções 3 e 5 (pausam durante a troca e
# retomam depois), opção 13 (desinstala). A opção 4 não chama nada de
# propósito: ela vive na porta 8080 e o watchdog só olha 8000/8001.
readonly WD_ESTADO_DIR="/var/lib/ggci-watchdog"
readonly WD_LOCK="${WD_ESTADO_DIR}/manutencao.lock"
readonly WD_PROD_ATIVA="${WD_ESTADO_DIR}/producao_ativa"

function watchdog_instalado() {
    [ -d "$WD_ESTADO_DIR" ] && [ -x /usr/local/bin/ggci-watchdog.sh ]
}

# Silencia o watchdog enquanto derrubamos e subimos a pilha. Sem isso ele
# acordaria no meio da troca, veria a 8001 muda e criaria um segundo Gunicorn
# disputando a porta e sobrescrevendo /tmp/gunicorn.pid.
#
# Gravamos o instante de EXPIRAÇÃO, não o de criação: se este script morrer
# antes de retomar (Ctrl+C bruto, kill, queda de energia), o lock vence sozinho
# e a vigilância volta. Um lock eterno desligaria o watchdog em silêncio.
#
# Escrita resiliente: tenta como labs (o caso normal, já que install_watchdog
# faz chown do diretório) e cai para sudo -n se o dono for outro — cenário real
# em servidores que receberam o watchdog antes do chown existir. Só usamos
# sudo -n (não interativo) de propósito: travar o restart da produção num
# prompt de senha seria pior do que o problema que o watchdog resolve. Se as
# duas tentativas falharem, avisamos alto, porque um pausar que falha em
# silêncio devolve exatamente a colisão que queríamos evitar.
function _wd_escrever() {
    local conteudo="$1" destino="$2"
    echo "$conteudo" > "$destino" 2>/dev/null && return 0
    echo "$conteudo" | sudo -n tee "$destino" >/dev/null 2>&1 && return 0
    log_msg "warn" "Não foi possível escrever em ${destino} — watchdog pode agir durante a troca."
    return 1
}

function _wd_remover() {
    local destino="$1"
    [ -e "$destino" ] || return 0
    rm -f "$destino" 2>/dev/null && return 0
    sudo -n rm -f "$destino" 2>/dev/null && return 0
    log_msg "warn" "Não foi possível remover ${destino}."
    return 1
}

function watchdog_pausar() {
    local minutos="${1:-15}"
    watchdog_instalado || return 0
    _wd_escrever "$(( $(date +%s) + minutos * 60 ))" "$WD_LOCK"
}

function watchdog_retomar() {
    watchdog_instalado || return 0
    _wd_remover "$WD_LOCK"
}

# Declara se a produção DEVERIA estar no ar. Sem esta marca o watchdog observa
# mas não ressuscita nada — é o que impede de ele reerguer a produção quando
# você desligou de propósito ou está rodando apenas o ambiente DEV.
function watchdog_marcar_prod() {
    watchdog_instalado || return 0
    case "$1" in
        ativa)   _wd_escrever "$(date +%s)" "$WD_PROD_ATIVA" ;;
        inativa) _wd_remover "$WD_PROD_ATIVA" ;;
    esac
}

# --------------------------------------------------------------------------
# SINCRONIZAÇÃO DA ESTRUTURA DO BANCO (MIGRAÇÕES)
# --------------------------------------------------------------------------
# POR QUE EXISTE: os arquivos de migração são ignorados pelo git (.gitignore),
# logo eles nunca viajam de DEV para MAIN nem para PROD. Um campo novo em
# qualquer model chega no destino como código, mas a coluna correspondente não
# existe no banco — e o ambiente inteiro cai com "Unknown column ... in 'field
# list'", derrubando inclusive o login.
#
# COMO FUNCIONA: gera os arquivos de migração faltantes e os aplica. É
# idempotente: onde já estiver tudo em dia, não gera nem aplica nada.
#
# QUEM CHAMA: as opções 3 (produção), 4 (desenvolvimento) e 5 (publicação),
# sempre ANTES de subir o servidor.
function sync_migrations() {
    run_with_stream "python3 manage.py makemigrations gestao_acessos --noinput && python3 manage.py makemigrations --noinput && python3 manage.py migrate --noinput" "Sincronizando estrutura do banco (migrações)"
}

# Instala (ou reinstala) o watchdog. Idempotente: pode rodar quantas vezes for
# preciso. Chamada pela opção 1; os arquivos-fonte viajam no git, em scripts/.
function install_watchdog() {
    local fonte="${PWD}/scripts"

    if [ ! -f "${fonte}/ggci_watchdog.sh" ]; then
        log_msg "warn" "scripts/ggci_watchdog.sh não encontrado — watchdog não instalado."
        return 0
    fi

    run_with_stream "
        sudo install -m 755 '${fonte}/ggci_watchdog.sh' /usr/local/bin/ggci-watchdog.sh &&
        sudo install -m 644 '${fonte}/ggci-watchdog.service' /etc/systemd/system/ggci-watchdog.service &&
        sudo install -m 644 '${fonte}/ggci-watchdog.timer' /etc/systemd/system/ggci-watchdog.timer &&
        sudo mkdir -p ${WD_ESTADO_DIR} &&
        sudo chown labs:labs ${WD_ESTADO_DIR} &&
        sudo touch /var/log/ggci-watchdog.log &&
        sudo systemctl daemon-reload &&
        sudo systemctl enable --now ggci-watchdog.timer
    " "Instalando watchdog do acesso público (Funnel + Nginx + Gunicorn)"

    # O diretório de estado pertence ao usuário labs de propósito: as funções
    # watchdog_* rodam sem sudo em pontos onde o portal.sh pode não ter mais
    # credencial em cache, e travar o fluxo de produção num prompt de senha
    # seria pior do que o problema que o watchdog resolve.
}

function ask_confirm() {
    local prompt="$1"
    echo -ne "   ${C_YELL}[!]${C_RESET} ${C_WHIT}${prompt} (s/N): ${C_RESET}"
    read -r conf
    conf="${conf,,}" 
    if [[ "$conf" == "s" || "$conf" == "sim" || "$conf" == "y" || "$conf" == "yes" ]]; then
        return 0
    else
        return 1
    fi
}

# --------------------------------------------------------------------------
# 3. LÓGICA DE NEGÓCIO - AMBIENTE (.env)
# --------------------------------------------------------------------------
function env_wizard() {
    print_phase "🔑 SINCRONIZAÇÃO DE CREDENCIAIS"
    
    if [ ! -f .env ]; then 
        run_with_stream "cp .env.example .env" "Gerando arquivo .env base"
    fi
    
    echo -ne "   ${C_CYAN}➤${C_RESET} ${C_WHIT}Defina a Senha do MySQL Local${C_RESET} ${C_GRAY}(DB_PASSWORD):${C_RESET} "
    read -r db_pass
    
    if [ ! -z "$db_pass" ]; then
        export K="DB_PASSWORD"; export V="$db_pass"
        python3 -c "import os, re; k,v=os.environ.get('K'),os.environ.get('V'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\"{k}='{v}'\",c,flags=re.MULTILINE))"
        log_msg "ok" "Senha do banco injetada no ambiente."
    fi

    echo ""
    echo -e "   ${C_CYAN}➤${C_RESET} ${C_PURP}Cole o JSON de credenciais abaixo e pressione Enter 2x:${C_RESET}"
    json_input=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && break
        json_input+="$line"
    done

    if [ ! -z "$json_input" ]; then
        export JSON_DATA="$json_input"
        run_with_stream "
python3 -c \"
import os, re, sys
try:
    json_str = os.environ.get('JSON_DATA', '')
    
    data = {}
    matches = re.findall(r'[\'\\\"]?([A-Za-z0-9_]+)[\'\\\"]?\s*[:=]\s*[\'\\\"](.*?)[\'\\\"]', json_str)
    for k, v in matches:
        data[k] = v
    
    content = ''
    if os.path.exists('.env'):
        with open('.env', 'r') as f: content = f.read()
        
    def get_val(key, default=''):
        m = re.search(f'^{key}=\\'?(.*?)\\'?$', content, flags=re.MULTILINE)
        return m.group(1) if m else default

    new_env = '# ==========================================================================\\n'
    new_env += '# ARQUIVO DE CONFIGURAÇÕES (.env)\\n'
    new_env += '# ==========================================================================\\n\\n'
    new_env += '# --- 1. CONFIGURAÇÕES DO DJANGO ---\\n'
    new_env += 'DEBUG=True\\n'
    new_env += f\\\"SECRET_KEY='{get_val('SECRET_KEY', 'gerada-automaticamente-pelo-setup')}'\\n\\\"
    new_env += 'ALLOWED_HOSTS=*\\n\\n'
    
    new_env += '# --- 2. BANCO DE DADOS LOCAL (MYSQL) ---\\n'
    db_name = 'portal_ggci'
    cwd = os.getcwd()
    if cwd.endswith('-prod'):
        db_name = 'portal_ggci_prod'
    elif cwd.endswith('-dev'):
        db_name = 'portal_ggci_dev'

    new_env += f\\\"DB_NAME='{get_val('DB_NAME', db_name)}'\\n\\\"
    new_env += 'DB_USER=\\'portal_user\\'\\n'
    new_env += f\\\"DB_PASSWORD='{get_val('DB_PASSWORD', 'ovg@2026')}'\\n\\\"
    new_env += 'DB_HOST=\\'127.0.0.1\\'\\n'
    new_env += 'DB_PORT=\\'3306\\'\\n\\n'
    
    new_env += '# --- 3. DASHBOARD POLICHAT ---\\n'
    new_env += f\\\"DASHBOARD_POLICHAT_USER_PROD='{data.get('DASHBOARD_POLICHAT_USER_PROD', get_val('DASHBOARD_POLICHAT_USER_PROD', ''))}'\\n\\\"
    new_env += f\\\"DASHBOARD_POLICHAT_PASS_PROD='{data.get('DASHBOARD_POLICHAT_PASS_PROD', get_val('DASHBOARD_POLICHAT_PASS_PROD', ''))}'\\n\\\"
    new_env += f\\\"DASHBOARD_POLICHAT_USER_DEV='{data.get('DASHBOARD_POLICHAT_USER_DEV', get_val('DASHBOARD_POLICHAT_USER_DEV', ''))}'\\n\\\"
    new_env += f\\\"DASHBOARD_POLICHAT_PASS_DEV='{data.get('DASHBOARD_POLICHAT_PASS_DEV', get_val('DASHBOARD_POLICHAT_PASS_DEV', ''))}'\\n\\n\\\"
    
    new_env += '# --- 4. PORTAL PBU (GOVERNO) ---\\n'
    new_env += f\\\"PORTAL_PBU_USER='{data.get('PORTAL_PBU_USER', get_val('PORTAL_PBU_USER', ''))}'\\n\\\"
    new_env += f\\\"PORTAL_PBU_PASS_AGENDAMENTOS='{data.get('PORTAL_PBU_PASS_AGENDAMENTOS', get_val('PORTAL_PBU_PASS_AGENDAMENTOS', ''))}'\\n\\\"
    new_env += f\\\"PORTAL_PBU_PASS_VALORES_BOLSAS='{data.get('PORTAL_PBU_PASS_VALORES_BOLSAS', get_val('PORTAL_PBU_PASS_VALORES_BOLSAS', ''))}'\\n\\n\\\"
    
    new_env += '# --- 5. BANCO DE DADOS EXTERNO (SIBU) ---\\n'
    new_env += f\\\"SIBU_BANCO_DADOS_HOST='{data.get('SIBU_BANCO_DADOS_HOST', get_val('SIBU_BANCO_DADOS_HOST', '10.237.1.16'))}'\\n\\\"
    new_env += f\\\"SIBU_BANCO_DADOS_USER='{data.get('SIBU_BANCO_DADOS_USER', get_val('SIBU_BANCO_DADOS_USER', ''))}'\\n\\\"
    new_env += f\\\"SIBU_BANCO_DADOS_PASS='{data.get('SIBU_BANCO_DADOS_PASS', get_val('SIBU_BANCO_DADOS_PASS', ''))}'\\n\\\"
    new_env += f\\\"SIBU_BANCO_DADOS_NAME='{data.get('SIBU_BANCO_DADOS_NAME', get_val('SIBU_BANCO_DADOS_NAME', 'sibu'))}'\\n\\n\\\"

    new_env += '# --- 6. SERVIDOR E AUTOMACOES ---\\n'
    new_env += f\\\"PWD_SERVER='{data.get('PWD_SERVER', get_val('PWD_SERVER', ''))}'\\n\\\"
    new_env += f\\\"SSH_KEY_PASSPHRASE='{data.get('SSH_KEY_PASSPHRASE', get_val('SSH_KEY_PASSPHRASE', ''))}'\\n\\\"

    with open('.env', 'w') as f: f.write(new_env)
except Exception as e:
    sys.exit(1)
\"" "Processando e injetando JSON de credenciais"
    fi

    if grep -q "gerada-automaticamente" .env; then
        run_with_stream "
            new_key=\$(python3 -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\") &&
            export K_S=\"SECRET_KEY\" V_S=\"\${new_key}\" &&
            python3 -c \"import os, re; k,v=os.environ.get('K_S'),os.environ.get('V_S'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\\\"{k}='{v}'\\\",c,flags=re.MULTILINE))\"
        " "Gerando Chave de Criptografia Segura (Django)"
    fi

    log_msg "info" "Instalando rotina de automação no sistema (Cron)..."
    if [ -f "scripts/cron.conf" ]; then
        run_with_stream "crontab scripts/cron.conf" "Registrando scripts/cron.conf no crontab do Linux"
        log_msg "ok" "Automação instalada! O servidor agora opera no piloto automático."
    else
        log_msg "warn" "Arquivo scripts/cron.conf não encontrado. O Cron não foi ativado."
    fi
}

# --------------------------------------------------------------------------
# 4. LÓGICA DE NEGÓCIO - INSTALAÇÃO
# --------------------------------------------------------------------------
function setup_full() {
    print_ovg_logo
    check_sudo

    # ONDE O CLONE BASE ESTÁ, capturado antes de tudo. Vários `run_with_stream`
    # desta função fazem `cd` lá dentro, e `run_with_stream` usa `eval` — o
    # diretório VAZA para os passos seguintes. Guardar aqui é o que permite os
    # passos posteriores voltarem ao lugar certo sem depender do `pwd` do momento.
    local BASE_DIR="$(pwd)"
    
    print_phase "🚀 FASE 0: PREPARAÇÃO DO TERRENO"

    # O setup reinstala tudo e derruba a produção por vários minutos. Se um
    # watchdog de instalação anterior estiver ativo, ele tentaria reerguer a
    # pilha no meio do caminho. 60 min cobrem o pior caso (pip + playwright).
    watchdog_pausar 60

    run_with_stream "sudo pkill -f 'manage.py runserver.*8080' || true; sudo pkill -f 'gunicorn.*8001' || true" "Desligando processos Python zumbis"

    print_phase "📦 FASE 1: MOTOR DO SISTEMA (Isso pode levar alguns minutos)"
    run_with_stream "sudo sed -i -E 's|URIs: https?://.*ubuntu.com/ubuntu/|URIs: http://us-central1.gce.archive.ubuntu.com/ubuntu/|' /etc/apt/sources.list.d/ubuntu.sources || true" "Configurando espelho interno do Google Cloud (GCP)"
    run_with_stream "sudo apt-get update -yqq" "Atualizando lista de repositórios do SO"
    run_with_stream "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-venv python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config nginx samba samba-common smbclient curl tmux cron" "Instalando Core Linux, Nginx, Samba e Utilitários"
    run_with_stream "bash -c 'if ! command -v tailscale > /dev/null; then curl -fsSL https://tailscale.com/install.sh | sh; fi'" "Instalando Tailscale"
    run_with_stream "bash -c 'if ! command -v cloudflared > /dev/null; then curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb; fi'" "Instalando Cloudflared"
    run_with_stream "/usr/bin/python3 -m venv venv" "Criando Ambiente Virtual"
    source venv/bin/activate
    run_with_stream "pip install --upgrade pip && pip install -r requirements.txt" "Instalando Bibliotecas do Sistema (Pip)"
    run_with_stream "pip install --upgrade playwright sqlalchemy polars pyarrow fastparquet mysql-connector-python xlsxwriter" "Instalando e Atualizando dependências de Dados (Motor IA)"
    run_with_stream "playwright install chromium" "Construindo Navegador Headless (Playwright)"

    env_wizard

    print_phase "📂 FASE 1.5: ESTRUTURAÇÃO DE AMBIENTES E SAMBA"
    run_with_stream "
        git config pull.rebase false 2>/dev/null || true
        # TOPOLOGIA (rode esta opção de dentro do clone base, ~/portal-ggci):
        #   ~/portal-ggci       clone base + orquestrador — o deploy (opção 5) roda AQUI
        #   ~/portal-ggci-dev   worktree da branch dev — é onde se desenvolve
        #   ~/portal-ggci-prod  cópia rsync SEM .git — é o que o gunicorn serve
        #
        # PROD é cópia, não worktree, de propósito: sem .git ninguém commita de
        # produção por acidente e um checkout errado não derruba o serviço. O
        # sync_production (opção 5) reforça isso com --exclude '.git'. Antes aqui
        # havia um 'git worktree add' que, quando funcionava, produzia um prod
        # rastreado que o rsync seguinte sobrescrevia — deixando o worktree sujo.
        if [ ! -d '/home/labs/portal-ggci-prod' ]; then
            rsync -a --exclude 'venv' --exclude '.git' ./ /home/labs/portal-ggci-prod/
            # PROD nasce já com a configuração de produção. Antes o .env vinha
            # copiado cru e só a opção 5 aplicava estes dois ajustes — ou seja,
            # numa instalação nova a produção subia com DEBUG=True (tela amarela
            # do Django exposta ao visitante) e apontando para o banco errado.
            cp .env /home/labs/portal-ggci-prod/.env
            sed -i \"s|^DEBUG=.*|DEBUG=False|\" /home/labs/portal-ggci-prod/.env
            sed -i \"s|^DB_NAME=.*|DB_NAME='portal_ggci'|\" /home/labs/portal-ggci-prod/.env
        fi
        # Remove atalho antigo se existir e cria um venv real
        if [ -L '/home/labs/portal-ggci-prod/venv' ]; then rm '/home/labs/portal-ggci-prod/venv'; fi
        if [ ! -d '/home/labs/portal-ggci-prod/venv' ]; then
            python3 -m venv /home/labs/portal-ggci-prod/venv
            /home/labs/portal-ggci-prod/venv/bin/pip install -r /home/labs/portal-ggci-prod/requirements.txt
        fi

        # DEV é worktree de verdade: é onde se commita, então precisa do git.
        # Se o worktree add falhar (base sem .git), o rsync mantém o ambiente
        # utilizável, mas sem versionamento — o aviso abaixo torna isso visível
        # em vez de deixar a pessoa descobrir na hora do primeiro commit.
        if [ ! -d '/home/labs/portal-ggci-dev' ]; then
            git branch dev origin/dev 2>/dev/null || true
            git worktree add /home/labs/portal-ggci-dev dev 2>/dev/null \
              || { rsync -a --exclude 'venv' --exclude '.git' ./ /home/labs/portal-ggci-dev/; \
                   echo '[AVISO] portal-ggci-dev criado SEM git: a base nao e um clone. Commits nao funcionarao ali.'; }
            # DEV aponta para o SEU banco. Sem esta linha os dois ambientes
            # compartilhavam portal_ggci, e um teste no dev alterava produção.
            cp .env /home/labs/portal-ggci-dev/.env
            sed -i \"s|^DEBUG=.*|DEBUG=True|\" /home/labs/portal-ggci-dev/.env
            sed -i \"s|^DB_NAME=.*|DB_NAME='portal_ggci_dev'|\" /home/labs/portal-ggci-dev/.env
        fi
        # Remove atalho antigo se existir e cria um venv real
        if [ -L '/home/labs/portal-ggci-dev/venv' ]; then rm '/home/labs/portal-ggci-dev/venv'; fi
        if [ ! -d '/home/labs/portal-ggci-dev/venv' ]; then
            python3 -m venv /home/labs/portal-ggci-dev/venv
            /home/labs/portal-ggci-dev/venv/bin/pip install -r /home/labs/portal-ggci-dev/requirements.txt
        fi
    " "Criando diretórios isolados (Produção e Dev)"

    run_with_stream "
        sudo bash -c '
        if ! grep -q \"\\[Portal_GGCI\\]\" /etc/samba/smb.conf; then
            echo -e \"\\n[Portal_GGCI]\\npath = /home/labs/portal-ggci\\nvalid users = labs\\nread only = no\\nbrowsable = yes\" >> /etc/samba/smb.conf
        fi
        if ! grep -q \"\\[Portal_GGCI_Prod\\]\" /etc/samba/smb.conf; then
            echo -e \"\\n[Portal_GGCI_Prod]\\npath = /home/labs/portal-ggci-prod\\nvalid users = labs\\nread only = no\\nbrowsable = yes\" >> /etc/samba/smb.conf
        fi
        if ! grep -q \"\\[Portal_GGCI_Dev\\]\" /etc/samba/smb.conf; then
            echo -e \"\\n[Portal_GGCI_Dev]\\npath = /home/labs/portal-ggci-dev\\nvalid users = labs\\nread only = no\\nbrowsable = yes\" >> /etc/samba/smb.conf
        fi
        systemctl restart smbd
        '
    " "Configurando e ativando o Servidor Samba (Rede)"

    local smb_pass=$(grep -E '^PWD_SERVER=' .env | cut -d '=' -f2 | tr -d "'\"")
    if [ -n "$smb_pass" ]; then
        run_with_stream "bash -c '(echo \"$smb_pass\"; echo \"$smb_pass\") | sudo smbpasswd -s -a labs'" "Configurando senha do Samba (Rede) para o usuário labs"
    fi

    print_phase "🗄️ FASE 2: ARQUITETURA DE DADOS (MySQL)"
    local pass=$(grep -E '^DB_PASSWORD=' .env | cut -d '=' -f2 | tr -d "'\"")
    local db_name="portal_ggci"
    local db_user="portal_user"
    local mysql_cmd=""
    
    if MYSQL_PWD="${pass}" mysql -u root -e "quit" >/dev/null 2>&1; then mysql_cmd="MYSQL_PWD='${pass}' mysql -u root"
    elif mysql -u root -e "quit" >/dev/null 2>&1; then mysql_cmd="mysql -u root"
    elif sudo mysql -e "quit" >/dev/null 2>&1; then mysql_cmd="sudo mysql"
    else
        log_msg "warn" "Detectada falha no MySQL. Executando protocolo de resgate..."
        run_with_stream "sudo service mysql stop || true; sudo mysqld_safe --skip-grant-tables --skip-networking & sleep 5; sudo mysql -e \"FLUSH PRIVILEGES; ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '${pass}'; FLUSH PRIVILEGES;\"; sudo pkill mysqld; sleep 2; sudo service mysql start" "Resgatando MySQL"
    fi

    # DOIS bancos, não um. Antes só o de produção era criado, e como a FASE 1.5
    # copiava o mesmo .env para os dois ambientes, DEV subia escrevendo no banco de
    # PRODUÇÃO. Separar aqui é o que faz "dev sendo dev e prod sendo prod" valer já
    # na primeira instalação, e não só depois da primeira opção 5.
    run_with_stream "
        sudo mysql -e \"DROP DATABASE IF EXISTS ${db_name}; CREATE DATABASE ${db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\" &&
        sudo mysql -e \"DROP DATABASE IF EXISTS ${db_name}_dev; CREATE DATABASE ${db_name}_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\" &&
        sudo mysql -e \"DROP USER IF EXISTS '${db_user}'@'localhost';\" &&
        sudo mysql -e \"CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${pass}';\" &&
        sudo mysql -e \"GRANT ALL PRIVILEGES ON ${db_name}.* TO '${db_user}'@'localhost';\" &&
        sudo mysql -e \"GRANT ALL PRIVILEGES ON ${db_name}_dev.* TO '${db_user}'@'localhost';\" &&
        sudo mysql -e \"FLUSH PRIVILEGES;\" &&
        export K_U=\"DB_USER\" V_U=\"${db_user}\" &&
        python3 -c \"import os, re; k,v=os.environ.get('K_U'),os.environ.get('V_U'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\\\"{k}='{v}'\\\",c,flags=re.MULTILINE))\"
    " "Alocando tabelas e concedendo privilégios locais"

    print_phase "🧬 FASE 3: MIGRAÇÕES E DADOS INICIAIS"
    run_with_stream "python3 manage.py makemigrations gestao_acessos --noinput && python3 manage.py makemigrations --noinput && python3 manage.py migrate --noinput" "Aplicando Migrações estruturais do Django"
    
    # O snapshot real de usuários não é versionado (contém hash de senha e
    # session_key de pessoas reais, e o repositório é público). Num clone novo ele
    # não existe, então caímos no template — que cria só o 'admin' e exige definir
    # a senha logo em seguida. Sem este fallback, um servidor recém-instalado
    # subiria sem nenhum usuário e ninguém conseguiria entrar.
    if [ -s gestao_acessos_iniciais.json ]; then
        run_with_stream "python3 manage.py loaddata gestao_acessos_iniciais.json" "Restaurando Snapshot de Usuários"
    elif [ -s gestao_acessos_iniciais.example.json ]; then
        run_with_stream "python3 manage.py loaddata gestao_acessos_iniciais.example.json" "Criando usuário admin inicial (template)"
        log_msg "warn" "Instalação nova: defina a senha do admin com 'python3 manage.py changepassword admin'."
    fi

    # O bloco acima migrou o banco de PRODUÇÃO (portal_ggci), que é o do
    # orquestrador. O banco de DEV é outro e precisa das mesmas tabelas, senão o
    # ambiente sobe e quebra no primeiro acesso — "table doesn't exist". Rodamos
    # de dentro do DEV_DIR justamente para que o Django leia o .env de lá.
    local DEV_DIR="/home/labs/portal-ggci-dev"
    if [ -d "$DEV_DIR/venv" ]; then
        local semente="gestao_acessos_iniciais.json"
        [ -s "$DEV_DIR/$semente" ] || semente="gestao_acessos_iniciais.example.json"
        # SUBSHELL `( ... )`: `run_with_stream` executa por `eval`, no shell atual.
        # Sem os parênteses este `cd` (e o `activate` junto) VAZAM para o resto da
        # função — e a FASE 4 seguia rodando de dentro do DEV. O efeito concreto
        # era o `install_watchdog`, que monta o caminho com `${PWD}/scripts`:
        # ele instalava em /usr/local/bin o watchdog do worktree de DEV, com o que
        # estivesse sem commit lá, em vez do que está no clone base.
        run_with_stream "( cd '$DEV_DIR' && . venv/bin/activate && python3 manage.py makemigrations --noinput && python3 manage.py migrate --noinput && { [ -s '$semente' ] && python3 manage.py loaddata '$semente' || true; } )" "Preparando o banco do ambiente DEV"
    fi

    print_phase "🎨 FASE 3.5: ARQUIVOS ESTÁTICOS DOS TRÊS AMBIENTES"

    # POR QUE ISTO PRECISA ESTAR AQUI.
    #
    # `settings.py` usa `CompressedManifestStaticFilesStorage` — o `{% static %}`
    # não monta o caminho sozinho, ele CONSULTA `staticfiles/staticfiles.json`.
    # Esse manifesto é gerado pelo `collectstatic` e a pasta é gitignored
    # (`.gitignore:22`), então ela não vem no clone nem no `git worktree add`:
    # cada ambiente precisa gerar o seu.
    #
    # Até 02/09/2026 a opção 1 não gerava nenhum. O efeito não aparecia ao abrir a
    # tela — com `DEBUG=True` o Django devolve o caminho cru e nem toca no
    # manifesto —, e é justamente por isso que passou tanto tempo despercebido.
    # Onde ele aparecia era em `manage.py test`, que força `DEBUG=False`: TODA
    # tela renderizada estourava `ValueError: Missing staticfiles manifest entry`.
    # Um worktree de DEV recém-criado pela opção 1 nascia com a suíte de testes
    # quebrada por 9 erros que não tinham nada a ver com o código.
    #
    # OS TRÊS, e não só produção: o DEV é onde se roda teste (é ele quem mais
    # precisa), o BASE é de onde a opção 5 faz o rsync, e o PROD é quem serve o
    # Nginx de verdade. A opção 3 já gera o de quem ela levanta, mas ela roda
    # DEPOIS — e o dano acontece antes.
    #
    # SUBSHELL `( ... )` em cada um: `run_with_stream` executa por `eval`, no shell
    # atual, então um `cd` solto aqui contaminaria as fases seguintes.
    run_with_stream "
        ( cd '$BASE_DIR' && . venv/bin/activate && python3 manage.py collectstatic --noinput )
    " "Compilando estáticos do ambiente BASE"

    if [ -d "$DEV_DIR/venv" ]; then
        run_with_stream "
            ( cd '$DEV_DIR' && . venv/bin/activate && python3 manage.py collectstatic --noinput )
        " "Compilando estáticos do ambiente DEV"
    fi

    if [ -d '/home/labs/portal-ggci-prod/venv' ]; then
        run_with_stream "
            ( cd '/home/labs/portal-ggci-prod' && . venv/bin/activate && python3 manage.py collectstatic --noinput )
        " "Compilando estáticos do ambiente PRODUÇÃO"
    fi

    print_phase "🛡️ FASE 4: AGENDAMENTO E AUTO-RECUPERAÇÃO"

    run_with_stream "sudo systemctl enable cron && sudo service cron start && crontab scripts/cron.conf 2>/dev/null || true" "Ativando Agendador de Tarefas Automático (Cron)"

    # O cron levanta a produção (@reboot e 00:01, via start_server.py, que
    # dispara a opção 3). O watchdog cobre o intervalo entre esses ciclos: se o
    # Funnel se desanunciar às 09h, sem ele o site fica fora até a virada do dia.
    install_watchdog

    run_with_stream "grep -q 'default-shell /bin/bash' ~/.tmux.conf || echo 'set-option -g default-shell /bin/bash' >> ~/.tmux.conf" "Configurando bash como terminal padrão do Tmux"

    # O setup terminou, mas nada foi levantado ainda: quem sobe a produção é a
    # opção 3. Retomamos a vigilância e deixamos a marca de produção ativa
    # desligada, para o watchdog não tentar erguer o que ainda não existe.
    watchdog_marcar_prod inativa
    watchdog_retomar

    echo -e "   ${C_GREE}${C_BOLD}✨ SETUP FINALIZADO COM SUCESSO! ✨${C_RESET}"
    wait_key
}

# --------------------------------------------------------------------------
# 5. ROBÔS E AUTOMAÇÕES (Arquivos Temporários Seguros)
# --------------------------------------------------------------------------
function run_robot_polichat() {
    print_ovg_logo
    print_phase "🤖 ROBÔ DE EXTRAÇÃO: POLICHAT"
    
    # 💡 Técnica Sênior: Escrever o script num arquivo real limpa bugs de aspas do Bash
    cat << 'EOF' > .tmp_robot.py
import sys, os
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
import django
django.setup()

from apps.dashboards.dash_polichat.services.polichat_extrator import executar_pipeline
try:
    sucesso = executar_pipeline()
    sys.exit(0 if sucesso else 1) # Se for False, sai com código de erro 1
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

    run_with_stream "python3 .tmp_robot.py" "Acionando Motor de Extração de Conversas..."
    local exit_code=$?
    rm -f .tmp_robot.py # Limpa a sujeira
    
    if [ $exit_code -eq 0 ]; then 
        log_msg "ok" "Pipeline PoliChat executada com sucesso."
        show_output_folder "dados_polichat/analise_anual"
    else
        log_msg "err" "A Pipeline falhou ou foi abortada (Timeout/Erro no Metabase)."
    fi
    wait_key
}

function run_robot_documentos() {
    print_ovg_logo
    print_phase "🧠 ROBÔ DE EXTRAÇÃO: DOCUMENTOS E PAGAMENTOS (IA)"

    # Aqui existia um .tmp_robot.py que chamava extrator/consolidador/ggci
    # direto, sem processo_id. Desde que a extração passou a isolar cada
    # execução em dados/processamento/proc_<id>/, essa chamada morria em
    # "ValueError: O processo_id é obrigatório." — tanto neste menu quanto no
    # cron, que digitava a opção 7 por stdin. O comando abaixo é o mesmo
    # caminho da tela web (cria o registro e delega ao executar_motor_ia) e
    # imprime só o resumo por etapa; o detalhado fica em
    # apps/automacoes/analise_ia/cron/detalhado_<data>.log.
    # --completo porque este menu promete o robô inteiro (extração no site,
    # consolidação e relatório). O cron, por outro lado, chama este mesmo comando
    # SEM a flag: lá só interessa deixar os Parquet do dia prontos.
    run_with_stream "python3 manage.py cron_analise_ia --completo" "Acionando Auditoria Cognitiva de Documentos..."
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then 
        log_msg "ok" "Pipeline IA executada com sucesso."
        # O relatório final não fica mais em dados/dados_analise_ia: cada
        # execução salva dentro da própria pasta proc_<id>. O caminho exato sai
        # na linha CONCLUIDO do resumo, logo acima.
        show_output_folder "apps/automacoes/analise_ia/dados/processamento"
    else
        log_msg "err" "A Pipeline falhou ou encontrou erros de execução."
    fi
    wait_key
}

# --------------------------------------------------------------------------
# 6. MONITORAMENTO E USUÁRIOS
# --------------------------------------------------------------------------
function list_logged_users() {
    print_ovg_logo
    print_phase "👥 USUÁRIOS LOGADOS ATUALMENTE"
    
    cat << 'EOF' > .tmp_users.py
import sys, os
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
import django
django.setup()

from django.contrib.sessions.models import Session
from django.utils import timezone
from apps.inicio.gestao_acessos.models import Usuario

now = timezone.now()
active_sessions = Session.objects.filter(expire_date__gt=now)

usuarios_online = {}
for session in active_sessions:
    data = session.get_decoded()
    user_id = data.get('_auth_user_id')
    if user_id:
        try:
            u = Usuario.objects.get(id=user_id)
            if u.session_key == session.session_key:
                usuarios_online[u.usuario] = u
        except Usuario.DoesNotExist:
            pass

if not usuarios_online:
    print("Nenhum usuário ativo no momento.")
else:
    print(f"{'NOME DO USUÁRIO':<35} | {'LOGIN':<30} | {'PERFIL':<15}")
    print("─" * 85)
    for login, u in usuarios_online.items():
        print(f"{u.nome[:34]:<35} | {login[:29]:<30} | {u.perfil.title():<15}")
EOF

    run_with_stream "python3 .tmp_users.py" "Varrendo sessões ativas no banco de dados..."
    rm -f .tmp_users.py
    wait_key
}

function server_monitoring() {
    print_ovg_logo
    print_phase "📊 MONITORAMENTO DE SAÚDE DO SERVIDOR"
    run_with_stream "python3 manage.py monitorar_servidor" "Coletando métricas de hardware..."
    wait_key
}

# --------------------------------------------------------------------------
# 6.5. SERVIDOR WEB OTIMIZADO (NGINX + GUNICORN)
# --------------------------------------------------------------------------
function run_server() {
    print_ovg_logo
    print_phase "🚀 INICIANDO SERVIDOR WEB OTIMIZADO"

    # Pausa a vigilância durante a troca. Cobre de uma vez os quatro caminhos
    # que chegam aqui: esta opção no menu, a opção 5 (que termina mandando "3"
    # no tmux) e o start_server.py do cron (@reboot e 00:01), que faz o mesmo.
    # Por isso a proteção mora nesta função, e não em cada chamador.
    watchdog_pausar 15

    sync_migrations

    run_with_stream "python3 manage.py collectstatic --noinput" "Compilando arquivos estáticos para o Nginx"
    
    log_msg "info" "Configurando Nginx Proxy..."
    check_sudo
    cat << 'EOF' > .tmp_nginx.conf
server {
    listen 8000;
    server_name _;
    
    # Otimizações drásticas para Tailscale e túneis
    sendfile off;
    tcp_nopush on;
    tcp_nodelay on;
    
    # Compressão na camada HTTP.
    # Otimizado: Comprime apenas texto e CSV. Não comprime XLSX/ZIP pois remove o Content-Length e sobrecarrega a CPU.
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript text/csv application/csv;

    location /protected-media/ {
        internal;
        alias PWD_PLACEHOLDER/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        
        # Aumentar buffers de proxy para não gargalar pacotes
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        send_timeout 300s;
    }

    client_max_body_size 0;
}
EOF

    # Substitui o placeholder pelo diretório atual
    sed -i "s|PWD_PLACEHOLDER|$PWD|g" .tmp_nginx.conf

    # Garantir que o Nginx (www-data) possa acessar a pasta home do usuário 'labs'
    chmod a+x /home/labs
    
    log_msg "info" "Desligando instâncias antigas de Produção..."
    check_sudo
    if [ -f /tmp/gunicorn.pid ]; then
        sudo kill $(cat /tmp/gunicorn.pid) 2>/dev/null || true
    fi
    sudo pkill -f 'gunicorn.*8001' || true
    sudo pkill -f "${PWD}/manage.py loop_polichat" || true
    sudo pkill -f 'tailscale funnel.*8000' || true
    sudo pkill -f 'cloudflared.*8000' || true
    sudo fuser -k 8000/tcp 2>/dev/null || true
    sudo fuser -k 8001/tcp 2>/dev/null || true
    rm -f /tmp/gunicorn.pid /tmp/cf_tunnel.log /tmp/cf_accel.json 2>/dev/null
    sleep 2
    
    run_with_stream "sudo rm -f /etc/nginx/sites-available/ggci /etc/nginx/sites-enabled/ggci && sudo cp .tmp_nginx.conf /etc/nginx/sites-available/portal_ggci && sudo ln -sf /etc/nginx/sites-available/portal_ggci /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default && sudo service nginx restart" "Aplicando blindagem Nginx na porta 8000"
    rm -f .tmp_nginx.conf
    
    echo ""
    echo -e "   ${C_GREE}${C_BOLD}✔ O Servidor está ONLINE e Blindado!${C_RESET}"
    echo -e "   ${C_CYAN}➤ Acesso Local Seguro (Nginx):${C_RESET} ${C_WHIT}http://127.0.0.1:8000${C_RESET}"
    echo -e "   ${C_PURP}➤ Acesso Público para Usuários:${C_RESET} ${C_WHIT}(Aguarde, o link HTTPS aparecerá logo abaixo)${C_RESET}"
    echo -e "   ${C_YELL}Pressione CTRL+C para derrubar tudo e voltar ao menu.${C_RESET}"
    echo ""
    
    log_msg "info" "Abrindo Túnel Tailscale na porta 8000..."
    sudo tailscale funnel --bg --yes 8000
    
    sleep 2 # Dá um tempinho para o Tailscale processar
    
    log_msg "info" "Ativando Acelerador Cloudflare em Background..."
    python3 - << 'EOF' &
import subprocess, re, json, sys
def main():
    with open("/tmp/cf_tunnel.log", "w") as logfile:
        proc = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', 'http://127.0.0.1:8000'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        url = None
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break
            if line:
                logfile.write(line)
                logfile.flush()
                if not url:
                    match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
                    if match and match.group(1) != 'https://api.trycloudflare.com':
                        url = match.group(1)
                        with open('/tmp/cf_accel.json', 'w') as f: json.dump({'url': url}, f)
        proc.wait()
if __name__ == '__main__': main()
EOF
    local cf_pid=$!

    # Aguarda 5 segundos e tenta ler o link do Cloudflare
    sleep 5
    if [ -f /tmp/cf_accel.json ]; then
        local cf_url=$(python3 -c "import json; print(json.load(open('/tmp/cf_accel.json'))['url'])")
        echo -e "   ${C_GREE}➤ Acesso Público (Cloudflare):${C_RESET} ${C_WHIT}${cf_url}${C_RESET}"
    fi

    # Roda o Gunicorn em background
    gunicorn portal_ggci.wsgi:application --bind 127.0.0.1:8001 --workers 4 --threads 8 --worker-class gthread --timeout 300 --pid /tmp/gunicorn.pid &
    local guni_pid=$!
    
    log_msg "info" "Iniciando Robô Contínuo do PoliChat em background..."
    python3 "${PWD}/manage.py" loop_polichat > /dev/null 2>&1 &
    local loop_pid=$!

    # A pilha está de pé: declara produção ativa e devolve a vigilância. A
    # ordem importa — marcar antes de retomar evita a janela em que o watchdog
    # acorda, vê o lock removido e a marca ainda ausente, e decide não agir.
    watchdog_marcar_prod ativa
    watchdog_retomar
    log_msg "ok" "Watchdog de acesso público vigiando (systemd, ciclo de 60s)."

    # Prepara a armadilha (trap) para interceptar o CTRL+C.
    # O watchdog_marcar_prod inativa é o primeiro passo: sem ele, o desligamento
    # manual seria lido como pane e a produção voltaria sozinha em ~2 minutos.
    trap 'echo -e "\n   ${C_YELL}[!] Desligando Servidores, Túneis e Robôs...${C_RESET}"; watchdog_marcar_prod inativa; watchdog_pausar 5; sudo pkill -f "tailscale funnel.*8000" 2>/dev/null; sudo kill $guni_pid 2>/dev/null; sudo kill -TERM $cf_pid 2>/dev/null; sudo kill $loop_pid 2>/dev/null; sudo fuser -k 8000/tcp 2>/dev/null; sudo fuser -k 8001/tcp 2>/dev/null; sudo pkill -f "cloudflared.*8000" 2>/dev/null; rm -f /tmp/gunicorn.pid /tmp/cf_tunnel.log /tmp/cf_accel.json 2>/dev/null; sleep 1' SIGINT
    
    # Aguarda a execução dos processos
    wait $guni_pid 2>/dev/null
    wait $cf_pid 2>/dev/null
    
    # Restaura o trap padrão do Bash
    trap - SIGINT
    
    echo ""
    log_msg "warn" "Servidor Desligado."
    wait_key
}

# --------------------------------------------------------------------------
# 6.6. AMBIENTE DE DESENVOLVIMENTO (LIVE RELOAD)
# --------------------------------------------------------------------------
function run_dev_server() {
    print_ovg_logo
    print_phase "🛠️  AMBIENTE DE DESENVOLVIMENTO (LIVE RELOAD)"
    
    log_msg "info" "Suas alterações no código serão recarregadas automaticamente!"
    log_msg "info" "A Produção NÃO será afetada (rodando em paralelo)."
    
    check_sudo
    
    # ATENÇÃO: o DEV não chama watchdog_pausar nem watchdog_retomar, e isso é
    # deliberado. Ele vive na 8080, enquanto o watchdog só observa 8000/8001 —
    # nada aqui pode confundi-lo. Mais importante: o start_server.py sobe a
    # produção (opção 3) e, 15s depois, o DEV (opção 4). Se esta função
    # retomasse a vigilância, ela arrancaria o lock que a produção ainda pode
    # estar usando para terminar de subir, e o watchdog atacaria uma pilha
    # ainda pela metade. Quem pausa é quem derruba a produção.
    log_msg "info" "Desligando instâncias antigas de DEV..."
    sudo fuser -k 8080/tcp 2>/dev/null || true
    sudo pkill -f 'manage.py runserver.*8080' || true
    sudo pkill -f "${PWD}/manage.py loop_polichat" || true
    sudo pkill -f 'cloudflared.*8080' || true
    rm -f /tmp/cf_tunnel_dev.log /tmp/cf_accel_dev.json 2>/dev/null
    sleep 1
    
    local local_ip=$(hostname -I | awk '{print $1}')
    echo -e "   ${C_CYAN}➤ Acesso Local Dev:${C_RESET} ${C_WHIT}http://${local_ip}:8080${C_RESET}"
    echo -e "   ${C_PURP}➤ Acesso Público Dev:${C_RESET} ${C_WHIT}(Aguarde o link do Cloudflare...)${C_RESET}"
    echo -e "   ${C_YELL}Pressione CTRL+C para derrubar apenas o DEV.${C_RESET}"
    echo ""
    
    log_msg "info" "Ativando Túnel Cloudflare para DEV em Background..."
    python3 - << 'EOF' &
import subprocess, re, json, sys
def main():
    with open("/tmp/cf_tunnel_dev.log", "w") as logfile:
        proc = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', 'http://127.0.0.1:8080'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        url = None
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break
            if line:
                logfile.write(line)
                logfile.flush()
                if not url:
                    match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
                    if match:
                        url = match.group(1)
                        with open('/tmp/cf_accel_dev.json', 'w') as f: json.dump({'url': url}, f)
        proc.wait()
if __name__ == '__main__': main()
EOF
    local cf_pid=$!

    # Aguarda o Cloudflare gerar o link (polling dinâmico de até 15 segundos)
    local timeout=15
    local elapsed=0
    while [ ! -f /tmp/cf_accel_dev.json ] && [ $elapsed -lt $timeout ]; do
        sleep 1
        elapsed=$((elapsed+1))
    done

    if [ -f /tmp/cf_accel_dev.json ]; then
        local cf_url=$(python3 -c "import json; print(json.load(open('/tmp/cf_accel_dev.json'))['url'])")
        echo -e "   ${C_GREE}➤ Link DEV Público (Cloudflare):${C_RESET} ${C_WHIT}${cf_url}${C_RESET}"
    else
        echo -e "   ${C_YELL}➤ Aviso: O túnel Cloudflare demorou para responder. Verifique /tmp/cf_tunnel_dev.log${C_RESET}"
    fi

    # Gera E aplica as migrações antes de servir. Antes só gerava, em silêncio:
    # o banco de DEV ficava defasado do model e a falha só aparecia na tela.
    sync_migrations

    # ESTÁTICOS DO DEV — e não é para o runserver, que não precisa deles.
    #
    # Com `DEBUG=True` o `{% static %}` devolve o caminho cru e nunca abre o
    # manifesto: a tela abriria igual sem isto. Quem precisa é `manage.py test`,
    # que força `DEBUG=False` e aí passa a consultar `staticfiles/staticfiles.json`
    # de verdade — e DEV é justamente o ambiente onde se roda teste.
    #
    # A opção 1 gera o manifesto na instalação; este passo é o que impede que ele
    # ENVELHEÇA. Todo arquivo novo em `static/` nasce fora dele, e a primeira
    # renderização sob teste estoura `Missing staticfiles manifest entry` —
    # apontando para o arquivo novo, que é sintoma, não causa. Regenerar ao subir
    # o DEV custa ~3s e fecha o buraco no ponto em que ele se abre.
    run_with_stream "python3 manage.py collectstatic --noinput" "Atualizando estáticos do DEV (necessários para 'manage.py test')"

    # Roda o servidor do Django no modo DEV
    python3 manage.py runserver 0.0.0.0:8080 &
    local dj_pid=$!
    
    log_msg "info" "Iniciando Robô Contínuo do PoliChat em background..."
    python3 "${PWD}/manage.py" loop_polichat > /dev/null 2>&1 &
    local loop_pid=$!
    
    # Trap exclusivo do DEV
    trap 'echo -e "\n   ${C_YELL}[!] Desligando Ambiente DEV e Robôs...${C_RESET}"; sudo kill $dj_pid 2>/dev/null; sudo kill -TERM $cf_pid 2>/dev/null; sudo kill $loop_pid 2>/dev/null; sudo fuser -k 8080/tcp 2>/dev/null; sudo pkill -f "cloudflared.*8080" 2>/dev/null; rm -f /tmp/cf_tunnel_dev.log /tmp/cf_accel_dev.json 2>/dev/null; sleep 1' SIGINT
    
    wait $dj_pid 2>/dev/null
    wait $cf_pid 2>/dev/null
    
    trap - SIGINT
    echo ""
    log_msg "warn" "Ambiente de Desenvolvimento Desligado."
    wait_key
}

# --------------------------------------------------------------------------
# 6.7. HOT RELOAD EM PRODUÇÃO
# --------------------------------------------------------------------------
function sync_production() {
    print_ovg_logo
    print_phase "🔄 ATUALIZAR PRODUÇÃO COM CÓDIGO DO DEV"
    
local PROD_DIR="/home/labs/portal-ggci-prod"
    local MAIN_DIR="/home/labs/portal-ggci"
    local CURRENT_DIR=$(pwd)

    log_msg "info" "Isso derrubará o servidor temporariamente para uma atualização limpa."
    check_sudo
    
    # Passphrase da CHAVE SSH — coisa distinta da senha do servidor. Até 01/09/2026
    # este trecho lia PWD_SERVER, assumindo que fossem iguais; quando a passphrase
    # da chave foi rotacionada, o push automático passaria a falhar em silêncio.
    # O fallback para PWD_SERVER mantém instalações antigas funcionando.
    local pass=$(grep -E '^SSH_KEY_PASSPHRASE=' .env | cut -d '=' -f2- | tr -d "'\"")
    [ -z "$pass" ] && pass=$(grep -E '^PWD_SERVER=' .env | cut -d '=' -f2- | tr -d "'\"")
    if [ -n "$pass" ]; then
        echo -e "#!/bin/bash
echo \"$pass\"" > /tmp/askpass_portal.sh
        chmod +x /tmp/askpass_portal.sh
        export SSH_ASKPASS=/tmp/askpass_portal.sh
        export DISPLAY=:0
        export SSH_ASKPASS_REQUIRE=force
    fi
    
    # Janela longa de propósito: derruba a pilha, faz merge, rsync e religa o
    # tmux. Note que NÃO chamamos watchdog_retomar no fim desta função — quem
    # devolve a vigilância é a opção 3, disparada no tmux lá embaixo, depois de
    # a produção estar realmente de pé. Retomar aqui abriria uma janela entre o
    # send-keys e a subida do Gunicorn. Se o tmux falhar, o lock expira sozinho
    # e o watchdog assume o conserto.
    watchdog_pausar 20

    log_msg "info" "Desligando servidor de Produção e Túneis atuais..."
    sudo pkill -f 'gunicorn.*8001' || true
    sudo pkill -f 'tailscale funnel.*8000' || true
    sudo fuser -k 8000/tcp 2>/dev/null || true
    sudo fuser -k 8001/tcp 2>/dev/null || true
    rm -f /tmp/gunicorn.pid /tmp/cf_tunnel.log /tmp/cf_accel.json 2>/dev/null
    tmux kill-session -t prod 2>/dev/null || true
    sleep 1

    log_msg "info" "Extraindo lista de usuários mais recente da Produção..."
    cd "$PROD_DIR"
    run_with_stream "python3 manage.py dumpdata gestao_acessos.Usuario --indent 4 | python3 -c 'import sys, json; d=json.load(sys.stdin); [item.get(\"fields\", {}).pop(\"last_login\", None) for item in d]; print(json.dumps(d, indent=4))' > .tmp_backup.json && mv .tmp_backup.json gestao_acessos_iniciais.json || { rm -f .tmp_backup.json; false; }" "Gerando snapshot de segurança do banco PROD"

    # Espelha o snapshot de usuários de PROD para DEV por CÓPIA, sem passar pelo Git.
    # Antes daqui saía um commit + push automático — era ele que publicava nome,
    # login, hash de senha e session_key de pessoas reais num repositório público.
    log_msg "info" "Sincronizando usuários de Produção para o ambiente DEV..."
    local DEV_DIR="/home/labs/portal-ggci-dev"
    if [ -d "$DEV_DIR" ] && [ -s "$PROD_DIR/gestao_acessos_iniciais.json" ]; then
        cp -f "$PROD_DIR/gestao_acessos_iniciais.json" "$DEV_DIR/"
        log_msg "ok" "Snapshot de usuários espelhado em DEV (local, não versionado)."
    fi

    log_msg "info" "Navegando para a pasta do Repositório Principal (MAIN)..."
    cd "$MAIN_DIR" || { log_msg "err" "Não foi possível encontrar a pasta raiz do projeto."; watchdog_retomar; return; }

    log_msg "info" "Garantindo que a raiz está na branch MAIN..."
    git checkout main > /dev/null 2>&1
    
    log_msg "info" "Baixando o código mais recente do Github (origin/dev)..."
    if ! setsid git pull origin dev --no-edit; then
        log_msg "err" "Falha ao mesclar o código do DEV. Pode haver conflitos."
        rm -f /tmp/askpass_portal.sh
        # A produção antiga continua no ar (nada foi sobrescrito ainda), então
        # devolvemos a vigilância em vez de esperar o lock expirar.
        watchdog_retomar
        return
    fi
    
    log_msg "info" "Sincronizando a branch MAIN com o Github..."
    if ! setsid git push origin main; then
        log_msg "warn" "Sincronizando divergências com o servidor remoto..."
        setsid git pull origin main --no-edit
        setsid git push origin main
    fi
    
    rm -f /tmp/askpass_portal.sh

    # Migrações rodam aqui, no MAIN, e não por acaso: este é o único momento em
    # que o código novo já chegou (git pull acima) e o rsync ainda não partiu.
    # Como o MAIN compartilha o banco com a PRODUÇÃO, a estrutura é atualizada
    # agora, e os arquivos de migração recém-gerados seguem no rsync abaixo —
    # sem isso eles nunca existiriam do lado de lá, por serem ignorados no git.
    sync_migrations

    log_msg "info" "Atualizando a pasta de PRODUÇÃO com os novos arquivos..."
    rsync -a --exclude 'venv' --exclude '.git' --exclude '.env' "$MAIN_DIR/" "$PROD_DIR/"

    # O watchdog roda de /usr/local/bin, fora do alcance do rsync. Sem
    # reinstalar aqui, uma correção feita em scripts/ chegaria em produção como
    # arquivo mas nunca entraria em vigor. Estamos no MAIN_DIR, já com o código
    # novo do git pull acima — é o momento certo.
    install_watchdog

    # Sincroniza as credenciais: copia o .env do DEV (fonte da verdade) para PROD,
    # ajustando apenas os valores que são diferentes por natureza entre os ambientes.
    log_msg "info" "Sincronizando credenciais do DEV para PRODUÇÃO..."
    cp -f "$DEV_DIR/.env" "$PROD_DIR/.env"
    sed -i "s|^DEBUG=True|DEBUG=False|" "$PROD_DIR/.env"
    sed -i "s|^DB_NAME='portal_ggci_dev'|DB_NAME='portal_ggci'|" "$PROD_DIR/.env"

    # O dump já foi feito no início da função.
    # Copiar o JSON mais recente para o PROD (já está lá, mas o rsync pode ter sobrescrito)
    cp -f "$DEV_DIR/gestao_acessos_iniciais.json" "$PROD_DIR/" 2>/dev/null || true

    cd "$CURRENT_DIR"
    
    log_msg "ok" "Produção atualizada com sucesso!"
    
    log_msg "info" "Limpando as pastas 'dados' e 'logs' de todos os aplicativos em Produção..."
    run_with_stream "find \"$PROD_DIR/apps\" -type d \\( -name \"dados\" -o -name \"logs\" \\) | xargs -I {} sh -c 'rm -rf \"{}\"/* 2>/dev/null || true'" "Apagando conteúdos temporários e logs"
    
    log_msg "info" "Religando o Tmux de Produção do zero automaticamente..."
    tmux new-session -d -s prod /bin/bash
    tmux send-keys -t prod "cd $PROD_DIR" C-m
    tmux send-keys -t prod ". venv/bin/activate && bash portal.sh" C-m
    sleep 3
    tmux send-keys -t prod "3" C-m
    
    log_msg "ok" "Servidor de Produção foi completamente reiniciado e está voltando online em background!"
    wait_key
}


# --------------------------------------------------------------------------
# 7. UTILITÁRIOS (BACKUP E DESTRUIÇÃO)
# --------------------------------------------------------------------------
function user_backup() {
    print_ovg_logo
    print_phase "💾 SNAPSHOT DE SEGURANÇA"
    run_with_stream "python3 manage.py dumpdata gestao_acessos.Usuario --indent 4 | python3 -c 'import sys, json; d=json.load(sys.stdin); [item.get(\"fields\", {}).pop(\"last_login\", None) for item in d]; print(json.dumps(d, indent=4))' > .tmp_backup.json && mv .tmp_backup.json gestao_acessos_iniciais.json || { rm -f .tmp_backup.json; false; }" "Extraindo e formatando JSON de Usuários Atuais"
    
    log_msg "info" "Sincronizando backup com o Github..."
    
    # Passphrase da CHAVE SSH — coisa distinta da senha do servidor. Até 01/09/2026
    # este trecho lia PWD_SERVER, assumindo que fossem iguais; quando a passphrase
    # da chave foi rotacionada, o push automático passaria a falhar em silêncio.
    # O fallback para PWD_SERVER mantém instalações antigas funcionando.
    local pass=$(grep -E '^SSH_KEY_PASSPHRASE=' .env | cut -d '=' -f2- | tr -d "'\"")
    [ -z "$pass" ] && pass=$(grep -E '^PWD_SERVER=' .env | cut -d '=' -f2- | tr -d "'\"")
    if [ -n "$pass" ]; then
        echo -e "#!/bin/bash\necho \"$pass\"" > /tmp/askpass_portal.sh
        chmod +x /tmp/askpass_portal.sh
        export SSH_ASKPASS=/tmp/askpass_portal.sh
        export DISPLAY=:0
        export SSH_ASKPASS_REQUIRE=force
    fi

    # O backup NÃO vai para o Git. O arquivo carrega nome, login, hash de senha e
    # session_key de pessoas reais, e este repositório é público — publicá-lo
    # entrega 23 hashes para ataque de dicionário offline, sem limite de tentativas.
    # O arquivo fica no servidor e é espelhado entre os ambientes por cópia.
    # Quem clonar do zero parte do gestao_acessos_iniciais.example.json.
    if [ -s gestao_acessos_iniciais.json ]; then
        log_msg "ok" "Backup de usuários atualizado localmente (não versionado)."

        # Espelha para os outros ambientes por cópia, mantendo todos com a mesma base.
        local current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
        if [ "$current_branch" == "main" ]; then
            for destino in /home/labs/portal-ggci-dev /home/labs/portal-ggci-prod; do
                if [ -d "$destino" ]; then
                    cp -f gestao_acessos_iniciais.json "$destino/"
                    log_msg "ok" "Backup espelhado em ${destino##*/}."
                fi
            done
        fi
    else
        log_msg "warn" "Backup não gerado ou vazio — nada a espelhar."
    fi
    rm -f /tmp/askpass_portal.sh
    wait_key
}

function clean_logs() {
    print_ovg_logo
    print_phase "🧹 LIMPEZA DE ARQUIVOS DE LOG (.log)"
    
    if ask_confirm "Deseja remover todos os arquivos .log do projeto?"; then
        run_with_stream "find . -type f -name '*.log' -exec rm -f {} +" "Apagando arquivos .log..."
        log_msg "ok" "Todos os arquivos .log foram removidos com sucesso!"
    else
        echo ""
        log_msg "info" "Operação abortada."
    fi
    wait_key
}

function clean_proc_data() {
    print_ovg_logo
    print_phase "🗑️  LIMPEZA DE PASTAS DE PROCESSAMENTO (proc)"
    
    if ask_confirm "Deseja remover todas as pastas 'proc' dos diretórios de dados?"; then
        run_with_stream "find . -type d -name 'proc*' -path '*/dados/*' -exec rm -rf {} +" "Apagando diretórios proc das pastas de dados..."
        log_msg "ok" "Pastas 'proc' removidas com sucesso!"
    else
        echo ""
        log_msg "info" "Operação abortada."
    fi
    wait_key
}

function list_first_parquets() {
    print_ovg_logo
    print_phase "🔍 RASTREIO DE GERAÇÃO DE PARQUETS (PRIMEIRO DO DIA)"
    
    echo -e "   ${C_CYAN}➤ Buscando o primeiro parquet gerado hoje para cada App...${C_RESET}\n"
    
    local today=$(date +%Y-%m-%d)
    local found_any=false
    
    for app_dir in apps/*; do
        if [ -d "$app_dir" ]; then
            local app_name=$(basename "$app_dir")
            local first_parquet=$(find "$app_dir" -type f -name "*.parquet" -newermt "$today" -printf '%T+ %u %p\n' 2>/dev/null | sort | head -n 1)
            
            if [ -n "$first_parquet" ]; then
                local p_time=$(echo "$first_parquet" | awk '{print $1}')
                local p_user=$(echo "$first_parquet" | awk '{print $2}')
                local p_path=$(echo "$first_parquet" | awk '{print $3}')
                
                # Identificando quem gerou:
                local gerador="Usuários (Desconhecido)"
                if [[ "$PWD" == *"-dev"* ]]; then
                    gerador="Usuários (Dev)"
                elif [[ "$PWD" == *"-prod"* ]]; then
                    gerador="Usuários (Prod)"
                else
                    gerador="Usuários do Sistema"
                fi
                
                # Checando se foi o Cron (Bot) pelo horário de pico de execução (entre 00:00 e 00:30)
                # Extrai apenas a hora e o minuto
                local p_hour_min=$(date -d "${p_time%+*}" +%H:%M 2>/dev/null || echo "12:00")
                if [[ "$p_hour_min" > "00:00" && "$p_hour_min" < "00:45" ]]; then
                    gerador="Bot Automático (Cron)"
                fi
                
                echo -e "   ${C_PURP}App:${C_RESET} ${C_WHIT}${app_name}${C_RESET}"
                echo -e "      ${C_GRAY}Arquivo:${C_RESET} ${p_path}"
                echo -e "      ${C_GRAY}Gerador:${C_RESET} ${C_YELL}${gerador}${C_RESET}"
                echo -e "      ${C_GRAY}Data e Hora:${C_RESET} ${C_GREE}${p_time}${C_RESET}"
                echo ""
                found_any=true
            fi
        fi
    done
    
    if [ "$found_any" = false ]; then
        log_msg "info" "Nenhum arquivo parquet foi gerado no dia de hoje."
    fi
    
    wait_key
}

function teardown_full() {
    print_ovg_logo
    print_phase "🧹 DESTRUIÇÃO TOTAL DO AMBIENTE"
    echo -e "   ${C_REDD}Isso removerá o MySQL, Banco de Dados, Ambientes Virtuais e Dependências.${C_RESET}\n"
    
    if ask_confirm "Tem certeza que deseja apagar TUDO e formatar o servidor?"; then
        check_sudo
        echo ""

        # Primeiro de tudo: silencia e remove o watchdog. Se ele sobrevivesse à
        # destruição, passaria o resto da vida tentando reerguer um Gunicorn
        # cujo venv acabou de ser apagado, a cada 60 segundos.
        watchdog_pausar 60
        watchdog_marcar_prod inativa
        run_with_stream "
            sudo systemctl disable --now ggci-watchdog.timer 2>/dev/null || true;
            sudo rm -f /etc/systemd/system/ggci-watchdog.timer /etc/systemd/system/ggci-watchdog.service /usr/local/bin/ggci-watchdog.sh;
            sudo systemctl daemon-reload 2>/dev/null || true;
            sudo rm -rf /var/lib/ggci-watchdog /var/log/ggci-watchdog.log
        " "Removendo watchdog de auto-recuperação"

        run_with_stream "sudo pkill -f 'gunicorn.*8001' || true; sudo pkill -f 'manage.py runserver.*8080' || true; sudo pkill -f 'manage.py loop_polichat' || true; sudo pkill -f 'cloudflared.*8000' || true; sudo pkill -f 'cloudflared.*8080' || true; sudo pkill -f 'tailscale funnel.*8000' || true; tmux kill-session -t prod 2>/dev/null || true; tmux kill-session -t dev 2>/dev/null || true" "Desligando todos os processos, túneis e sessões (Tmux)"
        run_with_stream "crontab -r 2>/dev/null || true" "Removendo agendamentos do Cron"
        run_with_stream "sudo systemctl stop mysql nginx smbd || true" "Parando Serviços (MySQL, Nginx, Samba)"
        run_with_stream "sudo DEBIAN_FRONTEND=noninteractive apt-get purge -yqq mysql-server mysql-client mysql-common nginx nginx-common samba samba-common smbclient; sudo apt-get autoremove -yqq; sudo rm -rf /etc/mysql /var/lib/mysql /var/log/mysql /etc/nginx /etc/samba" "Vaporizando Serviços e Dependências"
        deactivate 2>/dev/null || true
        run_with_stream "rm -rf .env db.sqlite3 venv; sudo rm -rf /home/labs/portal-ggci-prod /home/labs/portal-ggci-dev; git worktree prune 2>/dev/null || true" "Apagando configurações, ambientes virtuais e pastas prod/dev"
        
        echo ""
        log_msg "ok" "O Sistema foi neutralizado."
    else
        echo ""
        log_msg "info" "Operação abortada."
    fi
    wait_key
}

# --------------------------------------------------------------------------
# MENU PRINCIPAL (LOOP ANTI-FALHAS)
# --------------------------------------------------------------------------
while true; do
    print_ovg_logo
    
    echo -e "   ${C_CYAN}${C_BOLD} 1 ${C_RESET} ${C_WHIT}📦 Instalação e Atualização Completa${C_RESET}"
    echo -e "   ${C_PURP}${C_BOLD} 2 ${C_RESET} ${C_WHIT}💾 Salvar Backup de Usuários (JSON)${C_RESET}"
    echo ""
    echo -e "   ${C_GREE}${C_BOLD} 3 ${C_RESET} ${C_WHIT}🚀 Iniciar Servidor Web Otimizado de PRODUÇÃO (Nginx + Gunicorn)${C_RESET}"
    echo -e "   ${C_YELL}${C_BOLD} 4 ${C_RESET} ${C_WHIT}🛠️  Iniciar Ambiente de DESENVOLVIMENTO (Live Reload / Link Isolado)${C_RESET}"
    echo -e "   ${C_CYAN}${C_BOLD} 5 ${C_RESET} ${C_WHIT}🔄 Atualizar PRODUÇÃO com base no DEV (Atualização Limpa Offline)${C_RESET}"
    echo ""
    echo -e "   ${C_GREE}${C_BOLD} 6 ${C_RESET} ${C_WHIT}🤖 Executar Robô de Extração: PoliChat${C_RESET}"
    echo -e "   ${C_GREE}${C_BOLD} 7 ${C_RESET} ${C_WHIT}🧠 Executar Robô de Extração: Documentos e Pagamentos (IA)${C_RESET}"
    echo ""
    echo -e "   ${C_CYAN}${C_BOLD} 8 ${C_RESET} ${C_WHIT}👥 Listar Usuários Logados Atualmente${C_RESET}"
    echo -e "   ${C_GRAY}${C_BOLD} 9 ${C_RESET} ${C_WHIT}📊 Monitorar Saúde do Servidor (CPU/RAM/Disco)${C_RESET}"
    echo ""
    echo -e "   ${C_YELL}${C_BOLD} 10 ${C_RESET} ${C_WHIT}🧹 Limpar arquivos .log do Projeto${C_RESET}"
    echo -e "   ${C_YELL}${C_BOLD} 11 ${C_RESET} ${C_WHIT}🗑️  Apagar pastas de processamento (proc) dos dados${C_RESET}"
    echo -e "   ${C_PURP}${C_BOLD} 12 ${C_RESET} ${C_WHIT}🔍 Rastrear Primeira Geração de Parquets do Dia${C_RESET}"
    echo ""
    echo -e "   ${C_REDD}${C_BOLD} 13 ${C_RESET} ${C_WHIT}🧹 Destruição Total do Ambiente${C_RESET}"
    echo -e "   ${C_GRAY}${C_BOLD} 0 ${C_RESET} ${C_WHIT}🚪 Sair do Painel${C_RESET}"
    echo ""
    draw_line
    echo -ne "   ${C_CYAN}${C_BOLD}Selecione a diretriz desejada: ${C_RESET}"
    
    read -r raw_opt
    opt=$(echo "$raw_opt" | tr -dc '0-9')
    
    case $opt in
        1) setup_full ;;
        2) user_backup ;;
        3) run_server ;;
        4) run_dev_server ;;
        5) sync_production ;;
        6) run_robot_polichat ;;
        7) run_robot_documentos ;;
        8) list_logged_users ;;
        9) server_monitoring ;;
        10) clean_logs ;;
        11) clean_proc_data ;;
        12) list_first_parquets ;;
        13) teardown_full ;;
        0) clear; exit 0 ;;
        *) log_msg "err" "Comando não reconhecido."; sleep 1 ;;
    esac
done