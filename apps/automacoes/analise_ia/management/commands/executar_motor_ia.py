"""
Propósito: Script de background (Management Command) que encapsula a orquestração IA, atuando como entrypoint CLI isolado.
Autor: N/A
Dependências: django.core.management, threading, time
"""
import traceback
import sys
import os
import threading
import time
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.automacoes.analise_ia.models import ProcessamentoAnaliseIA
from apps.automacoes.analise_ia.services import extrator, consolidador, ggci

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

FAIXA_ETL = (3, 35)
FAIXA_EXTRACAO = (35, 78)


def _teto_da_etapa(progresso):
    """Até onde a barra pode subir sozinha, sem um marco novo no log."""
    degraus = (FAIXA_ETL[0], FAIXA_ETL[1], FAIXA_EXTRACAO[1], 82, 92, 99)
    for degrau in degraus:
        if progresso < degrau:
            return degrau - 1
    return 99


def _andamento_do_marcador(texto, marcador, faixa):
    """Último `[<marcador>] n/total` do texto, projetado na faixa; None sem marcador."""
    import re

    ultimo = None
    for feitos, total in re.findall(r"\[" + marcador + r"\]\s*(\d+)/(\d+)", texto):
        ultimo = (int(feitos), int(total))
    if not ultimo or ultimo[1] <= 0:
        return None

    inicio, fim = faixa
    return int(inicio + (fim - inicio) * min(ultimo[0] / ultimo[1], 1.0))


def _progresso_da_extracao(texto):
    return _andamento_do_marcador(texto, "EXTRACAO_PROGRESSO", FAIXA_EXTRACAO)


def _progresso_do_etl(texto):
    return _andamento_do_marcador(texto, "ETL_PROGRESSO", FAIXA_ETL)


PROGRESS_MAP_ABSOLUTE = [
    ("Extração concluída",                              78),
    ("Consolidando e limpando",                         79),
    ("Consolidação concluída",                          81),
    ("Analisando regras de negócio",                    82),
    ("IDENTIFICAR   | AUSENTES",                        84),
    ("CONECTANDO    | BD SIBU",                         86),
    ("AUDITORIA     | DOCS",                            88),
    ("AUDITORIA     | RIAF",                            91),
    ("RELATORIO     | GERAL",                           92),
    ("GERANDO       | RELATORIO",                       93),
    ("GERANDO       | RESUMO",                          93),
    ("GERANDO       | DOCS  ] Contrato",                94),
    ("GERANDO       | RIAF",                            95),
    ("GERANDO       | DOCS  ] Benefício",               95),
    ("GERANDO       | DOCS  ] Financiamento",           96),
    ("GERANDO       | DOCS  ] Histórico",               96),
    ("GERANDO       | PAGTO",                           97),
    ("SALVANDO      | ARQUIV",                          98),
    ("Regras aplicadas:",                               99),
]

PROGRESS_MAP_INCREMENT = [
    "Download concluído",
    "Lido:",
    "base carregada",
    "Injetados",
    "Adicionado",
]

PROGRESS_MAP_INCREMENT_2 = [
    "Gerado com sucesso e colunas",
]

