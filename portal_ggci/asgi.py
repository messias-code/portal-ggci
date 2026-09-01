"""
==========================================================================
CONFIGURAÇÃO ASGI (Asynchronous Server Gateway Interface)
==========================================================================
Este arquivo é o "irmão mais novo e moderno" do wsgi.py. Enquanto o WSGI 
lida com requisições tradicionais (uma por vez por processo), o ASGI 
prepara o Portal GGCI para trabalhar de forma assíncrona.

⚠️ QUANDO ELE É USADO?
Se no futuro o portal precisar de recursos em tempo real (como WebSockets, 
um chat interno, notificações ao vivo empurradas pelo servidor) e for 
hospedado usando servidores assíncronos como Uvicorn ou Daphne.
Por enquanto, na nossa arquitetura padrão, o Django usará mais o wsgi.py.
"""

import os

from django.core.asgi import get_asgi_application

# --------------------------------------------------------------------------
# 1. APONTAMENTO DAS CONFIGURAÇÕES GLOBAIS
# Assim como no WSGI e no manage.py, diz ao servidor externo onde encontrar 
# o "cérebro" do projeto (banco de dados, senhas, chaves).
# -> Arquivo referenciado: portal_ggci/settings.py
# --------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal_ggci.settings')

# --------------------------------------------------------------------------
# 2. EXPOSIÇÃO DO APLICATIVO (O MOTOR ASSÍNCRONO)
# Cria e expõe a variável 'application'. Servidores ASGI modernos vão 
# procurar especificamente por essa variável para conseguir manter várias 
# conexões simultâneas (assíncronas) abertas com os navegadores dos usuários.
# --------------------------------------------------------------------------
application = get_asgi_application()