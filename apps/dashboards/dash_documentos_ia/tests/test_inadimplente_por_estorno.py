"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_inadimplente_por_estorno.py ===
Propósito: Trava a regra que tira da cobrança quem não recebeu repasse líquido no semestre.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: a regra anterior era `qtd_pagtos == 0`, e ela NUNCA disparava — na tabela de
pagamentos não existe uma única linha com zero lançamentos (0 de 65.197 pares
inscrição/semestre). Quem devolveu a bolsa por inteiro continuava com `qtd_pagtos > 0` e saía
como `Ausente`, isto é, como pendência cobrável da IES.

O ESTRAGO ERA REAL: em 2025-2, 33 inscrições de histórico foram cobradas assim. Todas com
repasse líquido de R$ 0,00 — gente que foi desligada por NÃO MATRICULADO antes de estudar,
que desistiu da bolsa, ou que trocou de parcial para integral e migrou de inscrição. Nesse
último caso a cobrança ainda saía DUPLICADA: a inscrição velha (estornada) e a nova (que de
fato recebeu) apareciam as duas como pendentes, para a mesma pessoa e o mesmo semestre.

O QUE ESTE TESTE GARANTE: `qtd_pagtos - qtd_pagtos_retroativos <= 0` marca `Inadimplente`;
quem recebeu de verdade continua sendo cobrado; e a linha NUNCA é removida do DataFrame —
essa é a lição de `test_estorno_nao_remove_linha.py`, que este teste não pode desfazer.

