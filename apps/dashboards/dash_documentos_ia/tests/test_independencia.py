"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_independencia.py ===
Propósito: Trava a independência do dash_documentos_ia em relação ao analise_ia.
Autor: N/A
Dependências Principais: unittest, ast

POR QUÊ EXISTE: este app nasceu como cópia do analise_ia, e a cópia ficou pela metade.
Em 18/08/2026 ele ainda importava `diagnostico` do outro app (módulo que nem existia
aqui), lia os 16 arquivos .sql de dentro de `apps/automacoes/analise_ia/sql/` e gravava
o cache do Gemini na pasta do vizinho. Nada disso aparecia como erro no `manage.py
check` — só quebraria em produção, ou pior, funcionaria lendo dados do app errado.

O QUE ESTE TESTE GARANTE: nenhum módulo de serviço deste app importa do analise_ia,
e nenhum caminho de arquivo que ele monta aponta para lá. Se alguém copiar mais um
arquivo do analise_ia sem reapontar os caminhos, quebra aqui.
"""
import ast
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_ggci.settings")
import django

django.setup()

from apps.dashboards.dash_documentos_ia.services import ggci

APP_DIR = os.path.join(PROJECT_ROOT, "apps", "dashboards", "dash_documentos_ia")

def _arquivos_python():
    """
    Arquivos .py de PRODUÇÃO do app.

    `tests/` fica de fora de propósito: esta suíte importa o analise_ia para comparar
    os dois apps (é exatamente o que `test_sufixo_tabelas` faz ao provar que os nomes
    de tabela não colidem). Proibir o import aqui tornaria a comparação impossível.
    `migrations/` é gerado e `dados/` não é código.
    """
    for raiz, pastas, arquivos in os.walk(APP_DIR):
        pastas[:] = [p for p in pastas if p not in ("__pycache__", "migrations", "dados", "tests")]
        for nome in arquivos:
            if nome.endswith(".py"):
                yield os.path.join(raiz, nome)


def _docstrings(arvore):
    """
    Os nós de string que são docstring, por identidade.

    Precisam sair da varredura de caminhos: as docstrings deste app explicam de onde
    ele veio e citam `apps/automacoes/analise_ia/sql/` ao contar o que estava errado.
    Documentar o histórico é legítimo; montar um caminho para lá em tempo de execução
    não é. A diferença entre os dois casos é exatamente esta função.
    """
    encontrados = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            corpo = getattr(no, "body", None)
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
                if isinstance(corpo[0].value.value, str):
                    encontrados.add(id(corpo[0].value))
    return encontrados


class TestSemImportarDoAnaliseIA(unittest.TestCase):
    """Nenhum módulo deste app pode importar do analise_ia."""

    def test_nenhum_import_do_outro_app(self):
        infratores = []
        for caminho in _arquivos_python():
            arvore = ast.parse(open(caminho, encoding="utf-8").read(), filename=caminho)
            for no in ast.walk(arvore):
                if isinstance(no, ast.ImportFrom) and no.module and "analise_ia" in no.module:
                    infratores.append(f"{os.path.relpath(caminho, PROJECT_ROOT)}:{no.lineno} → {no.module}")
                elif isinstance(no, ast.Import):
                    for alias in no.names:
                        if "analise_ia" in alias.name:
                            infratores.append(f"{os.path.relpath(caminho, PROJECT_ROOT)}:{no.lineno} → {alias.name}")
        self.assertEqual(infratores, [], "imports do analise_ia encontrados:\n  " + "\n  ".join(infratores))

    def test_diagnostico_existe_localmente(self):
        """O extrator usa `diagnostico`; ele tem de morar aqui, não no vizinho."""
        self.assertTrue(os.path.exists(os.path.join(APP_DIR, "services", "diagnostico.py")))


class TestCaminhosApontamParaEsteApp(unittest.TestCase):
    """Nenhum caminho de arquivo montado pelo app pode cair na pasta do analise_ia."""

    def test_cache_do_gemini_fica_neste_app(self):
        caminho = ggci.caminho_cache_gemini()
        self.assertIn(os.path.join("dashboards", "dash_documentos_ia"), caminho)
        self.assertNotIn("analise_ia", caminho)

    def test_cache_nao_fica_no_diretorio_dos_espelhos_sql(self):
        """tabelas_sql/ é só para espelhos PY_ggci_*; o cache não é espelho de SQL nenhum."""
        self.assertNotIn(os.sep + "tabelas_sql" + os.sep, ggci.caminho_cache_gemini())

    def test_nenhum_literal_de_caminho_aponta_para_o_analise_ia(self):
        """
        Varre as strings do código atrás de caminhos para o outro app. Comentários e
        docstrings ficam de fora — citar o analise_ia numa explicação é legítimo,
        montar um caminho de arquivo para ele em tempo de execução não é.
        """
        infratores = []
        for caminho in _arquivos_python():
            arvore = ast.parse(open(caminho, encoding="utf-8").read(), filename=caminho)
            ignorar = _docstrings(arvore)
            for no in ast.walk(arvore):
                if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in ignorar:
                    if "analise_ia" in no.value and ("/" in no.value or "\\" in no.value):
                        infratores.append(f"{os.path.relpath(caminho, PROJECT_ROOT)}:{no.lineno} → {no.value!r}")
        self.assertEqual(infratores, [], "caminhos para o analise_ia encontrados:\n  " + "\n  ".join(infratores))


class TestArvoreSQLPropria(unittest.TestCase):
    """O app precisa dos seus próprios .sql — não pode ler os do vizinho."""

    def test_pasta_sql_existe(self):
        self.assertTrue(os.path.isdir(os.path.join(APP_DIR, "sql")))

    def test_todo_sql_do_mapa_existe_em_disco(self):
        """
        Se um caminho do mapa estiver errado, `atualizar_cache_parquets` não levanta
        exceção: ele simplesmente pula o CREATE e faz `SELECT` numa tabela que não
        existe, e o erro sai como um aviso perdido no meio do log.
        """
        for nome_tabela, caminho_sql in _mapa_tabelas():
            self.assertTrue(
                os.path.exists(caminho_sql),
                f"{nome_tabela}: arquivo ausente → {caminho_sql}",
            )


def _mapa_tabelas():
    """
    Extrai (nome_tabela, caminho_sql) do `mapa_tabelas` sem executar a função —
    ela abre conexão com o SIBU logo na primeira linha, e esta suíte não toca rede.
    """
    import inspect
    import re

    from apps.dashboards.dash_documentos_ia.services import extrator

    fonte = inspect.getsource(extrator.atualizar_cache_parquets)
    pares = re.findall(r'\("(PY_ggci_[a-z0-9_]+)", os\.path\.join\(PROJECT_ROOT, "(apps/[^"]+\.sql)"\)', fonte)
    assert pares, "mapa_tabelas não encontrado — o formato do código mudou?"
    return [(nome, os.path.join(PROJECT_ROOT, rel)) for nome, rel in pares]


if __name__ == "__main__":
    unittest.main()
