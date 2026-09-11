"""
=== ARQUIVO: ~/.claude/tools/ggci_shot.py ===
Propósito: Renderiza uma tela LOGADA do portal num Chromium headless e salva PNG,
    inclusive em estados que só existem sob o cursor (`:hover`).
Dependências Principais: django, playwright (ambos já no venv do projeto)

POR QUÊ EXISTE: mudança de CSS não se confere lendo CSS. Especificidade, ordem de
cascata e utilitária de Tailwind purgada são justamente o que escapa da leitura —
um `position: relative` num seletor de id já apagou o botão de filtros da tela sem
que nada no arquivo parecesse errado.

COMO FUNCIONA: sobe um `StaticLiveServerTestCase` com banco SQLite DESCARTÁVEL e um
usuário de fixture criado na hora. Isso é deliberado: forjar sessão no banco real
desloga a pessoa que estiver usando o portal. Nada aqui toca o banco de produção.

O `--hover` recebe um seletor CSS e o Playwright posiciona o mouse de verdade sobre o
elemento antes de disparar, porque `:hover` não se força por classe.

USO:
    venv/bin/python ~/.claude/tools/ggci_shot.py --url /dashboards/documentos-ia/ \
        --out /tmp/tela.png [--hover ".docia-kpi-card" ] [--clip "#kpi-row"]
        [--tema eleitoral] [--largura 1920] [--altura 1080]
"""
import argparse
import os
import sys
import unittest

REPO = os.environ.get("GGCI_REPO", "/home/labs/portal-ggci-dev")
sys.path.insert(0, REPO)
os.chdir(REPO)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
#  Settings de captura ANTES do setup: ver o cabeçalho de `ggci_shot_settings.py`
#  para por que a troca de banco não pode ser feita depois.
os.environ["DJANGO_SETTINGS_MODULE"] = "ggci_shot_settings"

import django  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402

django.setup()
setup_test_environment()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.staticfiles.testing import StaticLiveServerTestCase  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def capturar(args):
    runner = DiscoverRunner(verbosity=0, interactive=False)
    config = runner.setup_databases()
    try:
        User = get_user_model()
        #  Usuário de fixture com todas as permissões `p_*` do modelo ligadas, para
        #  passar pelos `_tem_permissao` de qualquer tela sem precisar saber qual
        #  flag cada uma exige. Nasce e morre dentro do SQLite descartável.
        perms = {f.name: True for f in User._meta.get_fields()
                 if f.name.startswith('p_')}
        user = User.objects.create_user(
            usuario='shot@ovg.org.br', nome='Captura Headless',
            password='x', perfil='administrador',
            is_staff=True, is_superuser=True, **perms
        )

        class Caso(StaticLiveServerTestCase):
            def runTest(self):
                #  A SESSÃO É CRIADA ANTES DE ABRIR O NAVEGADOR, e não por
                #  estilo: o `sync_playwright()` roda um event loop na thread
                #  principal, e o ORM do Django se recusa a trabalhar dentro de
                #  contexto async (`SynchronousOnlyOperation`). Qualquer consulta
                #  feita lá dentro estoura. O cookie sai pronto aqui fora; o
                #  servidor responde noutra thread, onde a regra não vale.
                self.client.force_login(user)
                cookie = self.client.cookies["sessionid"].value

                with sync_playwright() as p:
                    nav = p.chromium.launch()
                    pag = nav.new_page(
                        viewport={"width": args.largura, "height": args.altura})
                    pag.context.add_cookies([{
                        "name": "sessionid", "value": cookie,
                        "url": self.live_server_url,
                    }])
                    if args.console:
                        #  Erro de JS não aparece no PNG: a tela só fica vazia.
                        #  Sem isto, "some tudo ao recarregar" vira adivinhação.
                        pag.on("console", lambda m: print(
                            f"[console:{m.type}] {m.text}", file=sys.stderr))
                        pag.on("pageerror", lambda e: print(
                            f"[pageerror] {e}", file=sys.stderr))
                    if args.pre_js:
                        #  Roda ANTES dos scripts da página, a cada navegação. É o
                        #  único jeito de semear `localStorage` a tempo de o
                        #  `<head>` síncrono já encontrar o estado — que é
                        #  exatamente o que acontece num F5 de verdade.
                        pag.add_init_script(args.pre_js)
                    pag.goto(self.live_server_url + args.url,
                             wait_until="networkidle")
                    if args.tema:
                        pag.evaluate(
                            f"document.documentElement.dataset.tema = '{args.tema}'")
                    if args.js:
                        #  Executa JS arbitrário antes do print. É o que permite
                        #  fotografar estado transitório — um esqueleto de
                        #  carregamento vive 200ms e não se alcança de outro jeito.
                        pag.evaluate(args.js)
                    if args.hover:
                        #  Mouse de verdade sobre o elemento: `:hover` não se
                        #  simula por classe.
                        pag.hover(args.hover)
                    pag.wait_for_timeout(args.espera)
                    alvo = pag.locator(args.clip) if args.clip else pag
                    alvo.screenshot(path=args.out)
                    print(f"OK  {args.out}  <- {args.url}"
                          + (f"  :hover({args.hover})" if args.hover else ""))
                    nav.close()

        #  Roda pelo unittest, e não chamando `runTest()` direto: é o
        #  `setUpClass` do LiveServerTestCase que sobe o servidor numa thread e o
        #  `_pre_setup` que cria o `self.client`. Sem esse ciclo não há nem porta
        #  para o navegador acessar.
        resultado = unittest.TextTestRunner(
            stream=open(os.devnull, 'w'), verbosity=0
        ).run(unittest.TestSuite([Caso()]))
        for _, tb in resultado.errors + resultado.failures:
            print(tb, file=sys.stderr)
        if not resultado.wasSuccessful():
            raise SystemExit(1)
    finally:
        runner.teardown_databases(config)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="/dashboards/documentos-ia/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hover", default=None, help="seletor que recebe o mouse")
    ap.add_argument("--clip", default=None, help="seletor a recortar no PNG")
    ap.add_argument("--tema", default=None, choices=["eleitoral"])
    ap.add_argument("--js", default=None, help="JS a executar antes do print")
    ap.add_argument("--pre-js", dest="pre_js", default=None,
                    help="JS a executar ANTES dos scripts da pagina (semear localStorage)")
    ap.add_argument("--console", action="store_true",
                    help="imprime mensagens de console e erros de JS no stderr")
    ap.add_argument("--largura", type=int, default=1920)
    ap.add_argument("--altura", type=int, default=1080)
    ap.add_argument("--espera", type=int, default=900, help="ms para as animações assentarem")
    args = ap.parse_args()
    try:
        capturar(args)
    finally:
        teardown_test_environment()
