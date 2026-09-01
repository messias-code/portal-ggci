"""
Módulo de Visualização: Formatador de Listas
O QUE FAZ: Entrega a interface SPA para conversão de listas simples em filtros de Banco de Dados.
POR QUÊ EXISTE: Reduzir a carga de trabalho de estagiários/analistas que precisam transformar 
colunas do Excel em queries SQL do tipo `IN ('A', 'B')`.
COMO FUNCIONA: Ponto de entrada protegido via decorator. Retorna um HTML que possui 
a lógica de parsing construída nativamente no lado do cliente via JavaScript.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def formatador_listas(request):
    """
    O QUE FAZ: Valida permissões e renderiza o Formatador de Listas.
    POR QUÊ EXISTE: Proteger o acesso de acordo com o painel de Permissões Globais do GGCI.
    COMO FUNCIONA: 
        1. Avalia a flag booleana `request.user.p_formatador_listas`.
        2. Bloqueia forçando um redirect para o hub de ferramentas se o acesso for negado.
        3. Exceção automática aplicada ao superusuário de admin.
    """
    if not request.user.p_formatador_listas and request.user.usuario != 'admin@ovg.org.br':
        return redirect('ferramentas')
    return render(request, 'formatador_listas/index.html')
