from django.urls import path
from . import views

urlpatterns = [
    path('api/polichat/iniciar/', views.iniciar_extracao_polichat, name='iniciar_polichat'),
    path('api/polichat/status/<int:processo_id>/', views.checar_status_polichat, name='status_polichat'),
    path('api/polichat/baixar/<int:processo_id>/', views.baixar_resultado_polichat, name='baixar_polichat'),
]
