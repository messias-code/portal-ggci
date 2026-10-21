"""
=== ARQUIVO: apps/sugestoes/controle_acesso/management/commands/executar_controle_acesso.py ===
Propósito: Rotina de background do botão "Atualizar" do Controle de Acesso.
Dependências: django.core.management, fcntl, threading.

Uma etapa só: `extrator.atualizar_parquets`, que materializa as tabelas `PY_ggci_*_controle_acesso` no
SIBU, grava os Parquets e apaga as tabelas. A ficha é montada na hora da consulta, a partir
desses Parquets — não há relatório para gerar depois.

O desenho segue o `executar_doc_ia`: trava de execução única por `flock`, log e progresso
gravados no registro a cada ~0,8 s, barra movida pelo marcador `[ETL_PROGRESSO] n/total`.
"""
import fcntl
import os
import re
import sys
import threading
import time
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.sugestoes.controle_acesso.models import ProcessamentoControleAcesso
from apps.sugestoes.controle_acesso.services import extrator, scraping

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# flock e não arquivo-sentinela: o kernel libera a trava se o processo morrer (kill -9,
# reboot), sem heurística de idade. A trava é do MOTOR: duas execuções disputariam as
# mesmas tabelas temporárias no SIBU, mesmo com registros diferentes.
CAMINHO_TRAVA = os.path.join(
    settings.BASE_DIR, "apps", "sugestoes", "controle_acesso", "dados", ".execucao.lock"
)

# A barra anda pelo ETL de 3% a 98%, uma fatia por tabela concluída.
FAIXA_ETL = (3, 98)


def adquirir_trava_de_execucao():
    """O arquivo travado (precisa ficar vivo durante a execução) ou None se já há outro ciclo."""
    os.makedirs(os.path.dirname(CAMINHO_TRAVA), exist_ok=True)
    arquivo = open(CAMINHO_TRAVA, "w")
    try:
        fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        arquivo.close()
        return None
    arquivo.write(f"{os.getpid()}\n")
    arquivo.flush()
    return arquivo


def _progresso_do_etl(texto):
    """Último `[ETL_PROGRESSO] n/total` do texto, projetado em FAIXA_ETL; None sem marcador."""
    achados = re.findall(r"\[ETL_PROGRESSO\]\s*(\d+)/(\d+)", texto)
    if not achados:
        return None
    feitas, total = (int(x) for x in achados[-1])
    if total <= 0:
        return None
    inicio, fim = FAIXA_ETL
    return int(inicio + (fim - inicio) * min(feitas / total, 1.0))


class LogCapture:
    """
    Desvia o stdout do motor para o registro no banco, que é o que a tela lê.
    Grava no máximo a cada ~0,8 s (ou na hora, em marcos de fim/erro) e carimba a hora em
    cada linha do terminal.
    """

    def __init__(self, original, proc):
        self.original = original
        self.proc = proc
        self.lock = threading.Lock()
        self.buffer = ""
        self.last_save = time.time()
        self.needs_timestamp = True

    def write(self, message):
        with self.lock:
            for chunk in message.splitlines(True):
                if self.needs_timestamp and chunk != "\n":
                    self.original.write(f"[{timezone.localtime():%d/%m/%Y %H:%M:%S}] ")
                self.original.write(chunk)
                self.needs_timestamp = chunk.endswith("\n")

            self.buffer += message
            agora = time.time()
            if agora - self.last_save > 0.8 or any(x in message for x in ("🎉", "❌", "🛑")):
                self.descarregar()
                self.last_save = agora

    def descarregar(self):
        """Grava o que está no buffer e avança a barra, sem passar de 99 (100 é do fim)."""
        if not self.buffer:
            return
        self.proc.refresh_from_db(fields=["log", "progresso"])
        progresso = self.proc.progresso
        medido = _progresso_do_etl(self.buffer)
        if medido is not None:
            progresso = max(progresso, medido)
        self.proc.progresso = min(progresso, 99)
        self.proc.log += self.buffer
        self.proc.save(update_fields=["log", "progresso"])
        self.buffer = ""

    def flush(self):
        self.original.flush()


