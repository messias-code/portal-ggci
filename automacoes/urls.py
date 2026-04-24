from django.urls import path
from . import views

urlpatterns = [
    path('api/iniciar-processamento/', views.iniciar_processamento_ia, name='iniciar_processamento_ia'),
    path('api/status-processamento/<int:processo_id>/', views.checar_status_ia, name='checar_status_ia'),
    path('api/parar-processamento/<int:processo_id>/', views.parar_processamento_ia, name='parar_processamento_ia'),
    path('api/baixar-resultado/<int:processo_id>/', views.baixar_resultado_ia, name='baixar_resultado_ia'),
]