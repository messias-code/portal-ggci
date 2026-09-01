"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_documento_entregue_nao_volta_a_ausente.py ===
Propósito: Trava as duas falhas que faziam o histórico recém-entregue continuar "Ausente"
no dashboard por mais atualizações que fossem disparadas — inclusive a bruta.
Autor: N/A
Dependências Principais: pandas, django.test

O CASO REAL (27/08/2026): 48 bolsistas de SULDAMERICA e FICEPE entregaram o histórico de
2025-2 em 26/08. A extração funcionou — as 48 linhas estavam no `.xlsx` baixado e no
`consolidado_processados_historico.parquet`. Mesmo assim a aba Histórico continuou
mostrando `Ausente`, com `Processado = Sim`, uma combinação que o motor não sabe produzir
a partir dos dados. Duas falhas encadeadas explicavam isso:

1. CONSOLIDADOR — o `elif` que renomeia `Status Gemini` -> `Status_IA` cobria `proc_geral`
   e `proc_riaf`, mas não `proc_historico`. O consolidado do histórico saía SEM a coluna
   de status, e as 21 mil linhas trazidas do ScriptCase entravam no motor mudas. Na
   prática o histórico dependia só do espelho D-1 do banco, que é justamente a espera que
   a extração existe para encurtar.

2. CACHE DO GEMINI — `Ausente` era gravado no cache local como se fosse resultado da IA.
   Não é: é o carimbo que o próprio motor põe em quem está na lista de pendentes e não
   entregou. Como a linha do documento chegava sem status (falha 1), ela caía no
   `mask_vazio`, o cache batia na chave e restaurava `Ausente` por cima — junto com
   `Processado = SIM`. A ausência virava permanente.

