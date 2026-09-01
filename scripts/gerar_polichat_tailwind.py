"""
Materializa o CSS que o Tailwind CDN gera para o polichat.  (v2)

A v1 abria a página real e injetava as classes via DOM, contando com o
MutationObserver do play CDN para recompilar. Não recompilou: o CSS saiu só com
as classes do estado inicial, e a falha só apareceu no comparador de estilo
computado — `bg-pink-500` ficou sem regra. Um canário agora guarda contra isso.

Esta versão entrega as classes já no HTML servido, que é o caminho que o CDN
processa no primeiro passe. Não precisamos da página real: precisamos do CDN
compilando a lista de classes com o mesmo tailwind.config que a tela usava.
"""
import re, pathlib, sys

BASE = pathlib.Path("/home/labs/portal-ggci-dev")
TPL = BASE/"apps/dashboards/dash_polichat/templates/dash_polichat/polichat/index.html"
JS  = BASE/"apps/dashboards/dash_polichat/static/dash_polichat/js/polichat.js"
DESTINO = BASE/"apps/dashboards/dash_polichat/static/dash_polichat/css/polichat-tailwind.css"

# As cores da marca vinham do bloco tailwind.config que ficava no <head> da tela.
CONFIG = """tailwind.config={theme:{extend:{colors:{
  pink:{500:'#f0248c'},yellow:{400:'#ffd000'},
  purple:{700:'#9424f0'},green:{600:'#14b355'}}}}}"""

def plausivel(t):
    if '$' in t or '{' in t or '}' in t: return False
    if not re.match(r'[a-z-]', t): return False
    if re.fullmatch(r'-?\d[\d.]*[a-z%]*', t): return False
    return len(t) <= 60

tokens = set()
for arq in (TPL, JS):
    txt = arq.read_text()
    for m in re.finditer(r'class(?:List)?\s*=\s*["\']([^"\']+)["\']', txt):
        tokens.update(m.group(1).split())
    for m in re.finditer(r'["\'`]([^"\'`\n]{1,400})["\'`]', txt):
        tokens.update(m.group(1).split())
    for m in re.finditer(r'classList\.(?:add|remove|toggle|replace)\(([^)]*)\)', txt):
        for t in re.findall(r'["\']([^"\']+)["\']', m.group(1)):
            tokens.update(t.split())

tokens = sorted(t for t in tokens if plausivel(t))
# Utilitários de cor da marca: podem só aparecer em variantes com opacidade
# (bg-pink-500/70), e ainda assim precisam existir na forma base.
for base in ("pink-500","yellow-400","purple-700","green-600"):
    for pref in ("bg","text","border","from","to","via"):
        tokens.append(f"{pref}-{base}")
tokens = sorted(set(tokens))
print(f"classes a compilar: {len(tokens)}")

html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<script src='https://cdn.tailwindcss.com'></script>"
        f"<script>{CONFIG}</script></head><body>"
        + "".join(f"<div class=\"{c}\"></div>" for c in tokens)
        + "</body></html>")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width":1600,"height":900}).new_page()
    pg.set_content(html, wait_until="networkidle")

    canarios = ["bg-pink-500", "w-4", "backdrop-blur-3xl"]
    ok = False
    for _ in range(40):
        pg.wait_for_timeout(500)
        if all(pg.evaluate("""(c)=>{for(const f of document.styleSheets){if(f.href)continue;
                let rs;try{rs=f.cssRules}catch(e){continue}
                for(const r of rs) if(r.cssText && r.cssText.startsWith('.'+c+' ')) return true}
                return false}""", c) for c in canarios):
            ok = True; break
    if not ok:
        sys.exit("ERRO: o JIT não compilou os canários — abortando para não gerar CSS incompleto.")
    print("  JIT confirmado:", ", ".join(canarios))
    pg.wait_for_timeout(1500)

    css = pg.evaluate("""()=>{const out=[];
        for(const f of document.styleSheets){ if(f.href) continue;
            let rs; try{rs=f.cssRules}catch(e){continue}
            for(const r of rs) out.push(r.cssText); }
        return out.join('\\n');}""")
    b.close()

# O cssText do Chromium arredonda para 6 dígitos significativos ao serializar,
# então a fração 66.666667% do Tailwind volta como 66.6667%. A diferença é de
# 0,016px em 900px — invisível, mas é divergência real e sem motivo. Restaurar é
# barato; foi a última diferença que sobrou no comparador de estilo computado.
css = css.replace("width: 66.6667%", "width: 66.666667%")

cabecalho = """/*
 * polichat-tailwind.css — ARQUIVO GERADO. Não edite à mão.
 *
 * Materializa o CSS que `cdn.tailwindcss.com` (Tailwind v3) produzia para esta
 * tela, com o `tailwind.config` que vivia no <head> já resolvido dentro dele
 * (cores da marca: pink 500 #f0248c, yellow 400 #ffd000, purple 700 #9424f0,
 * green 600 #14b355).
 *
 * POR QUE ISTO EXISTE: o polichat era a única tela do portal que carregava o
 * Tailwind por CDN, em modo JIT. Lá QUALQUER classe funcionava, mesmo as que não
 * existem em nenhum outro lugar — era isso que fazia markup copiado desta tela
 * quebrar em silêncio em todas as outras. Também era a última dependência de
 * build em runtime do projeto.
 *
 * POR QUE NÃO APONTAMOS PARA static/css/output.css: o bundle do portal é v4.3.0
 * e o CDN servia v3. Trocar um pelo outro mudaria cores, sombras e escalas de
 * mais de 400 utilitárias de uma vez. Este arquivo congela o visual aprovado.
 *
 * PARA REGENERAR: o extrator vive no commit que introduziu este arquivo. Ele
 * coleta as classes do template e do JS, manda o CDN compilar e serializa o
 * resultado, com canários que abortam se o JIT não tiver terminado.
 */
"""
DESTINO.write_text(cabecalho + css + "\n")
print(f"gerado: {DESTINO.name}  ({DESTINO.stat().st_size//1024} KB, {css.count('}')} regras)")
