"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_estorno_nao_remove_linha.py ===
Propósito: Garantir que o beneficiário que devolveu toda a bolsa continue no relatório.
Autor: N/A
Dependências Principais: pandas, django.test

POR QUÊ EXISTE: `calcular_auditoria_ia` tinha um descarte silencioso — quando
`qtd_pagtos == qtd_pagtos_retroativos` a linha era eliminada da planilha inteira.

A leitura do dado estava certa: `qtd_pagtos_retroativos` conta os pagamentos CANCELADOS A
100% (bolsa devolvida); cancelamento parcial não entra na conta. A igualdade significa
mesmo "todo o repasse do semestre voltou". O erro era a AÇÃO — devolver a bolsa não apaga
o fato de a IES ter, ou não ter, entregado o documento.

E o estrago era duplo: a função roda DEPOIS que enviados e Ausentes já estão no mesmo
DataFrame, então o filtro derrubava a linha das duas categorias ao mesmo tempo. O
beneficiário sumia do relatório e ninguém notava que o documento dele nunca foi conferido.
Em 2025-2 isso escondia 223 históricos enviados e 33 pendências.

Estes testes travam a ausência do filtro nos dois lados — enviado e Ausente — porque
reintroduzi-lo esconderia os mesmos casos de novo, e sem deixar rastro no relatório.
"""
import tempfile
import os
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.automacoes.analise_ia.services import ggci


def _linhas(**col):
    """DataFrame com o mínimo que `calcular_auditoria_ia` exige para rodar."""
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [ggci.DOC_HISTORICO] * n,
        'CPF': [str(i) for i in range(n)],
        'Faculdade': ['IES EXEMPLO'] * n,
        'Curso': ['DIREITO'] * n,
        'tipo_bolsa_final': ['INTEGRAL'] * n,
        'Gemini Mensalidade C/ Desconto': [0.0] * n,
        'Gemini Mensalidade S/ Desconto': [0.0] * n,
        'Mensalidade C/ Desconto': [0.0] * n,
        'Mensalidade S/ Desconto': [0.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


class EstornoCompletoNaoRemoveLinhaTests(SimpleTestCase):

    def _auditar(self, df):
        """
        Roda a auditoria com o cache Gemini apontado para um arquivo descartável — a função
        lê e grava o cache local, e um teste não pode encostar no cache real do app.
        """
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                return ggci.calcular_auditoria_ia(df)

    def test_enviado_com_bolsa_toda_devolvida_continua_na_planilha(self):
        """6 pagamentos, 6 cancelados a 100%. O documento foi entregue e tem de aparecer."""
        df = _linhas(
            Inscrição=[2140283, 2195094],
            Status_IA=['Válido', 'Válido'],
            qtd_pagtos=[6, 6],
            qtd_pagtos_retroativos=[6, 0],
        )
        out = self._auditar(df)
        self.assertEqual(sorted(out['Inscrição'].tolist()), [2140283, 2195094])

    def test_ausente_com_bolsa_toda_devolvida_nao_e_apagado_aqui(self):
        """
        O CORTE MUDOU DE LUGAR, e é sobre isso que este teste passou a ser.

        A pendência de quem não teve repasse líquido não deve mesmo ser cobrada — isso não
        mudou nas três revisões desta regra. O que mudou é ONDE ela é barrada: agora em
        `sem_repasse_liquido`, na geração dos ausentes, ANTES de a linha existir. Aqui, em
        `calcular_auditoria_ia`, não pode haver descarte nenhum: neste ponto os documentos
        ENTREGUES e os AUSENTES já dividem o mesmo DataFrame, e foi exatamente uma máscara
        escrita aqui que apagou 223 históricos entregues em 2025-2.

        Então a linha passa reta e sai carimbada `Inadimplente` — que é o que o motor faz
        com quem não teve repasse. Na prática ela não chega até aqui, porque o filtro da
        origem já a barrou; o teste garante que, se chegar, ninguém a apague neste ponto.
        """
        df = _linhas(
            Inscrição=[2213322],
            Status_IA=['Ausente'],
            qtd_pagtos=[2],
            qtd_pagtos_retroativos=[2],
        )
        out = self._auditar(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out['Status_IA'].iloc[0], 'Inadimplente')

    def test_cancelamento_parcial_nunca_foi_alvo_do_filtro(self):
        """
        Cancelamento de 40%/60% não entra em `qtd_pagtos_retroativos` — só os de 100%. Uma
        linha com retroativos menores que os pagamentos jamais casaria com a máscara antiga;
        o teste fixa isso para que ninguém "conserte" a contagem somando parciais.
        """
        df = _linhas(
            Inscrição=[2184451],
            Status_IA=['Válido'],
            qtd_pagtos=[6],
            qtd_pagtos_retroativos=[3],
        )
        out = self._auditar(df)
        self.assertEqual(len(out), 1)

    def test_colunas_de_pagamento_seguem_no_relatorio_para_quem_quiser_filtrar(self):
        """
        Nenhuma coluna nova foi criada para sinalizar o estorno, porque não é preciso:
        `qtd_pagtos` e `qtd_pagtos_retroativos` já saem lado a lado e permitem identificar
        o caso na planilha. Se elas sumirem da saída, o caso volta a ficar invisível.
        """
        df = _linhas(
            Inscrição=[2140283],
            Status_IA=['Válido'],
            qtd_pagtos=[6],
            qtd_pagtos_retroativos=[6],
        )
        out = self._auditar(df)
        self.assertIn('qtd_pagtos', out.columns)
        self.assertIn('qtd_pagtos_retroativos', out.columns)
        self.assertEqual(out['qtd_pagtos'].iloc[0], 6)
        self.assertEqual(out['qtd_pagtos_retroativos'].iloc[0], 6)