O QUE ESTE TESTE GARANTE: o status do histórico sobrevive à consolidação, `Ausente` nunca
entra no cache, e um cache herdado com `Ausente` não sobrescreve o documento entregue.
"""
import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboards.dash_documentos_ia.services import consolidador, ggci


def _linhas(**col):
    """DataFrame com o mínimo que `calcular_auditoria_ia` exige para rodar."""
    n = len(col['Inscrição'])
    base = {
        'Semestre': ['2025-2'] * n,
        'Documento Tipo': [ggci.DOC_HISTORICO] * n,
        'CPF': [str(i) for i in range(n)],
        # A IA leu CPF e semestre e eles conferem com o cadastro: sem isso o motor trata a
        # leitura como retorno vazio e o veredito vira `Não Processado` por outro caminho.
        'Gemini CPF': [str(i) for i in range(n)],
        'Gemini Semestre': ['2025/2'] * n,
        'Faculdade': ['IES EXEMPLO'] * n,
        'Curso': ['ENFERMAGEM'] * n,
        'tipo_bolsa_final': ['INTEGRAL'] * n,
        'Gemini Mensalidade C/ Desconto': [0.0] * n,
        'Gemini Mensalidade S/ Desconto': [0.0] * n,
        'Mensalidade C/ Desconto': [0.0] * n,
        'Mensalidade S/ Desconto': [0.0] * n,
        # Bolsa efetivamente repassada: sem isso a linha vira `Inadimplente` pela regra do
        # estorno e o teste mediria outra coisa.
        'qtd_pagtos': [6] * n,
        'qtd_pagtos_retroativos': [0] * n,
        'total bolsa paga': [9000.0] * n,
    }
    base.update(col)
    return pd.DataFrame(base)


def _cache_com(status, inscricao='2076868'):
    """Uma linha de cache na chave Inscrição_Semestre_Documento, rodada hoje."""
    agora = pd.Timestamp.now()
    return pd.DataFrame({
        'Inscrição': [inscricao],
        'Semestre': ['2025-2'],
        'Documento Tipo': [ggci.DOC_HISTORICO],
        'Status_IA': [status],
        'Data_Processamento_Cache': [agora],
        'IA_Run_Date': [agora],
    })


class CacheNaoMemorizaAusenteTests(SimpleTestCase):

    def _auditar(self, df, cache_inicial=None):
        """
        Roda a auditoria com o cache Gemini apontado para um arquivo descartável, opcionalmente
        semeado — a função lê e grava o cache local, e um teste não pode encostar no cache real.
        Devolve (resultado, cache em disco depois da execução).
        """
        with tempfile.TemporaryDirectory() as tmp:
            alvo = os.path.join(tmp, 'cache_teste.parquet')
            if cache_inicial is not None:
                cache_inicial.to_parquet(alvo, engine='pyarrow', index=False)
            with patch.object(ggci, 'caminho_cache_gemini', lambda: alvo):
                resultado = ggci.calcular_auditoria_ia(df)
            depois = pd.read_parquet(alvo) if os.path.exists(alvo) else pd.DataFrame()
        return resultado, depois

    def test_ausente_nao_entra_no_cache(self):
        """
        `Ausente` diz que o documento não chegou. Guardar isso é guardar a NEGATIVA de um
        fato que muda sozinho no dia seguinte — o único status que o cache não pode reter.
        """
        df = _linhas(
            Inscrição=[2076868, 2102102],
            Status_IA=['Ausente', 'Válido'],
        )
        _, cache = self._auditar(df)

        self.assertNotIn('Ausente', set(cache['Status_IA']),
                         'o cache voltou a memorizar Ausente')
        self.assertIn('Válido', set(cache['Status_IA']),
                      'o cache parou de guardar o resultado legítimo da IA')

    def test_documento_entregue_vence_o_ausente_herdado_do_cache(self):
        """
        O caso das 48: cache de ontem diz Ausente, o documento chegou hoje e ainda não foi
        processado pela IA. O certo é `Não Processado` — enviado, aguardando a fila —, não
        `Ausente`, que manda cobrar de novo quem já entregou.
        """
        df = _linhas(Inscrição=[2076868], Status_IA=[''])
        resultado, _ = self._auditar(df, cache_inicial=_cache_com('Ausente'))

        self.assertEqual(resultado['Status_IA'].iloc[0], 'Não Processado')

    def test_resultado_real_da_ia_continua_sendo_restaurado(self):
        """
        A contraprova: o cache existe para vencer a latência do D-1. Um `Válido` guardado
        ainda tem de sobrepor a linha sem status, senão a correção teria matado a função.
        """
        df = _linhas(Inscrição=[2076868], Status_IA=[''], Processado=['SIM'])
        resultado, _ = self._auditar(df, cache_inicial=_cache_com('Válido'))

        self.assertEqual(resultado['Status_IA'].iloc[0], 'Válido')

    def test_expurga_ausentes_ja_gravados_por_versoes_antigas(self):
        """
        O cache de produção chegou com 85 mil linhas `Ausente` acumuladas. Elas precisam
        sair sozinhas na primeira execução — sem apagar o arquivo, que guarda os
        Válido/Inválido legítimos.
        """
        herdado = pd.concat([_cache_com('Ausente', '2076868'),
                             _cache_com('Válido', '2102102')], ignore_index=True)
        df = _linhas(Inscrição=[2211365], Status_IA=['Válido'])
        _, cache = self._auditar(df, cache_inicial=herdado)

        self.assertNotIn('Ausente', set(cache['Status_IA']))
        self.assertIn('2102102', set(cache['Inscrição'].astype(str)))


class ConsolidadoDoHistoricoTemStatusTests(SimpleTestCase):

    COLUNAS_SCRIPTCASE = ['Status OVG', 'Status Gemini', 'Gemini Inconsistencias', 'Inscrição',
                          'Bolsista', 'CPF', 'Faculdade', 'Curso', 'Coleta ID', 'Documento Tipo',
                          'Semestre', 'Status Obs', 'Data Processamento']

    def _consolidar_historico(self, linhas):
        """
        Escreve um `.xlsx` no formato exato que o ScriptCase devolve para HISTORICO e roda
        o consolidador sobre ele. `get_configs` monta caminhos relativos, então o cwd vira
        o diretório temporário e nada é escrito dentro do repositório.
        """
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            pasta = os.path.join(tmp, 'apps/dashboards/dash_documentos_ia/dados/processamento',
                                 'proc_1/analise_documentos_processados/HISTORICO/2025')
            os.makedirs(pasta)
            pd.DataFrame(linhas).to_excel(os.path.join(pasta, 'historico_2025-2.xlsx'), index=False)
            try:
                os.chdir(tmp)
                consolidador.consolidar(processo_id=1)
                saida = os.path.join(
                    tmp, 'apps/dashboards/dash_documentos_ia/dados/processamento/proc_1',
                    'analise_documentos_processados/CONSOLIDADO',
                    'consolidado_processados_historico.parquet')
                return pd.read_parquet(saida)
            finally:
                os.chdir(cwd)

    def test_status_gemini_do_historico_vira_status_ia(self):
        """Sem este rename o histórico extraído chega mudo ao motor e o cache decide por ele."""
        linhas = {c: [''] for c in self.COLUNAS_SCRIPTCASE}
        linhas.update({
            'Status OVG': ['Inválido'],
            'Status Gemini': ['Válido'],
            'Inscrição': [2076868],
            'Documento Tipo': ['HISTÓRICO ESCOLAR'],
            'Semestre': ['2025-2'],
        })
        df = self._consolidar_historico(linhas)

        self.assertIn('Status_IA', df.columns)
        self.assertEqual(df['Status_IA'].iloc[0], 'Válido')
        for morta in ('Status Gemini', 'Status OVG', 'Status Obs'):
            self.assertNotIn(morta, df.columns)
