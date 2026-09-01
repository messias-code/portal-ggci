from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required(login_url='/')
def dashboards(request):
    """
    O QUE FAZ: Renderiza o hub de Dashboards, que lista os painéis disponíveis.
    POR QUÊ EXISTE: Camada de segurança base (Gatekeeper) do menu.
    COMO FUNCIONA: Libera o acesso a quem tiver permissão para QUALQUER painel do
                   hub — ou ao admin. Checar só p_dash_polichat barrava quem
                   tivesse apenas o dashboard de Documentos IA.
    """
    tem_acesso = request.user.p_dash_polichat or request.user.p_dash_documentos_ia
    if not tem_acesso and request.user.usuario != 'admin@ovg.org.br':
        return redirect('inicio')
    return render(request, 'menu_dashboards/index.html')
