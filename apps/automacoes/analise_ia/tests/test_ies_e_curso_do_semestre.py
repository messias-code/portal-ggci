"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_ies_e_curso_do_semestre.py ===
Propósito: Travar, dentro de `mesclar_sql_e_reordenar`, a IES e o curso do PRÓPRIO
           semestre do documento para quem transferiu de faculdade no meio do benefício.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: o cadastro do SIBU (`universitarios`) guarda só a faculdade e o curso de
HOJE. O histórico por semestre existe apenas em `sibu.lancamento`, e é de lá que os
espelhos passaram a ler os dois. Só que o `mapping_fallback` desfazia isso no final:
o ramo da `Faculdade` invertia a precedência em TODAS as linhas, deixando o último
semestre do aluno escrever por cima do semestre que tinha vindo certo do banco.

Caso real (15/09/2026), inscrição 2203791: pagou ENGENHARIA AGRONÔMICA na UNIGOYAZES de
07/2025 a 06/2026 e ENGENHARIA CIVIL na UNIARAGUAIA a partir de 08/2026 — o relatório
mostrava UNIARAGUAIA/ENGENHARIA CIVIL nos quatro semestres.

Os dois casos estão separados de propósito porque a inversão TINHA motivo e ele continua
valendo: na linha que o banco não sabe responder por semestre, a `Faculdade` é o nome lido
do DOCUMENTO — abreviado e sujo — e o nome do cadastro é melhor do que ele. A precedência
não foi trocada, foi restringida a essas linhas.
"""
import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services.ggci import mesclar_sql_e_reordenar


UNIGOYAZES = 'UNIGOYAZES - CENTRO UNIVERSITARIO GOYAZES - CENTRO DE ESTUDOS OCTAVIO DIAS DE OL'
UNIARAGUAIA = 'UNIARAGUAIA - CENTRO UNIVERSITARIO ARAGUAIA - SOCIEDADE DE EDUCACAO E CULTURA DE'


def _documento(inscricao, semestre, faculdade=None, curso=None):
    """Uma linha de documento, com o mínimo que a função exige para rodar."""
    dados = {
        'Inscrição': [inscricao],
        'Semestre': [semestre],
        'Documento Tipo': ['Contrato'],
        'Status_IA': ['Não Processado'],
        'CPF': ['71606110128'],
    }
    if faculdade is not None:
        dados['Faculdade'] = [faculdade]
    if curso is not None:
        dados['Curso'] = [curso]
    return pd.DataFrame(dados)


def _historico_da_transferencia():
    """O aluno 2203791 como o banco o conhece: dois semestres, duas faculdades."""
    return pd.DataFrame({
        'uni_codigo': [2203791, 2203791],
        'semestre': ['2025-2', '2026-2'],
        'nome_faculdade_sql': [UNIGOYAZES, UNIARAGUAIA],
        'CUR_NOME': ['ENGENHARIA AGRONÔMICA', 'ENGENHARIA CIVIL'],
        'tipo_bolsa_final': ['INTEGRAL', 'INTEGRAL'],
        'qtd_pagtos': [6, 1],
    })


class IesECursoDoSemestreTests(SimpleTestCase):

    def test_quem_transferiu_mantem_a_ies_do_proprio_semestre(self):
        """
        O documento é de 2025-2 e o banco tem esse semestre: a IES tem de ser a UNIGOYAZES,
        mesmo o aluno estando hoje na UNIARAGUAIA. Era exatamente aqui que o fallback
        entrava e trocava as duas.
        """
        obtido = mesclar_sql_e_reordenar(
            _documento(2203791, '2025-2'), _historico_da_transferencia())
        self.assertIn('UNIGOYAZES', obtido['Faculdade'].iloc[0].upper())

    def test_quem_transferiu_mantem_o_curso_do_proprio_semestre(self):
        """
        O curso anda junto com a IES: transferir de faculdade quase sempre é trocar de
        curso, e ler a faculdade do semestre com o curso de hoje monta um par que nunca
        existiu. É esta coluna que a regra de curso do RIAF e do Histórico compara com o
        que a IA leu no documento.
        """
        obtido = mesclar_sql_e_reordenar(
            _documento(2203791, '2025-2'), _historico_da_transferencia())
        self.assertEqual(obtido['Curso'].iloc[0].upper(), 'ENGENHARIA AGRONÔMICA')

    def test_o_semestre_seguinte_recebe_a_ies_e_o_curso_novos(self):
        """A contraprova: em 2026-2 o mesmo aluno tem de aparecer na UNIARAGUAIA."""
        obtido = mesclar_sql_e_reordenar(
            _documento(2203791, '2026-2'), _historico_da_transferencia())
        self.assertIn('UNIARAGUAIA', obtido['Faculdade'].iloc[0].upper())
        self.assertEqual(obtido['Curso'].iloc[0].upper(), 'ENGENHARIA CIVIL')

    def test_semestre_ausente_no_banco_continua_usando_o_ultimo_conhecido(self):
        """
        A intenção original do fallback, preservada. O documento é de 2024-2, semestre que
        o banco não conhece: sem nada por semestre para consultar, vale o último cadastro,
        e ele tem de vencer o nome sujo que veio do documento.
        """
        obtido = mesclar_sql_e_reordenar(
            _documento(2203791, '2024-2', faculdade='UNIARAG. CENTRO UNIV.'),
            _historico_da_transferencia())
        self.assertIn('UNIARAGUAIA', obtido['Faculdade'].iloc[0].upper())

    def test_curso_do_documento_tem_precedencia_sobre_o_banco(self):
        """
        O preenchimento por semestre só tapa buraco. O `Curso` que o espelho do documento
        já trouxe — hoje também lido do lançamento daquele semestre — continua mandando,
        senão a correção do SQL seria desfeita aqui dentro.
        """
        obtido = mesclar_sql_e_reordenar(
            _documento(2203791, '2025-2', curso='Agronomia'),
            _historico_da_transferencia())
        self.assertEqual(obtido['Curso'].iloc[0], 'Agronomia')
