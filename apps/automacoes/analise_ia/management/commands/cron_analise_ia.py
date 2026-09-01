"""
Propósito: Entrada NÃO-INTERATIVA do ciclo diário do Análise IA (cron e opção 7 do portal.sh).
Autor: N/A
Dependências: django.core.management, subprocess, signal, portal_ggci.processos

O QUE O CRON PRECISA FAZER (e o que não precisa)
  O ciclo da madrugada existe para uma coisa só: deixar os Parquet de
  `dados/tabelas_sql/` atualizados com o dia de hoje. Eles são o espelho local
  das tabelas `PY_ggci_*` do SIBU, e são o que faz a geração do relatório ser
  rápida quando o funcionário chega de manhã e clica em gerar — o motor lê
  disco em vez de reconsultar o banco, que leva minutos.

  O cron NÃO gera o .xlsx. O relatório final é decisão de quem clica: depende
  dos documentos, semestres e abas que a pessoa escolhe na tela. Produzir um
  arquivo de 74 MB toda madrugada, que ninguém pediu e que provavelmente não
  bate com os filtros que a pessoa vai querer, é trabalho jogado fora — e é
  scraping desnecessário contra o ScriptCase.

  Por isso o modo padrão deste comando é `--somente-parquets` (implícito): ele
  chama `extrator.atualizar_cache_parquets()` e para por aí. Segundos ou poucos
  minutos, sem Playwright, sem banco de processos, sem Excel.

  A flag `--completo` roda o pipeline inteiro (extração no site, consolidação e
  relatório). É o que a opção 7 do portal.sh usa, quando alguém pede o robô
  completo de propósito, na mão.

POR QUE ESTE ARQUIVO EXISTE
  Até 18/08/2026 o cron acionava o robô "digitando" no menu do portal.sh
  (`echo -e '7\\n\\n0\\n' | bash portal.sh`), e isso trouxe dois defeitos:

    1. A opção 7 montava um .tmp_robot.py que chamava `extrator.executar()` SEM
       `processo_id`. Como `atualizar_cache_parquets()` roda ANTES dessa
       validação, os Parquet até saíam todo dia — mas o processo morria logo
       depois com `ValueError: O processo_id é obrigatório.`, terminando sempre
       em erro e deixando o log com cara de rotina quebrada.
    2. Como quem rodava era uma interface de terminal, o log recebia o banner
       ASCII, o menu inteiro (duas vezes: na entrada e no "Pressione [ENTER]"),
       códigos ANSI e `TERM environment variable not set.`.

  Aqui não há TUI: uma linha por etapa no stdout, e a saída integral no arquivo
  `cron/detalhado_<data>.log` para quando for preciso investigar.
"""
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA
from apps.automacoes.analise_ia.services import extrator
from portal_ggci.processos import popen_com_limite

# ==============================================================================
# CONFIGURAÇÃO DO MODO --completo
# ==============================================================================
# Espelha o que a tela (templates/analise_ia/index.html) envia quando alguém
# abre a página e clica em processar sem mexer em nada: o initAnaliseIA() clica
# em cada "SELECIONAR TODOS", marcando todos os semestres dos 5 documentos; os
# semestres dos relatórios gerenciais ficam como o HTML os deixa. Os períodos
# impossíveis (RIAF antes de 2026, ano futuro, 2º semestre antes de julho) são
# descartados pelo próprio extrator.
PAYLOAD_PIPELINE_COMPLETO = {
    "documentos": ["CONTRATOS", "RIAF", "BENEFICIOS", "FINANCIAMENTO", "HISTORICO"],
    "periodos_por_doc": {
        "CONTRATOS":     ["2025-1", "2025-2", "2026-1", "2026-2"],
        "RIAF":          ["2026-1", "2026-2", "2027-1", "2027-2"],
        "BENEFICIOS":    ["2025-1", "2025-2", "2026-1", "2026-2"],
        "FINANCIAMENTO": ["2025-1", "2025-2", "2026-1", "2026-2"],
        "HISTORICO":     ["2025-1", "2025-2", "2026-1", "2026-2"],
    },
    "sems_riaf": ["2026-1"],
    "sems_contratos": ["2025-1", "2025-2"],
    "formato": "EXCEL",
    "gerar_relatorio": True,
    "gerar_relatorio_riaf": True,
    "gerar_quantitativo": True,
    "gerar_pagamentos": True,
    "processados_hoje": [],
    # O cron nunca faz atualização bruta: ele roda todo dia e o filtro de pendentes é o que
    # mantém a execução curta. Rebaixar o semestre inteiro é ação manual, feita na tela.
    "atualizacao_bruta": [],
}

