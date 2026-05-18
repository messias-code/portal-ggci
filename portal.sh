#!/bin/bash

# ==========================================================================
# 🌌 PORTAL GGCI - INTERFACE DE COMANDO SÊNIOR (ULTRA UX V8 - BULLETPROOF)
# ==========================================================================
# Autor: Ihan Messias (GGCI/OVG)
# Finalidade: Gestão Total de Infraestrutura e Ambiente com Live Logs
# ==========================================================================

# --------------------------------------------------------------------------
# 1. CORES E VARIÁVEIS (ANSI 256)
# --------------------------------------------------------------------------
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
        echo -e "   ${C_WHIT}${win_path}${C_RESET}"
        
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
    sudo -v
    (while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null) &
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
import os, json, re, sys
try:
    json_str = os.environ.get('JSON_DATA')
    json_str = re.sub(r',\s*}', '}', json_str)
    data = json.loads(json_str)
    with open('.env', 'r') as f: content = f.read()
    content = re.sub(r'^# ={10,}\n# TEMPLATE.*?# ={10,}\n+', '', content, flags=re.DOTALL)
    mapping = {
        'POLICHAT_USER': 'DASHBOARD_POLICHAT_USER', 'POLICHAT_PASS': 'DASHBOARD_POLICHAT_PASS',
        'PBU_USER': 'PORTAL_PBU_USER', 'PBU_PASS_SCRIPTCASE': 'PORTAL_PBU_PASS_ANALISE_IA',
        'PBU_PASS_BOLSA': 'PORTAL_PBU_PASS_PAGAMENTOS', 
        'SIBU_HOST': 'SIBU_BANCO_DADOS_HOST', 'SIBU_USER': 'SIBU_BANCO_DADOS_USER',
        'SIBU_PASS': 'SIBU_BANCO_DADOS_PASS', 'SIBU_NAME': 'SIBU_BANCO_DADOS_NAME',
        'SIBU_BANCO_DADOS_HOST': 'SIBU_BANCO_DADOS_HOST', 'SIBU_BANCO_DADOS_USER': 'SIBU_BANCO_DADOS_USER',
        'SIBU_BANCO_DADOS_NAME': 'SIBU_BANCO_DADOS_NAME', 'SIBU_BANCO_DADOS_PASS': 'SIBU_BANCO_DADOS_PASS'
    }
    for k, v in data.items():
        key = mapping.get(k, k)
        if re.search(f'^{key}=', content, flags=re.MULTILINE):
            content = re.sub(f'^{key}=.*', f\\\"{key}='{v}'\\\", content, flags=re.MULTILINE)
        else:
            content += f\\\"\n{key}='{v}'\\\"
    with open('.env', 'w') as f: f.write(content)
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
}

# --------------------------------------------------------------------------
# 4. LÓGICA DE NEGÓCIO - INSTALAÇÃO
# --------------------------------------------------------------------------
function setup_full() {
    print_ovg_logo
    check_sudo
    
    print_phase "🚀 FASE 0: PREPARAÇÃO DO TERRENO"
    run_with_stream "sudo pkill -f 'manage.py runserver' || true; sudo pkill -f 'gunicorn' || true" "Desligando processos Python zumbis"

    print_phase "📦 FASE 1: MOTOR DO SISTEMA (Isso pode levar alguns minutos)"
    run_with_stream "sudo apt-get update -yqq" "Atualizando lista de repositórios do SO"
    run_with_stream "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config" "Instalando Core Linux"
    run_with_stream "python3 -m pip install --break-system-packages -r requirements.txt" "Instalando Bibliotecas do Sistema (Pip)"
    run_with_stream "playwright install --with-deps chromium" "Construindo Navegador Headless (Playwright)"

    env_wizard

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

    run_with_stream "
        sudo mysql -e \"DROP DATABASE IF EXISTS ${db_name}; CREATE DATABASE ${db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\" &&
        sudo mysql -e \"DROP USER IF EXISTS '${db_user}'@'localhost';\" &&
        sudo mysql -e \"CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${pass}';\" &&
        sudo mysql -e \"GRANT ALL PRIVILEGES ON ${db_name}.* TO '${db_user}'@'localhost';\" &&
        sudo mysql -e \"FLUSH PRIVILEGES;\" &&
        export K_U=\"DB_USER\" V_U=\"${db_user}\" &&
        python3 -c \"import os, re; k,v=os.environ.get('K_U'),os.environ.get('V_U'); c=open('.env').read(); f=open('.env','w'); f.write(re.sub(f'^{k}=.*',f\\\"{k}='{v}'\\\",c,flags=re.MULTILINE))\"
    " "Alocando tabelas e concedendo privilégios locais"

    print_phase "🧬 FASE 3: MIGRAÇÕES E DADOS INICIAIS"
    run_with_stream "python3 manage.py makemigrations gestao_acessos --noinput && python3 manage.py makemigrations --noinput && python3 manage.py migrate --noinput" "Aplicando Migrações estruturais do Django"
    
    if [ -f gestao_acessos_iniciais.json ]; then
        run_with_stream "python3 manage.py loaddata gestao_acessos_iniciais.json" "Restaurando Snapshot de Usuários"
    fi

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

from apps.dash_polichat.services.polichat_extrator import executar_pipeline
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
    
    cat << 'EOF' > .tmp_robot.py
import sys, os
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
import django
django.setup()

try:
    from apps.analise_ia.services.extrator import executar
    sucesso = executar()
    sys.exit(0 if sucesso is not False else 1)
except Exception as e:
    from django.core.management import call_command
    try:
        call_command('executar_motor_ia')
        sys.exit(0)
    except:
        try:
            call_command('executar_motor_ia', '0')
            sys.exit(0)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            sys.exit(1)
EOF

    run_with_stream "python3 .tmp_robot.py" "Acionando Auditoria Cognitiva de Documentos..."
    local exit_code=$?
    rm -f .tmp_robot.py
    
    if [ $exit_code -eq 0 ]; then 
        log_msg "ok" "Pipeline IA executada com sucesso."
        show_output_folder "dados_analise"
    else
        log_msg "err" "A Pipeline falhou ou encontrou erros de execução."
    fi
    wait_key
}

