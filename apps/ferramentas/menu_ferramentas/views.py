"""
Módulo de Visualização: Menu de Ferramentas
O QUE FAZ: Responsável por renderizar a interface de navegação (hub) das ferramentas do portal.
POR QUÊ EXISTE: Organiza e restringe o acesso ao hub de ferramentas dependendo da permissão do usuário.
COMO FUNCIONA: Usa o decorador `@login_required` para segurança e avalia as flags do modelo `Usuarios`.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def ferramentas(request):
    """
    O QUE FAZ: Renderiza o painel central de ferramentas (Formatador de Listas, etc).
    POR QUÊ EXISTE: É a página de destino (landing page) quando o usuário clica em "Ferramentas" na sidebar.
    COMO FUNCIONA: 
        1. Verifica se o usuário atual (`request.user`) possui a flag `p_ferramentas` ativa ou se é o `admin`.
        2. Se não possuir acesso, força um redirecionamento de segurança para a rota `inicio`.
        3. Caso contrário, entrega o template `index.html` do menu de ferramentas.
    """
    if not request.user.p_ferramentas and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
    return render(request, 'menu_ferramentas/index.html')
