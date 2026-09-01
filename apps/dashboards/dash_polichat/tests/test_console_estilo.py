"""
=== ARQUIVO: apps/dashboards/dash_polichat/tests/test_console_estilo.py ===
Propósito: Garante que toda classe usada pelo console de atualização exista de fato
           no CSS desta tela.
Autor: N/A
Dependências Principais: unittest, re, pathlib

POR QUÊ EXISTE: esta tela não usa o bundle do portal. Ela tem um Tailwind próprio,
`polichat-tailwind.css`, que foi compilado e purgado a partir do markup que existia no
momento em que o `cdn.tailwindcss.com` saiu de cena. Antes disso o CDN rodava em modo JIT
e QUALQUER classe funcionava aqui — inclusive as que não existem em nenhum outro lugar do
portal.

A consequência é a pior possível para revisão: classe que entra no HTML depois daquela
compilação não tem regra nenhuma e **falha em silêncio**. Nada quebra, nada aparece no
console do navegador, `manage.py check` passa. O elemento simplesmente não é pintado.

Foi exatamente o que aconteceu quando o console foi trazido do dash_documentos_ia: 48
utilitárias vieram junto e nenhuma existia aqui. Os três círculos do terminal ficavam 0x0 e
sem cor, a barra de progresso animava a largura sendo transparente, e a rolagem rosa nunca
apareceu. Visualmente parecia "um modal sem estilo"; na verdade era o purge.

ARMADILHA DE AUDITORIA (custou um diagnóstico errado durante a construção): não basta ler
`class="..."`. Boa parte das classes do console é montada em template literal com
interpolação — `class="${sub ? 'ml-8' : 'ml-4'} my-0.5 ..."`. Um regex que ignore atributos
contendo `${}` pula justamente as classes mais repetidas do log e devolve um alegre "nenhuma
faltando". Por isso `classes_de` desmonta a interpolação e colhe também os literais de
string de dentro dela.
"""
import pathlib
import re
import unittest

APP = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = APP / "templates" / "dash_polichat" / "polichat" / "index.html"
JS = APP / "static" / "dash_polichat" / "js" / "polichat.js"
CSS_DIR = APP / "static" / "dash_polichat" / "css"

# Ordem irrelevante para a checagem: o que importa é a união do que esta tela carrega.
CSS_DA_TELA = [
    "polichat-tailwind.css",
    "polichat.css",
    "polichat-eleitoral.css",
    "dash_polichat.css",
]

# Font Awesome vem de CDN e não tem regra em CSS local; não é o que este teste vigia.
PREFIXOS_EXTERNOS = ("fa-",)

# Âncoras que delimitam o console dentro de cada arquivo. Se alguma sumir, o teste
# falha em vez de silenciosamente checar o arquivo inteiro (ou nada).
ANCORA_TEMPLATE = ("poli-modal-console", "HALOS DE FUNDO")
ANCORA_JS = ("Lógica do Terminal do Polichat", "Fim da lógica do Terminal")


def recortar(texto, inicio, fim, arquivo):
    if inicio not in texto or fim not in texto:
        raise AssertionError(
            f"Âncoras do console não encontradas em {arquivo}: {inicio!r} / {fim!r}. "
            "Se o bloco foi renomeado, atualize as âncoras deste teste."
        )
    return texto[texto.index(inicio):texto.index(fim)]


def classes_de(trecho):
    """Colhe os nomes de classe de um trecho de HTML ou de JS.

    Trata `class="a b ${cond ? 'x' : 'y'} c"` colhendo `a`, `b`, `c`, `x` e `y`.
    """
    achadas = set()
    for atributo in re.findall(r'class="([^"]*)"', trecho):
        for interpolacao in re.findall(r"\$\{([^}]*)\}", atributo):
            for literal in re.findall(r"['\"]([^'\"]*)['\"]", interpolacao):
                achadas.update(literal.split())
        achadas.update(re.sub(r"\$\{[^}]*\}", " ", atributo).split())
    return {c for c in achadas if c and not c.startswith(PREFIXOS_EXTERNOS)}


def seletor_de(classe):
    """Nome de classe -> seletor CSS, escapando o que o Tailwind escapa.

    `bg-[#ff5f56]` vira `.bg-\\[\\#ff5f56\\]`; `my-0.5` vira `.my-0\\.5`.
    """
    return "." + re.sub(r"([\[\]()#.:/%,])", r"\\\1", classe)


