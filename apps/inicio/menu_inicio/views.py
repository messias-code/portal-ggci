from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def inicio(request):
    """Renderiza o dashboard principal após o login (Cards de Início)."""
    return render(request, 'menu_inicio/index.html')
