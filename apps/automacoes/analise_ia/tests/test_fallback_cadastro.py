"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_fallback_cadastro.py ===
Propósito: Travar o repasse de Modalidade e dos períodos pelo fallback por Inscrição
           dentro de `mesclar_sql_e_reordenar`.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `mesclar_sql_e_reordenar` tem DOIS caminhos de recuperação quando o
cadastro do aluno não vem completo, e eles cobrem situações diferentes:

1. **Remapeamento por último semestre** (`df.update(df_remapped)`): age quando a chave
   (Inscrição + Semestre) NÃO bate no banco. Copia o bloco inteiro do último semestre
   conhecido, então já trazia Modalidade e períodos "de graça".
2. **`mapping_fallback`**: age em TODAS as linhas, inclusive nas que bateram no semestre
   certo mas cuja linha veio com o campo em branco. Esse caminho listava `matricula`,
   `email` e telefones, mas omitia `modalidade`, `periodo_atual` e `periodo_quantidade` —
   dado de cadastro que não muda com o semestre e que não tinha motivo para ficar de fora.

O teste separa os dois cenários de propósito: o primeiro documenta que o caminho (1) já
funcionava (guarda contra regressão de quem mexer no remapeamento) e o segundo é o que a
correção do `mapping_fallback` passou a cobrir.
"""
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.ggci import mesclar_sql_e_reordenar


COLS_CADASTRO = ['Modalidade', 'Período atual', 'Período quantidade', 'Matricula']


def _documento(inscricao, semestre):
    """Uma linha de documento, com o mínimo que a função exige para rodar."""
    return pd.DataFrame({
        'Inscrição': [inscricao],
        'Semestre': [semestre],
        'Documento Tipo': ['Histórico Escolar'],
        'Status_IA': ['Não Processado'],
        'CPF': ['70226605140'],
    })


def _colher(df):
    return {c: (df[c].iloc[0] if c in df.columns else '<AUSENTE>') for c in COLS_CADASTRO}


class FallbackCadastroTests(SimpleTestCase):

    def test_semestre_ausente_no_banco_usa_o_ultimo_conhecido(self):
        """
        Caminho (1). O documento é de 2025-2 e o banco só conhece o aluno em 2026-1 —
        situação real dos 7 alunos da IAESUP no espelho do histórico. `periodo_atual`
        retrocede de 7 para 6 porque `calc_diff` desconta a diferença de semestres;
        `periodo_quantidade` e `modalidade` não dependem do semestre e vão inteiros.
        """
        df_sql = pd.DataFrame({
            'uni_codigo': [2213322], 'semestre': ['2026-1'],
            'modalidade': ['Presencial'], 'periodo_atual': [7.0], 'periodo_quantidade': [8],
            'matricula': ['12345'], 'tipo_bolsa_final': ['INTEGRAL'], 'qtd_pagtos': [0],
        })
        obtido = _colher(mesclar_sql_e_reordenar(_documento(2213322, '2025-2'), df_sql))
        self.assertEqual(obtido['Modalidade'], 'Presencial')
        self.assertEqual(obtido['Período quantidade'], 8)
        self.assertEqual(obtido['Período atual'], 6.0)

    def test_linha_do_semestre_certo_em_branco_cai_no_fallback(self):
        """
        Caminho (2), o que a correção cobriu. O aluno BATE em 2025-2, mas o cadastro
        daquele semestre veio vazio. Antes só `Matricula` era recuperada; `Modalidade` e
        os períodos saíam em branco para o relatório.
        """
        df_sql = pd.DataFrame({
            'uni_codigo': [555, 555], 'semestre': ['2025-2', '2026-1'],
            'modalidade': ['', 'EAD'],
            'periodo_atual': ['', 7.0],
            'periodo_quantidade': ['', 8],
            'matricula': ['', '12345'],
            'tipo_bolsa_final': ['INTEGRAL', 'INTEGRAL'], 'qtd_pagtos': [0, 0],
        })
        obtido = _colher(mesclar_sql_e_reordenar(_documento(555, '2025-2'), df_sql))
        self.assertEqual(obtido['Modalidade'], 'EAD')
        self.assertEqual(obtido['Período quantidade'], 8)
        self.assertEqual(obtido['Período atual'], 7.0)
        self.assertEqual(obtido['Matricula'], '12345')

    def test_valor_do_semestre_certo_tem_precedencia_sobre_o_fallback(self):
        """
        O fallback só preenche buraco. Se o semestre do documento tem o dado, ele manda —
        senão um aluno que trocou de modalidade herdaria a do semestre errado.
        """
        df_sql = pd.DataFrame({
            'uni_codigo': [777, 777], 'semestre': ['2025-2', '2026-1'],
            'modalidade': ['Presencial', 'EAD'],
            'periodo_atual': [3.0, 4.0], 'periodo_quantidade': [8, 10],
            'matricula': ['999', '111'],
            'tipo_bolsa_final': ['PARCIAL', 'PARCIAL'], 'qtd_pagtos': [1, 1],
        })
        obtido = _colher(mesclar_sql_e_reordenar(_documento(777, '2025-2'), df_sql))
        self.assertEqual(obtido['Modalidade'], 'Presencial')
        self.assertEqual(obtido['Período quantidade'], 8)
        self.assertEqual(obtido['Período atual'], 3.0)

    def test_zero_nao_e_buraco_e_nao_pode_ser_sobrescrito(self):
        """
        `qtd_periodos = 0` é dado real da origem (109 linhas em 2025/2), não ausência.
        O fallback não pode "consertar" o zero puxando o valor de outro semestre — isso
        mascararia cadastro incompleto da IES, que é justamente o que se quer enxergar.
        """
        df_sql = pd.DataFrame({
            'uni_codigo': [888, 888], 'semestre': ['2025-2', '2026-1'],
            'modalidade': ['Presencial', 'Presencial'],
            'periodo_atual': [0.0, 5.0], 'periodo_quantidade': [0, 10],
            'matricula': ['321', '321'],
            'tipo_bolsa_final': ['INTEGRAL', 'INTEGRAL'], 'qtd_pagtos': [1, 1],
        })
        obtido = _colher(mesclar_sql_e_reordenar(_documento(888, '2025-2'), df_sql))
        self.assertEqual(obtido['Período quantidade'], 0)
        self.assertEqual(obtido['Período atual'], 0.0)
