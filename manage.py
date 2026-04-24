#!/usr/bin/env python
"""
==========================================================================
GERENCIADOR CENTRAL DO DJANGO (manage.py)
==========================================================================
Utilitário de linha de comando para tarefas administrativas do projeto.
É através deste arquivo que o servidor interage com o código, rodando 
comandos como 'runserver', 'migrate' e 'loaddata' (usados no setup.sh).

⚠️ IMPORTANTE: Este é um arquivo núcleo padrão do framework. Quase nunca 
precisamos editá-lo. As configurações reais do portal e banco de dados 
ficam no arquivo: portal_ggci/settings.py
"""
import os
import sys


def main():
    """Função principal que inicializa o ambiente e executa os comandos do terminal."""
    
    # --------------------------------------------------------------------------
    # 1. CONFIGURAÇÃO DE AMBIENTE
    # Aponta para o arquivo de configurações principal da nossa aplicação.
    # Diz ao Python: "Tudo o que você precisa saber sobre o projeto está aqui".
    # -> Arquivo de referência: portal_ggci/settings.py
    # --------------------------------------------------------------------------
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')
    
    # --------------------------------------------------------------------------
    # 2. CARREGAMENTO E VALIDAÇÃO DO NÚCLEO
    # Tenta importar o motor de execução do Django. Se falhar, emite um alerta
    # claro para a equipe avisando que o ambiente virtual (Conda/Venv) pode 
    # estar desativado ou as bibliotecas do requirements.txt não foram instaladas.
    # --------------------------------------------------------------------------
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Não foi possível importar o Django. Você tem certeza que ele está "
            "instalado e disponível no seu ambiente? Você esqueceu de ativar o "
            "ambiente virtual antes de rodar o comando?"
        ) from exc
        
    # --------------------------------------------------------------------------
    # 3. EXECUÇÃO DO COMANDO
    # Pega o que a equipe digitou no terminal (ex: ['manage.py', 'makemigrations'])
    # através do sys.argv e repassa para o Django fazer a mágica acontecer.
    # --------------------------------------------------------------------------
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()