"""
Serviço de Dados: Polichat Financeiro
Responsável por carregar, calcular e filtrar os dados da análise financeira da Meta e da Polichat.
"""

import os
import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = BASE_DIR / 'dados'
PARQUET_FILE = DADOS_DIR / 'atendimentos_financeiro.parquet'
JSON_FILE = DADOS_DIR / 'resumo_financeiro.json'
EXCEL_FILE = DADOS_DIR / 'comparativo_meta_jan_set_2026.xlsx'

_CACHE_RESUMO = None
_CACHE_DF = None


def obter_resumo_financeiro():
    """Retorna o resumo executivo, KPIs e tabelas mensais estruturadas."""
    global _CACHE_RESUMO
    if _CACHE_RESUMO is None:
        if JSON_FILE.exists():
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                _CACHE_RESUMO = json.load(f)
        else:
            _CACHE_RESUMO = {}
    return _CACHE_RESUMO


def obter_dados_simulador():
    """
    Retorna os parâmetros de simulação baseados no estudo real da OVG e regras da Meta.
    Volume consolidado: 680.490 msgs | Histórico Meta: R$ 6.200,50 | Nova Regra Meta: R$ 23.502,15
    """
    return {
        'kpis': {
            'total_creditos': 680490,
            'custo_historico': 6200.50,
            'custo_simulado': 23502.15,
            'diferenca': 17301.65,
            'media_mensal_msgs': 75610,
            'fatura_polichat_atual': 13354.92,
            'fatura_polichat_renovacao': 15146.98,
            'teto_mensal': 14477.44,
            'excesso_teto_mensal': 669.54,
            'fixo_mensal': 1818.88,
            'tarifa_pacote_1000': 363.75,
            'tarifa_meta_msg': 0.0350,
        },
        'metricas': [
            {
                'id': 'msg_ativa',
                'nome': 'Mensagens de Serviço (Atendimento)',
                'creditos': 492282,
                'preco_antigo': 0.0,
                'preco_novo': 16914.87,
                'diferenca': 16914.87,
                'media_mensal': 54698,
            },
            {
                'id': 'disparo',
                'nome': 'Campanhas de Disparo (Administração)',
                'creditos': 185260,
                'preco_antigo': 6157.41,
                'preco_novo': 6484.10,
                'diferenca': 326.69,
                'media_mensal': 20584,
            },
            {
                'id': 'template',
                'nome': 'Templates de Notificação Ativa',
                'creditos': 2948,
                'preco_antigo': 43.09,
                'preco_novo': 103.18,
                'diferenca': 60.10,
                'media_mensal': 328,
            },
            {
                'id': 'msg_receptiva',
                'nome': 'Mensagens Receptivas (Entrada Alunos)',
                'creditos': 437500,
                'preco_antigo': 0.0,
                'preco_novo': 0.0,
                'diferenca': 0.0,
                'media_mensal': 48611,
            },
        ],
        'mensal': [
            {'mes': 'Jan', 'nome': 'Janeiro', 'preco_antigo': 503.02, 'preco_novo': 3059.35, 'pct_antigo': 16, 'pct_novo': 100},
            {'mes': 'Fev', 'nome': 'Fevereiro', 'preco_antigo': 722.93, 'preco_novo': 2923.83, 'pct_antigo': 25, 'pct_novo': 96},
            {'mes': 'Mar', 'nome': 'Março', 'preco_antigo': 773.85, 'preco_novo': 2524.66, 'pct_antigo': 31, 'pct_novo': 100},
            {'mes': 'Abr', 'nome': 'Abril', 'preco_antigo': 996.45, 'preco_novo': 2467.47, 'pct_antigo': 40, 'pct_novo': 100},
            {'mes': 'Mai', 'nome': 'Maio', 'preco_antigo': 845.85, 'preco_novo': 2854.46, 'pct_antigo': 30, 'pct_novo': 100},
            {'mes': 'Jun', 'nome': 'Junho', 'preco_antigo': 571.66, 'preco_novo': 3303.37, 'pct_antigo': 17, 'pct_novo': 100},
            {'mes': 'Jul', 'nome': 'Julho', 'preco_antigo': 515.17, 'preco_novo': 2202.48, 'pct_antigo': 23, 'pct_novo': 100},
            {'mes': 'Ago', 'nome': 'Agosto', 'preco_antigo': 666.40, 'preco_novo': 2410.35, 'pct_antigo': 28, 'pct_novo': 100},
            {'mes': 'Set', 'nome': 'Setembro', 'preco_antigo': 605.19, 'preco_novo': 1756.20, 'pct_antigo': 34, 'pct_novo': 100},
        ]
    }


