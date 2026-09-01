"""
==========================================================================
COMMAND: EXECUTAR PIPELINE POLICHAT
==========================================================================
Management command que executa a extração e tratamento de dados do Polichat
em background. Segue o mesmo padrão do executar_motor_ia.py
==========================================================================
"""

import traceback
import sys
import os
import signal
import threading
import time
from django.utils import timezone
from django.core.management.base import BaseCommand
from apps.dashboards.dash_polichat.models import ProcessamentoPolichat
from apps.dashboards.dash_polichat.services import polichat_extrator

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class LogCapture:
    """Captura os prints do pipeline e salva no banco em tempo real"""
    
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
                if self.needs_timestamp and chunk != '\n':
                    ts = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
                    self.original.write(f"[{ts}] ")
                self.original.write(chunk)
                self.needs_timestamp = chunk.endswith('\n')
                
            self.buffer += message
            agora = time.time()
            
            # Salva a cada 1s ou em mensagens importantes no BD
            if agora - self.last_save > 1.0 or any(e in message for e in ["✅", "🚀", "🎉", "❌", "🏆"]):
                self.proc.refresh_from_db(fields=['log', 'progresso'])
                
                novo_progresso = self.proc.progresso
                msg = str(self.buffer)
                
                # Atualiza progresso baseado nas mensagens
                if "Login em" in msg:
                    novo_progresso = max(novo_progresso, 10)
                elif "Iframe localizado" in msg:
                    novo_progresso = max(novo_progresso, 20)
                elif "Filtro de Data" in msg:
                    novo_progresso = max(novo_progresso, 25)
                elif "Aguardando Metabase" in msg:
                    novo_progresso = max(novo_progresso, 30)
                elif "Localizando tabela" in msg:
                    novo_progresso = max(novo_progresso, 40)
                elif "Aguardando download" in msg:
                    novo_progresso = max(novo_progresso, 45)
                elif "DOWNLOAD CONCLUÍDO" in msg:
                    novo_progresso = max(novo_progresso, 55)
                elif "Mesclando dados" in msg or "Base histórica" in msg:
                    novo_progresso = max(novo_progresso, 60)
                elif "Limpando e formatando telefones" in msg:
                    novo_progresso = max(novo_progresso, 70)
                elif "Processando datas e fusos horários" in msg:
                    novo_progresso = max(novo_progresso, 80)
                elif "Calculando tempos de jornada" in msg:
                    novo_progresso = max(novo_progresso, 90)
                elif "SUCESSO" in msg:
                    novo_progresso = max(novo_progresso, 99)
                
                if novo_progresso > 99:
                    novo_progresso = 99
                    
                self.proc.progresso = novo_progresso
                self.proc.log += self.buffer
                self.proc.save(update_fields=['log', 'progresso'])
                
                self.buffer = ""
                self.last_save = agora

    def flush(self):
        self.original.flush()

class Command(BaseCommand):
    help = 'Executa o pipeline de extração e tratamento de dados do Polichat'

    def add_arguments(self, parser):
        parser.add_argument('processo_id', type=int)

    def handle(self, *args, **options):
        processo_id = options['processo_id']

        # ── SIGTERM vira exceção ──────────────────────────────────────────
        # O processo é lançado com prazo de 24h (portal_ggci/processos.py), e
        # o `timeout` encerra mandando SIGTERM. Só que o Python NÃO transforma
        # sinal em exceção por padrão: o interpretador simplesmente morre, o
        # `except` mais abaixo nunca roda e o registro fica preso em
        # "EXTRAINDO" para sempre — exatamente o estado inconsistente que este
        # trabalho veio corrigir.
        #
        # O handler abaixo levanta uma exceção comum (herdando de Exception, e
        # não de BaseException) justamente para ser capturada pelo `except
        # Exception` do bloco principal, que marca FALHA e grava o traceback.
        # Se fosse SystemExit ou KeyboardInterrupt, passaria direto.
        def _ao_receber_sigterm(signum, frame):
            raise RuntimeError(
                'Processo encerrado por exceder o tempo limite de execução '
                '(SIGTERM recebido do supervisor de prazo).'
            )

        signal.signal(signal.SIGTERM, _ao_receber_sigterm)

        try:
            proc = ProcessamentoPolichat.objects.get(id=processo_id)
        except ProcessamentoPolichat.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Processo {processo_id} não encontrado.'))
            return

        original_stdout = sys.stdout
        sys.stdout = LogCapture(sys.stdout, proc)

        def registrar_log(mensagem):
            print(mensagem)

        try:
            tempo_inicio = time.time()
            usuario = proc.usuario_solicitante or "Desconhecido"
            
            # --- FASE 1: EXTRAÇÃO ---
            proc.status = 'EXTRAINDO'
            proc.progresso = 5
            proc.save(update_fields=['status', 'progresso'])
            
            registrar_log(f"=======================================================")
            registrar_log(f"🚀 INICIANDO PIPELINE POLICHAT | ID: {processo_id}")
            registrar_log(f"👤 USUÁRIO: {usuario}")
            registrar_log(f"=======================================================")

            import datetime
            hoje_str = datetime.date.today().strftime("%Y-%m-%d")
            arquivo_controle = os.path.join(polichat_extrator.DOWNLOAD_PATH, "ultimo_anual.txt")
            arquivo_pickle = os.path.join(polichat_extrator.DOWNLOAD_PATH, "cache_dataframe.pkl")
            
            primeira_vez_dia = True
            extracao_completa = False
            
            if not os.path.exists(arquivo_pickle):
                extracao_completa = True
            elif os.path.exists(arquivo_controle):
                with open(arquivo_controle, "r") as f:
                    if f.read().strip() == hoje_str:
                        primeira_vez_dia = False
                        
            polichat_extrator.limpar_pasta_downloads()
            sucesso_extracao = polichat_extrator.extrair_relatorio_metabase(primeira_vez_dia, extracao_completa)

            if not sucesso_extracao:
                registrar_log("\n⚠️ Pipeline abortado: o CSV não pôde ser extraído.")
                proc.status = 'FALHA'
                proc.progresso = 100
                proc.data_fim = timezone.now()
                proc.save()
                return

            # --- FASE 2: TRATAMENTO ---
            proc.status = 'TRATANDO'
            proc.save(update_fields=['status'])
            registrar_log("\n🔄 Iniciando tratamento de dados...")

            sucesso_tratamento = polichat_extrator.analisar_e_limpar_dados(primeira_vez_dia)

            if not sucesso_tratamento:
                registrar_log("\n⚠️ Tratamento de dados falhou.")
                proc.status = 'FALHA'
                proc.progresso = 100
                proc.data_fim = timezone.now()
                proc.save()
                return
            
            if sucesso_tratamento and (primeira_vez_dia or extracao_completa):
                with open(arquivo_controle, "w") as f:
                    f.write(hoje_str)

            tempo_total = time.time() - tempo_inicio
            minutos = int(tempo_total // 60)
            segundos = int(tempo_total % 60)

            proc.status = 'CONCLUIDO'
            proc.progresso = 100
            proc.data_fim = timezone.now()
            proc.arquivo_resultado = polichat_extrator.ARQUIVO_EXCEL
            proc.save()
            registrar_log(f"\n🎉 Pipeline concluído em {minutos}m e {segundos}s!")

        except Exception as e:
            proc.status = 'FALHA'
            proc.data_fim = timezone.now()
            erro_detalhado = traceback.format_exc()
            registrar_log(f"\n❌ FALHA CRÍTICA:\n{erro_detalhado}")
            proc.save()
        finally:
            sys.stdout = original_stdout
