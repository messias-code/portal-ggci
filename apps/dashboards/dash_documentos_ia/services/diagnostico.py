"""
==========================================================================
DIAGNÓSTICO VISUAL DA EXTRAÇÃO (PLAYWRIGHT)
==========================================================================
O servidor não tem ambiente gráfico: o Chromium roda `headless=True` e
ninguém consegue olhar a tela para descobrir em que ponto uma extração
emperrou. Este módulo resolve isso gravando o que o navegador estava vendo
no momento exato da falha.

DESLIGADO POR PADRÃO — e isso é importante. Capturar tela custa tempo e
disco, e a extração roda com 8 tarefas em paralelo. Nada aqui executa a menos
que a variável de ambiente correspondente esteja ligada, então o caminho de
produção continua idêntico ao de hoje.

MODOS DISPONÍVEIS

  EXTRATOR_DIAGNOSTICO=1
      Captura PNG + HTML sempre que uma tarefa é descartada por não achar o
      que esperava (grid vazio, botão Exportação ausente, filtro não
      encontrado). É o modo para responder "por que esse documento não veio?".

  EXTRATOR_TRACE=1
      Liga o tracing nativo do Playwright. Gera um .zip por tarefa contendo
      screenshot ANTES e DEPOIS de cada ação, snapshot do DOM, requisições de
      rede e console. É mais pesado, mas é o passo a passo completo.

      Para ver: baixe o .zip e abra em https://trace.playwright.dev — roda no
      navegador, não instala nada e não precisa de ambiente gráfico no
      servidor. É a forma mais próxima de "assistir ao robô trabalhando".

COMO USAR
    cd /home/labs/portal-ggci-dev
    EXTRATOR_DIAGNOSTICO=1 venv/bin/python3 manage.py executar_motor_ia <id>

    # investigação completa de uma execução
    EXTRATOR_DIAGNOSTICO=1 EXTRATOR_TRACE=1 venv/bin/python3 manage.py executar_motor_ia <id>

ONDE OS ARQUIVOS CAEM
    apps/dashboards/dash_documentos_ia/logs/diagnostico/<data_hora_da_execucao>/

    Cada captura vira um par de arquivos com o mesmo nome base:
        <etapa>__<documento>_<semestre>__<hhmmss>.png    o que estava na tela
        <etapa>__<documento>_<semestre>__<hhmmss>.html   o DOM naquele instante

    O HTML acompanha o PNG de propósito: quando o Playwright não encontra um
    elemento, a pergunta seguinte costuma ser "ele existe no DOM e está
    invisível, ou não existe?" — e só a imagem não responde isso.
==========================================================================
"""

import os
import re
import datetime
from pathlib import Path

from django.conf import settings

ATIVO = os.getenv("EXTRATOR_DIAGNOSTICO", "0") == "1"
TRACE_ATIVO = os.getenv("EXTRATOR_TRACE", "0") == "1"

# Uma pasta por execução, nomeada pelo horário de início. Evita que a
# investigação de hoje se misture com a de ontem.
_CARIMBO_EXECUCAO = datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M")

_RAIZ = Path(settings.BASE_DIR) / "apps" / "dashboards" / "dash_documentos_ia" / "logs" / "diagnostico"
PASTA_EXECUCAO = _RAIZ / _CARIMBO_EXECUCAO


def _preparar_pasta():
    PASTA_EXECUCAO.mkdir(parents=True, exist_ok=True)
    return PASTA_EXECUCAO


def _higienizar(texto):
    """Transforma a tag da tarefa em algo que sobrevive a um nome de arquivo.

    As tags vêm no formato "[ANÁLISE    | BENEFICIOS    | 2025-1]" — cheias de
    espaço, barra vertical e acento. Sem isso, o nome do arquivo fica
    impossível de digitar no terminal.
    """
    limpo = re.sub(r"[^\w\-]+", "_", str(texto), flags=re.UNICODE)
    return limpo.strip("_")[:80]


def capturar(page, etapa, tag=""):
    """Salva PNG + HTML da página no estado atual.

    Silencioso e à prova de falha: diagnóstico nunca pode derrubar a extração
    que está tentando diagnosticar. Se a captura falhar (página já fechada,
    disco cheio), o erro é engolido e a extração segue.

    Args:
        page: o objeto `page` do Playwright.
        etapa: identificador curto do ponto do código (ex.: "sem_botao_export").
        tag: a tag da tarefa, para saber de qual documento/semestre se trata.
    """
    if not ATIVO:
        return None
    try:
        pasta = _preparar_pasta()
        base = f"{_higienizar(etapa)}__{_higienizar(tag)}__{datetime.datetime.now().strftime('%H%M%S_%f')[:13]}"

        caminho_png = pasta / f"{base}.png"
        # full_page captura além da dobra: o aviso de "registros não
        # encontrados" do ScriptCase costuma ficar abaixo da área visível.
        page.screenshot(path=str(caminho_png), full_page=True)

        caminho_html = pasta / f"{base}.html"
        caminho_html.write_text(page.content(), encoding="utf-8", errors="ignore")

        print(f"   🔍 DIAGNÓSTICO: {caminho_png.name}")
        return caminho_png
    except Exception as erro:
        print(f"   🔍 DIAGNÓSTICO: falha ao capturar ({erro})")
        return None


def iniciar_trace(context, tag=""):
    """Liga o tracing do Playwright no contexto, se EXTRATOR_TRACE=1."""
    if not TRACE_ATIVO:
        return
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    except Exception as erro:
        print(f"   🔍 TRACE: não foi possível iniciar ({erro})")


def encerrar_trace(context, tag=""):
    """Fecha o tracing e grava o .zip. Precisa ser chamado antes do contexto
    morrer, senão o arquivo sai truncado."""
    if not TRACE_ATIVO:
        return
    try:
        pasta = _preparar_pasta()
        destino = pasta / f"trace__{_higienizar(tag)}__{datetime.datetime.now().strftime('%H%M%S')}.zip"
        context.tracing.stop(path=str(destino))
        print(f"   🔍 TRACE: {destino.name}  (abra em https://trace.playwright.dev)")
    except Exception as erro:
        print(f"   🔍 TRACE: não foi possível encerrar ({erro})")