# Todas as categorias, para o cache cobrir as 16 tabelas do mapa do extrator.
DOCS_PARA_CACHE = ["CONTRATOS", "RIAF", "BENEFICIOS", "FINANCIAMENTO", "HISTORICO"]

PASTA_CRON = os.path.join(settings.BASE_DIR, "apps", "automacoes", "analise_ia", "cron")
PASTA_PARQUETS = os.path.join(settings.BASE_DIR, "apps", "automacoes", "analise_ia", "dados", "tabelas_sql")
ARQUIVO_LOCK = os.path.join(PASTA_CRON, "analise_ia.lock")
ARQUIVO_SELO = os.path.join(PASTA_CRON, "ultima_execucao.json")
MAX_LOGS_DETALHADOS = 7

# Teto do modo parquets. As consultas do SIBU levam minutos; duas horas é folga
# larga. O objetivo não é interromper consulta lenta, é impedir que uma conexão
# pendurada vire processo fantasma — o mesmo problema que portal_ggci/processos.py
# descreve (um loop_polichat sobreviveu 4 dias consumindo um núcleo inteiro).
TETO_SEGUNDOS_PARQUETS = 2 * 60 * 60

# Carimbo que o LogCapture do executar_motor_ia coloca no início de cada linha.
PREFIXO_TIMESTAMP = re.compile(r"^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\] ")


def _duracao(segundos):
    """Formata segundos como 42s / 7m13s / 1h05m — sem casas decimais inúteis."""
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m{segundos % 60:02d}s"
    return f"{segundos // 3600}h{(segundos % 3600) // 60:02d}m"


def _plural(quantidade, singular, plural):
    """Evita o "1 tabelas" — o resumo é lido por gente todo dia, não por parser."""
    return f"{quantidade} {singular if quantidade == 1 else plural}"


class PrazoEstourado(Exception):
    """O modo parquets passou do teto de tempo — provavelmente conexão pendurada."""


class SaidaDuplicada:
    """
    O QUE FAZ: Substitui o sys.stdout enquanto o cache roda.
    POR QUÊ EXISTE: os prints do extrator são a única fonte de verdade sobre o
    que aconteceu com cada tabela. Precisam ir INTEIROS para o arquivo detalhado
    e, ao mesmo tempo, alimentar os contadores que viram a linha do resumo.
    """

    def __init__(self, destino):
        self.destino = destino
        self.atualizadas = 0
        self.ja_eram_de_hoje = 0
        self.falhas = 0
        self.esperas = 0

    def write(self, texto):
        self.destino.write(texto)
        if "Parquet salvo:" in texto:
            self.atualizadas += 1
        elif "já possui Parquet válido de hoje" in texto:
            self.ja_eram_de_hoje += 1
        elif "Erro ao processar tabela" in texto or "Erro grave no Cache Manager" in texto:
            self.falhas += 1
        elif "Aguardando outro processo extrair" in texto:
            self.esperas += 1
        return len(texto)

    def flush(self):
        self.destino.flush()


