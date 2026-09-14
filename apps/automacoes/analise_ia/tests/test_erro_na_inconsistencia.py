"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_erro_na_inconsistencia.py ===
Propósito: Trava a regra da mensalidade COM desconto no contrato — o que não invalida e o
que é erro de catalogação da própria IA.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: no contrato, a mensalidade COM desconto responde por quase toda a
inconsistência apontada pela IA — "não localizado" (11.609 linhas), "é menor" (8.004) e "é
maior" (2.736) no Parquet de 13/09/2026. Nenhuma delas invalida o documento: não achar o
desconto, ou achar um diferente do que o sistema tem, é divergência de desconto, não erro
de documento. Quem invalida contrato é semestre, CPF e mensalidade INTEGRAL.

Isso já era verdade no código — as três frases nunca entraram em
`matematica_invalida_financeiro` —, mas era verdade por OMISSÃO, e omissão não avisa quando
alguém a desfaz. Meia linha acrescentada àquela expressão jogaria 22 mil contratos válidos
para `Falso Válido` sem que teste nenhum reclamasse. Os três primeiros casos aqui existem
para que essa meia linha quebre alguma coisa.

O QUE MUDOU DE FATO é o segundo grupo: a frase estar errada sobre o dado que a própria IA
extraiu. "não localizado" com `Gemini Mensalidade C/ Desconto` preenchido, "é menor" com o
valor maior ou igual, "é maior" com o valor menor ou igual. O contrato continua válido — o
que falhou foi a CATALOGAÇÃO —, e agora ele sai como `Erro na Inconsistência` em vez de se
misturar aos válidos puros. São 2.119 linhas na medição de 13/09/2026, 8,7% dos válidos do
contrato, e a maior parte delas (2.080) é o "não localizado" com valor lido.

O ÚLTIMO GRUPO É O CONTRAPESO: erro de catalogação NUNCA esconde documento inválido. Se
semestre, CPF ou mensalidade integral divergirem, `Falso Válido` vem antes e prevalece.

