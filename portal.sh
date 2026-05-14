#!/bin/bash

# ==========================================================================
# 🌌 PORTAL GGCI - INTERFACE DE COMANDO SÊNIOR
# ==========================================================================
# Autor: Ihan Messias (GGCI/OVG)
# Finalidade: Gestão Total de Infraestrutura e Ambiente
# ==========================================================================

# Configurações de exibição
export COLUMNS=$(tput cols)

# Paleta de Cores Premium (ANSI)
CLR_PRIME='\033[38;5;45m'   # Ciano vibrante
CLR_SECND='\033[38;5;170m'  # Magenta/Roxo suave
CLR_SUCCS='\033[38;5;82m'   # Verde limão
CLR_WARNN='\033[38;5;214m'  # Laranja
CLR_DANGG='\033[38;5;196m'  # Vermelho
CLR_TEXTT='\033[38;5;253m'  # Branco acinzedado
CLR_DIMMM='\033[38;5;242m'  # Cinza escuro
CLR_RESET='\033[0m'
CLR_BOLD='\033[1m'

# --------------------------------------------------------------------------
# INTERFACE E ELEMENTOS VISUAIS
# --------------------------------------------------------------------------
function draw_line() {
    printf "${CLR_DIMMM}%.s─${CLR_RESET}" $(seq 1 $(tput cols))
    echo ""
}

function print_banner() {
    clear
    echo -e "${CLR_PRIME}${CLR_BOLD}"
    echo "  _____   ____  _____ _______       _      "
    echo " |  __ \ / __ \|  __ \__   __|/\   | |     "
    echo " | |__) | |  | | |__) | | |  /  \  | |     "
    echo " |  ___/| |  | |  _  /  | | / /\ \ | |     "
    echo " | |    | |__| | | \ \  | |/ ____ \| |____ "
    echo " |_|     \____/|_|  \_\ |_/_/    \_\______|"
    echo -e "           ${CLR_SECND}GERÊNCIA DE GESTÃO GGCI${CLR_RESET}"
    echo ""
    draw_line
}

function print_msg() {
    case $1 in
        "step")  echo -e "\n${CLR_PRIME}${CLR_BOLD}🚀 $2${CLR_RESET}" ;;
        "ok")    echo -e "  ${CLR_SUCCS}✔ $2${CLR_RESET}" ;;
        "warn")  echo -e "  ${CLR_WARNN}⚠ $2${CLR_RESET}" ;;
        "err")   echo -e "  ${CLR_DANGG}✖ $2${CLR_RESET}" ;;
        "info")  echo -e "  ${CLR_DIMMM}ℹ $2${CLR_RESET}" ;;
    esac
}

function wait_key() {
    echo -e "\n${CLR_DIMMM}Pressione qualquer tecla para voltar ao centro de comando...${CLR_RESET}"
    read -n 1 -s
}