def obter_dataframe():
    """Retorna o DataFrame otimizado em memória."""
    global _CACHE_DF
    if _CACHE_DF is None:
        if PARQUET_FILE.exists():
            _CACHE_DF = pd.read_parquet(PARQUET_FILE)
        else:
            _CACHE_DF = pd.DataFrame()
    return _CACHE_DF


def filtrar_atendimentos(busca='', categoria='', janela='', mes=None, pagina=1, por_pagina=25):
    """
    Filtra e pagina os atendimentos com alto desempenho sobre o DataFrame em memória.
    """
    df = obter_dataframe()
    if df.empty:
        return {
            'registros': [],
            'total': 0,
            'pagina': 1,
            'por_pagina': por_pagina,
            'total_paginas': 0
        }

    sub = df

    if busca:
        termo = busca.strip().lower()
        sub = sub[
            sub['tel'].str.lower().str.contains(termo, na=False) |
            sub['operadores'].str.lower().str.contains(termo, na=False)
        ]

    if categoria:
        sub = sub[sub['categoria'].str.contains(categoria, na=False)]

    if janela:
        sub = sub[sub['janela'] == janela]

    if mes:
        try:
            mes_num = int(mes)
            sub = sub[sub['mes'] == mes_num]
        except (ValueError, TypeError):
            pass

    total = len(sub)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(1, min(pagina, total_paginas))

    inicio = (pagina - 1) * por_pagina
    fim = inicio + por_pagina
    fatia = sub.iloc[inicio:fim]

    registros = []
    for row in fatia.itertuples():
        registros.append({
            'data': getattr(row, 'data_str', str(row.data)),
            'mes': getattr(row, 'mes', 0),
            'telefone': getattr(row, 'tel', '-') or '-',
            'operador': getattr(row, 'operadores', '-') or '-',
            'categoria': getattr(row, 'categoria', '-'),
            'janela': getattr(row, 'janela', '-'),
            'msg_ben': int(getattr(row, 'msg_ben', 0)),
            'servico': int(getattr(row, 'servico', 0)),
            'template': int(getattr(row, 'template', 0)),
            'disparo': int(getattr(row, 'disparo', 0)),
            'total_ovg': int(getattr(row, 'ovg', 0)),
            'v_antes': round(float(getattr(row, 'v_antes', 0.0)), 4),
            'v_depois': round(float(getattr(row, 'v_depois', 0.0)), 4),
            'diferenca': round(float(getattr(row, 'v_depois', 0.0) - getattr(row, 'v_antes', 0.0)), 4),
            'por_que': getattr(row, 'por_que', '')
        })

    return {
        'registros': registros,
        'total': total,
        'pagina': pagina,
        'por_pagina': por_pagina,
        'total_paginas': total_paginas
    }


def obter_caminho_planilha():
    """Retorna o caminho do arquivo oficial em Excel para download."""
    if EXCEL_FILE.exists():
        return EXCEL_FILE
    alt = Path('/home/labs/portal-ggci-dev/artefatos_explicativos/polichat_financeiro/comparativo_meta_jan_set_2026.xlsx')
    if alt.exists():
        return alt
    return None