Espelho do teste homônimo do dash_documentos_ia — o dashboard é a visualização deste relatório.
"""

import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services import ggci

NAO_LOCALIZADO = 'Valor da mensalidade com desconto não localizado no contrato'
MENOR = 'Mensalidade com desconto no contrato é menor que o esperado'
MAIOR = 'Mensalidade com desconto no contrato é maior que o esperado'


def _linhas(**col):
    """
    Um contrato por linha, com o mínimo que `calcular_auditoria_ia` exige.

    Os padrões são de um contrato SEM defeito nenhum fora do desconto: CPF, semestre e
    curso batendo, mensalidade integral idêntica à do sistema e seis pagamentos líquidos
    (senão a linha vira `Inadimplente`, que sobrepõe qualquer veredito).

    `Processado` PRECISA VIR 'SIM'. Sem ela, `calcular_auditoria_ia` reescreve o status para
    `Não Processado` e, logo depois, o recalcula a partir do texto da inconsistência — toda
    linha com uma frase qualquer sairia `Inválido`, e o teste mediria esse caminho em vez da
    regra do desconto.
    """
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [ggci.DOC_CONTRATO] * n,
        'Status_IA': ['Válido'] * n,
        'Processado': ['SIM'] * n,
        'CPF': [str(i) for i in range(n)],
        'Gemini CPF': [str(i) for i in range(n)],
        'Gemini Semestre': ['2025/2'] * n,
        'Faculdade': ['IES EXEMPLO'] * n,
        'Curso': ['DIREITO'] * n,
        'Gemini Curso': ['DIREITO'] * n,
        'tipo_bolsa_final': ['PARCIAL'] * n,
        'Mensalidade S/ Desconto': [1000.0] * n,
        'Gemini Mensalidade S/ Desconto': [1000.0] * n,
        'Mensalidade C/ Desconto': [500.0] * n,
        'qtd_pagtos': [6] * n,
        'qtd_pagtos_retroativos': [0] * n,
        'total bolsa paga': [3000.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


class ErroNaInconsistenciaTests(SimpleTestCase):

    def _auditar(self, df):
        """Cache Gemini apontado para arquivo descartável — um teste não encosta no cache real."""
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                return ggci.calcular_auditoria_ia(df)

    def _status(self, **col):
        return self._auditar(_linhas(**col))['Status_IA'].tolist()

    # --- o desconto sozinho não invalida nada -------------------------------------

    def test_desconto_nao_localizado_de_verdade_continua_valido(self):
        """A IA não achou o valor e disse que não achou. É a frase certa sobre o dado certo."""
        self.assertEqual(self._status(
            Inscrição=[2200001],
            **{'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [0.0]},
        ), ['Válido'])

    def test_desconto_menor_de_verdade_continua_valido(self):
        """Desconto menor que o esperado é divergência de desconto, não defeito de documento."""
        self.assertEqual(self._status(
            Inscrição=[2200002],
            **{'Gemini Inconsistencias': [MENOR],
               'Gemini Mensalidade C/ Desconto': [400.0]},
        ), ['Válido'])

    def test_desconto_maior_de_verdade_continua_valido(self):
        """O espelho do anterior: para cima também não invalida."""
        self.assertEqual(self._status(
            Inscrição=[2200003],
            **{'Gemini Inconsistencias': [MAIOR],
               'Gemini Mensalidade C/ Desconto': [600.0]},
        ), ['Válido'])

    # --- a frase errada sobre o próprio dado da IA --------------------------------

    def test_nao_localizado_com_valor_lido_e_erro_na_inconsistencia(self):
        """
        O caso de longe mais comum: 2.080 das 2.119 linhas da medição de 13/09/2026. A IA
        extraiu R$ 500,00 e, na mesma resposta, escreveu que não tinha localizado o valor.
        """
        self.assertEqual(self._status(
            Inscrição=[2200004],
            **{'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Erro na Inconsistência'])

    def test_menor_com_valor_igual_e_erro_na_inconsistencia(self):
        """Disse "é menor" sobre um valor idêntico ao do sistema."""
        self.assertEqual(self._status(
            Inscrição=[2200005],
            **{'Gemini Inconsistencias': [MENOR],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Erro na Inconsistência'])

    def test_menor_com_valor_maior_e_erro_na_inconsistencia(self):
        self.assertEqual(self._status(
            Inscrição=[2200006],
            **{'Gemini Inconsistencias': [MENOR],
               'Gemini Mensalidade C/ Desconto': [600.0]},
        ), ['Erro na Inconsistência'])

    def test_maior_com_valor_menor_e_erro_na_inconsistencia(self):
        self.assertEqual(self._status(
            Inscrição=[2200007],
            **{'Gemini Inconsistencias': [MAIOR],
               'Gemini Mensalidade C/ Desconto': [400.0]},
        ), ['Erro na Inconsistência'])

    def test_regra_e_so_do_contrato(self):
        """
        A mesma frase num RIAF não vira `Erro na Inconsistência`. A regra nasce de como o
        desconto é lido no contrato, e `is_contrato` não serve de máscara para ela porque
        casa CONTRATO, RIAF e RELATÓRIO juntos.
        """
        self.assertNotIn('Erro na Inconsistência', self._status(
            Inscrição=[2200008],
            **{'Documento Tipo': [ggci.DOC_RIAF],
               'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ))

    # --- o curso não é cobrado de quem não o carrega ------------------------------

    def test_contrato_sem_curso_lido_continua_valido(self):
        """
        O CASO REAL, e o que mantinha `Erro na Inconsistência` em zero.

        Os demais testes deste arquivo preenchem `Gemini Curso` — e é justamente isso que
        escondia o defeito. No espelho, o prompt do contrato NUNCA extrai o curso:
        `gemini_curso` vem vazio em 53.232 dos 53.453 contratos. Com a regra de curso
        valendo para toda aba, `ia_curso == ''` invalidava a matemática de todos eles e a
        IA dizendo `Válido` virava `Falso Válido` — 24.349 contra 146 no Parquet de
        14/09/2026.
        """
        self.assertEqual(self._status(
            Inscrição=[2200011],
            **{'Gemini Curso': [''],
               'Gemini Inconsistencias': ['Sem inconsistências'],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Válido'])

    def test_contrato_sem_curso_lido_alcanca_erro_na_inconsistencia(self):
        """
        A consequência direta: `Erro na Inconsistência` é decidido DEPOIS de `Falso
        Válido`, então bastava o curso vazio para ele nunca ser alcançado. Com a regra
        restrita a quem carrega o campo, a mesma linha chega ao veredito que lhe cabe.
        """
        self.assertEqual(self._status(
            Inscrição=[2200012],
            **{'Gemini Curso': [''],
               'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Erro na Inconsistência'])

    def test_contrato_com_curso_divergente_continua_valido(self):
        """
        Os 221 contratos com `gemini_curso` preenchido são refugo do prompt desalinhado —
        treze deles dizem "(Item válido)". Um campo que o documento não traz não vira
        prova contra ele nem quando vem sujo.
        """
        self.assertEqual(self._status(
            Inscrição=[2200013],
            **{'Gemini Curso': ['(Item válido)'],
               'Gemini Inconsistencias': ['Sem inconsistências'],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Válido'])

    def test_riaf_sem_curso_lido_continua_falso_valido(self):
        """
        O CONTRAPESO: o RIAF carrega o curso de verdade (11,2% de vazio, contra 100% do
        contrato), e ali o vazio continua invalidando — é a IA não tendo achado o que
        está no arquivo. A correção restringe a regra, não a remove.
        """
        self.assertEqual(self._status(
            Inscrição=[2200014],
            **{'Documento Tipo': [ggci.DOC_RIAF],
               'Gemini Curso': [''],
               'Gemini Inconsistencias': ['Sem inconsistências'],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Falso Válido'])

    def test_historico_com_curso_divergente_continua_falso_valido(self):
        """O histórico é o outro que traz o curso: divergência ali segue invalidando."""
        self.assertEqual(self._status(
            Inscrição=[2200015],
            **{'Documento Tipo': [ggci.DOC_HISTORICO],
               'Gemini Curso': ['ENFERMAGEM'],
               'Gemini Inconsistencias': ['Sem inconsistências'],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Falso Válido'])

    # --- o erro de catalogação nunca esconde documento inválido -------------------

    def test_semestre_divergente_continua_falso_valido(self):
        """Semestre errado invalida o contrato, e `Falso Válido` vem antes na decisão."""
        self.assertEqual(self._status(
            Inscrição=[2200009],
            **{'Gemini Semestre': ['2025/1'],
               'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Falso Válido'])

    def test_mensalidade_integral_divergente_continua_falso_valido(self):
        """
        A mensalidade SEM desconto é a que invalida. Com ela divergindo, a frase errada
        sobre o desconto continua existindo — mas o que a tela precisa mostrar é o
        documento inválido, não o deslize de catalogação.
        """
        self.assertEqual(self._status(
            Inscrição=[2200010],
            **{'Gemini Mensalidade S/ Desconto': [900.0],
               'Gemini Inconsistencias': [NAO_LOCALIZADO],
               'Gemini Mensalidade C/ Desconto': [500.0]},
        ), ['Falso Válido'])
