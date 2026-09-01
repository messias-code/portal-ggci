"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_sufixo_tabelas.py ===
Propósito: Impede que dash_documentos_ia e analise_ia voltem a disputar os mesmos
           nomes de tabela no SIBU.
Autor: N/A
Dependências Principais: unittest, inspect, re

POR QUÊ EXISTE: `atualizar_cache_parquets` roda, para cada tabela, o ciclo
`DROP → CREATE → SELECT → DROP`. Até 18/08/2026 os dois apps geravam exatamente os
mesmos 16 nomes (`PY_ggci_*_dev`), então rodar os dois juntos fazia o DROP de um cair
em cima do SELECT do outro — a tabela sumia no meio da leitura e o erro saía como um
aviso solto no log, sem nada indicando a causa.

O file lock NÃO protege disso: ele vive em `dados/tabelas_sql/.lock_<tabela>`, dentro
da pasta de cada app, então são dois locks distintos guardando um mesmo recurso remoto.
A única defesa é o nome ser diferente.

O QUE ESTE TESTE GARANTE: a interseção entre os nomes dos dois apps é vazia, e o nome
que o código monta é exatamente o que o arquivo .sql cria. Um `.sql` copiado do vizinho
sem re-sufixar quebra aqui, e não em produção.
"""
import inspect
import os
import re
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.automacoes.analise_ia.services import extrator as extrator_analise
from apps.dashboards.dash_documentos_ia.services import extrator as extrator_docs
from apps.dashboards.dash_documentos_ia.services import ggci as ggci_docs

PADRAO_MAPA = re.compile(r'\("(PY_ggci_[a-z0-9_]+)", os\.path\.join\(PROJECT_ROOT, "(apps/[^"]+\.sql)"\)')
PADRAO_CREATE = re.compile(r"CREATE (?:TABLE|OR REPLACE VIEW) sibu\.(\S+)")


def mapa_de(modulo):
    """(nome_tabela, caminho_sql) do mapa, lido do código-fonte — não abre conexão."""
    fonte = inspect.getsource(modulo.atualizar_cache_parquets)
    pares = PADRAO_MAPA.findall(fonte)
    assert pares, f"mapa_tabelas não encontrado em {modulo.__name__}"
    return pares


class TestSufixoDoApp(unittest.TestCase):
    def test_sufixo_e_o_deste_app(self):
        self.assertEqual(extrator_docs.SUFIXO_APP, "_documentos_ia")
        self.assertEqual(ggci_docs.SUFIXO_APP, "_documentos_ia")

    def test_extrator_e_ggci_concordam(self):
        """Os dois módulos montam nomes de Parquet — divergir aqui faz um não achar o do outro."""
        self.assertEqual(extrator_docs.SUFIXO_TABELAS, ggci_docs.SUFIXO_TABELAS)

    def test_sufixo_termina_com_o_ambiente(self):
        """
        A ordem importa: `atualizar_cache_parquets` deriva o nome base fazendo
        `nome_tabela.replace(env_suffix, "")`. Se o ambiente não estivesse no fim,
        o replace comeria um pedaço do meio do nome.
        """
        self.assertTrue(extrator_docs.SUFIXO_TABELAS.endswith(("_dev", "_prod")))
        self.assertTrue(extrator_docs.SUFIXO_TABELAS.startswith("_documentos_ia"))


class TestSemColisaoEntreApps(unittest.TestCase):
    def test_interseccao_de_nomes_e_vazia(self):
        nomes_docs = {nome for nome, _ in mapa_de(extrator_docs)}
        nomes_analise = {nome for nome, _ in mapa_de(extrator_analise)}
        colisao = nomes_docs & nomes_analise
        self.assertEqual(
            colisao, set(),
            "os dois apps criariam a MESMA tabela no SIBU e um dropava a do outro:\n  "
            + "\n  ".join(sorted(colisao)),
        )

    def test_os_dois_apps_declaram_a_mesma_quantidade_de_tabelas(self):
        """Se um ganhar uma tabela nova, o outro provavelmente também precisa dela."""
        self.assertEqual(len(mapa_de(extrator_docs)), len(mapa_de(extrator_analise)))

    def test_sufixos_dos_dois_apps_sao_diferentes(self):
        self.assertNotEqual(extrator_docs.SUFIXO_TABELAS, extrator_analise.SUFIXO_TABELAS)


class TestArquivoSQLCasaComONome(unittest.TestCase):
    """
    O nome que o código monta tem de ser o mesmo que o .sql cria. O código faz
    `sql_content.replace(nome_base, nome_tabela)` antes de mandar ao banco: se o
    .sql criar outro nome, o replace não encontra nada, o CREATE roda com o nome
    errado e o SELECT seguinte procura uma tabela que ninguém criou.
    """

    def _conferir(self, modulo, sufixo_app):
        env = "_dev" if extrator_docs.SUFIXO_TABELAS.endswith("_dev") else "_prod"
        for nome, rel in mapa_de(modulo):
            caminho = os.path.join(PROJECT_ROOT, rel)
            with self.subTest(tabela=nome):
                self.assertTrue(os.path.exists(caminho), f"arquivo ausente: {rel}")

                self.assertTrue(
                    nome.endswith(sufixo_app),
                    f"{nome} não termina com {sufixo_app}",
                )

                # Reproduz exatamente o que atualizar_cache_parquets faz.
                nome_tabela = f"{nome}{env}"
                nome_base = nome_tabela.replace(env, "")
                conteudo = open(caminho, encoding="utf-8").read()
                criados = PADRAO_CREATE.findall(conteudo.replace(nome_base, nome_tabela))

                self.assertEqual(
                    criados, [nome_tabela],
                    f"{rel} cria {criados}, mas o código espera ['{nome_tabela}']",
                )

    def test_documentos_ia(self):
        self._conferir(extrator_docs, "_documentos_ia")

    def test_analise_ia(self):
        self._conferir(extrator_analise, "_analise_ia")

    def test_nenhum_sql_deste_app_menciona_o_outro(self):
        pasta = os.path.join(PROJECT_ROOT, "apps", "dashboards", "dash_documentos_ia", "sql")
        for raiz, _, arquivos in os.walk(pasta):
            for nome in arquivos:
                if not nome.endswith(".sql"):
                    continue
                caminho = os.path.join(raiz, nome)
                with self.subTest(arquivo=nome):
                    self.assertNotIn("_analise_ia", open(caminho, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