class LogCapture:
    """
    O QUE FAZ: Uma classe Wrapper (Proxy) para o sys.stdout.
    POR QUÊ EXISTE: Intercepta a saída (prints) das rotinas de processamento e os salva em banco de dados em tempo real.
    COMO FUNCIONA: Captura o buffer de texto. Calcula o progresso % baseado nas palavras-chave no buffer,
    dá flush() periodicamente para o DB model `ProcessamentoAnaliseIA`.
    """
    def __init__(self, original, proc):
        self.original = original
        self.proc = proc
        self.lock = threading.Lock()
        self.buffer = ""
        self.last_save = time.time()
        self.needs_timestamp = True
        
        self.block_timers = {}
        self.current_block = "INIT"
        self.block_start = time.time()

    def _detectar_bloco(self, msg):
        """Avalia que parte do macroprocesso está sendo ativada para tracking de duração (APM)."""
        blocos = [
            ("processamento massivo",   "ETL_SQL"),
            ("Baixando planilhas do ScriptCase", "EXTRAÇÃO"),
            ("Consolidando e limpando", "CONSOLIDAÇÃO"),
            ("Analisando regras",       "GGCI_INICIO"),
            ("IDENTIFICAR   | AUSENTES","GGCI_PENDENCIAS"),
            ("CONECTANDO    | PAGAMENTOS", "GGCI_SQL"),
            ("AUDITORIA     | DOCS",    "GGCI_AUDITORIA_DOCS"),
            ("AUDITORIA     | RIAF",    "GGCI_AUDITORIA_RIAF"),
            ("RELATORIO     | GERAL",   "GGCI_EXCEL_INIT"),
            ("GERANDO       | DOCS",    "GGCI_ABA_DOCS"),
            ("GERANDO       | RIAF",    "GGCI_ABA_RIAF"),
            ("GERANDO       | RESUMO",  "GGCI_RESUMO"),
            ("GERANDO       | RELATORIO", "GGCI_RELATORIO"),
            ("SALVANDO      | ARQUIV",  "GGCI_SAVE"),
            ("Regras aplicadas:",       "GGCI_FIM"),
        ]
        # O buffer junta tudo desde o último flush: com o SQL em cache, a abertura do
        # ETL e a do ScriptCase caem no mesmo trecho. Vale a etapa que aparece por
        # ÚLTIMO — a primeira da lista rotulava o ScriptCase inteiro como ETL_SQL.
        achados = [(msg.rfind(trigger), nome_bloco) for trigger, nome_bloco in blocos if trigger in msg]
        return max(achados)[1] if achados else None

    def _registrar_timing(self, novo_bloco):
        agora = time.time()
        duracao = agora - self.block_start
        if self.current_block:
            # ACUMULA em vez de sobrescrever. Vários gatilhos disparam mais de uma vez por
            # execução ("GERANDO | DOCS" sai uma vez por aba de documento; "GERANDO | RIAF"
            # sai para a aba Riaf e outra para o Relatório RIAF IES), e a versão anterior
            # guardava só o último trecho — o total da fase aparecia menor do que é, e a
            # ordem em que as abas são geradas mudava o número sem que nada tivesse mudado.
            anterior = self.block_timers.get(self.current_block, 0.0)
            self.block_timers[self.current_block] = round(anterior + duracao, 2)
        self.current_block = novo_bloco
        self.block_start = agora

    def write(self, message):
        if "[GGCI_SILENT_WAIT]" in message:
            with self.lock:
                agora = time.time()
                if agora - self.last_save > 0.8:
                    self.proc.refresh_from_db(fields=['progresso'])
                    atual = self.proc.progresso
                    teto = _teto_da_etapa(atual)
                    if atual < teto:
                        self.proc.progresso = min(atual + 1, teto)
                        self.proc.save(update_fields=['progresso'])
                        self.last_save = agora
            return

        with self.lock:
            for chunk in message.splitlines(True):
                if self.needs_timestamp and chunk != '\n':
                    ts = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
                    self.original.write(f"[{ts}] ")
                self.original.write(chunk)
                self.needs_timestamp = chunk.endswith('\n')

            self.buffer += message
            agora = time.time()
            
            # Força o salvamento imediato no banco apenas para flags críticas (sucesso final ou erro)
            force_flush = any(x in message for x in ["🎉", "❌", "FALHA", "🛑"])
            
            # Throttling de I/O em BD (0.8 seg)
            if agora - self.last_save > 0.8 or force_flush:
                self.proc.refresh_from_db(fields=['log', 'progresso'])
                novo_progresso = self.proc.progresso
                msg_str = str(self.buffer)
                
                novo_bloco = self._detectar_bloco(msg_str)
                if novo_bloco and novo_bloco != self.current_block:
                    self._registrar_timing(novo_bloco)
                
                for trigger, target in PROGRESS_MAP_ABSOLUTE:
                    if trigger in msg_str:
                        novo_progresso = max(novo_progresso, target)
                        break 

                medido = _progresso_da_extracao(msg_str)
                if medido is not None:
                    novo_progresso = max(novo_progresso, medido)
                medido = _progresso_do_etl(msg_str)
                if medido is not None:
                    novo_progresso = max(novo_progresso, medido)
                
                # Tetos dinâmicos para evitar que logs incrementais estourem a barra antes da hora
                limite_inc = _teto_da_etapa(novo_progresso)
                
                for trigger in PROGRESS_MAP_INCREMENT:
                    if trigger in msg_str:
                        novo_progresso = min(novo_progresso + 1, limite_inc)
                        break
                
                for trigger in PROGRESS_MAP_INCREMENT_2:
                    if trigger in msg_str:
                        novo_progresso = min(novo_progresso + 2, limite_inc)
                        break
                
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
        """Retorna as métricas de tempo coletadas para cada fase do processo."""
        self._registrar_timing("FIM")
        lines = []
        for bloco, tempo in self.block_timers.items():
            if tempo > 0.5:
                lines.append(f"⏱ {bloco}: {tempo:.1f}s")
        return "\n".join(lines)


