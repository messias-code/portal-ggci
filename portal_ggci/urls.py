"""
==========================================================================
ROTEADOR CENTRAL DO SISTEMA (urls.py)
==========================================================================
Este arquivo funciona como o "GPS" do Portal GGCI. Ele mapeia os endereços
(URLs) que o usuário digita no navegador para as lógicas em Python (Views)
que processarão e devolverão a página ou os dados corretos.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

from apps.inicio.gestao_acessos import views as gestao_acessos_views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Login e Logout
    path('', TemplateView.as_view(template_name='gestao_acessos/login/index.html'), name='home'),
    path('api/verificar-login/', gestao_acessos_views.verificar_login, name='verificar_login'),
    path('logout/', gestao_acessos_views.fazer_logout, name='logout'),
    
    # Início (Hub e Gestão)
    path('inicio/', include('apps.inicio.menu_inicio.urls')),
    path('inicio/gestao-acessos/', gestao_acessos_views.gestao_acessos, name='gestao_acessos'),
    path('api/salvar-usuario/', gestao_acessos_views.api_salvar_usuario, name='api_salvar_usuario'),
    path('inicio/alterar-senha/', include('apps.inicio.alteracao_senha.urls')),
    
    # Ferramentas
    path('ferramentas/', include('apps.ferramentas.menu_ferramentas.urls')),
    path('ferramentas/formatador-listas/', include('apps.ferramentas.formatador_listas.urls')),
    path('ferramentas/formatador-dados/', include('apps.ferramentas.formatador_dados.urls')),
    
    # Automações
    # Cada automação vive sob o hub que a contém: a URL passa a descrever a
    # navegação real do portal (hub -> app), no mesmo padrão de /ferramentas/.
    path('automacoes/', include('apps.automacoes.menu_automacoes.urls')),
    path('automacoes/analise-ia/', include('apps.automacoes.analise_ia.urls')),
    path('automacoes/recalculo-bolsas/', include('apps.automacoes.recalculo_bolsas.urls')),
    path('automacoes/enquadramento-cursos/', include('apps.automacoes.enquadramento_cursos.urls')),

    # Dashboards
    path('dashboards/', include('apps.dashboards.menu_dashboards.urls')),
    path('dashboards/polichat/', include('apps.dashboards.dash_polichat.urls')),
    path('dashboards/documentos-ia/', include('apps.dashboards.dash_documentos_ia.urls')),
]