"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/management/commands/cron_documentos_ia.py ===
Propósito: Entrada NÃO-INTERATIVA do ciclo diário do Documentos IA (cron).
Autor: N/A
Dependências: django.core.management, subprocess, portal_ggci.processos

POR QUE ESTE COMANDO EXISTE
  O peso da atualização não está em montar os Parquets de saída (26 segundos),
  e sim em materializar os 16 espelhos `PY_ggci_*` no SIBU. Medido em 18/08/2026:
  6m20s no total, dos quais ~5 minutos foram só as consultas ao banco — a de
  beneficiários levou 66s e a de pagamentos 64s.

  Esses espelhos são cache diário: `atualizar_cache_parquets` pula a consulta se
  o Parquet local já tem data de hoje. Ou seja, quem paga os 5 minutos é a
  PRIMEIRA execução do dia; as seguintes leem do disco. Sem este cron, quem paga
  é o primeiro funcionário que abre o dashboard de manhã e clica em "Atualizar".

  Com ele, o ciclo roda de madrugada e o botão responde rápido o dia inteiro.

COMO FUNCIONA
  Mesmo caminho que a tela web usa — cria um registro `ProcessamentoDocIA` e
  delega ao `executar_doc_ia` —, só que sem navegador. Lê a saída do motor linha
  a linha e a divide em dois destinos:

    • stdout  → resumo: uma linha por etapa, com contadores e duração.
    • arquivo → `cron/detalhado_<data>.log`: a saída integral, para depurar.

  É o mesmo desenho do `cron_analise_ia`, com uma diferença importante: aquele
  monta um payload com documentos, períodos e flags, porque a tela do Análise IA
  tem filtros. Aqui não há payload — o escopo é fixo e mora em `executar_doc_ia`.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA
from portal_ggci.processos import popen_com_limite

PASTA_CRON = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia", "cron")
ARQUIVO_LOCK = os.path.join(PASTA_CRON, "documentos_ia.lock")
ARQUIVO_SELO = os.path.join(PASTA_CRON, "ultima_execucao.json")
MAX_LOGS_DETALHADOS = 7

# Carimbo que o LogCapture do executar_doc_ia coloca no início de cada linha.
PREFIXO_TIMESTAMP = re.compile(r"^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\] ")


def _duracao(segundos):
    """Formata uma duração em segundos como '42s', '3m07s' ou '1h05m'."""
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m{segundos % 60:02d}s"
    return f"{segundos // 3600}h{(segundos % 3600) // 60:02d}m"


def _plural(quantidade, singular, plural):
    """'1 tabela' / '3 tabelas' — evita o '1 tabelas' no log."""
    return f"{quantidade} {singular if quantidade == 1 else plural}"


