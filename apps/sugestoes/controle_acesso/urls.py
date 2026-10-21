"""
Roteamento: Controle de Acesso

Incluído sob o prefixo `/sugestoes/controle-acesso/`: a tela, a consulta da ficha, o PDF de um envio, o anexo manual e o trio
do botão "Atualizar" — iniciar, acompanhar e abortar.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.controle_acesso, name='controle_acesso'),
    path('api/consultar/', views.api_consultar, name='controle_acesso_consultar'),
    path('api/pdf/', views.api_pdf, name='controle_acesso_pdf'),
    path('api/anexo/', views.api_anexo, name='controle_acesso_anexo'),
    path('api/iniciar/', views.iniciar_atualizacao, name='controle_acesso_iniciar'),
    path('api/status/<int:processo_id>/', views.status_atualizacao, name='controle_acesso_status'),
    path('api/parar/<int:processo_id>/', views.parar_atualizacao, name='controle_acesso_parar'),
]