Espelho do teste homônimo do analise_ia — este app precisa mostrar o mesmo número que o relatório.
"""
import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import ggci


def _linhas(**col):
    """DataFrame com o mínimo que `calcular_auditoria_ia` exige para rodar."""
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [ggci.DOC_HISTORICO] * n,
        'CPF': [str(i) for i in range(n)],
        'Gemini CPF': [str(i) for i in range(n)],
        'Gemini Semestre': ['2025/2'] * n,
        'Faculdade': ['IES EXEMPLO'] * n,
        'Curso': ['DIREITO'] * n,
        'tipo_bolsa_final': ['PARCIAL'] * n,
        'Gemini Mensalidade C/ Desconto': [0.0] * n,
        'Gemini Mensalidade S/ Desconto': [0.0] * n,
        'Mensalidade C/ Desconto': [0.0] * n,
        'Mensalidade S/ Desconto': [0.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


class InadimplentePorEstornoTests(SimpleTestCase):

    def _auditar(self, df):
        """Cache Gemini apontado para arquivo descartável — um teste não encosta no cache real."""
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                return ggci.calcular_auditoria_ia(df)

    def test_inadimplente_sem_documento_nao_e_descartado_nesta_funcao(self):
        """
        O caso das 33: um lançamento, cancelado a 100%, e nenhum documento entregue. Saía
        `Ausente`, e a IES era cobrada por um histórico de um semestre que a OVG não custeou.

        ESTA FUNÇÃO NÃO A DESCARTA — o corte está na origem, em `sem_repasse_liquido`, antes
        de a linha `Ausente` nascer (ver `test_estorno_nao_remove_linha.py`). Aqui ela só é
        carimbada `Inadimplente`, e é isso que o teste fixa: um descarte escrito neste ponto
        veria os documentos entregues no mesmo DataFrame e levaria os dois.

        MEDIDO NA BASE, quando o corte ainda não existia: eram 1.204 linhas assim nas cinco
        abas — 33 só no Histórico de 2025-2, todas de inscrições migradas cujo lançamento foi
        cancelado a 100%, com a cobrança real já na inscrição nova.
        """
        out = self._auditar(_linhas(
            Inscrição=[2196605],
            Status_IA=['Ausente'],
            qtd_pagtos=[1], qtd_pagtos_retroativos=[1],
            **{'total bolsa paga': [0.0]},
        ))
        self.assertEqual(len(out), 1)
        self.assertEqual(out['Status_IA'].iloc[0], 'Inadimplente')

    def test_quem_recebeu_de_verdade_continua_sendo_cobrado(self):
        """
        O contrapeso, e o mais importante: a correção não pode virar sub-cobrança. Seis
        pagamentos, nenhum cancelado — a pendência é legítima e tem de continuar `Ausente`.
        """
        out = self._auditar(_linhas(
            Inscrição=[2193227],
            Status_IA=['Ausente'],
            qtd_pagtos=[6], qtd_pagtos_retroativos=[0],
            **{'total bolsa paga': [9000.0]},
        ))
        self.assertEqual(out['Status_IA'].iloc[0], 'Ausente')

    def test_estorno_parcial_nao_isenta(self):
        """
        `qtd_pagtos_retroativos` conta só os cancelamentos de 100%. Seis pagamentos com dois
        devolvidos ainda deixam quatro meses custeados — e quatro meses custeados se auditam.
        """
        out = self._auditar(_linhas(
            Inscrição=[2200037],
            Status_IA=['Ausente'],
            qtd_pagtos=[6], qtd_pagtos_retroativos=[2],
            **{'total bolsa paga': [6000.0]},
        ))
        self.assertEqual(out['Status_IA'].iloc[0], 'Ausente')

    def test_par_de_troca_de_bolsa_cobra_uma_vez_so(self):
        """
        Parcial desligada (estornada) + integral ativa (paga), mesma pessoa e mesmo semestre.
        A cobrança tem de sobrar exatamente na inscrição que ficou com a bolsa. Antes as duas
        apareciam como pendentes, cobrando duas vezes o mesmo histórico da mesma IES.

        AS DUAS LINHAS PERMANECEM; o que as separa é o status. Só `Ausente` é pendência
        cobrável, e é o que as fórmulas do gerencial somam; a parcial estornada sai
        `Inadimplente`, que elas descartam por `"<>INADIMPLENTE"`. A cobrança continua
        acontecendo uma vez só — a diferença é que agora dá para VER a que foi descartada,
        em vez de ela simplesmente não existir.
        """
        out = self._auditar(_linhas(
            Inscrição=[2101284, 2193227],
            Status_IA=['Ausente', 'Ausente'],
            qtd_pagtos=[1, 1], qtd_pagtos_retroativos=[1, 0],
            **{'CPF': ['4523858306', '4523858306'],
               'Gemini CPF': ['4523858306', '4523858306'],
               'total bolsa paga': [0.0, 9000.0]},
        ))
        self.assertEqual(sorted(out['Inscrição'].tolist()), [2101284, 2193227])
        por_inscricao = dict(zip(out['Inscrição'], out['Status_IA']))
        self.assertEqual(por_inscricao[2193227], 'Ausente')
        self.assertEqual(por_inscricao[2101284], 'Inadimplente')

    def test_inadimplente_que_entregou_continua_visivel(self):
        """
        A METADE QUE NÃO PODE SUMIR, e a diferença inteira entre esta regra e o filtro
        removido em 14324a7: aquele derrubava a linha só por olhar o pagamento, e levava junto
        223 históricos ENVIADOS em 2025-2.

        Quem devolveu a bolsa mas entregou o documento continua no relatório de propósito — é
        o caso que o time usa para parar de mandar esses documentos para a IA, já que não
        havia obrigação de entregá-los.
        """
        out = self._auditar(_linhas(
            Inscrição=[2140283],
            Status_IA=['Válido'],
            qtd_pagtos=[6], qtd_pagtos_retroativos=[6],
            **{'total bolsa paga': [0.0]},
        ))
        self.assertEqual(len(out), 1)
        self.assertEqual(out['Inscrição'].iloc[0], 2140283)
        self.assertEqual(out['Status_IA'].iloc[0], 'Inadimplente')

    def test_veredito_do_documento_sobrevive_a_sobreposicao(self):
        """
        `Inadimplente` SOBREPÕE o veredito da IA, e até 31/08/2026 o veredito era destruído
        nessa sobreposição — não sobrava coluna nenhuma dizendo se o arquivo tinha sido lido.

        O DASHBOARD PRECISA DESSA RESPOSTA para separar "Inadimplentes Proc." de
        "Inadimplentes Não Proc.". Sem ela, ele adivinhava por `Processado`, que é o carimbo
        da FILA (espelho do SIBU + agendamento) e não o resultado da leitura: no Parquet de
        31/08/2026 havia 20.736 linhas com `Processado = SIM` cujo próprio `Status_IA` era
        `Não Processado`.

        As duas linhas abaixo são o par que a tela não conseguia distinguir: as duas saem
        `Inadimplente`, as duas dizem `Processado = SIM`, e só o veredito separa a que a IA
        leu da que nunca passou pela IA.
        """
        out = self._auditar(_linhas(
            Inscrição=[2140283, 2185963],
            Status_IA=['Válido', ''],
            Processado=['SIM', 'SIM'],
            qtd_pagtos=[6, 0], qtd_pagtos_retroativos=[6, 0],
            **{'total bolsa paga': [0.0, 0.0]},
        ))
        self.assertEqual(list(out['Status_IA']), ['Inadimplente', 'Inadimplente'])

        veredito = dict(zip(out['Inscrição'], out['Veredito Documento']))
        self.assertEqual(veredito[2140283], 'Válido')
        self.assertEqual(veredito[2185963], 'Não Processado')

    def test_veredito_e_escrito_para_toda_linha_e_nao_so_para_o_inadimplente(self):
        """
        A coluna é o veredito da IA, não um anexo do inadimplente: o dashboard trata linha
        sem veredito como Parquet defasado e cai no desempate antigo, então uma coluna
        preenchida pela metade reintroduziria o bug exatamente onde ele já esteve.
        """
        out = self._auditar(_linhas(
            Inscrição=[2193227, 2200037],
            Status_IA=['Ausente', 'Válido'],
            Processado=['NÃO', 'SIM'],
            qtd_pagtos=[6, 6], qtd_pagtos_retroativos=[0, 0],
            **{'total bolsa paga': [9000.0, 9000.0]},
        ))
        self.assertEqual(list(out['Veredito Documento']), ['Ausente', 'Válido'])
        self.assertFalse(out['Veredito Documento'].isna().any())
