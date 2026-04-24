"""
==========================================================================
ROTEADOR CENTRAL DO SISTEMA (urls.py)
==========================================================================
Este arquivo funciona como o "GPS" do Portal GGCI. Ele mapeia os endereços
(URLs) que o usuário digita no navegador para as lógicas em Python (Views)
que processarão e devolverão a página ou os dados corretos.

Sempre que a equipe criar uma tela nova ou um novo endpoint de API para 
o Fetch/AJAX, o caminho deve ser registrado na lista 'urlpatterns' abaixo.
"""

# ==========================================================================
# 1. IMPORTAÇÕES NECESSÁRIAS
# ==========================================================================
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

# Importa o arquivo que contém a inteligência e as regras de negócio do app.
# -> Arquivo referenciado: usuarios/views.py
from usuarios import views

# ==========================================================================
# 2. MAPEAMENTO DE ROTAS (URL PATTERNS)
# ==========================================================================
urlpatterns = [
    # Rota padrão do painel de administração nativo do Django.
    # Acessado via: seudominio.com/admin/
    path('admin/', admin.site.urls),
    
    # ----------------------------------------------------------------------
    # TELA DE LOGIN (ROTA RAIZ)
    # Quando o usuário acessa apenas o domínio vazio (/), o TemplateView
    # exibe diretamente o HTML do login, sem precisar de lógica extra no views.
    # IMPORTANTE: O parâmetro name='home' é vital, pois o redirecionamento 
    # após o "Sair do Sistema" (logout) procura exatamente por este nome.
    # -> Arquivo referenciado: templates/login/index.html
    # ----------------------------------------------------------------------
    path('', TemplateView.as_view(template_name='login/index.html'), name='home'),
    
    # ----------------------------------------------------------------------
    # APIS DE COMUNICAÇÃO (FETCH)
    # Rota "invisível" usada exclusivamente pelo Javascript para validar 
    # o usuário e senha de forma segura no backend.
    # -> Acionado por: static/login/script.js
    # -> Lógica executada em: def verificar_login (usuarios/views.py)
    # ----------------------------------------------------------------------
    path('api/verificar-login/', views.verificar_login, name='verificar_login'),
    
    # ----------------------------------------------------------------------
    # MÓDULOS DO PORTAL (ÁREA LOGADA)
    # Rotas protegidas pelas validações de sessão do Django.
    # ----------------------------------------------------------------------
    
    # Tela de Dashboard com os acessos modulares e dados do usuário.
    # -> Arquivo referenciado: templates/inicio/index.html
    path('inicio/', views.inicio, name='inicio'),
    
    # Rota de Ação: Não possui tela. Apenas destrói a sessão e redireciona.
    path('logout/', views.fazer_logout, name='logout'),
    
    # Tela Administrativa: Tabela de usuários e controle de permissões.
    # No views.py, existe um bloqueio que impede perfis 'comum' ou 'consulta' 
    # de entrarem nesta URL, mesmo que tentem digitar direto no navegador.
    # -> Arquivo referenciado: templates/inicio/gestao_acessos/index.html
    path('inicio/gestao-acessos/', views.gestao_acessos, name='gestao_acessos'),
    path('api/salvar-usuario/', views.api_salvar_usuario, name='api_salvar_usuario'),
    
    # Módulo de Alteração de Senha do Usuário
    path('inicio/alterar-senha/', views.alterar_senha_page, name='alterar_senha'),
    path('api/alterar-senha/', views.api_alterar_senha, name='api_alterar_senha'),
    
    # Ferramentas:
    path('ferramentas/', views.ferramentas, name='ferramentas'),
    path('ferramentas/formatador-listas/', views.formatador_listas, name='formatador_listas'),
    path('ferramentas/formatador-dados/', views.formatador_dados, name='formatador_dados'),
    
    # Automações:
    path('automacoes/', views.automacoes, name='automacoes'),
    path('menu/automacoes/analise-ia/', views.analise_ia_view, name='analise_ia'),

    # ======================================================================
    # APIS DO NOVO MOTOR DE IA (APP AUTOMACOES)
    # ======================================================================
    path('motor-ia/', include('automacoes.urls')),
]