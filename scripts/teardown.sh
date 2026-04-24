#!/bin/bash

# ==========================================================================
# SCRIPT DE LIMPEZA PROFUNDA (TEARDOWN / RESET)
# ATENÇÃO: Este é um script destrutivo!
# Ele serve para "zerar" o servidor caso algo dê muito errado. Ele apaga 
# todo o banco de dados, desinstala o MySQL do sistema operacional e remove
# os pacotes Python instalados pelo setup.
# O seu código fonte (HTML, CSS, JS, Python) fica intacto.
# ==========================================================================

# --------------------------------------------------------------------------
# 1. NAVEGAÇÃO SEGURA
# Garante que o script será executado a partir da pasta raiz do projeto.
# --------------------------------------------------------------------------
cd "$(dirname "$0")/.."

echo "⚠️  ATENÇÃO: INICIANDO A DESTRUIÇÃO TOTAL DO AMBIENTE! ⚠️"
echo "O seu código (repositório) não será apagado, mas o MySQL, os pacotes Python e o Banco de Dados vão sumir."

# Pausa de 3 segundos para dar tempo do administrador cancelar (Ctrl+C) se rodou por engano
sleep 3

# --------------------------------------------------------------------------
# 2. EXPURGO DO BANCO DE DADOS (MYSQL)
# Este bloco não apenas apaga o banco 'portal_ggci', mas arranca o MySQL 
# inteiro do Ubuntu, incluindo arquivos de configuração e logs de sistema.
# --------------------------------------------------------------------------
echo "🗑️ Desinstalando o MySQL e apagando todos os bancos de dados..."

# Tenta parar o serviço do MySQL antes de desinstalar (ignora erro se já estiver parado)
sudo service mysql stop || sudo systemctl stop mysql || true

# Remove todos os pacotes e dependências do MySQL Server e Client
sudo apt-get purge -y mysql-server mysql-client mysql-common mysql-server-core-* mysql-client-core-*

# Apaga fisicamente as pastas onde o MySQL guarda os dados salvos e as configurações
sudo rm -rf /etc/mysql /var/lib/mysql /var/log/mysql

# Limpa o gerenciador de pacotes do Ubuntu (remove sobras de instalações antigas)
sudo apt-get autoremove -y
sudo apt-get autoclean

# --------------------------------------------------------------------------
# 3. REMOÇÃO DOS PACOTES PYTHON
# Usa 'python3 -m pip' para garantir que o pip correto é invocado.
# --------------------------------------------------------------------------
echo "🧹 Removendo pacotes Python instalados pelo projeto..."
python3 -m pip uninstall -y django mysqlclient argon2-cffi 2>/dev/null || true

# --------------------------------------------------------------------------
# 4. LIMPEZA DE ARTEFATOS LOCAIS
# Remove caches de compilação e banco SQLite residual.
# --------------------------------------------------------------------------
echo "🧹 Removendo artefatos e caches locais..."

# Procura e deleta recursivamente todas as pastas '__pycache__' geradas pelo Python
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove o banco de dados padrão do Django (SQLite), caso tenha sido gerado acidentalmente
rm -f db.sqlite3

echo "========================================================="
echo "💥 LIMPEZA CONCLUÍDA! O SERVIDOR ESTÁ ZERADO DE NOVO."
echo "   Para reconstruir: bash scripts/setup.sh"
echo "========================================================="