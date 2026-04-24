#!/bin/bash

# ==========================================================================
# SCRIPT DE INSTALAÇÃO E CONFIGURAÇÃO AUTOMÁTICA (SETUP)
# Este script prepara um servidor Ubuntu/Debian do zero para rodar o Portal GGCI.
# Ele automatiza a instalação do banco de dados, bibliotecas Python no sistema,
# criação das tabelas e a injeção dos usuários iniciais.
# ==========================================================================

# Trava de segurança: Se qualquer comando falhar, o script é interrompido imediatamente
set -e

# Garante que o script está rodando a partir da raiz do projeto (onde fica o manage.py),
# independentemente da pasta em que o administrador chamou o comando no terminal.
cd "$(dirname "$0")/.."

echo "🚀 Iniciando a montagem automática do Portal GGCI..."

# --------------------------------------------------------------------------
# 1. DEPENDÊNCIAS DO SISTEMA OPERACIONAL
# --------------------------------------------------------------------------
echo "📦 Instalando pacotes do sistema (MySQL, Python, Cabeçalhos C, Pip)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dev default-libmysqlclient-dev mysql-server build-essential pkg-config

# --------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DO MYSQL
# No WSL2 e em alguns servidores, o MySQL não inicia automaticamente após
# a instalação. Este bloco garante que o serviço está rodando antes de
# tentar qualquer configuração de banco de dados.
# --------------------------------------------------------------------------
echo "🔌 Garantindo que o serviço MySQL está em execução..."
sudo service mysql start || sudo systemctl start mysql

# Aguarda 2 segundos para o MySQL terminar de inicializar completamente
sleep 2

# --------------------------------------------------------------------------
# 3. CONFIGURAÇÃO DO BANCO DE DADOS (MYSQL)
# --------------------------------------------------------------------------
echo "🗄️ Configurando o Banco de Dados MySQL com a senha ovg@2026..."

# Altera o método de autenticação do root para senha (necessário em instalações novas)
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY 'ovg@2026'; FLUSH PRIVILEGES;"

# Derruba o banco se já existir (garante estado limpo) e recria
mysql -u root -povg@2026 -e "DROP DATABASE IF EXISTS portal_ggci; CREATE DATABASE portal_ggci CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# --------------------------------------------------------------------------
# 4. PACOTES PYTHON (INSTALAÇÃO LOCAL NO SISTEMA)
# Usa 'python3 -m pip' para garantir que o pip correto é invocado,
# independentemente de como o sistema configurou os aliases.
# --------------------------------------------------------------------------
echo "🐍 Instalando dependências Python no sistema..."
python3 -m pip install --break-system-packages --upgrade pip
python3 -m pip install --break-system-packages django mysqlclient argon2-cffi

# --------------------------------------------------------------------------
# 5. MIGRAÇÕES E DADOS INICIAIS (DJANGO)
# --------------------------------------------------------------------------
echo "⚙️ Construindo as tabelas e injetando os usuários iniciais..."

# O parâmetro --noinput força o script a aceitar as mudanças automaticamente, sem pausar o setup
python3 manage.py makemigrations --noinput
python3 manage.py migrate --noinput
python3 manage.py loaddata usuarios_iniciais.json

echo "========================================================="
echo "✅ AMBIENTE CONSTRUÍDO COM SUCESSO! O PORTAL ESTÁ PRONTO."
echo "   Para iniciar: python3 manage.py runserver 0.0.0.0:8000"
echo "========================================================="