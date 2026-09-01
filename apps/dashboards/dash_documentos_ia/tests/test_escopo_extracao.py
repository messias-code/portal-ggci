"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_escopo_extracao.py ===
Propósito: Trava o escopo fixo do ciclo e o contrato do comando de background.
Autor: N/A
Dependências Principais: unittest, inspect

POR QUÊ EXISTE: o Documentos IA não tem tela de filtros — o dashboard compara documentos
e períodos entre si, então o ciclo precisa trazer o universo inteiro, sempre. Esse escopo
vive em duas constantes do `executar_doc_ia`, e um recorte acidental nelas não quebraria
nada: a extração rodaria mais rápido e o dashboard simplesmente mostraria menos, sem
qualquer erro. É o tipo de regressão que só aparece semanas depois, quando alguém nota
que um semestre sumiu do gráfico.

O QUE ESTE TESTE GARANTE: os 5 documentos e os 4 períodos continuam lá, o comando recebe
o processo_id por argumento, e as abas com fórmula do Excel seguem desligadas.
"""
import inspect
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.dashboards.dash_documentos_ia.management.commands import executar_doc_ia as mod
from apps.dashboards.dash_documentos_ia.services import extrator


class TestEscopoDoCiclo(unittest.TestCase):
    def test_traz_os_cinco_documentos(self):
        self.assertEqual(
            set(mod.DOCUMENTOS),
            {"CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF", "HISTORICO"},
        )

    def test_traz_os_quatro_periodos(self):
        self.assertEqual(mod.PERIODOS, ["2025-1", "2025-2", "2026-1", "2026-2"])

    def test_documentos_existem_no_extrator(self):
        """Um documento escrito errado seria ignorado em silêncio pelo planejador."""
        conhecidos = {d["categoria"] for d in extrator.CONFIG_DOCUMENTOS}
        desconhecidos = set(mod.DOCUMENTOS) - conhecidos
        self.assertEqual(desconhecidos, set(), f"documentos que o extrator não conhece: {desconhecidos}")

    def test_cobre_todos_os_documentos_que_o_extrator_sabe_baixar(self):
        conhecidos = {d["categoria"] for d in extrator.CONFIG_DOCUMENTOS}
        self.assertEqual(set(mod.DOCUMENTOS), conhecidos)


class TestChamadaDoMotor(unittest.TestCase):
    """Lê o código do handle — executá-lo abriria navegador e conexão com o SIBU."""

    def setUp(self):
        self.fonte = inspect.getsource(mod.Command.handle)

    def test_saida_e_parquet(self):
        self.assertIn('formato="PARQUET"', self.fonte)

    def test_relatorios_com_formula_ficam_desligados(self):
        """Relatório Contratos e Relatório RIAF são fórmula de Excel; não existem fora do xlsx."""
        self.assertIn("gerar_relatorio=False", self.fonte)
        self.assertIn("gerar_relatorio_riaf=False", self.fonte)

    def test_quantitativo_e_pagamentos_ficam_ligados(self):
        self.assertIn("gerar_quantitativo=True", self.fonte)
        self.assertIn("gerar_pagamentos=True", self.fonte)

    def test_periodos_vao_explicitos_para_todo_documento(self):
        """
        Sem periodos_por_doc, extrator e ggci caem cada um no seu próprio fallback.
        Hoje os dois coincidem, mas são listas escritas em lugares diferentes — o
        ciclo não pode depender de elas continuarem iguais.

        A EXTRAÇÃO passou a aceitar recorte (`escopo_da_execucao`), mas os períodos
        continuam sendo passados explicitamente nos dois casos.
        """
        self.assertIn("periodos_por_doc=periodos_por_doc", self.fonte)
        self.assertIn("periodos_por_doc={doc: PERIODOS for doc in DOCUMENTOS}", self.fonte)

    def test_as_regras_rodam_sempre_sobre_o_universo_inteiro(self):
        """
        A extração pode ser recortada; o cálculo, não. As regras comparam documentos e
        semestres entre si — um RIAF ausente depende do contrato do mesmo aluno —, e
        rodá-las sobre o recorte gravaria Parquets parciais, apagando da tela tudo o que
        não foi extraído naquela rodada.
        """
        import re

        chamada = re.search(r"ggci\.gerar_relatorio_geral\((.*?)\)", self.fonte, re.S).group(1)
        self.assertIn("docs_selecionados=DOCUMENTOS", chamada)
        self.assertIn("periodos_por_doc={doc: PERIODOS for doc in DOCUMENTOS}", chamada)
        self.assertIn("sems_riaf=PERIODOS", chamada)
        self.assertIn("sems_contratos=PERIODOS", chamada)
        # E o recorte configurado NÃO pode vazar para cá.
        for proibido in ("documentos,", "documentos)", "periodos_por_doc=periodos_por_doc"):
            self.assertNotIn(proibido, chamada)

    def test_o_recorte_configurado_chega_ao_extrator(self):
        """
        Os quatro campos que a tela configura têm de chegar ao extrator. Faltando um, a
        tela prometeria um recorte que o back-end ignora — e o log diria que rodou.
        """
        import re

        chamada = re.search(r"extrator\.executar\((.*?)\)", self.fonte, re.S).group(1)
        for esperado in ("docs_selecionados=documentos", "periodos_por_doc=periodos_por_doc",
                         "inscricoes_forcadas=processados_hoje",
                         "atualizacao_bruta=atualizacao_bruta"):
            self.assertIn(esperado, chamada)


class TestEscopoDaExecucao(unittest.TestCase):
    """
    `escopo_da_execucao` traduz o JSON gravado no banco no que o extrator entende.
    Ele precisa ser tolerante: a configuração pode ter sido escrita por uma versão
    anterior da tela, vir vazia (cron, clique simples) ou trazer nomes que não existem.
    """

    def test_sem_configuracao_o_escopo_e_completo(self):
        for vazio in ({}, None, [], "", {"documentos": []}):
            with self.subTest(configuracao=vazio):
                docs, por_doc, forcadas, bruta = mod.escopo_da_execucao(vazio)
                self.assertEqual(docs, mod.DOCUMENTOS)
                self.assertEqual(por_doc, {d: mod.PERIODOS for d in mod.DOCUMENTOS})
                self.assertEqual(forcadas, [])
                self.assertEqual(bruta, [])

    def test_recorte_valido_e_respeitado(self):
        docs, por_doc, forcadas, bruta = mod.escopo_da_execucao({
            "documentos": ["RIAF"],
            "periodos_por_doc": {"RIAF": ["2026-1"]},
            "processados_hoje": [{"documento": "RIAF", "semestres": ["2026-1"], "lista": "1,2"}],
            "atualizacao_bruta": [{"documento": "RIAF", "semestres": ["2026-1"]}],
        })
        self.assertEqual(docs, ["RIAF"])
        self.assertEqual(por_doc, {"RIAF": ["2026-1"]})
        self.assertEqual(len(forcadas), 1)
        self.assertEqual(len(bruta), 1)

    def test_nomes_desconhecidos_sao_descartados_sem_derrubar_o_resto(self):
        docs, por_doc, forcadas, bruta = mod.escopo_da_execucao({
            "documentos": ["RIAF", "NAO-EXISTE"],
            "periodos_por_doc": {"RIAF": ["2026-1", "1999-9"]},
            "processados_hoje": [{"documento": "NAO-EXISTE", "lista": "x"}, "lixo", 42],
            "atualizacao_bruta": "nem lista é",
        })
        self.assertEqual(docs, ["RIAF"])
        self.assertEqual(por_doc, {"RIAF": ["2026-1"]})
        self.assertEqual(forcadas, [])
        self.assertEqual(bruta, [])

    def test_documento_sem_semestre_vale_por_todos(self):
        """Payload antigo pode trazer o documento sem a lista de semestres."""
        _, por_doc, _, _ = mod.escopo_da_execucao({"documentos": ["CONTRATOS"]})
        self.assertEqual(por_doc, {"CONTRATOS": mod.PERIODOS})


class TestContratoDoComando(unittest.TestCase):
    def test_recebe_o_processo_id_por_argumento(self):
        """
        A versão anterior pescava `filter(status__in=ATIVOS).first()` do banco: com dois
        registros ativos, ela escrevia log e progresso no registro errado.
        """
        from argparse import ArgumentParser
        parser = ArgumentParser()
        mod.Command().add_arguments(parser)
        self.assertEqual(parser.parse_args(["42"]).processo_id, 42)

    def test_processo_id_e_obrigatorio(self):
        import contextlib
        import io
        from argparse import ArgumentParser
        parser = ArgumentParser()
        mod.Command().add_arguments(parser)
        # O argparse escreve a mensagem de uso no stderr antes de sair; sem o
        # redirect ela apareceria no meio da saída da suíte parecendo um erro real.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_mantem_teto_de_pastas_de_processamento(self):
        """As planilhas baixadas são insumo; sem teto, cada ciclo deixa centenas de MB."""
        self.assertGreaterEqual(mod.MAX_PASTAS_PROCESSAMENTO, 1)
        self.assertLessEqual(mod.MAX_PASTAS_PROCESSAMENTO, 5)


class TestSaidaEmPastaFixa(unittest.TestCase):
    def test_grava_uma_pasta_por_execucao(self):
        """
        O motor grava as abas em `processamento/proc_<id>/relatorio_geral/`, uma pasta
        por execução — não mais numa pasta fixa sobrescrita.

        ISTO AQUI JÁ CUSTOU CARO: quando o destino mudou, a tela continuou lendo a
        pasta fixa antiga e ficou parada na última execução que a usou. Em 21/08/2026
        ela mostrava dados de 18/08 com uma execução de 20/08 pronta no disco, sem
        erro em lugar nenhum. Por isso o teste abaixo, que amarra as duas pontas.
        """
        from apps.dashboards.dash_documentos_ia.services import ggci
        fonte = inspect.getsource(ggci.gerar_relatorio_geral)
        self.assertIn('os.path.join(base_dir, "relatorio_geral")', fonte)

    def test_a_tela_le_da_pasta_onde_o_motor_grava(self):
        """A ponta que faltava: de nada adianta gravar certo se a tela lê noutro lugar."""
        from apps.dashboards.dash_documentos_ia import views
        self.assertTrue(views.pasta_parquet_atual().endswith("relatorio_geral")
                        or views.pasta_parquet_atual() == views.PASTA_PARQUET)

    def test_gravacao_e_atomica(self):
        """Sem o .tmp + os.replace, abrir a tela durante a atualização lê um arquivo pela metade."""
        from apps.dashboards.dash_documentos_ia.services import ggci
        fonte = inspect.getsource(ggci.gerar_relatorio_geral)
        self.assertIn("os.replace(temporario, destino)", fonte)

    def test_remove_abas_ausentes_na_execucao(self):
        """Sem isso, um documento que deixasse de vir ficaria no dashboard para sempre."""
        from apps.dashboards.dash_documentos_ia.services import ggci
        fonte = inspect.getsource(ggci.gerar_relatorio_geral)
        self.assertIn("ausente nesta execução", fonte)


if __name__ == "__main__":
    unittest.main()


class TestBarraDeProgresso(unittest.TestCase):
    """
    A barra ficava presa perto do fim durante quase todo o ciclo. Duas causas, e as
    duas medidas: a escala dava 15% à extração, que é 90% do tempo real; e o ramo das
    esperas silenciosas usava teto fixo de 98, ignorando a etapa em curso.
    """

    def test_a_escala_e_monotonica(self):
        """Marco que desce faria a barra ANDAR PARA TRÁS — pior que ficar parada."""
        anterior = 0
        for trigger, alvo in mod.PROGRESS_MAP_ABSOLUTE:
            with self.subTest(marco=trigger.strip()):
                self.assertGreaterEqual(alvo, anterior)
                anterior = alvo
        self.assertEqual(anterior, 99, "o último marco antes do fim tem de ser 99")

    def test_a_extracao_ocupa_a_maior_parte_da_barra(self):
        """
        Medido em seis execuções: a extração leva de 53% a 89% do tempo, e o bloco das
        regras é quase constante (~40s). A barra tem de refletir isso.
        """
        inicio, fim = mod.FAIXA_EXTRACAO
        self.assertGreaterEqual(fim - inicio, 60,
                                "a etapa mais longa não pode ocupar uma fatia estreita da barra")
        self.assertEqual(fim, mod.PROGRESS_MAP_ABSOLUTE[0][1],
                         "o fim da faixa tem de encostar no marco 'Extração concluída'")

    def test_progresso_da_extracao_vem_da_contagem_de_arquivos(self):
        inicio, fim = mod.FAIXA_EXTRACAO
        self.assertEqual(mod._progresso_da_extracao("[EXTRACAO_PROGRESSO] 0/20"), inicio)
        self.assertEqual(mod._progresso_da_extracao("[EXTRACAO_PROGRESSO] 20/20"), fim)

        meio = mod._progresso_da_extracao("[EXTRACAO_PROGRESSO] 10/20")
        self.assertTrue(inicio < meio < fim, meio)

        # Vale o ÚLTIMO marcador do bloco: as tarefas terminam fora de ordem e o buffer
        # pode trazer vários de uma vez.
        self.assertEqual(
            mod._progresso_da_extracao("[EXTRACAO_PROGRESSO] 3/20\n[EXTRACAO_PROGRESSO] 7/20"),
            mod._progresso_da_extracao("[EXTRACAO_PROGRESSO] 7/20"))

    def test_progresso_da_extracao_ignora_lixo(self):
        """Sem marcador, quem manda são os marcos — e não uma divisão por zero."""
        for texto in ("", "sem marcador", "[EXTRACAO_PROGRESSO] 5/0", "[EXTRACAO_PROGRESSO] x/y"):
            with self.subTest(texto=texto):
                self.assertIsNone(mod._progresso_da_extracao(texto))

    def test_o_teto_nunca_deixa_a_barra_cruzar_a_etapa_sozinha(self):
        """
        Entre dois marcos a barra anda para dar sinal de vida, mas não pode ultrapassar
        o degrau seguinte: era isso que a fazia chegar a 98 no meio da extração e ficar
        lá pelo resto do ciclo.
        """
        inicio, fim = mod.FAIXA_EXTRACAO
        # No meio da extração, o teto é o fim dela — e não o fim da barra.
        self.assertEqual(mod._teto_da_etapa(inicio + 1), fim - 1)
        self.assertEqual(mod._teto_da_etapa(fim - 1), fim - 1)
        # E o teto nunca é menor que o ponto atual, o que faria a barra recuar.
        for ponto in range(0, 100):
            with self.subTest(ponto=ponto):
                self.assertGreaterEqual(mod._teto_da_etapa(ponto), min(ponto, 99))

    def test_o_extrator_emite_a_contagem_que_a_barra_le(self):
        """Os dois lados do contrato, para não se perderem um do outro."""
        import inspect

        from apps.dashboards.dash_documentos_ia.services import extrator

        fonte = inspect.getsource(extrator.executar)
        self.assertIn("[EXTRACAO_PROGRESSO]", fonte)
        self.assertIn("as_completed", fonte)