class Command(BaseCommand):
    help = "Traz do SIBU os dados da ficha do Controle de Acesso (roda em background)"

    def add_arguments(self, parser):
        # A flag vem ANTES do id na linha de comando: o Parar mata pelo id no fim dela.
        parser.add_argument('--bruta', action='store_true',
                            help='Ignora o cache do dia e lê do site os envios de documentos')
        parser.add_argument('processo_id', type=int)

    def handle(self, *args, **options):
        processo_id = options['processo_id']
        try:
            proc = ProcessamentoControleAcesso.objects.get(id=processo_id)
        except ProcessamentoControleAcesso.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Processo {processo_id} não encontrado."))
            return

        # A trava vem antes de qualquer escrita: o passo seguinte zera o log, e uma
        # execução recusada não pode apagar o log da que está no ar.
        trava = adquirir_trava_de_execucao()
        if trava is None:
            recado = ("🛑 Já existe uma atualização do Controle de Acesso em andamento. "
                      "Esta execução foi recusada para não disputar as tabelas temporárias do SIBU.")
            # Só carimba o registro desta tentativa (PENDENTE); um EXTRAINDO ou CONCLUIDO
            # pertence a outra execução e não pode ser sobrescrito.
            if proc.status == "PENDENTE":
                proc.status = "FALHA"
                proc.log = recado
                proc.data_fim = timezone.now()
                proc.save(update_fields=["status", "log", "data_fim"])
            self.stdout.write(self.style.WARNING(recado))
            return

        proc.log = ""
        proc.progresso = 0
        proc.data_fim = None
        proc.save(update_fields=["log", "progresso", "data_fim"])

        original_stdout = sys.stdout
        captura = LogCapture(sys.stdout, proc)
        sys.stdout = captura

        try:
            inicio = time.time()
            proc.status = "EXTRAINDO"
            proc.progresso = 2
            proc.save(update_fields=["status", "progresso"])
            bruta = options['bruta']
            total = len(extrator.TABELAS)
            if bruta:
                total += len(scraping.semestres_recentes()) * len(scraping.DOC_ID_DA_CATEGORIA)
                print("🔁 Atualização BRUTA: banco consultado de novo e envios de documentos lidos do site.")
            print("🚀 Iniciando extração do SIBU...")

            falhas = extrator.atualizar_parquets(forcar=bruta, total_etapas=total)
            if bruta:
                print("\n🌐 Lendo do site os documentos enviados...")
                falhas += scraping.atualizar_documentos_site(
                    processo_id, ja_feitas=len(extrator.TABELAS), total_etapas=total)
            if falhas:
                # Tabela que falhou mantém o Parquet anterior em disco: a tela segue com o
                # último dado bom daquela parte, mas a execução não pode se dizer concluída.
                raise RuntimeError(f"Falha ao atualizar: {', '.join(falhas)}.")

            duracao = time.time() - inicio
            print(f"\n📁 Dados disponíveis em: {extrator.PASTA_PARQUETS}")
            print(f"\n🎉 Processamento concluído em {int(duracao // 60)}m e {int(duracao % 60)}s!")

            captura.descarregar()
            proc.refresh_from_db(fields=["log"])
            proc.status = "CONCLUIDO"
            proc.progresso = 100
            proc.data_fim = timezone.now()
            proc.save()
        except Exception:
            print(f"\n❌ FALHA CRÍTICA:\n{traceback.format_exc()}")
            captura.descarregar()
            proc.refresh_from_db(fields=["log"])
            proc.status = "FALHA"
            proc.data_fim = timezone.now()
            proc.save()
        finally:
            sys.stdout = original_stdout
            trava.close()