class Command(BaseCommand):
    help = 'Executa o motor de extração e análise de IA em background'

    def add_arguments(self, parser):
        parser.add_argument('processo_id', type=int)

    def handle(self, *args, **options):
        """
        O QUE FAZ: Ponto de Início da Background Task.
        COMO FUNCIONA: Captura o ID do processo. Intercepta o sys.stdout. Dispara ETAPA 1 (Extração), ETAPA 2 (Consolidação) e ETAPA 3 (Cruzamento).
        """
        processo_id = options['processo_id']
        
        try:
            proc = ProcessamentoAnaliseIA.objects.get(id=processo_id)
        except ProcessamentoAnaliseIA.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Processo {processo_id} não encontrado.'))
            return

        original_stdout = sys.stdout
        log_capture = LogCapture(sys.stdout, proc)
        sys.stdout = log_capture  # <-- Injeção do Interceptor
        
        def registrar_log(mensagem):
            print(mensagem)

        try:
            tempo_inicio_global = time.time()
            
            proc.progresso = 2
            proc.status = 'EXTRAINDO'
            proc.save(update_fields=['status', 'progresso'])
            registrar_log("🚀 Iniciando processamento massivo...")
            
            config = proc.configuracoes or {}
            docs = config.get('documentos')
            if not docs: docs = []
            
            periodos_por_doc = config.get('periodos_por_doc', {})
            
            gerar_relatorio = config.get('gerar_relatorio', True)
            gerar_relatorio_riaf = config.get('gerar_relatorio_riaf', False)
            
            # Validação condicional que exige coerência temporal para permitir Relatório Gerencial
            docs_para_validar = docs if docs and "TODOS" not in docs else ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF"]
            
            # Check if there are multiple periods across any relevant documents
            todos_periodos_usados = set()
            for doc in docs_para_validar:
                if doc in periodos_por_doc:
                    todos_periodos_usados.update(periodos_por_doc[doc])
            
            tem_multiplos_periodos = len(todos_periodos_usados) > 1
            
            gerar_quant = config.get('gerar_quantitativo', True)
            gerar_pagamentos = config.get('gerar_pagamentos', True)

            pode_gerar_relatorio = (
                "CONTRATOS" in docs_para_validar and
                "FINANCIAMENTO" in docs_para_validar and
                "BENEFICIOS" in docs_para_validar and
                tem_multiplos_periodos and
                gerar_quant and
                gerar_pagamentos
            )
            
            pode_gerar_relatorio_riaf = (
                "RIAF" in docs_para_validar and
                "FINANCIAMENTO" in docs_para_validar and
                "BENEFICIOS" in docs_para_validar and
                tem_multiplos_periodos and
                gerar_quant and
                gerar_pagamentos
            )
            
            if gerar_relatorio and not pode_gerar_relatorio:
                registrar_log("! AVISO │ RELATÓRIO │ BLOQUEADO │ A aba 'Relatório Contratos' exige: Contratos, Financiamentos, Benefícios, Envios & Pendências e Pagamentos.")
                gerar_relatorio = False
                
            if gerar_relatorio_riaf and not pode_gerar_relatorio_riaf:
                registrar_log("! AVISO │ RELATÓRIO │ BLOQUEADO │ A aba 'Relatório Riaf' exige: Riaf, Financiamentos, Benefícios, Envios & Pendências e Pagamentos.")
                gerar_relatorio_riaf = False
            if not docs:
                registrar_log("🛑 Processo abortado: Nenhuma Base de Extração (Documentos) selecionada.")
                proc.status = 'CONCLUIDO'
                proc.progresso = 100
                proc.data_fim = timezone.now()
                proc.arquivo_resultado = None
                proc.save()
                return

            # Extrai inscrições forçadas do usuário (manual override)
            inscricoes_forcadas = config.get('processados_hoje', [])

            # Atualização bruta: pares documento+semestre que devem ignorar o filtro de
            # pendentes e rebaixar o semestre inteiro. Vem desligada por padrão.
            atualizacao_bruta = config.get('atualizacao_bruta', [])
            for item in atualizacao_bruta:
                alvo = item.get('documento')
                sems = ", ".join(item.get('semestres') or []) or "todos os semestres"
                registrar_log(f"🔁 ATUALIZAÇÃO BRUTA │ {alvo} │ {sems} │ Rebaixando enviados e ausentes, sem filtro de inscrições.")

            # === [ ETAPA 1: WEB SCRAPING ] ===
            total_baixado = extrator.executar(
                docs_selecionados=docs, 
                periodos_por_doc=periodos_por_doc, 
                processo_id=processo_id,
                inscricoes_forcadas=inscricoes_forcadas,
                atualizacao_bruta=atualizacao_bruta
            )
            
            # Curto-circuito protetor removido: Garantimos a execução do consolidator/ggci 
            # para que a planilha principal (export_conferencias) sempre seja gerada com os dados do banco.
            # if total_baixado == 0 and not gerar_relatorio_riaf and not gerar_relatorio:
            #     registrar_log("🛑 Processo abortado de forma inteligente.")
            #     proc.status = 'CONCLUIDO'
            #     proc.progresso = 100
            #     proc.data_fim = timezone.now()
            #     proc.arquivo_resultado = None
            #     proc.save()
            #     registrar_log(f"🎉 Processamento concluído em 0m e 0s!")
            #     return 

            # === [ ETAPA 2: MERGE EXCEL/PANDAS ] ===
            proc.refresh_from_db(fields=['progresso'])
            proc.status = 'CONSOLIDANDO'
            proc.progresso = max(proc.progresso, 78)
            proc.save(update_fields=['status', 'progresso'])
            registrar_log("🔄 Consolidando e limpando as planilhas base...")
            
            consolidador.consolidar(processo_id=processo_id)
            # registrar_log("Planilhas consolidadas e limpas.")

            # === [ ETAPA 3: REGRAS CONTÁBEIS (GGCI) ] ===
            proc.refresh_from_db(fields=['progresso'])
            proc.status = 'CRUZANDO'
            proc.progresso = max(proc.progresso, 82)
            proc.save(update_fields=['status', 'progresso'])
            registrar_log("🗄️ Analisando regras de negócio...")
            
            sems_riaf = config.get('sems_riaf', [])
            sems_contratos = config.get('sems_contratos', [])
            
            arquivo_saida_final = ggci.gerar_relatorio_geral(
                docs_selecionados=docs, 
                periodos_por_doc=periodos_por_doc, 
                gerar_relatorio=gerar_relatorio, 
                gerar_relatorio_riaf=gerar_relatorio_riaf,
                gerar_quantitativo=config.get('gerar_quantitativo', True),
                gerar_pagamentos=gerar_pagamentos,
                sems_riaf=sems_riaf,
                sems_contratos=sems_contratos,
                processo_id=processo_id,
                formato=config.get('formato', 'EXCEL')
            ) 
            # registrar_log("Regras de negócio aplicadas.")

            # ENCERRAMENTO
            tempo_total = time.time() - tempo_inicio_global
            minutos = int(tempo_total // 60)
            segundos = int(tempo_total % 60)
            
            timing_report = log_capture.get_timing_report()
            if timing_report:
                registrar_log(f"\n📊 Timing por bloco:\n{timing_report}")
                
            # === [ ETAPA 4: LIMPEZA DE PASTAS ] ===
            import shutil
            import os
            base_dados_dir = os.path.join(settings.BASE_DIR, "apps", "automacoes", "analise_ia", "dados", "processamento")
            temp_dir = os.path.join(base_dados_dir, f"proc_{processo_id}")
            # Remove a do processo atual (se tiver gerado arquivos, eles já foram pra saída final ou o arquivo final está na pasta superior)
            # Mas espera, se o arquivo final está salvo dentro do proc_ID, eu NÃO posso apagar!
            # O Analise IA gera o arquivo final e o usuário precisa baixar da pasta!
            # Em dash_documentos_ia a gente copiou os CSVs para /dados/analise_ia/ e apagamos.
            # No Analise IA, o "arquivo_saida_final" aponta pra dentro de proc_X!
            
            # Limpeza de pastas proc_* antigas, manter máx 3
            if os.path.exists(base_dados_dir):
                proc_dirs = [os.path.join(base_dados_dir, d) for d in os.listdir(base_dados_dir) if d.startswith('proc_')]
                proc_dirs.sort(key=os.path.getctime)
                while len(proc_dirs) > 3:
                    dir_to_remove = proc_dirs.pop(0)
                    try:
                        shutil.rmtree(dir_to_remove)
                    except:
                        pass
                        
            # Limpeza dos logs antigos (manter no máximo 3)
            log_dir = os.path.join(settings.BASE_DIR, "apps", "automacoes", "analise_ia", "logs")
            if os.path.exists(log_dir):
                log_files = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.startswith('execucao_') and f.endswith('.log')]
                log_files.sort(key=os.path.getctime)
                while len(log_files) > 3:
                    file_to_remove = log_files.pop(0)
                    try:
                        os.remove(file_to_remove)
                    except:
                        pass
            
            registrar_log(f"🎉 Processamento concluído em {minutos}m e {segundos}s!")
            proc.refresh_from_db(fields=['log'])
            proc.status = 'CONCLUIDO'
            proc.progresso = 100
            proc.data_fim = timezone.now()
            proc.arquivo_resultado = arquivo_saida_final
            if log_capture.buffer:
                proc.log += log_capture.buffer
                log_capture.buffer = ""
            proc.save()

        except Exception as e:
            erro_detalhado = traceback.format_exc()
            registrar_log(f"\n❌ FALHA CRÍTICA:\n{erro_detalhado}")
            proc.refresh_from_db(fields=['log'])
            proc.status = 'FALHA'
            proc.data_fim = timezone.now()
            if log_capture.buffer:
                proc.log += log_capture.buffer
                log_capture.buffer = ""
            proc.save()
        finally:
            # Garante liberação do Stdout
            sys.stdout = original_stdout
