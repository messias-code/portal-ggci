"""
Módulo de Visualização: Formatador de Dados
O QUE FAZ: Entrega a interface SPA (Single Page Application) da ferramenta de formatação.
POR QUÊ EXISTE: Atua como ponto de entrada protegido, garantindo que apenas usuários 
com a permissão correta (`p_formatador_dados`) possam acessar a ferramenta.
COMO FUNCIONA: Sendo uma ferramenta *client-side*, a view não processa dados, apenas bloqueia
ou autoriza a renderização do arquivo estático HTML contendo o JS de formatação.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def formatador_dados(request):
    """
    O QUE FAZ: Valida permissões e renderiza o painel principal do Formatador de Dados.
    POR QUÊ EXISTE: Redirecionar usuários não autorizados de volta ao menu e proteger a ferramenta.
    COMO FUNCIONA: 
        1. Inspeciona `request.user.p_formatador_dados` e a exceção de admin.
        2. Se falso, força o `redirect('ferramentas')`.
        3. Se verdadeiro, entrega o template HTML puro.
    """
    if not request.user.p_formatador_dados and request.user.usuario != 'admin@ovg.org.br':
        return redirect('ferramentas')
    return render(request, 'formatador_dados/index.html')
