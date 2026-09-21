"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_motivos_da_divergencia.py ===
Propósito: Trava o conteúdo da coluna `Motivos Divergência` — o texto que a aba Análise IA
mostra ao parar o ponteiro sobre o `Status IA` da linha.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `Falso Válido` diz que a matemática discorda da IA, e nunca em QUE campo.
Como o veredito só existe quando a IA NÃO viu problema, a coluna `Gemini Inconsistencias`
daquela linha costuma dizer "Sem inconsistências" — e descobrir que o reprovado foi o CPF
exigia comparar as 63 colunas da tabela duas a duas, no olho.

A COLUNA NÃO É UMA SEGUNDA REGRA. Ela reaproveita as mesmas máscaras que compõem
`matematica_invalida`: cada pedaço elementar daquela expressão vira uma frase. Se o veredito
mudar, o motivo muda junto. O risco que este teste cobre é o oposto — alguém mexer numa das
máscaras e o motivo continuar dizendo o que era verdade antes, que é o defeito mais caro
possível numa tela cuja função é explicar.

A FRASE É A DO CATÁLOGO DOS PROMPTS (`prompts/<TIPO>/prompt.yaml`), e hoje ela é a MESMA
para todo documento: os três prompts foram padronizados em "no documento". É o mesmo
vocabulário da coluna `Gemini Inconsistencias`, e é de propósito: a mesma falha com dois
nomes na mesma tela faria parecer que são duas.
"""

import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import ggci
from apps.dashboards.dash_documentos_ia.views import _motivos_das_linhas


def _linhas(documento=None, **col):
    """
    Um documento por linha, com o mínimo que `calcular_auditoria_ia` exige.

    Os padrões descrevem um documento SEM defeito nenhum: CPF, semestre e curso batendo,
    mensalidade integral idêntica à do sistema e seis pagamentos líquidos — sem eles a linha
    vira `Inadimplente`, que sobrepõe o veredito e zera o motivo de propósito.

    `Processado` PRECISA VIR 'SIM', pelo mesmo motivo de `test_erro_na_inconsistencia`: sem
    ela o status é reescrito para `Não Processado` e a linha sai do caminho que se quer medir.
    """
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [documento or ggci.DOC_CONTRATO] * n,
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
        'Gemini Mensalidade C/ Desconto': [500.0] * n,
        'qtd_pagtos': [6] * n,
        'qtd_pagtos_retroativos': [0] * n,
        'total bolsa paga': [3000.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


class MotivosDaDivergenciaTests(SimpleTestCase):

    def _auditar(self, df):
        """Cache Gemini apontado para arquivo descartável — um teste não encosta no cache real."""
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                return ggci.calcular_auditoria_ia(df)

    def _motivos(self, documento=None, **col):
        saida = self._auditar(_linhas(documento, **col))
        return saida['Motivos Divergência'].tolist(), saida['Status_IA'].tolist()

    # --- o caso que originou a coluna ---------------------------------------------

    def test_falso_valido_por_cpf_diz_que_foi_o_cpf(self):
        """
        A linha exata que levantou o pedido: contrato de 2025-1 dado por válido pela IA, com
        `Sem inconsistências` na coluna dela, e um CPF que não é o do sistema.
        """
        motivos, status = self._motivos(
            Inscrição=[2040982],
            **{'CPF': ['94443076115'], 'Gemini CPF': ['7743666131'],
               'Gemini Inconsistencias': ['Sem inconsistências']},
        )
        self.assertEqual(status, ['Falso Válido'])
        self.assertEqual(motivos, ['CPF do documento diverge do sistema'])

    def test_documento_sem_divergencia_nao_tem_motivo(self):
        """Nada a explicar: a flag da tela não ganha tooltip, e a célula não vira ruído."""
        motivos, status = self._motivos(Inscrição=[2200001])
        self.assertEqual(status, ['Válido'])
        self.assertEqual(motivos, [''])

    # --- a listinha ---------------------------------------------------------------

    def test_dois_motivos_saem_na_ordem_do_catalogo(self):
        """
        CPF é nível crítico, semestre é nível alto — e a ordem é a mesma que o prompt exige
        da IA ao concatenar inconsistências, para que as duas listas se leiam no mesmo sentido.
        """
        motivos, _ = self._motivos(
            Inscrição=[2200002],
            **{'CPF': ['111'], 'Gemini CPF': ['999'], 'Gemini Semestre': ['2024/1']},
        )
        self.assertEqual(motivos, ['CPF do documento diverge do sistema'
                                   ' | Semestre diverge com sistema'])

    def test_cpf_ausente_e_cpf_divergente_sao_frases_diferentes(self):
        """Campo em branco e campo trocado são falhas diferentes, e o catálogo as separa."""
        motivos, _ = self._motivos(Inscrição=[2200003], **{'Gemini CPF': ['']})
        self.assertEqual(motivos, ['CPF não localizado no documento'])

    # --- erro na inconsistência: a frase errada E a certa --------------------------

    def test_erro_na_inconsistencia_mostra_a_frase_que_a_ia_deveria_ter_escrito(self):
        """
        Aqui o documento está certo e quem errou foi a IA: ela escreveu "não localizado"
        sobre um valor que ela mesma leu. Dizer só que a frase está errada devolve o
        revisor ao ponto de partida — o motivo precisa fechar a conta e dizer qual era a
        frase certa para aquele valor, que neste caso é nenhuma.
        """
        motivos, status = self._motivos(
            Inscrição=[2200008],
            **{'Gemini Inconsistencias': ['Valor da mensalidade com desconto não localizado no documento']},
        )
        self.assertEqual(status, ['Erro na Inconsistência'])
        self.assertEqual(motivos, ["A IA Apontou 'Mensalidade com desconto não localizado',"
                                   " Mas leu um valor no documento"
                                   " | O Correto Seria: 'Valor da mensalidade com desconto"
                                   " está CONFORME o esperado no documento'"])

    def test_a_frase_correta_sai_do_valor_que_a_ia_leu(self):
        """
        A IA apontou MAIOR sobre um valor MENOR que o do sistema. A frase certa não é
        "sem inconsistências": existe divergência, só que para o outro lado — e é ela que
        o revisor precisa ver para saber que o prompt inverteu a comparação, não que a
        inventou.
        """
        motivos, status = self._motivos(
            Inscrição=[2200009],
            **{'Gemini Inconsistencias': ['Mensalidade com desconto no contrato é MAIOR que o esperado'],
               'Gemini Mensalidade C/ Desconto': [400.0]},
        )
        self.assertEqual(status, ['Erro na Inconsistência'])
        self.assertIn("O Correto Seria: 'Valor da mensalidade com desconto é MENOR"
                      " que o esperado no documento'", motivos[0])

    def test_desconto_divergente_sozinho_nao_vira_motivo(self):
        """
        Mensalidade COM desconto menor, e a IA calada a respeito: pela regra do contrato
        isso não invalida nada, o documento é `Válido` — e um tooltip aqui contradiria o
        próprio veredito da linha.
        """
        motivos, status = self._motivos(
            Inscrição=[2200010], **{'Gemini Mensalidade C/ Desconto': [400.0]})
        self.assertEqual(status, ['Válido'])
        self.assertEqual(motivos, [''])

    # --- falso inválido: a lista é da IA ------------------------------------------

    def test_falso_invalido_lista_o_que_a_ia_apontou(self):
        """
        A IA reprovou um documento que o sistema confere. Não há divergência NOSSA a
        listar — se houvesse, o veredito seria `Inválido`. O que o balão mostra são as
        frases da própria IA, que são o que precisa ser revisto no prompt.
        """
        motivos, status = self._motivos(
            Inscrição=[2200011],
            **{'Status_IA': ['Inválido'],
               'Gemini Inconsistencias': ['Nome do aluno diverge do sistema,'
                                          ' Mantenedora da IES diverge do sistema']},
        )
        self.assertEqual(status, ['Falso Inválido'])
        self.assertEqual(motivos, ['Nome do aluno diverge do sistema'
                                   ' | Mantenedora da IES diverge do sistema'])

    def test_falso_invalido_sem_frase_nao_inventa_lista(self):
        """
        `Inválido` com "Sem inconsistências" é a IA se contradizendo no veredito, e não
        uma lista vazia a exibir — repetir a frase como se fosse motivo diria ao operador
        que o documento foi reprovado por não ter problema nenhum.
        """
        motivos, status = self._motivos(
            Inscrição=[2200012],
            **{'Status_IA': ['Inválido'], 'Gemini Inconsistencias': ['Sem inconsistências']},
        )
        self.assertEqual(status, ['Falso Inválido'])
        self.assertEqual(motivos, [''])

    # --- a frase segue o documento ------------------------------------------------

    def test_riaf_usa_a_mesma_frase_do_contrato(self):
        """
        Os três prompts foram padronizados em "no documento", então o RIAF diz exatamente o
        que o contrato diz. Ter dois nomes para a mesma falha, na mesma tela, faria o revisor
        procurar uma diferença que não existe.
        """
        motivos, _ = self._motivos(
            documento=ggci.DOC_RIAF,
            Inscrição=[2200004],
            **{'CPF': ['111'], 'Gemini CPF': ['999']},
        )
        self.assertIn('CPF do documento diverge do sistema', motivos[0])

    # --- o que NÃO vira motivo ----------------------------------------------------

    def test_historico_nao_ganha_motivo_financeiro(self):
        """
        Regra financeira não faz parte da verificação do histórico escolar — é a mesma
        dispensa que `matematica_invalida` já dá a ele, e o motivo não pode contradizê-la.
        """
        motivos, status = self._motivos(
            documento=ggci.DOC_HISTORICO,
            Inscrição=[2200005],
            **{'Gemini Mensalidade S/ Desconto': [400.0]},
        )
        self.assertEqual(status, ['Válido'])
        self.assertEqual(motivos, [''])

    def test_documento_nao_lido_nao_ganha_motivo(self):
        """
        Não processado, ausente e corrompido não passaram por auditoria de conteúdo. Listar
        "CPF não localizado" para um documento que nunca chegou transforma ausência em erro
        de preenchimento — e é o tipo de frase que vira cobrança indevida à IES.
        """
        motivos, status = self._motivos(
            Inscrição=[2200006],
            **{'Status_IA': ['Não Processado'], 'Gemini CPF': [''], 'Processado': ['NÃO']},
        )
        self.assertEqual(status, ['Não Processado'])
        self.assertEqual(motivos, [''])

    def test_inadimplente_nao_ganha_motivo(self):
        """Sem repasse líquido não há documento a cobrar, então não há divergência a explicar."""
        motivos, status = self._motivos(
            Inscrição=[2200007],
            **{'CPF': ['111'], 'Gemini CPF': ['999'],
               'qtd_pagtos': [0], 'total bolsa paga': [0.0]},
        )
        self.assertEqual(status, ['Inadimplente'])
        self.assertEqual(motivos, [''])


class MotivosNaRespostaDaTelaTests(SimpleTestCase):
    """A ponte entre a coluna do Parquet e a lista que a tabela recebe."""

    def test_motivos_acompanham_a_ordem_final_das_linhas(self):
        """
        A série é separada ANTES do recorte de colunas, e a tabela é ordenada e cortada
        DEPOIS. Sem reindexar pelo índice final, o motivo da linha 3 apareceria na linha 1.
        """
        serie = pd.Series(['CPF do documento diverge do sistema',
                           '',
                           'A | B'], index=[10, 11, 12])
        df = pd.DataFrame({'status_ia': ['x', 'y']}, index=[12, 10])

        self.assertEqual(_motivos_das_linhas(serie, df), [['A', 'B'],
                                                          ['CPF do documento diverge do sistema']])

    def test_relatorio_antigo_nao_derruba_a_tabela(self):
        """
        Parquet gerado antes desta mudança não tem a coluna. A tela precisa continuar de pé
        sem tooltip — e não em branco, que é o que aconteceria se a view estourasse aqui.
        """
        self.assertEqual(_motivos_das_linhas(None, pd.DataFrame({'a': [1, 2]})), [])
