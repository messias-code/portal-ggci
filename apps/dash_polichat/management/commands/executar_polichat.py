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
import threading
import time
from django.utils import timezone
from django.core.management.base import BaseCommand
from apps.dash_polichat.models import ProcessamentoPolichat
from apps.dash_polichat.services import polichat_extrator

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class LogCapture:
    """Captura os prints do pipeline e salva no banco em tempo real"""
    
    def __init__(self, original, proc):
        self.original = original
        self.proc = proc
        self.lock = threading.Lock()
        self.buffer = ""
        self.last_save = time.time()

    def write(self, message):
        self.original.write(message)
        with self.lock:
            self.buffer += message
            agora = time.time()
            
            # Salva a cada 1s ou em mensagens importantes
            if agora - self.last_save > 1.0 or any(e in message for e in ["✅", "🚀", "🎉", "❌", "🏆"]):
                self.proc.refresh_from_db(fields=['log', 'progresso'])
                
                novo_progresso = self.proc.progresso
                msg = str(self.buffer)
                
                # Atualiza progresso baseado nas mensagens
                if "Login enviado" in msg:
                    novo_progresso = max(novo_progresso, 10)
                elif "Metabase carregado" in msg:
                    novo_progresso = max(novo_progresso, 20)
                elif "Configurando filtro" in msg:
                    novo_progresso = max(novo_progresso, 25)
                elif "Aguardando o Metabase processar" in msg:
                    novo_progresso = max(novo_progresso, 30)
                elif "Localizando tabela" in msg:
                    novo_progresso = max(novo_progresso, 40)
                elif "Iniciando download" in msg:
                    novo_progresso = max(novo_progresso, 45)
                elif "DOWNLOAD CONCLUÍDO" in msg:
                    novo_progresso = max(novo_progresso, 55)
                elif "CSV carregado" in msg:
                    novo_progresso = max(novo_progresso, 60)
                elif "Nomes de atendentes" in msg:
                    novo_progresso = max(novo_progresso, 65)
                elif "Período do dia" in msg:
                    novo_progresso = max(novo_progresso, 70)
                elif "Avaliação de tempo" in msg:
                    novo_progresso = max(novo_progresso, 75)
                elif "Diagnóstico e status" in msg:
                    novo_progresso = max(novo_progresso, 80)
                elif "Colunas de tempo" in msg:
                    novo_progresso = max(novo_progresso, 85)
                elif "Gerando ficheiro Excel" in msg:
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
            
            # --- FASE 1: EXTRAÇÃO ---
            proc.status = 'EXTRAINDO'
            proc.progresso = 5
            proc.save(update_fields=['status', 'progresso'])
            registrar_log("🚀 Iniciando pipeline de extração Polichat...")

            polichat_extrator.limpar_pasta_downloads()
            sucesso_extracao = polichat_extrator.extrair_relatorio_metabase()

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

            sucesso_tratamento = polichat_extrator.analisar_e_limpar_dados()

            if not sucesso_tratamento:
                registrar_log("\n⚠️ Tratamento de dados falhou.")
                proc.status = 'FALHA'
                proc.progresso = 100
                proc.data_fim = timezone.now()
                proc.save()
                return

            # --- FINALIZAÇÃO ---
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
