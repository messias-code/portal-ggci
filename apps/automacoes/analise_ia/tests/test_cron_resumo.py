"""
=== ARQUIVO: apps/automacoes/analise_ia/tests/test_cron_resumo.py ===
Propósito: Trava o resumo que o comando `cron_analise_ia` imprime no log do cron.
Autor: N/A
Dependências Principais: unittest, django (apenas settings)

POR QUÊ EXISTE: O cron do Análise IA passou meses falhando em silêncio porque
ninguém lia o log — ele vinha com o banner e o menu inteiro do portal.sh, e o
erro real ("ValueError: O processo_id é obrigatório.") ficava perdido no meio da
tela despejada. O comando novo troca isso por uma linha por etapa, e essas linhas
só valem alguma coisa enquanto casarem com o texto que o motor de fato imprime.

O QUE ESTE TESTE GARANTE: se alguém mudar o texto de "🎉 Extração concluída",
"🎉 Consolidação concluída" ou "🎉 Regras aplicadas" nos serviços, o resumo para
de reconhecer a etapa — e este teste quebra antes que o cron volte a ficar mudo.

NÃO TOCA banco, rede nem o site do SIBU: alimenta o parser com linhas de log.
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.automacoes.analise_ia.management.commands import cron_analise_ia as mod


def rodar_parser(linhas):
    """Alimenta o parser com um log e devolve as linhas de resumo emitidas."""
    comando = mod.Command()
    emitidas = []
    comando._linha = lambda rotulo, texto: emitidas.append((rotulo, texto))

    estado = {
        "etapa": "EXTRACAO",
        "inicio_etapa": 0.0,
        "cache": 0,
        "downloads": 0,
        "avisos": 0,
        "planilhas": 0,
        "arquivos_extraidos": None,
        "erro": None,
        "capturando_traceback": False,
    }
    for linha in linhas:
        comando._interpretar(linha, estado)
    return emitidas, estado


class TestDuracao(unittest.TestCase):
    def test_abaixo_de_um_minuto_sai_em_segundos(self):
        self.assertEqual(mod._duracao(42), "42s")

    def test_minutos_com_segundos_zero_a_esquerda(self):
        self.assertEqual(mod._duracao(7 * 60 + 3), "7m03s")

    def test_acima_de_uma_hora_troca_para_horas(self):
        self.assertEqual(mod._duracao(3 * 3600 + 5 * 60), "3h05m")


class TestParserDeEtapas(unittest.TestCase):
    """As mensagens abaixo são cópias literais dos prints dos serviços."""

    def test_ciclo_completo_emite_uma_linha_por_etapa(self):
        log = [
            "[18/08/2026 00:06:40] 🚀 Iniciando processamento massivo...\n",
            "[18/08/2026 00:06:41] [EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_espelho_riaf_d1_2026_dev.parquet\n",
            "[18/08/2026 00:06:42] [EXTRATOR   | INFO          | DISCO LOCAL] Parquet salvo: PY_ggci_pendentes_riaf_geral_dev.parquet\n",
            "[18/08/2026 00:20:10] [EXTRATOR   | CONTRATOS     | 2025-1] ✅ Download concluído com sucesso (Pronto para sobrescrever).\n",
            "[18/08/2026 00:21:11] [EXTRATOR   | HISTORICO     | 2026-2] ⚠️ Sem registros (Vazio).\n",
            "[18/08/2026 00:31:04] 🎉 Extração concluída: 412 Arquivos baixados e estruturados em 24m e 24s.\n",
            "[18/08/2026 00:32:00] [CONSOLIDAR | PLANILHA      | CONTRATO] contratos.xlsx salvo em 3.20s\n",
            "[18/08/2026 00:33:42] 🎉 Consolidação concluída: Planilhas consolidadas e limpas em 2m e 38s.\n",
            "[18/08/2026 00:52:11] 🎉 Regras aplicadas: Relatório gerado em 18m e 29s.\n",
        ]
        emitidas, estado = rodar_parser(log)
        rotulos = [rotulo for rotulo, _ in emitidas]

        self.assertEqual(rotulos, ["EXTRACAO", "CONSOLIDA", "GGCI"])
        self.assertIn("2 tabelas em cache", emitidas[0][1])
        self.assertIn("412 arquivos", emitidas[0][1])
        self.assertIn("1 aviso", emitidas[0][1])
        self.assertIn("1 planilha", emitidas[1][1])
        self.assertEqual(estado["etapa"], "FINALIZACAO")
        self.assertIsNone(estado["erro"])

    def test_extracao_vazia_tambem_fecha_a_etapa(self):
        log = ["[18/08/2026 00:07:02] ⚠️ EXTRAÇÃO VAZIA: Nenhum arquivo corresponde aos filtros (Bloqueio por Regras).\n"]
        emitidas, estado = rodar_parser(log)

        self.assertEqual(emitidas[0][0], "EXTRACAO")
        self.assertIn("0 arquivos", emitidas[0][1])
        self.assertEqual(estado["etapa"], "CONSOLIDACAO")

    def test_falha_critica_guarda_a_excecao_e_nao_o_traceback(self):
        """
        A exceção é a ÚLTIMA linha não indentada do traceback. O carimbo de
        timestamp que o LogCapture põe na frente precisa ser descartado antes,
        senão toda linha parece não indentada e o parser guarda o "File ..." .
        """
        log = [
            "[18/08/2026 00:12:00] ❌ FALHA CRÍTICA:\n",
            "[18/08/2026 00:12:00] Traceback (most recent call last):\n",
            '[18/08/2026 00:12:00]   File "/home/labs/portal-ggci-dev/apps/automacoes/analise_ia/services/extrator.py", line 760, in executar\n',
            "[18/08/2026 00:12:00]     raise ValueError(\"O processo_id é obrigatório.\")\n",
            "[18/08/2026 00:12:00] ValueError: O processo_id é obrigatório.\n",
        ]
        _, estado = rodar_parser(log)
        self.assertEqual(estado["erro"], "ValueError: O processo_id é obrigatório.")

    def test_aviso_de_relatorio_bloqueado_aparece_no_resumo(self):
        log = ["[18/08/2026 00:06:41] ! AVISO │ RELATÓRIO │ BLOQUEADO │ A aba 'Relatório Riaf' exige: Riaf, Financiamentos, Benefícios, Envios & Pendências e Pagamentos.\n"]
        emitidas, _ = rodar_parser(log)

        self.assertEqual(emitidas[0][0], "AVISO")
        self.assertTrue(emitidas[0][1].startswith("A aba 'Relatório Riaf' exige"))

    def test_aborto_limpo_do_motor_vira_motivo_da_falha(self):
        log = ["[18/08/2026 00:06:41] 🛑 Processo abortado: Nenhuma Base de Extração (Documentos) selecionada.\n"]
        _, estado = rodar_parser(log)

        self.assertEqual(estado["erro"], "Processo abortado: Nenhuma Base de Extração (Documentos) selecionada.")


class TestPayloadDoPipelineCompleto(unittest.TestCase):
    """
    Este payload vale só para o modo --completo (opção 7 do menu) — o cron diário
    não gera relatório. Ainda assim precisa satisfazer as validações do
    executar_motor_ia, senão os dois relatórios gerenciais são silenciosamente
    desligados e quem pediu o robô na mão recebe uma planilha incompleta.
    """

    def test_cobre_os_documentos_exigidos_pelos_relatorios(self):
        docs = mod.PAYLOAD_PIPELINE_COMPLETO["documentos"]
        for exigido in ("CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF"):
            self.assertIn(exigido, docs)

    def test_tem_mais_de_um_periodo_entre_os_documentos_validados(self):
        periodos = set()
        for doc in ("CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF"):
            periodos.update(mod.PAYLOAD_PIPELINE_COMPLETO["periodos_por_doc"][doc])
        self.assertGreater(len(periodos), 1)

    def test_flags_de_relatorio_ligadas_com_semestres_definidos(self):
        payload = mod.PAYLOAD_PIPELINE_COMPLETO
        self.assertTrue(payload["gerar_quantitativo"])
        self.assertTrue(payload["gerar_pagamentos"])
        self.assertTrue(payload["sems_contratos"])
        self.assertTrue(payload["sems_riaf"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