# --------------------------------------------------------------------------
# 6. MONITORAMENTO
# --------------------------------------------------------------------------
function server_monitoring() {
    print_ovg_logo
    print_phase "📊 MONITORAMENTO DE SAÚDE DO SERVIDOR"
    run_with_stream "python3 manage.py monitorar_servidor" "Coletando métricas de hardware..."
    wait_key
}

# --------------------------------------------------------------------------
# 7. UTILITÁRIOS (BACKUP E DESTRUIÇÃO)
# --------------------------------------------------------------------------
function user_backup() {
    print_ovg_logo
    print_phase "💾 SNAPSHOT DE SEGURANÇA"
    run_with_stream "python3 manage.py dumpdata gestao_acessos.Usuario --indent 4 > gestao_acessos_iniciais.json" "Extraindo e formatando JSON de Usuários Atuais"
    wait_key
}

function teardown_full() {
    print_ovg_logo
    print_phase "🧹 DESTRUIÇÃO TOTAL DO AMBIENTE"
    echo -e "   ${C_REDD}Isso removerá o MySQL, Banco de Dados, Ambientes Virtuais e Dependências.${C_RESET}\n"
    
    if ask_confirm "Tem certeza que deseja apagar TUDO e formatar o servidor?"; then
        check_sudo
        echo ""
        run_with_stream "sudo service mysql stop || true" "Parando Banco de Dados"
        run_with_stream "sudo apt-get purge -yqq mysql-server mysql-client mysql-common; sudo rm -rf /etc/mysql /var/lib/mysql /var/log/mysql" "Vaporizando MySQL"
        run_with_stream "python3 -m pip uninstall -y django mysqlclient playwright python-dotenv >/dev/null 2>&1 || true" "Removendo pacotes vitais"
        run_with_stream "rm -rf .env db.sqlite3" "Apagando configurações sensíveis"
        
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
    echo -e "   ${C_GREE}${C_BOLD} 4 ${C_RESET} ${C_WHIT}🤖 Executar Robô de Extração: PoliChat${C_RESET}"
    echo -e "   ${C_GREE}${C_BOLD} 5 ${C_RESET} ${C_WHIT}🧠 Executar Robô de Extração: Documentos e Pagamentos (IA)${C_RESET}"
    echo ""
    echo -e "   ${C_CYAN}${C_BOLD} 7 ${C_RESET} ${C_WHIT}📊 Monitorar Saúde do Servidor (CPU/RAM/Disco)${C_RESET}"
    echo ""
    echo -e "   ${C_REDD}${C_BOLD} 9 ${C_RESET} ${C_WHIT}🧹 Destruição Total do Ambiente${C_RESET}"
    echo -e "   ${C_GRAY}${C_BOLD} 0 ${C_RESET} ${C_WHIT}🚪 Sair do Painel${C_RESET}"
    echo ""
    draw_line
    echo -ne "   ${C_CYAN}${C_BOLD}Selecione a diretriz desejada: ${C_RESET}"
    
    read -r raw_opt
    opt=$(echo "$raw_opt" | tr -dc '0-9')
    
    case $opt in
        1) setup_full ;;
        2) user_backup ;;
        4) run_robot_polichat ;;
        5) run_robot_documentos ;;
        7) server_monitoring ;;
        9) teardown_full ;;
        0) clear; exit 0 ;;
        *) log_msg "err" "Comando não reconhecido."; sleep 1 ;;
    esac
done