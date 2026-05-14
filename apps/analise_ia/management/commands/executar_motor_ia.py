import traceback
import sys
import os
import threading
import time
from django.utils import timezone
from django.core.management.base import BaseCommand
from apps.analise_ia.models import ProcessamentoAnaliseIA
from apps.analise_ia.services import extrator, consolidador, ggci

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# ==========================================
# MAPA DE PROGRESSO PONDERADO POR ETAPA
# ==========================================
# Cada string-chave mapeia para um progresso ABSOLUTO (não incremental).
# O sistema busca a PRIMEIRA correspondência na ordem do dicionário.
# Faixas:  EXTRAÇÃO 0-35 | CONSOLIDAÇÃO 35-50 | GGCI 50-100

PROGRESS_MAP_ABSOLUTE = [
    # --- EXTRAÇÃO (0% → 35%) ---
    ("Extração concluída",                              35),
    
    # --- CONSOLIDAÇÃO (35% → 50%) ---
    ("Consolidando e limpando",                         38),
    ("Planilhas consolidadas e limpas",                 50),
    
    # --- GGCI (50% → 100%) ---
    ("Analisando regras de negócio",                    52),
    ("Identificando bolsistas sem documentação",        58),
    ("Buscando dados financeiros dos bolsistas",        60),
    ("Conectando ao sistema de pagamentos",             63),
    ("Dados financeiros carregados com sucesso",        66),
    ("Calculando auditorias e cruzando dados financeiros (Documentos)", 70),
    ("Calculando auditorias e cruzando dados financeiros (RIAF)",       76),
    ("Inicializando conversor e motor do Excel",        78),
    ("Gerando aba Documentos",                          80),
    ("Gerando aba Riaf",                                85),
    ("Processando Resumo Quantitativo",                 88),
    ("Gerando Abas Gerenciais",                         92),
    ("Salvando e compilando arquivo físico",            95),
    ("SUPER-EXTRAÇÃO CONCLUÍDA E SALVA",                99),
]

# Strings que incrementam +1 (para a fase de extração com muitos downloads)
PROGRESS_MAP_INCREMENT = [
    "Download concluído",
    "Lido:",
    "base carregada",
    "Injetados",
    "Adicionado",
]

# Strings que incrementam +2 (para consolidação com vários arquivos)
PROGRESS_MAP_INCREMENT_2 = [
    "Gerado com sucesso e colunas",
]


class LogCapture:
    """
    Captura stdout, acumula num buffer e salva periodicamente no banco.
    Usa mapa de progresso ponderado + rastreamento de timing por bloco.
    """
    def __init__(self, original, proc):
        self.original = original
        self.proc = proc
        self.lock = threading.Lock()
        self.buffer = ""
        self.last_save = time.time()
        
        # Timing por bloco — rastreia quanto tempo cada etapa leva
        self.block_timers = {}
        self.current_block = "INIT"
        self.block_start = time.time()

    def _detectar_bloco(self, msg):
        """Detecta em qual bloco estamos baseado na mensagem"""
        blocos = [
            ("processamento massivo",   "EXTRAÇÃO"),
            ("Consolidando e limpando", "CONSOLIDAÇÃO"),
            ("Analisando regras",       "GGCI_INICIO"),
            ("Identificando bolsistas", "GGCI_PENDENCIAS"),
            ("Conectando ao sistema",   "GGCI_SQL"),
            ("Calculando auditorias e cruzando dados financeiros (Documentos)", "GGCI_AUDITORIA_DOCS"),
            ("Calculando auditorias e cruzando dados financeiros (RIAF)",       "GGCI_AUDITORIA_RIAF"),
            ("Inicializando conversor", "GGCI_EXCEL_INIT"),
            ("Gerando aba Documentos",  "GGCI_ABA_DOCS"),
            ("Gerando aba Riaf",        "GGCI_ABA_RIAF"),
            ("Processando Resumo",      "GGCI_RESUMO"),
            ("Gerando Abas Gerenciais", "GGCI_RELATORIO"),
            ("Salvando e compilando",   "GGCI_SAVE"),
            ("SUPER-EXTRAÇÃO",          "GGCI_FIM"),
        ]
        for trigger, nome_bloco in blocos:
            if trigger in msg:
                return nome_bloco
        return None

    def _registrar_timing(self, novo_bloco):
        """Fecha o timer do bloco atual e abre o do novo"""
        agora = time.time()
        duracao = agora - self.block_start
        
        if self.current_block:
            self.block_timers[self.current_block] = round(duracao, 2)
        
        self.current_block = novo_bloco
        self.block_start = agora

    def write(self, message):
        self.original.write(message)
        with self.lock:
            self.buffer += message
            
            agora = time.time()
            force_flush = any(x in message for x in ["✅", "🚀", "🎉", "❌", "FALHA", "🤖", "💾", "🗄️", "🔍", "⚡"])
            
            if agora - self.last_save > 0.8 or force_flush:
                self.proc.refresh_from_db(fields=['log', 'progresso'])
                
                novo_progresso = self.proc.progresso
                msg_str = str(self.buffer)
                
                # --- Detectar e registrar timing do bloco ---
                novo_bloco = self._detectar_bloco(msg_str)
                if novo_bloco and novo_bloco != self.current_block:
                    self._registrar_timing(novo_bloco)
                
                # --- 1. Progresso ABSOLUTO (faixas fixas por etapa) ---
                for trigger, target in PROGRESS_MAP_ABSOLUTE:
                    if trigger in msg_str:
                        novo_progresso = max(novo_progresso, target)
                        break  # Usa a PRIMEIRA correspondência
                
                # --- 2. Progresso INCREMENTAL (+1 para downloads, leituras etc) ---
                for trigger in PROGRESS_MAP_INCREMENT:
                    if trigger in msg_str:
                        novo_progresso += 1
                        break
                
                for trigger in PROGRESS_MAP_INCREMENT_2:
                    if trigger in msg_str:
                        novo_progresso += 2
                        break
                
                # Teto de segurança — só o status final pode ser 100
                if novo_progresso > 99:
                    novo_progresso = 99
                    
                self.proc.progresso = novo_progresso
                self.proc.log += self.buffer
                self.proc.save(update_fields=['log', 'progresso'])
                
                self.buffer = ""
                self.last_save = agora

    def flush(self):
        self.original.flush()
    
    def get_timing_report(self):
        """Retorna relatório de tempo por bloco para análise"""
        # Fecha o último bloco
        self._registrar_timing("FIM")
        
        lines = []
        for bloco, tempo in self.block_timers.items():
            if tempo > 0.5:  # Só mostra blocos relevantes
                lines.append(f"⏱ {bloco}: {tempo:.1f}s")
        return "\n".join(lines)

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
        log_capture = LogCapture(sys.stdout, proc)
        sys.stdout = log_capture
        
        def registrar_log(mensagem):
            print(mensagem)

        try:
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
            
            # --- RELATÓRIO DE TIMING ---
            timing_report = log_capture.get_timing_report()
            if timing_report:
                registrar_log(f"\n📊 Timing por bloco:\n{timing_report}")
            
            proc.status = 'CONCLUIDO'
            proc.progresso = 100
            proc.data_fim = timezone.now()
            proc.arquivo_resultado = ggci.ARQUIVO_GERAL_SAIDA
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