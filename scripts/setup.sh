#!/bin/bash

# ==========================================================================
# SCRIPT DE INSTALAÇÃO E CONFIGURAÇÃO AUTOMÁTICA (SETUP)
# Este script prepara um servidor Ubuntu/Debian do zero para rodar o Portal GGCI.
# Ele automatiza a instalação do banco de dados, bibliotecas Python no sistema,
# criação das tabelas e a injeção dos usuários iniciais.
# ==========================================================================

# Trava de segurança: Se qualquer comando falhar, o script é interrompido imediatamente
set -e

# Garante que o script está rodando a partir da raiz do projeto
cd "$(dirname "$0")/.."

# ==========================================================================
# CORES E FORMATAÇÃO VISUAL
# ==========================================================================
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_RED='\033[31m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_BLUE='\033[34m'
C_CYAN='\033[36m'
C_MAGENTA='\033[35m'

function print_header() {
    clear
    echo -e "${C_CYAN}${C_BOLD}"
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║                  🚀 PORTAL GGCI - SETUP AUTOMATIZADO                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝${C_RESET}"
    echo ""
}

function print_step() {
    echo -e "\n${C_BLUE}${C_BOLD}▶ $1${C_RESET}"
}

function print_success() {
    echo -e "${C_GREEN}  ✔ $1${C_RESET}"
}

function print_warning() {
    echo -e "${C_YELLOW}  ! $1${C_RESET}"
}

function print_error() {
    echo -e "${C_RED}  ✖ $1${C_RESET}"
}

print_header

# --------------------------------------------------------------------------
# 1. DEPENDÊNCIAS DO SISTEMA OPERACIONAL
# --------------------------------------------------------------------------
print_step "Instalando pacotes do sistema (MySQL, Python, Cabeçalhos C, Pip)..."
# Desativa output excessivo para não poluir
sudo apt-get update -yqq >/dev/null 2>&1 || true
sudo DEBIAN_FRONTEND=noninteractive apt-get install -yqq python3 python3-pip python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config >/dev/null 2>&1
print_success "Pacotes de sistema instalados e atualizados."

# --------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DO MYSQL
# --------------------------------------------------------------------------
print_step "Garantindo que o serviço MySQL está em execução..."
sudo service mysql start >/dev/null 2>&1 || sudo systemctl start mysql >/dev/null 2>&1
sleep 2
print_success "Serviço MySQL ativo e operante."

# --------------------------------------------------------------------------
# 3. PACOTES PYTHON
# --------------------------------------------------------------------------
print_step "Instalando dependências Python no sistema..."
python3 -m pip install --break-system-packages --upgrade pip -q
python3 -m pip install --break-system-packages -r requirements.txt -q
playwright install --with-deps chromium >/dev/null 2>&1
print_success "Dependências Python instaladas."

# --------------------------------------------------------------------------
# 4. CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE (.env) E CHAVES
# --------------------------------------------------------------------------
print_step "Configurando as variáveis de ambiente locais..."
if [ ! -f .env ]; then
    print_warning "Arquivo .env não encontrado. Copiando do .env.example..."
    cp .env.example .env
else
    print_success "Arquivo .env detectado."
fi

print_step "Gerando nova SECRET_KEY de forma automatizada..."
python3 -c "
import re
from django.core.management.utils import get_random_secret_key
try:
    new_key = get_random_secret_key()
    with open('.env', 'r') as f: content = f.read()
    content = re.sub(r\"^SECRET_KEY=.*\", f\"SECRET_KEY='{new_key}'\", content, flags=re.MULTILINE)
    with open('.env', 'w') as f: f.write(content)
except Exception as e:
    print(f'Erro ao gerar key: {e}')
"
print_success "SECRET_KEY atualizada com segurança no .env."

# Extrair a senha configurada no .env para usar nas operações do banco
ENV_DB_PASSWORD=$(grep -E '^DB_PASSWORD=' .env | cut -d '=' -f2 | tr -d "'\"")

if [ "$ENV_DB_PASSWORD" = "ovg@2026" ]; then
    echo -e "\n${C_YELLOW}${C_BOLD}╔══════════════════════════════════════════════════════════════════════╗"
    echo -e "║                      ⚠️  ALERTA DE SEGURANÇA ⚠️                      ║"
    echo -e "║ A senha do banco de dados no seu arquivo .env está configurada com   ║"
    echo -e "║ o padrão inseguro ('ovg@2026').                                      ║"
    echo -e "╚══════════════════════════════════════════════════════════════════════╝${C_RESET}\n"
    
    read -p "$(echo -e ${C_CYAN}${C_BOLD}"Deseja alterar a senha agora? (s/n): "${C_RESET})" choice
    if [[ "$choice" =~ ^[sS]$ ]]; then
        while true; do
            echo ""
            # A senha é visível para permitir CTRL+V, conforme solicitado
            read -p "$(echo -e ${C_MAGENTA}"Digite a nova senha segura: "${C_RESET})" new_pass1
            read -p "$(echo -e ${C_MAGENTA}"Confirme a nova senha segura: "${C_RESET})" new_pass2
            
            if [ -z "$new_pass1" ]; then
                print_error "A senha não pode ser vazia."
                continue
            fi
            
            if [ "$new_pass1" = "$new_pass2" ]; then
                export NEW_PASS="$new_pass1"
                python3 -c "
import os, re
new_pass = os.environ.get('NEW_PASS', '')
try:
    with open('.env', 'r') as f: content = f.read()
    content = re.sub(r\"^DB_PASSWORD=.*\", f\"DB_PASSWORD='{new_pass}'\", content, flags=re.MULTILINE)
    with open('.env', 'w') as f: f.write(content)
except Exception as e:
    print(f'Erro ao atualizar senha: {e}')
"
                ENV_DB_PASSWORD="$new_pass1"
                print_success "Senha atualizada com sucesso no .env!"
                break
            else:
                print_error "As senhas não coincidem. Tente novamente."
            fi
        done
    else
        print_warning "Continuando com a senha padrão insegura."
    fi
fi

# --------------------------------------------------------------------------
# 5. CONFIGURAÇÃO DO BANCO DE DADOS (MYSQL)
# --------------------------------------------------------------------------
print_step "Configurando o Banco de Dados MySQL com a senha definida no .env..."

# Altera o método de autenticação do root para senha (necessário em instalações novas)
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '${ENV_DB_PASSWORD}'; FLUSH PRIVILEGES;" >/dev/null 2>&1 || true

# Derruba o banco se já existir (garante estado limpo) e recria
mysql -u root -p"${ENV_DB_PASSWORD}" -e "DROP DATABASE IF EXISTS portal_ggci; CREATE DATABASE portal_ggci CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" >/dev/null 2>&1
print_success "Banco de dados recriado."

# --------------------------------------------------------------------------
# 6. MIGRAÇÕES E DADOS INICIAIS (DJANGO)
# --------------------------------------------------------------------------
print_step "Construindo as tabelas e injetando os usuários iniciais..."

python3 manage.py makemigrations --noinput >/dev/null 2>&1
python3 manage.py migrate --noinput >/dev/null 2>&1
python3 manage.py loaddata gestao_acessos_iniciais.json >/dev/null 2>&1
print_success "Tabelas e usuários configurados."

echo -e "\n${C_GREEN}${C_BOLD}"
echo "========================================================================"
echo "✅ AMBIENTE CONSTRUÍDO COM SUCESSO! O PORTAL ESTÁ PRONTO."
echo "   Para iniciar o servidor, execute:"
echo "   gunicorn portal_ggci.wsgi:application --bind 0.0.0.0:8000"
echo "   (ou: python manage.py runserver)"
echo "========================================================================${C_RESET}\n"
