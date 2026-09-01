"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/tests/test_escopo_atualizacao_ui.py ===
Propósito: Trava o que o modal "Escopo da atualização" só tem no teclado e no tema escuro.
Autor: N/A
Dependências Principais: django.test, re

POR QUÊ EXISTE: o modal foi desenhado inteiro em CSS próprio — `static/css/output.css` é
um bundle Tailwind purgado e sem build no repositório, então utilitária ausente falha em
silêncio. Isso vale também para o que o desenho ESQUECE: nada avisa que um controle não
tem foco de teclado, ou que uma cor literal não ganhou contraparte escura. Os dois defeitos
são invisíveis para quem desenvolve com mouse e no tema claro.

O CASO QUE MOTIVOU O ARQUIVO: os quatro períodos são `<input class="sr-only">` seguidos de
um `<span>` desenhado. O foco cai no input invisível, então o Tab atravessava os quatro sem
nada acontecer na tela — o modal era operável no mouse e mudo no teclado.

O QUE ESTE TESTE GARANTE: todo controle do modal desenha foco; o período pinta o anel no
irmão visível; e as cores literais do arquivo claro têm contraparte em `[data-tema="eleitoral"]`.
"""
import os
import re

from django.test import SimpleTestCase

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
CSS_DIR = os.path.join(PROJECT_ROOT, 'apps', 'dashboards', 'dash_documentos_ia',
                       'static', 'dash_documentos_ia', 'css')
CSS_CLARO = os.path.join(CSS_DIR, 'dash_documentos_ia.css')
CSS_ESCURO = os.path.join(CSS_DIR, 'dash_documentos_ia-eleitoral.css')


def _ler(caminho):
    with open(caminho, encoding='utf-8') as fh:
        return fh.read()


def _sem_comentarios(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _seletores(css, tirar_tema=False):
    achados = set()
    for bloco in re.finditer(r'([^{}]+)\{', _sem_comentarios(css)):
        for sel in bloco.group(1).split(','):
            sel = sel.strip()
            if tirar_tema:
                sel = sel.replace('html[data-tema="eleitoral"] ', '')
            if 'cfgx' in sel or 'cfg-' in sel:
                achados.add(sel)
    return achados


class FocoDeTecladoTests(SimpleTestCase):

    def setUp(self):
        self.css = _sem_comentarios(_ler(CSS_CLARO))

    def test_todo_controle_do_modal_desenha_foco(self):
        """Um controle sem foco visível é um controle que só existe para quem usa mouse."""
        for controle in ('.cfgx__fechar', '.cfgx__mini', '.cfgx-acao', '.cfgx__btn'):
            self.assertIn(f'{controle}:focus-visible', self.css,
                          f'{controle} não desenha foco de teclado')

    def test_periodo_pinta_o_anel_no_irmao_visivel(self):
        """
        O `<input>` do período é `sr-only`. Pintar o foco NELE não aparece na tela — o anel
        tem de ir para o `<span>` irmão, que é o que a pessoa enxerga.
        """
        self.assertIn('.cfg-periodo:focus-visible + .cfgx-periodo__caixa', self.css)

    def test_foco_e_visible_e_nao_focus_puro(self):
        """
        `:focus` puro faria o anel piscar a cada clique de mouse. A distinção é o que
        mantém o recurso acessível sem virar ruído visual.
        """
        for bruto in ('.cfgx-acao:focus{', '.cfgx-acao:focus ', '.cfgx__btn:focus{'):
            self.assertNotIn(bruto, self.css.replace(' {', '{'))

    def test_respeita_quem_pediu_menos_movimento(self):
        self.assertIn('prefers-reduced-motion', self.css)


class ParidadeDeTemaTests(SimpleTestCase):
    """
    O arquivo escuro não redesenha nada: ele reapresenta no escuro o que o claro desenhou.
    Uma cor literal sem contraparte fica igual nos dois temas — e cinza-claro pensado para
    fundo branco vira, no escuro, o elemento MAIS forte da tela.
    """

    def test_nenhuma_cor_do_modal_ficou_sem_contraparte_escura(self):
        claro = _ler(CSS_CLARO)
        escuro = _ler(CSS_ESCURO)
        sem_tema = _seletores(claro) - _seletores(escuro, tirar_tema=True)

        corpo_claro = _sem_comentarios(claro)
        pinta = re.compile(r'(^|;|\s)(color|background|background-color|box-shadow)\s*:', re.I)

        faltando = []
        for sel in sorted(sem_tema):
            bloco = re.search(re.escape(sel) + r'\s*(,[^{]*)?\{([^}]*)\}', corpo_claro)
            if bloco and pinta.search(bloco.group(2)):
                faltando.append(sel)

        self.assertEqual(faltando, [],
                         f'cores do modal sem versão escura: {faltando}')

    def test_o_anel_de_foco_e_reajustado_no_escuro(self):
        """O roxo da marca some contra a superfície escura; o token já vem clareado."""
        escuro = _sem_comentarios(_ler(CSS_ESCURO))
        self.assertIn(':focus-visible', escuro)
        self.assertIn('outline-color: var(--tema-primaria)', escuro)


class LarguraCurtaTests(SimpleTestCase):
    """
    O modal é `max-width: 94vw`. No celular a linha de documento não quebrava, e nome longo
    com dois botões de ação espremia o texto até sobrar reticência.
    """

    def test_existe_recorte_para_tela_estreita(self):
        css = _sem_comentarios(_ler(CSS_CLARO))
        self.assertIn('@media (max-width: 560px)', css)

    def test_a_linha_de_documento_quebra(self):
        css = _sem_comentarios(_ler(CSS_CLARO))
        estreito = css.split('@media (max-width: 560px)')[1]
        self.assertIn('.cfgx-doc__linha { flex-wrap: wrap; }', estreito)

class ChipDePeriodoTests(SimpleTestCase):
    """
    O rótulo dos quatro botões de ano-semestre saía visivelmente fora do centro.

    A CAUSA não era o alinhamento e sim o check: ele é `opacity: 0` enquanto o período
    está desmarcado, e opacity NÃO tira do fluxo — o ícone seguia ocupando a largura
    dele mais o `gap`, empurrando o texto para a direita. O estado marcado parecia
    certo porque aí o ícone aparecia no espaço que já estava reservado.
    """

    def setUp(self):
        self.css = _sem_comentarios(_ler(CSS_CLARO))

    def _bloco(self, seletor):
        achado = re.search(re.escape(seletor) + r'\s*\{([^}]*)\}', self.css)
        self.assertIsNotNone(achado, f'{seletor} sumiu da folha')
        return achado.group(1)

    def test_o_check_sai_do_fluxo(self):
        """Enquanto ele ocupar espaço, nenhum ajuste de alinhamento centra o texto."""
        self.assertIn('position: absolute', self._bloco('.cfgx-periodo__marca'))

    def test_o_rotulo_e_centralizado(self):
        self.assertIn('justify-content: center', self._bloco('.cfgx-periodo__caixa'))

    def test_o_padding_do_chip_e_simetrico(self):
        """
        Padding assimétrico devolveria o problema por outro caminho: o texto ficaria
        centrado na caixa mas deslocado em relação à borda visível.
        """
        corpo = self._bloco('.cfgx-periodo__caixa')
        padding = re.search(r'padding:\s*([^;]+);', corpo).group(1).split()
        self.assertEqual(len(padding), 2,
                         f'padding do chip deixou de ser simétrico: {padding}')

    def test_os_quatro_chips_tem_a_mesma_largura(self):
        """Sem `min-width` a fileira lê como quatro retângulos parecidos, não um grupo."""
        self.assertIn('min-width', self._bloco('.cfgx-periodo__caixa'))


class ConsoleNaoDuplicaTests(SimpleTestCase):
    """
    `initDashDocumentosIA` roda no DOMContentLoaded E no turbo:load. Na primeira carga os
    dois disparam, e sem trava o botão Atualizar saía daqui com DOIS ouvintes: um clique
    abria DUAS execuções, dois `acompanhar()` escreviam no mesmo `#console-logs` e a tela
    de logs passava a alternar entre execuções diferentes, crescendo sem parar.
    """

    def setUp(self):
        js = os.path.join(PROJECT_ROOT, 'apps', 'dashboards', 'dash_documentos_ia',
                          'static', 'dash_documentos_ia', 'js', 'dash_documentos_ia.js')
        self.js = _ler(js)

    def test_o_botao_atualizar_so_ganha_um_ouvinte(self):
        self.assertIn("btnAtualizar && !btnAtualizar.dataset.ligadoDocia", self.js)

    def test_a_marca_vive_no_elemento_e_nao_em_window(self):
        """
        O Turbo substitui o <body>: uma trava em `window` sobreviveria à navegação e
        deixaria o botão NOVO sem ouvinte nenhum. O dataset nasce limpo com o elemento.
        """
        self.assertNotIn('window.__atualizarLigadoDocIA', self.js)
        self.assertIn("btnAtualizar.dataset.ligadoDocia = '1'", self.js)

    def test_existe_trava_sincrona_entre_o_clique_e_a_resposta(self):
        """
        `__processo_id_docia` só é preenchido no `.then`. Sem uma trava síncrona, dois
        handlers (ou dois cliques) atravessam a janela antes de o fetch responder.
        """
        self.assertIn('window.__iniciandoDocIA', self.js)
        clique = self.js.split("btnAtualizar.addEventListener('click'")[1][:600]
        self.assertIn('if (window.__iniciandoDocIA) { return; }', clique)