class TestClassesDoConsoleExistem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = "".join((CSS_DIR / nome).read_text(encoding="utf-8") for nome in CSS_DA_TELA)
        template = TEMPLATE.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        cls.classes = (
            classes_de(recortar(template, *ANCORA_TEMPLATE, TEMPLATE.name))
            | classes_de(recortar(js, *ANCORA_JS, JS.name))
        )

    def test_o_recorte_encontrou_um_console_de_verdade(self):
        """Guarda o próprio teste: recorte vazio passaria em tudo sem checar nada."""
        self.assertGreater(
            len(self.classes), 60,
            "O recorte do console devolveu poucas classes — provavelmente as âncoras "
            "pegaram o bloco errado, e aí este arquivo inteiro vira um teste falso-positivo.",
        )

    def test_toda_classe_do_console_tem_regra_no_css_desta_tela(self):
        faltando = sorted(c for c in self.classes if seletor_de(c) not in self.css)
        self.assertEqual(
            faltando, [],
            "Estas classes são usadas pelo console mas não existem em nenhum CSS desta tela.\n"
            "Elas NÃO vão falhar com erro: vão simplesmente não pintar nada.\n"
            "Declare cada uma em polichat.css (bloco 'CONSOLE DE ATUALIZAÇÃO').\n"
            f"Faltando: {faltando}",
        )

    def test_semaforo_do_terminal_tem_tamanho_e_cor(self):
        """As três bolinhas foram o sintoma mais visível do purge: 0x0 e transparentes."""
        for classe in ("w-3.5", "h-3.5", "bg-[#ff5f56]", "bg-[#ffbd2e]", "bg-[#27c93f]"):
            self.assertIn(seletor_de(classe), self.css, f"{classe} sumiu do CSS da tela.")

    def test_barra_de_progresso_tem_preenchimento(self):
        """Sem o gradiente a barra anima a largura sendo invisível — parece que não há barra."""
        for classe in ("bg-gradient-to-r", "from-pink-400", "to-purple-500"):
            self.assertIn(seletor_de(classe), self.css, f"{classe} sumiu do CSS da tela.")

    def test_barra_de_rolagem_rosa_existe(self):
        """No documentos_ia ela mora num <style> dentro do template; aqui precisa ser CSS do app."""
        self.assertIn(".scroll-rosinha::-webkit-scrollbar", self.css)


class TestTelaNaoRegridePraOCDN(unittest.TestCase):
    """O CDN em modo JIT fazia qualquer classe funcionar e mascarava exatamente o
    defeito que a classe de teste acima vigia. Voltar a ele apagaria a rede de proteção."""

    def setUp(self):
        self.template = TEMPLATE.read_text(encoding="utf-8")
        # O CDN é CITADO de propósito no comentário que explica por que ele saiu.
        # Vigiar o texto cru transformaria essa documentação em falha de teste; o
        # que interessa é se a tela volta a CARREGAR o script.
        self.sem_comentarios = re.sub(r"<!--.*?-->", "", self.template, flags=re.S)

    def test_nao_carrega_cdn_tailwind(self):
        self.assertNotRegex(
            self.sem_comentarios, r"""<(?:script|link)[^>]*cdn\.tailwindcss\.com""",
            "O Tailwind via CDN roda em JIT: qualquer classe passa a funcionar nesta tela e "
            "para de funcionar em todas as outras. Use polichat-tailwind.css.",
        )

    def test_carrega_o_tailwind_compilado_da_tela(self):
        self.assertIn("dash_polichat/css/polichat-tailwind.css", self.template)

    def test_css_e_js_da_tela_tem_cache_buster(self):
        """Sem bumpar o ?v= o navegador serve o arquivo antigo e a correção 'não chega'."""
        for arquivo in ("polichat.css", "polichat.js"):
            self.assertRegex(
                self.template, re.escape(arquivo) + r"' %\}\?v=\d+",
                f"{arquivo} precisa continuar sendo servido com ?v= — é o que força o "
                "navegador a baixar a versão nova depois de uma alteração.",
            )


if __name__ == "__main__":
    unittest.main()
