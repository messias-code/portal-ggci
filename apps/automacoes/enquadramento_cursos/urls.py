from django.urls import path
from . import views

urlpatterns = [
    # Módulo incluído sob `/automacoes/enquadramento-cursos/`: a raiz ('') é a página.
    path('', views.enquadramento_cursos_view, name='enquadramento_cursos_view'),
    # Names prefixados por app para não colidir com os de `analise_ia`,
    # que expõe exatamente a mesma superfície de API.
    path('api/iniciar-processamento/', views.iniciar_processamento_ia, name='enquadramento_cursos_iniciar'),
    path('api/status-processamento/<int:processo_id>/', views.checar_status_ia, name='enquadramento_cursos_status'),
    path('api/parar-processamento/<int:processo_id>/', views.parar_processamento_ia, name='enquadramento_cursos_parar'),
    path('api/baixar-resultado/<int:processo_id>/', views.baixar_resultado_ia, name='enquadramento_cursos_baixar'),
]