class Command(BaseCommand):
    help = "Atualiza o cache Parquet do Análise IA (padrão) ou roda o pipeline completo (--completo)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--completo",
            action="store_true",
            help="Roda o pipeline inteiro (extração no site + consolidação + relatório .xlsx). "
                 "Sem esta flag, só atualiza os Parquet — que é o que o cron precisa.",
        )
        parser.add_argument(
            "--uma-vez-por-dia",
            action="store_true",
            help="Sai sem fazer nada se o ciclo de hoje JÁ concluiu com sucesso. É como o cron chama.",
        )

    # --------------------------------------------------------------------------
    # SAÍDA RESUMIDA
    # --------------------------------------------------------------------------
    def _linha(self, rotulo, texto):
        """Emite uma linha do resumo. Rótulo com largura fixa para o log alinhar."""
        agora = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
        sys.__stdout__.write(f"[{agora}] {rotulo.ljust(10)} {texto}\n")
        sys.__stdout__.flush()

    # --------------------------------------------------------------------------
    # TRAVA CONTRA EXECUÇÃO SOBREPOSTA
    # --------------------------------------------------------------------------
    # O cron dispara às 00:01 e também no @reboot — uma queda de energia na
    # madrugada faria dois ciclos concorrerem pelas mesmas consultas pesadas.
    def _lock_ativo(self):
        if not os.path.exists(ARQUIVO_LOCK):
            return None
        try:
            with open(ARQUIVO_LOCK) as arquivo:
                pid = int(arquivo.read().strip())
            os.kill(pid, 0)  # Não mata: só pergunta ao SO se o processo existe.
            return pid
        except (ValueError, OSError):
            try:
                os.remove(ARQUIVO_LOCK)  # Lock órfão: o dono morreu sem limpar.
            except OSError:
                pass
            return None

    def _criar_lock(self):
        with open(ARQUIVO_LOCK, "w") as arquivo:
            arquivo.write(str(os.getpid()))

    def _remover_lock(self):
        try:
            os.remove(ARQUIVO_LOCK)
        except OSError:
            pass

    # --------------------------------------------------------------------------
    # SELO DE CONCLUSÃO
    # --------------------------------------------------------------------------
    # Quem decide se o ciclo de hoje já rodou é o RESULTADO gravado aqui, e não a
    # intenção de disparar. O start_server.py antigo marcava "IA feita hoje" logo
    # após o Popen: uma falha instantânea contava como sucesso.
    def _ler_selo(self):
        try:
            with open(ARQUIVO_SELO) as arquivo:
                return json.load(arquivo)
        except (OSError, ValueError):
            return {}

    def _gravar_selo(self, dados):
        try:
            with open(ARQUIVO_SELO, "w") as arquivo:
                json.dump(dados, arquivo, indent=4, ensure_ascii=False)
        except OSError:
            pass

    def _rotacionar_detalhados(self):
        try:
            arquivos = sorted(
                os.path.join(PASTA_CRON, nome)
                for nome in os.listdir(PASTA_CRON)
                if nome.startswith("detalhado_") and nome.endswith(".log")
            )
            for antigo in arquivos[:-MAX_LOGS_DETALHADOS]:
                os.remove(antigo)
        except OSError:
            pass

    # --------------------------------------------------------------------------
    # EXECUÇÃO
    # --------------------------------------------------------------------------
    def handle(self, *args, **options):
        os.makedirs(PASTA_CRON, exist_ok=True)

        # O nome da pasta distingue os dois ambientes que rodam o mesmo cron.
        ambiente = "prod" if str(settings.BASE_DIR).rstrip("/").endswith("-prod") else "dev"
        modo = "completo" if options["completo"] else "parquets"
        hoje = datetime.date.today().isoformat()

        if options["uma_vez_por_dia"]:
            selo = self._ler_selo()
            if selo.get("data") == hoje and selo.get("status") == "CONCLUIDO" and selo.get("modo") == modo:
                self._linha("PULADO", f"{ambiente} · ciclo {modo} de hoje já concluiu")
                return

        pid_ativo = self._lock_ativo()
        if pid_ativo:
            self._linha("PULADO", f"{ambiente} · já existe um ciclo em andamento (PID {pid_ativo})")
            return

        arquivo_detalhado = os.path.join(PASTA_CRON, f"detalhado_{hoje}.log")
        self._rotacionar_detalhados()

        self._criar_lock()
        inicio = time.time()
        try:
            if options["completo"]:
                selo_extra = self._modo_completo(ambiente, arquivo_detalhado)
            else:
                selo_extra = self._modo_parquets(ambiente, arquivo_detalhado)
        finally:
            self._remover_lock()

        total = time.time() - inicio
        try:
            linhas = sum(1 for _ in open(arquivo_detalhado, encoding="utf-8", errors="ignore"))
        except OSError:
            linhas = 0

        relativo = os.path.relpath(arquivo_detalhado, settings.BASE_DIR)
        if relativo.startswith(".."):
            relativo = arquivo_detalhado
        self._linha("DETALHE", f"{relativo} ({linhas} linhas)")

        self._gravar_selo({
            "data": hoje,
            "modo": modo,
            "status": selo_extra["status"],
            "duracao_segundos": int(total),
            "encerrado_em": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            **selo_extra["detalhes"],
        })

        if selo_extra["status"] != "CONCLUIDO":
            sys.exit(1)

    # --------------------------------------------------------------------------
    # MODO PADRÃO: SÓ OS PARQUET
    # --------------------------------------------------------------------------
    def _modo_parquets(self, ambiente, arquivo_detalhado):
        """
        Chama `atualizar_cache_parquets` no próprio processo — não há motivo para
        subprocesso aqui: não tem Playwright, não tem registro no banco, e a
        função já pula sozinha toda tabela cujo Parquet é de hoje.
        """
        self._linha("INICIO", f"{ambiente} · atualização do cache Parquet (sem relatório)")

        # buffering=1 (linha a linha): sem isso o Python segura a saída até
        # encher ~8KB, e um ciclo morto por kill ou pelo teto de tempo levaria
        # junto exatamente o material de que se precisa para saber por que morreu.
        with open(arquivo_detalhado, "a", encoding="utf-8", buffering=1) as detalhado:
            detalhado.write(f"\n{'=' * 78}\nCACHE PARQUET — {timezone.localtime():%d/%m/%Y %H:%M:%S}\n{'=' * 78}\n")

            espiao = SaidaDuplicada(detalhado)
            original = sys.stdout
            sys.stdout = espiao

            erro = None
            anterior = signal.signal(signal.SIGALRM, self._estourar_prazo)
            signal.alarm(TETO_SEGUNDOS_PARQUETS)
            try:
                extrator.atualizar_cache_parquets(DOCS_PARA_CACHE)
            except PrazoEstourado:
                erro = f"teto de {_duracao(TETO_SEGUNDOS_PARQUETS)} estourado — conexão com o SIBU pendurada?"
            except Exception as excecao:  # noqa: BLE001 — o motivo vai para o resumo e o traceback para o detalhado
                import traceback
                traceback.print_exc(file=detalhado)
                erro = f"{type(excecao).__name__}: {excecao}"[:300]
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, anterior)
                sys.stdout = original

        total_tabelas = espiao.atualizadas + espiao.ja_eram_de_hoje
        detalhe = (
            f"{_plural(espiao.atualizadas, 'tabela atualizada', 'tabelas atualizadas')}"
            f" · {espiao.ja_eram_de_hoje} já eram de hoje"
            f" · {_plural(espiao.falhas, 'falha', 'falhas')}"
        )
        if espiao.esperas:
            detalhe += f" · {espiao.esperas} em espera de lock"
        self._linha("PARQUETS", detalhe)

        if erro:
            self._linha("FALHA", erro)
            return {"status": "FALHA", "detalhes": {"motivo": erro, "tabelas_atualizadas": espiao.atualizadas}}

        # Uma tabela que falhou deixa o cache do dia incompleto: quem clicar em
        # gerar vai reconsultar o SIBU e esperar. Isso é falha, não detalhe.
        if espiao.falhas:
            self._linha("FALHA", f"{_plural(espiao.falhas, 'tabela ficou', 'tabelas ficaram')} sem Parquet de hoje")
            return {"status": "FALHA", "detalhes": {"tabelas_com_falha": espiao.falhas}}

        self._linha("CONCLUIDO", f"{total_tabelas} tabelas com Parquet de hoje · {self._tamanho_do_cache()}")
        return {"status": "CONCLUIDO", "detalhes": {
            "tabelas_atualizadas": espiao.atualizadas,
            "tabelas_ja_validas": espiao.ja_eram_de_hoje,
        }}

    def _estourar_prazo(self, *_):
        raise PrazoEstourado()

    def _tamanho_do_cache(self):
        """Tamanho total dos Parquet — sinal barato de que o cache não veio vazio."""
        try:
            total = sum(
                os.path.getsize(os.path.join(PASTA_PARQUETS, nome))
                for nome in os.listdir(PASTA_PARQUETS)
                if nome.endswith(".parquet")
            )
            return f"{total / (1024 * 1024):.1f} MB em disco"
        except OSError:
            return "tamanho indisponível"

    # --------------------------------------------------------------------------
    # MODO --completo: PIPELINE INTEIRO (opção 7 do portal.sh)
    # --------------------------------------------------------------------------
    def _modo_completo(self, ambiente, arquivo_detalhado):
        processo = ProcessamentoAnaliseIA.objects.create(
            status="PENDENTE",
            configuracoes=PAYLOAD_PIPELINE_COMPLETO,
        )
        docs = PAYLOAD_PIPELINE_COMPLETO["documentos"]
        self._linha("INICIO", f"{ambiente} · pipeline completo · processo #{processo.id} · {len(docs)} documentos")

        resultado = self._rodar_motor(processo.id, arquivo_detalhado)
        processo.refresh_from_db()

        if resultado["codigo"] == 0 and processo.status == "CONCLUIDO":
            saida = processo.arquivo_resultado or "(sem arquivo)"
            self._linha("CONCLUIDO", os.path.basename(saida))
            return {"status": "CONCLUIDO", "detalhes": {
                "processo_id": processo.id,
                "arquivo": processo.arquivo_resultado,
            }}

        if resultado["codigo"] == 124:
            # 124 é como o `timeout` do coreutils sinaliza morte por prazo —
            # ver portal_ggci/processos.py.
            motivo = "prazo máximo de execução estourado (24h) — o motor foi encerrado"
        else:
            motivo = resultado["erro"] or f"processo terminou como {processo.status} (código {resultado['codigo']})"

        self._linha("FALHA", f"etapa {resultado['etapa']} · {motivo}")
        return {"status": "FALHA", "detalhes": {
            "processo_id": processo.id,
            "etapa": resultado["etapa"],
            "motivo": motivo,
        }}

    def _rodar_motor(self, processo_id, arquivo_detalhado):
        """
        Dispara o `executar_motor_ia` e traduz a saída dele em resumo. Subprocesso
        para manter o motor intacto — o LogCapture dele continua alimentando o
        banco, que é de onde a tela web lê o progresso.
        """
        comando = [sys.executable, "-u", "manage.py", "executar_motor_ia", str(processo_id)]

        estado = {
            "etapa": "EXTRACAO",
            "inicio_etapa": time.time(),
            "cache": 0,
            "downloads": 0,
            "avisos": 0,
            "planilhas": 0,
            "arquivos_extraidos": None,
            "erro": None,
            "capturando_traceback": False,
        }

        with open(arquivo_detalhado, "a", encoding="utf-8", buffering=1) as detalhado:
            detalhado.write(f"\n{'=' * 78}\nPIPELINE COMPLETO processo #{processo_id} — {timezone.localtime():%d/%m/%Y %H:%M:%S}\n{'=' * 78}\n")

            filho = popen_com_limite(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                errors="replace",
            )
            for linha in filho.stdout:
                detalhado.write(linha)
                self._interpretar(linha, estado)
            filho.stdout.close()
            codigo = filho.wait()

        return {"codigo": codigo, "etapa": estado["etapa"], "erro": estado["erro"]}

    def _interpretar(self, linha_bruta, estado):
        """
        Traduz uma linha bruta do motor em contadores e marcos de etapa.

        Os gatilhos são as mensagens reais de extrator/consolidador/ggci — se
        alguma mudar de texto, o resumo perde a linha, mas o ciclo continua
        rodando e o detalhado guarda tudo. O teste test_cron_resumo.py trava isso.
        """
        # O carimbo de timestamp precisa sair antes da análise, senão a
        # indentação do traceback some e a heurística que acha a exceção falha.
        linha = PREFIXO_TIMESTAMP.sub("", linha_bruta)

        if "Parquet salvo:" in linha:
            estado["cache"] += 1
        elif "Download concluído" in linha:
            estado["downloads"] += 1
        elif "[CONSOLIDAR | PLANILHA" in linha:
            estado["planilhas"] += 1

        if "⚠️" in linha:
            estado["avisos"] += 1

        if "🎉 Extração concluída" in linha or "EXTRAÇÃO VAZIA" in linha:
            achado = re.search(r"Extração concluída:\s*(\d+)", linha)
            estado["arquivos_extraidos"] = int(achado.group(1)) if achado else 0
            duracao = time.time() - estado["inicio_etapa"]
            self._linha("EXTRACAO", (
                f"{_plural(estado['cache'], 'tabela', 'tabelas')} em cache"
                f" · {_plural(estado['arquivos_extraidos'], 'arquivo', 'arquivos')}"
                f" · {_plural(estado['avisos'], 'aviso', 'avisos')}"
                f" · {_duracao(duracao)}"
            ))
            estado.update(etapa="CONSOLIDACAO", inicio_etapa=time.time(), avisos=0)

        elif "🎉 Consolidação concluída" in linha:
            duracao = time.time() - estado["inicio_etapa"]
            self._linha("CONSOLIDA", f"{_plural(estado['planilhas'], 'planilha', 'planilhas')} · {_duracao(duracao)}")
            estado.update(etapa="GGCI", inicio_etapa=time.time(), avisos=0)

        elif "🎉 Regras aplicadas" in linha:
            duracao = time.time() - estado["inicio_etapa"]
            self._linha("GGCI", f"relatório gerado · {_duracao(duracao)}")
            estado.update(etapa="FINALIZACAO", inicio_etapa=time.time())

        elif "RELATÓRIO │ BLOQUEADO" in linha:
            self._linha("AVISO", linha.split("│")[-1].strip())

        elif "🛑" in linha:
            estado["erro"] = linha.split("🛑")[-1].strip()

        if "FALHA CRÍTICA" in linha:
            estado["capturando_traceback"] = True
        elif estado["capturando_traceback"] and linha.strip() and not linha.startswith((" ", "\t")):
            texto = linha.strip()
            if not texto.startswith("Traceback"):
                estado["erro"] = texto[:300]
