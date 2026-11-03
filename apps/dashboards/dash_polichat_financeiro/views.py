"""
Camada Web: Polichat Financeiro
Views e APIs para renderização do dashboard executivo e análise de custos Meta e Polichat.
"""

import json
from django.shortcuts import render, redirect
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from .services import data_service


def tem_permissao_polichat_financeiro(user):
    """Valida se o usuário logado possui privilégio de acesso ao painel financeiro."""
    if not user.is_authenticated:
        return False
    if user.usuario == 'admin@ovg.org.br' or getattr(user, 'is_superuser', False):
        return True
    return bool(
        getattr(user, 'p_polichat_financeiro', False)
        or getattr(user, 'p_dash_polichat', False)
    )


@login_required(login_url='/')
def polichat_financeiro_view(request):
    """
    O QUE FAZ: Renderiza o painel principal do Polichat - Financeiro.
    POR QUÊ EXISTE: Apresenta o estudo executivo de mudança de regras da Meta,
                   impacto contratual da Polichat e projeções de renovação em 03/2027.
    COMO FUNCIONA: Gatekeeper de segurança granular. Carrega resumo executivo, KPIs,
                   tabelas por categoria e histórico mensal.
    """
    if not tem_permissao_polichat_financeiro(request.user):
        return redirect('dashboards')

    resumo = data_service.obter_resumo_financeiro()
    simulador = data_service.obter_dados_simulador()

    contexto = {
        'titulo': 'Polichat - Financeiro',
        'kpis': resumo.get('kpis', {}),
        'categorias': resumo.get('categorias', []),
        'mensal': resumo.get('mensal', []),
        'contrato': resumo.get('contrato', {}),
        'tarifas_meta': resumo.get('tarifas_meta', []),
        'simulador': simulador,
        'mensal_json': json.dumps(resumo.get('mensal', [])),
        'categorias_json': json.dumps(resumo.get('categorias', [])),
        'simulador_json': json.dumps(simulador),
    }

    return render(request, 'dash_polichat_financeiro/index.html', contexto)


@login_required(login_url='/')
def api_polichat_financeiro_dados(request):
    """
    API assíncrona para filtragem e paginação ultra-rápida de atendimentos.
    """
    if not tem_permissao_polichat_financeiro(request.user):
        return JsonResponse({'sucesso': False, 'erro': 'Acesso não autorizado.'}, status=403)

    busca = request.GET.get('busca', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    janela = request.GET.get('janela', '').strip()
    mes = request.GET.get('mes', '').strip()
    
    try:
        pagina = int(request.GET.get('pagina', 1))
    except (ValueError, TypeError):
        pagina = 1

    try:
        por_pagina = min(100, max(10, int(request.GET.get('por_pagina', 25))))
    except (ValueError, TypeError):
        por_pagina = 25

    resultado = data_service.filtrar_atendimentos(
        busca=busca,
        categoria=categoria,
        janela=janela,
        mes=mes if mes else None,
        pagina=pagina,
        por_pagina=por_pagina
    )

    return JsonResponse({'sucesso': True, **resultado})


@login_required(login_url='/')
def download_planilha_comparativa(request):
    """
    Permite o download do arquivo oficial em Excel (comparativo_meta_jan_set_2026.xlsx).
    """
    if not tem_permissao_polichat_financeiro(request.user):
        return redirect('dashboards')

    caminho = data_service.obter_caminho_planilha()
    if not caminho or not caminho.exists():
        raise Http404('Arquivo de comparativo não encontrado no servidor.')

    return FileResponse(
        open(caminho, 'rb'),
        as_attachment=True,
        filename='comparativo_meta_jan_set_2026.xlsx'
    )
