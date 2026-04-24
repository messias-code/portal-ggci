"""
==========================================================================
CONFIGURAÇÃO WSGI (Web Server Gateway Interface)
==========================================================================
Este arquivo é a "porta de entrada" do Portal GGCI para a internet. 
Ele atua como um tradutor entre o nosso código em Python/Django e servidores 
web de alta performance usados em produção (como Gunicorn, Apache ou Nginx).

⚠️ IMPORTANTE: Assim como o manage.py, este é um arquivo de infraestrutura 
nativa do framework. Você normalmente só precisará mexer aqui quando for 
colocar o sistema no ar (deploy) em um servidor definitivo.
"""

import os

from django.core.wsgi import get_wsgi_application

# --------------------------------------------------------------------------
# 1. APONTAMENTO DAS CONFIGURAÇÕES GLOBAIS
# Garante que, quando o servidor web externo tentar ligar a aplicação, ele 
# saiba exatamente onde encontrar as variáveis de ambiente, conexões de 
# banco de dados e chaves de segurança do nosso projeto.
# -> Arquivo referenciado: portal_ggci/settings.py
# --------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')

# --------------------------------------------------------------------------
# 2. EXPOSIÇÃO DO APLICATIVO (O MOTOR DO PORTAL)
# Cria e expõe a variável 'application'. O servidor de produção (ex: Gunicorn) 
# vai procurar especificamente por essa variável para conseguir receber as 
# requisições (cliques, logins) dos usuários e processar as respostas do Django.
# --------------------------------------------------------------------------
application = get_wsgi_application()