class Command(BaseCommand):
    help = "Executa o ciclo diário do Documentos IA sem interface, com log resumido."

    def add_arguments(self, parser):
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
        sys.stdout.write(f"[{agora}] {rotulo.ljust(10)} {texto}\n")
        sys.stdout.flush()

    # --------------------------------------------------------------------------
    # TRAVA CONTRA EXECUÇÃO SOBREPOSTA
    # --------------------------------------------------------------------------
    # O cron dispara às 00:01 e também no @reboot — uma queda de energia na
    # madrugada faria duas extrações concorrerem pelas mesmas pastas de
    # processamento e pelo mesmo ScriptCase.
    def _lock_ativo(self):
        if not os.path.exists(ARQUIVO_LOCK):
            return None
        try:
            with open(ARQUIVO_LOCK) as arquivo:
                pid = int(arquivo.read().strip())
            os.kill(pid, 0)  # Não mata: só pergunta ao SO se o processo existe.
            return pid
        except (ValueError, OSError):
            # Lock órfão (processo morreu sem limpar) — some com ele e segue.
            try:
                os.remove(ARQUIVO_LOCK)
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
    # Quem decide se o ciclo de hoje já rodou é o RESULTADO gravado aqui, não a
    # intenção de disparar: uma falha instantânea não pode ser registrada como
    # sucesso, senão o dia inteiro fica sem atualização.
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

    # --------------------------------------------------------------------------
    # ROTAÇÃO DO LOG DETALHADO
    # --------------------------------------------------------------------------
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

        # O nome da pasta é o que distingue os dois ambientes que rodam o mesmo
        # cron em paralelo (portal-ggci-prod e portal-ggci-dev).
        ambiente = "prod" if str(settings.BASE_DIR).rstrip("/").endswith("-prod") else "dev"
        hoje = datetime.date.today().isoformat()

        if options["uma_vez_por_dia"]:
            selo = self._ler_selo()
            if selo.get("data") == hoje and selo.get("status") == "CONCLUIDO":
                self._linha("PULADO", f"{ambiente} · ciclo de hoje já concluiu (processo #{selo.get('processo_id')})")
                return

        pid_ativo = self._lock_ativo()
        if pid_ativo:
            self._linha("PULADO", f"{ambiente} · já existe um ciclo em andamento (PID {pid_ativo})")
            return

        arquivo_detalhado = os.path.join(PASTA_CRON, f"detalhado_{hoje}.log")
        self._rotacionar_detalhados()

        processo = ProcessamentoDocIA.objects.create(
            usuario_solicitante="cron",
            status="PENDENTE",
            log="Iniciando processo...",
        )

        self._linha("INICIO", f"{ambiente} · processo #{processo.id} · saída em Parquet")

        self._criar_lock()
        inicio_global = time.time()
        try:
            resultado = self._rodar_motor(processo.id, arquivo_detalhado)
        finally:
            self._remover_lock()

        total = time.time() - inicio_global
        processo.refresh_from_db()

        try:
            linhas_detalhado = sum(1 for _ in open(arquivo_detalhado, encoding="utf-8", errors="ignore"))
        except OSError:
            linhas_detalhado = 0

        if resultado["codigo"] == 0 and processo.status == "CONCLUIDO":
            self._linha("CONCLUIDO", f"{_duracao(total)} · {_plural(resultado['abas'], 'aba gravada', 'abas gravadas')}")
            self._gravar_selo({
                "data": hoje,
                "status": "CONCLUIDO",
                "processo_id": processo.id,
                "abas": resultado["abas"],
                "duracao_segundos": int(total),
                "encerrado_em": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            })
        else:
            if resultado["codigo"] == 124:
                # 124 é o código com que o `timeout` do coreutils mata o filho —
                # ver portal_ggci/processos.py. Sem essa tradução a mensagem
                # ficaria um número solto, sem dizer que houve estouro de prazo.
                motivo = "prazo máximo de execução estourado (24h) — o motor foi encerrado"
            else:
                motivo = resultado["erro"] or f"processo terminou como {processo.status} (código {resultado['codigo']})"
            self._linha("FALHA", f"etapa {resultado['etapa']} · {motivo}")
            self._gravar_selo({
                "data": hoje,
                "status": "FALHA",
                "processo_id": processo.id,
                "etapa": resultado["etapa"],
                "motivo": motivo,
                "duracao_segundos": int(total),
                "encerrado_em": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            })

        # Caminho relativo ao projeto é mais legível no log; se por algum motivo
        # o arquivo cair fora do BASE_DIR, mostra o absoluto em vez de um "../..".
        relativo = os.path.relpath(arquivo_detalhado, settings.BASE_DIR)
        if relativo.startswith(".."):
            relativo = arquivo_detalhado
        self._linha("DETALHE", f"{relativo} ({linhas_detalhado} linhas)")

        if resultado["codigo"] != 0 or processo.status != "CONCLUIDO":
            sys.exit(1)

    def _rodar_motor(self, processo_id, arquivo_detalhado):
        """
        O QUE FAZ: Dispara o `executar_doc_ia` e traduz a saída dele em resumo.
        POR QUÊ SUBPROCESSO: mantém o motor intacto (o LogCapture dele continua
        alimentando o banco, que é o que a tela web lê no polling) e nos dá o
        stdout em pipe para filtrar, sem que este comando precise conhecer as
        etapas por dentro.
        """
        comando = [sys.executable, "-u", "manage.py", "executar_doc_ia", str(processo_id)]

        estado = {
            "etapa": "EXTRACAO",
            "inicio_etapa": time.time(),
            "materializadas": 0,
            "reaproveitadas": 0,
            "avisos": 0,
            "planilhas": 0,
            "abas": 0,
            "linhas_gravadas": 0,
            "arquivos_extraidos": None,
            "erro": None,
            "capturando_traceback": False,
        }

        with open(arquivo_detalhado, "a", encoding="utf-8") as detalhado:
            detalhado.write(f"\n{'=' * 78}\nCICLO processo #{processo_id} — {timezone.localtime():%d/%m/%Y %H:%M:%S}\n{'=' * 78}\n")
            detalhado.flush()

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

        return {
            "codigo": codigo,
            "etapa": estado["etapa"],
            "erro": estado["erro"],
            "abas": estado["abas"],
            "linhas": estado["linhas_gravadas"],
        }

    def _interpretar(self, linha_bruta, estado):
        """
        Traduz uma linha bruta do motor em contadores e marcos de etapa.

        Os gatilhos são as mensagens reais que extrator/consolidador/ggci
        imprimem — se alguma mudar de texto, o resumo perde a linha, mas o ciclo
        continua rodando e o detalhado guarda tudo. `tests/test_cron_resumo.py`
        trava esses textos para que a mudança quebre um teste antes de o cron
        voltar a ficar mudo.
        """
        # O LogCapture do motor carimba "[dd/mm/aaaa hh:mm:ss] " no começo de
        # cada linha. Tiramos o carimbo antes de analisar, senão a indentação do
        # traceback some e a heurística que acha a exceção deixa de funcionar.
        linha = PREFIXO_TIMESTAMP.sub("", linha_bruta)

        if "Parquet salvo:" in linha:
            estado["materializadas"] += 1
        elif "já possui Parquet válido de hoje" in linha:
            estado["reaproveitadas"] += 1
        elif "[CONSOLIDAR | PLANILHA" in linha:
            estado["planilhas"] += 1

        if "⚠️" in linha:
            estado["avisos"] += 1

        # --- Cada aba gravada na saída ---
        achado_aba = re.search(r"GRAVADO\s*\|\s*PARQUET\]\s*(.+?):\s*(\d+) linhas", linha)
        if achado_aba:
            estado["abas"] += 1
            estado["linhas_gravadas"] += int(achado_aba.group(2))

        # --- Fim da extração ---
        if "🎉 Extração concluída" in linha or "EXTRAÇÃO VAZIA" in linha:
            achado = re.search(r"Extração concluída:\s*(\d+)", linha)
            estado["arquivos_extraidos"] = int(achado.group(1)) if achado else 0
            duracao = time.time() - estado["inicio_etapa"]
            # Separar as duas contagens é o que torna o log útil: "16 do cache" diz
            # que o ciclo da madrugada funcionou e o dia vai ser rápido; "16 criadas"
            # diz que o cache não estava lá e alguém pagou os ~5 minutos de consulta.
            detalhe = (
                f"{estado['reaproveitadas']} tabelas do cache"
                f" · {_plural(estado['materializadas'], 'criada', 'criadas')}"
                f" · {_plural(estado['arquivos_extraidos'], 'arquivo', 'arquivos')}"
                f" · {_plural(estado['avisos'], 'aviso', 'avisos')}"
                f" · {_duracao(duracao)}"
            )
            self._linha("EXTRACAO", detalhe)
            estado.update(etapa="CONSOLIDACAO", inicio_etapa=time.time(), avisos=0)

        # --- Fim da consolidação ---
        elif "🎉 Consolidação concluída" in linha:
            duracao = time.time() - estado["inicio_etapa"]
            self._linha("CONSOLIDA", f"{_plural(estado['planilhas'], 'planilha', 'planilhas')} · {_duracao(duracao)}")
            estado.update(etapa="GGCI", inicio_etapa=time.time(), avisos=0)

        # --- Fim das regras de negócio ---
        elif "🎉 Regras aplicadas" in linha:
            duracao = time.time() - estado["inicio_etapa"]
            self._linha("GGCI", f"{_plural(estado['abas'], 'aba', 'abas')} · {estado['linhas_gravadas']:,} linhas · {_duracao(duracao)}".replace(",", "."))
            estado.update(etapa="FINALIZACAO", inicio_etapa=time.time())

        # --- Abortos limpos do próprio motor ---
        elif "🛑" in linha:
            estado["erro"] = linha.split("🛑")[-1].strip()

        # --- Falha crítica: a última linha do traceback é a exceção de verdade ---
        if "FALHA CRÍTICA" in linha:
            estado["capturando_traceback"] = True
        elif estado["capturando_traceback"] and linha.strip() and not linha.startswith((" ", "\t")):
            texto = linha.strip()
            if not texto.startswith("Traceback"):
                estado["erro"] = texto[:300]
