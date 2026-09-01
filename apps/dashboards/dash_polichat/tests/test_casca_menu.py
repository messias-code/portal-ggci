"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_casca_menu.py ===
Propósito: Garante que toda tela com menu lateral declare os ganchos que o modo
           eleitoral usa para recolorir a casca.
Autor: N/A
Dependências Principais: unittest, re

POR QUÊ EXISTE: `menu-divisoria`, `menu-sair` e companhia são classes-GANCHO — não
pintam nada no modo padrão. Existem só para o `tema-menu.css` alcançá-las no eleitoral,
já que a casca (barra lateral e cabeçalho) fica FORA de `.area-trabalho` e escapa do
remapeamento em bloco.

A consequência de esquecer um gancho é invisível durante o desenvolvimento: no modo
padrão a tela fica perfeita, e o defeito só aparece para quem usa o eleitoral. Foi o que
aconteceu com o Recálculo de Bolsas e o Enquadramento de Cursos: os dois nasceram sem
`menu-divisoria` e com `border-gray-200/60` no lugar de `border-purple-100/50`. No escuro
aquele cinza-claro a 60% virava um fio quase branco cortando a barra lateral logo acima
de "SAIR DO SISTEMA" — enquanto as outras nove telas mostravam o fio discreto de
`--tema-borda`, a 13%.

Não é um defeito que `manage.py check` veja, nem que apareça em revisão de diff: a classe
que falta não deixa rastro nenhum no arquivo.

NOTA: mora na suíte do Polichat porque é a única que roda hoje no portal — mesma razão do
`test_console_compartilhado`. O escopo, porém, é a casca compartilhada.
"""
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[4]

# Ganchos que a casca precisa declarar. Ficam de fora os que dependem do TIPO de tela:
# `tela-voltar` só existe em tela interna, `area-trabalho` só onde há área de trabalho.
GANCHOS_DA_CASCA = ["menu-shell", "menu-sidebar", "menu-header", "menu-divisoria", "menu-sair"]


def telas_com_menu():
    """Toda tela que tem o botão de sair tem a casca completa."""
    achadas = []
    for caminho in sorted(RAIZ.glob("apps/**/templates/**/index.html")):
        texto = caminho.read_text(encoding="utf-8")
        if "url 'logout'" in texto:
            achadas.append((str(caminho.relative_to(RAIZ)), texto))
    return achadas


class TestGanchosDaCasca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.telas = telas_com_menu()

    def test_encontrou_as_telas(self):
        """Guarda o próprio teste: uma varredura vazia passaria em tudo."""
        self.assertGreaterEqual(
            len(self.telas), 10,
            "A varredura achou poucas telas com menu — o padrão de caminho mudou.",
        )

    def test_toda_tela_com_menu_declara_os_ganchos(self):
        for caminho, texto in self.telas:
            for gancho in GANCHOS_DA_CASCA:
                with self.subTest(tela=caminho, gancho=gancho):
                    self.assertIn(
                        gancho, texto,
                        f"{caminho} não declara `{gancho}`. No modo padrão nada muda — "
                        "esse gancho não pinta nada sozinho. No eleitoral, o "
                        "tema-menu.css não alcança o elemento e ele fica com a cor "
                        "clara sobre a casca escura.",
                    )

    def test_a_divisoria_do_sair_usa_a_mesma_borda_em_todas_as_telas(self):
        """A cor da borda importa junto com o gancho: no eleitoral o `tema-menu.css`
        sobrescreve a cor, mas no padrão quem manda é a utilitária do HTML — e telas
        diferentes com bordas diferentes é o começo da divergência."""
        bordas = {}
        for caminho, texto in self.telas:
            achado = re.search(
                r'class="[^"]*menu-divisoria[^"]*?(border-[a-z]+-\d+(?:/\d+)?)', texto
            )
            self.assertIsNotNone(
                achado, f"{caminho}: não achei a utilitária de borda da divisória."
            )
            bordas.setdefault(achado.group(1), []).append(caminho)
        self.assertEqual(
            len(bordas), 1,
            "As telas usam bordas diferentes na divisória do 'Sair do Sistema': "
            f"{ {k: [c.split('templates/')[-1] for c in v] for k, v in bordas.items()} }",
        )


class TestTemaAlcancaOsGanchos(unittest.TestCase):
    """De nada adianta o HTML declarar o gancho se o tema não o usa — e vice-versa."""

    @classmethod
    def setUpClass(cls):
        cls.tema = (RAIZ / "static" / "css" / "tema-menu.css").read_text(encoding="utf-8")
        # Comentários fora antes de procurar: este arquivo cita os nomes das classes
        # no texto que explica cada decisão, e a busca acusaria a documentação.
        cls.regras = re.sub(r"/\*.*?\*/", "", cls.tema, flags=re.S)

    def test_o_tema_recolore_a_divisoria_no_eleitoral(self):
        self.assertRegex(
            self.regras,
            r'html\[data-tema="eleitoral"\][^{}]*\.menu-divisoria',
            "O `tema-menu.css` deixou de tratar `.menu-divisoria`. Sem essa regra o "
            "gancho no HTML não serve para nada e o fio volta a ficar claro no escuro.",
        )

    def test_o_tema_recolore_o_botao_de_sair(self):
        self.assertRegex(self.regras, r'html\[data-tema="eleitoral"\][^{}]*\.menu-sair')


if __name__ == "__main__":
    unittest.main()