# --------------------------------------------------------------------------
# LÓGICA DE NEGÓCIO - AMBIENTE (.env)
# --------------------------------------------------------------------------
function env_wizard() {
    print_msg "step" "Sincronizando Variáveis de Ambiente"
    if [ ! -f .env ]; then 
        print_msg "info" "Criando .env a partir do template..."
        cp .env.example .env
    fi
    
    # 1. Senha do Banco (Manual por segurança)
    echo -ne "  ${CLR_TEXTT}Senha MySQL Local${CLR_RESET} (${CLR_DIMMM}DB_PASSWORD${CLR_RESET}): "
    read db_pass
    echo ""
    if [ ! -z "$db_pass" ]; then
        export K="DB_PASSWORD"; export V="$db_pass"
        python3 -c "import os, re; k,v=os.environ.get('K'),os.environ.get('V'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\"{k}='{v}'\",c,flags=re.MULTILINE))"
        print_msg "ok" "Senha do banco salva."
    fi

    # 2. Bloco JSON (Copia e Cola Multi-linha)
    echo -e "  ${CLR_PRIME}Cole o JSON abaixo e pressione Enter duas vezes para finalizar:${CLR_RESET}"
    json_input=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && break
        json_input+="$line"
    done

    if [ ! -z "$json_input" ]; then
        export JSON_DATA="$json_input"
        python3 -c "
import os, json, re
try:
    data = json.loads(os.environ.get('JSON_DATA'))
    with open('.env', 'r') as f: content = f.read()
    mapping = {
        'POLICHAT_USER': 'DASHBOARD_POLICHAT_USER',
        'POLICHAT_PASS': 'DASHBOARD_POLICHAT_PASS',
        'PBU_USER': 'PORTAL_PBU_USER',
        'PBU_PASS_SCRIPTCASE': 'PORTAL_PBU_PASS_AGENDAMENTOS',
        'PBU_PASS_BOLSA': 'PORTAL_PBU_PASS_VALORES_BOLSAS',
        'SIBU_PASS': 'SIBU_BANCO_DADOS_PASS'
    }
    for k, v in data.items():
        key = mapping.get(k, k)
        if re.search(f'^{key}=', content, flags=re.MULTILINE):
            content = re.sub(f'^{key}=.*', f\"{key}='{v}'\", content, flags=re.MULTILINE)
        else:
            content += f\"\n{key}='{v}'\"
    with open('.env', 'w') as f: f.write(content)
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" | grep -q "OK" && print_msg "ok" "Credenciais importadas." || print_msg "err" "Falha no JSON. Verifique se colou o bloco completo."
    fi

    if grep -q "gerada-automaticamente" .env; then
        local new_key=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
        export K_S="SECRET_KEY"; export V_S="${new_key}"
        python3 -c "import os, re; k,v=os.environ.get('K_S'),os.environ.get('V_S'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\"{k}='{v}'\",c,flags=re.MULTILINE))"
        print_msg "ok" "SECRET_KEY gerada com sucesso."
    fi
}

# --------------------------------------------------------------------------
# LÓGICA DE NEGÓCIO - INSTALAÇÃO (SETUP)
# --------------------------------------------------------------------------
function setup_full() {
    print_banner
    print_msg "step" "Fase 0: Limpando processos ativos"
    sudo pkill -f "manage.py runserver" >/dev/null 2>&1 || true
    sudo pkill -f "python3 manage.py" >/dev/null 2>&1 || true
    sudo pkill -f "gunicorn" >/dev/null 2>&1 || true
    print_msg "ok" "Ambiente limpo."

    print_msg "step" "Fase 1: Preparando Motor do Sistema (Apt & Pip)"
    sudo apt-get update -yqq >/dev/null 2>&1 || true
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -yqq python3 python3-pip python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config >/dev/null 2>&1
    python3 -m pip install --break-system-packages -r requirements.txt -q
    playwright install --with-deps chromium >/dev/null 2>&1
    print_msg "ok" "Dependências instaladas."

    env_wizard

    print_msg "step" "Fase 2: Arquitetura de Dados (MySQL)"
    local pass=$(grep -E '^DB_PASSWORD=' .env | cut -d '=' -f2 | tr -d "'\"")
    local db_name="portal_ggci"
    local db_user="portal_user"
    local mysql_cmd=""
    
    if MYSQL_PWD="${pass}" mysql -u root -e "quit" >/dev/null 2>&1; then
        mysql_cmd="MYSQL_PWD='${pass}' mysql -u root"
    elif mysql -u root -e "quit" >/dev/null 2>&1; then
        mysql_cmd="mysql -u root"
    elif sudo mysql -e "quit" >/dev/null 2>&1; then
        mysql_cmd="sudo mysql"
    else
        print_msg "warn" "Tentando Modo de Resgate..."
        sudo service mysql stop >/dev/null 2>&1 || true
        sudo mysqld_safe --skip-grant-tables --skip-networking & sleep 5
        sudo mysql -e "FLUSH PRIVILEGES; ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '${pass}'; FLUSH PRIVILEGES;" >/dev/null 2>&1 || true
        sudo pkill mysqld >/dev/null 2>&1 || true; sleep 2
        sudo service mysql start >/dev/null 2>&1 || true
        if MYSQL_PWD="${pass}" mysql -u root -e "quit" >/dev/null 2>&1; then
            mysql_cmd="MYSQL_PWD='${pass}' mysql -u root"
        fi
    fi

    if [ -z "$mysql_cmd" ]; then
        print_msg "err" "Não foi possível acessar o MySQL."; wait_key; return 1
    fi

    print_msg "info" "Configurando usuário '${db_user}'..."
    sudo mysql -e "DROP DATABASE IF EXISTS ${db_name}; CREATE DATABASE ${db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    sudo mysql -e "DROP USER IF EXISTS '${db_user}'@'localhost';"
    sudo mysql -e "CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${pass}';"
    sudo mysql -e "GRANT ALL PRIVILEGES ON ${db_name}.* TO '${db_user}'@'localhost';"
    sudo mysql -e "FLUSH PRIVILEGES;"
    
    export K_U="DB_USER"; export V_U="${db_user}"
    python3 -c "import os, re; k,v=os.environ.get('K_U'),os.environ.get('V_U'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\"{k}='{v}'\",c,flags=re.MULTILINE))"
    print_msg "ok" "Banco e usuário prontos."

    print_msg "info" "Aplicando migrações do Django..."
    python3 manage.py makemigrations gestao_acessos --noinput
    python3 manage.py makemigrations --noinput
    python3 manage.py migrate --noinput
    
    if [ -f gestao_acessos_iniciais.json ]; then
        python3 manage.py loaddata gestao_acessos_iniciais.json
        print_msg "ok" "Acessos restaurados."
    fi

    echo -e "\n${CLR_SUCCS}${CLR_BOLD}✨ SISTEMA PRONTO PARA DECOLO!${CLR_RESET}"
    wait_key
}

# --------------------------------------------------------------------------
# LÓGICA DE NEGÓCIO - BACKUP & TEARDOWN
# --------------------------------------------------------------------------
function user_backup() {
    print_banner
    print_msg "step" "Extraindo Snapshot de Usuários"
    python3 manage.py dumpdata gestao_acessos.Usuario --indent 4 > gestao_acessos_iniciais.json
    print_msg "ok" "Backup realizado com sucesso."
    wait_key
}

function teardown_full() {
    print_banner
    echo -e "${CLR_DANGG}${CLR_BOLD}❗ AVISO DE SEGURANÇA - DESTRUIÇÃO TOTAL ❗${CLR_RESET}"
    read -p "Confirma esta operação? (digite 'SIM'): " conf
    if [ "$conf" == "SIM" ]; then
        print_msg "step" "Desmontando infraestrutura..."
        sudo service mysql stop >/dev/null 2>&1 || true
        sudo apt-get purge -y mysql-server mysql-client mysql-common >/dev/null 2>&1
        sudo rm -rf /etc/mysql /var/lib/mysql /var/log/mysql
        python3 -m pip uninstall -y django mysqlclient playwright python-dotenv >/dev/null 2>&1 || true
        rm -rf .env db.sqlite3
        print_msg "ok" "Limpeza concluída."
    fi
    wait_key
}

# --------------------------------------------------------------------------
# MENU PRINCIPAL
# --------------------------------------------------------------------------
while true; do
    print_banner
    echo -e "  ${CLR_PRIME}${CLR_BOLD}[1]${CLR_RESET} ${CLR_TEXTT}🚀 Instalação e Atualização Completa${CLR_RESET}"
    echo -e "  ${CLR_SECND}${CLR_BOLD}[2]${CLR_RESET} ${CLR_TEXTT}💾 Salvar Backup de Usuários (JSON)${CLR_RESET}"
    echo -e "  ${CLR_DANGG}${CLR_BOLD}[3]${CLR_RESET} ${CLR_TEXTT}🧹 Limpeza Total do Ambiente${CLR_RESET}"
    echo -e "  ${CLR_DIMMM}${CLR_BOLD}[0]${CLR_RESET} ${CLR_TEXTT}🚪 Sair${CLR_RESET}"
    echo ""
    draw_line
    echo -ne "${CLR_PRIME}${CLR_BOLD}Seleção:${CLR_RESET} "
    read opt
    case $opt in
        1) setup_full ;;
        2) user_backup ;;
        3) teardown_full ;;
        0) clear; exit 0 ;;
    esac
done
