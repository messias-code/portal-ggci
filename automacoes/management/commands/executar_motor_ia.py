import traceback
import sys
import os
import threading
from django.utils import timezone
from django.core.management.base import BaseCommand
from automacoes.models import ProcessamentoAnaliseIA

from automacoes.services import extrator, consolidador, ggci

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class LogCapture:
    def __init__(self, original, proc):
        self.original = original
        self.proc = proc
        self.lock = threading.Lock()
        import time
        self.buffer = ""
        self.last_save = time.time()

    def write(self, message):
        self.original.write(message)
        with self.lock:
            self.buffer += message
            
            import time
            agora = time.time()
            if agora - self.last_save > 1.0 or "✅" in message or "🚀" in message or "🎉" in message:
                self.proc.refresh_from_db(fields=['log', 'progresso'])
                
                novo_progresso = self.proc.progresso
                msg_str = str(self.buffer)
                
                if "Download concluído" in msg_str:
                    novo_progresso += 1
                elif "Extração concluída" in msg_str:
                    novo_progresso = max(novo_progresso, 35)
                elif "Consolidando e limpando" in msg_str:
                    novo_progresso = max(novo_progresso, 40)
                elif "Gerado com sucesso e colunas" in msg_str:
                    novo_progresso += 2
                elif "Planilhas consolidadas e limpas" in msg_str:
                    novo_progresso = max(novo_progresso, 50)
                elif "Analisando regras de negócio" in msg_str:
                    novo_progresso = max(novo_progresso, 55)
                elif "Lido:" in msg_str or "base carregada" in msg_str:
                    novo_progresso += 1
                elif "Injetados" in msg_str or "Adicionado" in msg_str:
                    novo_progresso += 1
                elif "Conectando ao sistema de pagamentos" in msg_str:
                    novo_progresso += 3
                elif "Calculando auditorias e cruzando dados financeiros" in msg_str:
                    novo_progresso += 3
                elif "Finalizando e gerando o Relatório Geral" in msg_str:
                    novo_progresso = max(novo_progresso, 95)
                
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
    help = 'Executa o motor de extração e análise de IA em background'

    def add_arguments(self, parser):
        # Recebe o ID do processo que a view mandou
        parser.add_argument('processo_id', type=int)

    def handle(self, *args, **options):
        processo_id = options['processo_id']
        
        try:
            proc = ProcessamentoAnaliseIA.objects.get(id=processo_id)
        except ProcessamentoAnaliseIA.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Processo {processo_id} não encontrado.'))
            return

        original_stdout = sys.stdout
        sys.stdout = LogCapture(sys.stdout, proc)
        
        def registrar_log(mensagem):
            print(mensagem)

        try:
            import time
            tempo_inicio_global = time.time()
            
            proc.progresso = 2
            # --- ETAPA 1: EXTRAÇÃO ---
            proc.status = 'EXTRAINDO'
            proc.save(update_fields=['status', 'progresso'])
            registrar_log("🚀 Iniciando processamento massivo...")
            
            config = proc.configuracoes or {}
            docs = config.get('documentos', [])
            anos = config.get('anos', [])
            sems = config.get('semestres', [])
            gerar_relatorio = config.get('gerar_relatorio', True)
            
            # --- VALIDAÇÃO INICIAL DO RELATÓRIO ---
            docs_para_validar = docs if docs and "TODOS" not in docs else ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF"]
            sems_para_validar = sems if sems and "TODOS" not in sems else ["1", "2"]
            pode_gerar_relatorio = (
                "CONTRATOS" in docs_para_validar and
                "FINANCIAMENTO" in docs_para_validar and
                "BENEFICIOS" in docs_para_validar and
                "1" in sems_para_validar and
                "2" in sems_para_validar
            )
            if gerar_relatorio and not pode_gerar_relatorio:
                registrar_log(f"[AVISO | RELATÓRIO | BLOQUEADO] ⚠️ A aba 'Relatório' exige: Contratos, Financiamentos, Benefícios e Semestres 1/2 simultâneos.")
            
            total_baixado = extrator.executar(docs_selecionados=docs, anos_selecionados=anos, periodos_selecionados=sems)
            
            # --- O CURTO-CIRCUITO INTELIGENTE ---
            if total_baixado == 0:
                registrar_log("🛑 Processo abortado de forma inteligente.")
                proc.status = 'CONCLUIDO'
                proc.progresso = 100
                proc.data_fim = timezone.now()
                proc.arquivo_resultado = None # Sem arquivo pra baixar
                proc.save()
                registrar_log(f"🎉 Processamento concluído em 0m e 0s!")
                return # O return finaliza o processo, impedindo que a ETAPA 2 e 3 rodem!

            # --- ETAPA 2: CONSOLIDAÇÃO ---
            proc.status = 'CONSOLIDANDO'
            proc.save(update_fields=['status'])
            registrar_log("🔄 Consolidando e limpando as planilhas base...")
            
            consolidador.consolidar() # Chama a função do seu script original
            registrar_log("✅ Planilhas consolidadas e limpas.")

            # --- ETAPA 3: GGCI (Negócio) ---
            proc.status = 'CRUZANDO'
            proc.save(update_fields=['status'])
            registrar_log("🗄️ Analisando regras de negócio...")
            
            config = proc.configuracoes or {}
            docs = config.get('documentos', [])
            anos = config.get('anos', [])
            sems = config.get('semestres', [])
            gerar_relatorio = config.get('gerar_relatorio', True)
            
            # Passando os filtros completos pro motor
            ggci.gerar_relatorio_geral(docs_selecionados=docs, anos_selecionados=anos, sems_selecionados=sems, gerar_relatorio=gerar_relatorio) 
            registrar_log("✅ Regras de negócio aplicadas.")

            # --- FINALIZAÇÃO ---
            tempo_total = time.time() - tempo_inicio_global
            minutos = int(tempo_total // 60)
            segundos = int(tempo_total % 60)
            
            proc.status = 'CONCLUIDO'
            proc.progresso = 100
            proc.data_fim = timezone.now()
            proc.arquivo_resultado = 'relatorio_geral.xlsx'
            proc.save()
            registrar_log(f"🎉 Processamento concluído em {minutos}m e {segundos}s!")

        except Exception as e:
            # Se der qualquer erro em qualquer etapa, avisa o banco!
            proc.status = 'FALHA'
            proc.data_fim = timezone.now()
            erro_detalhado = traceback.format_exc()
            registrar_log(f"\n❌ FALHA CRÍTICA:\n{erro_detalhado}")
            proc.save()
        finally:
            sys.stdout = original_stdout