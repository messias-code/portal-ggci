from django.urls import path
from . import views

urlpatterns = [
    path('', views.alterar_senha_page, name='alterar_senha'),
    path('api/', views.api_alterar_senha, name='api_alterar_senha'),
]
