"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/management/commands/executar_doc_ia.py ===
Propósito: Rotina de background que traz os dados do SIBU para dentro do Documentos IA.
Dependências: django.core.management, threading, time, os, sys.

DIFERENÇA PARA O analise_ia: lá o usuário escolhe documentos, períodos e o que gerar numa
tela de filtros, e o resultado é um arquivo para ele baixar. Aqui não há filtros — o
dashboard precisa sempre do universo inteiro — e não há entrega: a saída são Parquets
tipados numa pasta fixa, prontos para virar gráfico.

Os dois apps rodam a mesma família de queries no SIBU, mas com nomes de tabela
individualizados pelo sufixo `_documentos_ia` (ver services/extrator.py), então podem
rodar ao mesmo tempo sem um derrubar a tabela do outro.
"""
import fcntl
import traceback
import shutil
import sys
import os
import threading
import time
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.dashboards.dash_documentos_ia.models import ProcessamentoDocIA
from apps.dashboards.dash_documentos_ia.services import extrator, consolidador, ggci

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# --- Escopo PADRÃO da extração ---
# O dashboard compara documentos e períodos entre si, então o padrão é trazer tudo:
# filtrar a leitura é decisão da tela, feita depois, sobre os dados já em disco.
#
# O escopo da EXTRAÇÃO, porém, passou a ser configurável. Não é a mesma coisa: quando
# um lote de documentos é processado à tarde, esperar o ciclo da madrugada só para o
# número mudar de "Não Processado" para "Processado" é tempo perdido. Configurando
# documento, semestre e as inscrições envolvidas, a atualização desce em minutos em vez
# de reprocessar 184 mil linhas.
DOCUMENTOS = ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF", "HISTORICO"]
PERIODOS = ["2025-1", "2025-2", "2026-1", "2026-2"]


def escopo_da_execucao(configuracoes):
    """
    O QUE FAZ: traduz o que a tela configurou no que o extrator entende.

    POR QUÊ TOLERA TUDO: a configuração vem de um JSON gravado no banco, que pode ter
    sido escrito por uma versão anterior da tela ou estar vazio (é o caso do cron e de
    quem clica em "Atualizar" sem configurar nada). Qualquer campo ausente ou malformado
    volta ao escopo completo, que é o comportamento que a rotina sempre teve.

    RETORNO: (documentos, periodos_por_doc, inscricoes_forcadas, atualizacao_bruta)
    """
    if not isinstance(configuracoes, dict) or not configuracoes:
        return DOCUMENTOS, {doc: PERIODOS for doc in DOCUMENTOS}, [], []

    pedidos = [d for d in (configuracoes.get('documentos') or []) if d in DOCUMENTOS]
    documentos = pedidos or DOCUMENTOS

    por_doc = configuracoes.get('periodos_por_doc') or {}
    periodos_por_doc = {}
    for doc in documentos:
        semestres = [s for s in (por_doc.get(doc) or []) if s in PERIODOS]
        # Documento escolhido sem semestre nenhum significa "todos" — a tela não deveria
        # mandar assim, mas um payload antigo pode.
        periodos_por_doc[doc] = semestres or PERIODOS

    def lista_de(chave):
        valor = configuracoes.get(chave) or []
        return [item for item in valor
                if isinstance(item, dict) and item.get('documento') in DOCUMENTOS]

    return documentos, periodos_por_doc, lista_de('processados_hoje'), lista_de('atualizacao_bruta')

# --- Trava de execução única -------------------------------------------------------
# POR QUÊ EXISTE: a proteção contra atualização dupla morava só em
# `iniciar_atualizacao_docia` (status ativo + pgrep). Quem chama o comando pelo terminal
# passa por fora dela, e em 27/08/2026 isso derrubou um ciclo inteiro: quatro execuções
# simultâneas com o MESMO id compartilharam `dados/processamento/proc_<id>/`, e cada uma
# chamou `limpar_pasta_raiz` sobre o que a outra tinha acabado de baixar. O log mostrava
# "Sem registros (Vazio)" em cascata e timeouts no botão de download do ScriptCase, como
# se o SIBU estivesse fora do ar.
#
# POR QUE flock E NÃO UM ARQUIVO-SENTINELA: o `flock` é do kernel e morre junto com o
# processo — queda, kill -9 ou reboot liberam sozinhos. Um arquivo comum precisaria de
# heurística de idade para não travar o app para sempre (é o que `adquirir_lock_cache`
# faz no ggci, onde a janela é de segundos; aqui um ciclo legítimo dura minutos e
# qualquer prazo seria chute).
#
# A TRAVA É DO MOTOR, NÃO DO REGISTRO: mesmo com ids diferentes, duas extrações disputam
# as mesmas tabelas temporárias no SIBU e o mesmo throttle de exportação do ScriptCase.
# Uma de cada vez é o que o app sempre assumiu — só não estava escrito em lugar nenhum.
CAMINHO_TRAVA = os.path.join(
    settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia", "dados", ".execucao.lock"
)


def adquirir_trava_de_execucao():
    """
    O QUE FAZ: garante que só um ciclo do motor rode por vez nesta instalação.
    RETORNO: o arquivo travado (que precisa ficar VIVO enquanto durar a execução — se o
        objeto for coletado, o kernel libera a trava junto), ou None se já há outro ciclo.
    """
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


# Quantas pastas de processamento (os .xls/.xlsx baixados do ScriptCase) manter em disco.
# Elas são só insumo: o resultado final vive em dados/parquet/. Sem esse teto, cada
# atualização deixaria para trás algumas centenas de MB de planilhas já consumidas.
MAX_PASTAS_PROCESSAMENTO = 2

# --- Barra de progresso -----------------------------------------------------------
# A escala saiu de MEDIÇÃO, e não de palpite. Somando o "Timing por bloco" das últimas
# seis execuções concluídas:
#
#     execução   total    extração   consolidação   regras (GGCI)
#     completa    399s    354s (89%)     1,2s          ~41s (10%)
#     completa    533s    414s (78%)     1,2s          ~40s  (8%)
#     recortada   101s     53s (53%)     2,8s          ~41s (40%)
#     recortada    96s     51s (53%)     1,2s          ~40s (42%)
#
# O bloco das REGRAS é praticamente CONSTANTE (~40s); quem varia de 51s a 414s é a
# extração. A escala antiga dava 15% à extração e 84% às regras — exatamente o inverso
# do tempo real, e é daí que vinha a barra grudada perto do fim: qualquer espera longa
# acontecia depois que ela já tinha subido tudo.
#
# Agora a extração ocupa a faixa 4→78 e caminha por CONTAGEM DE ARQUIVOS
# (`[EXTRACAO_PROGRESSO] n/total`, emitido pelo extrator), que é andamento real. Os
# marcos abaixo cobrem o resto, distribuídos pelo peso medido de cada bloco do GGCI.
FAIXA_EXTRACAO = (4, 78)

def _teto_da_etapa(progresso):
    """
    O QUE FAZ: até onde a barra pode subir sozinha, sem um marco novo no log.

    POR QUÊ EXISTE: entre dois marcos a barra precisa dar sinal de vida — parada, ela
    lê como travamento. Mas subir livre é pior: ela chega ao fim e fica lá, e aí o
    número deixa de significar qualquer coisa. O teto é o degrau seguinte menos um, de
    modo que a barra caminhe DENTRO da etapa e só a cruze quando o log disser que
    cruzou.
    """
    degraus = (FAIXA_EXTRACAO[0], FAIXA_EXTRACAO[1], 82, 92, 99)
    for degrau in degraus:
        if progresso < degrau:
            return degrau - 1
    return 99


def _progresso_da_extracao(texto):
    """
    O QUE FAZ: lê `[EXTRACAO_PROGRESSO] n/total` e devolve o ponto da barra.
    POR QUÊ: é o único andamento REAL que existe na etapa mais longa do ciclo. Sem ele,
        a barra atravessava 6 minutos de extração sem nenhuma informação — e qualquer
        movimento que ela fizesse ali seria invenção.
    RETORNO: o percentual dentro de `FAIXA_EXTRACAO`, ou None se não houver marcador.
    """
    import re

    ultimo = None
    for feitos, total in re.findall(r"\[EXTRACAO_PROGRESSO\]\s*(\d+)/(\d+)", texto):
        ultimo = (int(feitos), int(total))
    if not ultimo or ultimo[1] <= 0:
        return None

    inicio, fim = FAIXA_EXTRACAO
    return int(inicio + (fim - inicio) * min(ultimo[0] / ultimo[1], 1.0))


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
        blocos = [
            ("processamento massivo",   "EXTRAÇÃO"),
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
        for trigger, nome_bloco in blocos:
            if trigger in msg:
                return nome_bloco
        return None

    def _registrar_timing(self, novo_bloco):
        agora = time.time()
        duracao = agora - self.block_start
        if self.current_block:
            anterior = self.block_timers.get(self.current_block, 0.0)
            self.block_timers[self.current_block] = round(anterior + duracao, 2)
        self.current_block = novo_bloco
        self.block_start = agora

    def write(self, message):
        if "[GGCI_SILENT_WAIT]" in message:
            with self.lock:
                agora = time.time()
                if agora - self.last_save > 0.8:
                    self.proc.refresh_from_db(fields=["progresso"])
                    atual = self.proc.progresso
                    # ESTE RAMO IGNORAVA A ETAPA: o teto era 98 fixo e o passo, +4. Uma
                    # espera silenciosa no meio da extração — que é onde elas acontecem —
                    # empurrava a barra até 98 em poucos segundos, e ela ficava lá pelo
                    # resto do ciclo. Era esse o "parado em 99%". Agora o teto é o da
                    # etapa em curso, e o passo é de 1.
                    teto = _teto_da_etapa(atual)
                    if atual < teto:
                        self.proc.progresso = min(atual + 1, teto)
                        self.proc.save(update_fields=["progresso"])
                        self.last_save = agora
            return

        with self.lock:
            for chunk in message.splitlines(True):
                if self.needs_timestamp and chunk != "\n":
                    ts = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
                    self.original.write(f"[{ts}] ")
                self.original.write(chunk)
                self.needs_timestamp = chunk.endswith("\n")

            self.buffer += message
            agora = time.time()
            
            force_flush = any(x in message for x in ["🎉", "❌", "FALHA", "🛑"])
            
            if agora - self.last_save > 0.8 or force_flush:
                self.proc.refresh_from_db(fields=["log", "progresso"])
                novo_progresso = self.proc.progresso
                msg_str = str(self.buffer)
                
                novo_bloco = self._detectar_bloco(msg_str)
                if novo_bloco and novo_bloco != self.current_block:
                    self._registrar_timing(novo_bloco)
                
                for trigger, target in PROGRESS_MAP_ABSOLUTE:
                    if trigger in msg_str:
                        novo_progresso = max(novo_progresso, target)
                        break

                # Andamento REAL da extração, que é 90% do tempo do ciclo: o extrator
                # emite `[EXTRACAO_PROGRESSO] n/total` a cada arquivo concluído.
                medido = _progresso_da_extracao(msg_str)
                if medido is not None:
                    novo_progresso = max(novo_progresso, medido)
                
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
                self.proc.save(update_fields=["log", "progresso"])
                
                self.buffer = ""
                self.last_save = agora

    def flush(self):
        self.original.flush()
    
    def get_timing_report(self):
        self._registrar_timing("FIM")
        lines = []
        for bloco, tempo in self.block_timers.items():
            if tempo > 0.5:
                lines.append(f"⏱ {bloco}: {tempo:.1f}s")
        return "\n".join(lines)


class Command(BaseCommand):
    help = "Traz os dados do SIBU para o Dashboard Documentos IA (roda em background)"

    def add_arguments(self, parser):
        parser.add_argument('processo_id', type=int)

    def handle(self, *args, **options):
        """
        O QUE FAZ: Executa as três etapas da rotina e registra o progresso no banco.
        COMO FUNCIONA:
          1. EXTRAINDO   — extrator: baixa as planilhas do ScriptCase e atualiza os
                           espelhos SQL em Parquet.
          2. EXTRAINDO   — consolidador: junta e limpa as planilhas baixadas.
          3. TRATANDO    — ggci: aplica as regras de negócio e grava as abas em
                           dados/parquet/ (formato PARQUET, uma aba por arquivo).
          4. Limpa as pastas de processamento antigas.
        PARÂMETROS: processo_id (int) — o registro criado pela view antes de disparar.
        EFEITOS COLATERAIS: rede, disco e atualização contínua do registro no banco.
        """
        processo_id = options['processo_id']

        # O ID vem por argumento em vez de ser pescado do banco: a versão anterior fazia
        # `filter(status__in=ATIVOS).first()`, e com dois registros ativos ela escrevia o
        # log e o progresso no registro errado.
        try:
            proc = ProcessamentoDocIA.objects.get(id=processo_id)
        except ProcessamentoDocIA.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Processo {processo_id} não encontrado."))
            return

        # A trava vem ANTES de qualquer escrita, e a ordem aqui não é estilo: o passo
        # seguinte ZERA o log. Se a recusa viesse depois, uma execução barrada apagaria o
        # log da execução legítima que está no ar — trocaríamos uma corrida por outra pior.
        trava = adquirir_trava_de_execucao()
        if trava is None:
            recado = ("🛑 Já existe uma atualização do Documentos IA em andamento. "
                      "Esta execução foi recusada para não disputar a mesma pasta de "
                      "processamento nem as tabelas temporárias do SIBU.")
            # A recusa só CARIMBA o registro quando ele é desta tentativa — isto é, quando
            # está PENDENTE, o estado em que a tela e o cron o criam logo antes de chamar
            # o comando. Em qualquer outro estado o registro pertence a outra coisa, e
            # escrever nele destrói informação boa:
            #   EXTRAINDO/TRATANDO → é a execução legítima que está NO AR. Marcá-la como
            #     FALHA apagaria da tela o ciclo que está de fato rodando.
            #   CONCLUIDO → é um resultado válido, e é dele que sai a data que o botão
            #     "Atualizar" mostra. Uma recusa apagaria o carimbo de uma execução que
            #     deu certo.
            if proc.status == "PENDENTE":
                proc.status = "FALHA"
                proc.log = recado
                proc.data_fim = timezone.now()
                proc.save(update_fields=["status", "log", "data_fim"])
            self.stdout.write(self.style.WARNING(recado))
            return

        # O log é de UMA execução, e o LogCapture só sabe CONCATENAR (`proc.log += buffer`).
        # Quando o mesmo registro é reaproveitado — rodar o comando à mão com um ID que já
        # foi usado —, cada ciclo empilhava no anterior sem nunca limpar. O registro #1 deste
        # ambiente chegou a 53 execuções e 820 KB num campo só, e a tela, que mostra
        # `proc.log` inteiro, exibia todas elas de uma vez. Zerar aqui é o começo da
        # execução: quem vem pela tela ou pelo cron já nasce com o registro limpo, então
        # isto só muda o caso do reaproveitamento.
        proc.log = ""
        proc.progresso = 0
        proc.data_fim = None
        proc.save(update_fields=["log", "progresso", "data_fim"])

        original_stdout = sys.stdout
        log_capture = LogCapture(sys.stdout, proc)
        sys.stdout = log_capture

        try:
            tempo_inicio = time.time()

            proc.status = "EXTRAINDO"
            proc.progresso = 2
            proc.save(update_fields=["status", "progresso"])
            print("🚀 Iniciando processamento massivo...")

            documentos, periodos_por_doc, processados_hoje, atualizacao_bruta = \
                escopo_da_execucao(proc.configuracoes)

            if documentos != DOCUMENTOS or any(
                    periodos_por_doc[d] != PERIODOS for d in documentos):
                print("⚙️ Escopo configurado: "
                      + "; ".join(f"{d} ({', '.join(periodos_por_doc[d])})" for d in documentos))
            if processados_hoje:
                print(f"⚙️ Inscrições específicas em {len(processados_hoje)} recorte(s).")
            if atualizacao_bruta:
                print(f"⚙️ Atualização bruta em {len(atualizacao_bruta)} recorte(s).")

            # === ETAPA 1: extração (ScriptCase + espelhos SQL) ===
            extrator.executar(
                docs_selecionados=documentos,
                periodos_por_doc=periodos_por_doc,
                processo_id=processo_id,
                inscricoes_forcadas=processados_hoje,
                atualizacao_bruta=atualizacao_bruta,
            )

            # === ETAPA 2: consolidação das planilhas baixadas ===
            print("🔄 Consolidando e limpando as planilhas base...")
            consolidador.consolidar(processo_id=processo_id)

            # === ETAPA 3: regras de negócio e gravação em Parquet ===
            proc.refresh_from_db()
            proc.status = "TRATANDO"
            proc.progresso = max(proc.progresso, 25)
            proc.save(update_fields=["status", "progresso"])
            print("🗄️ Analisando regras de negócio...")

            # gerar_relatorio e gerar_relatorio_riaf ficam desligados de propósito: essas
            # duas abas são construídas com fórmulas do Excel e não existem fora do .xlsx.
            # As REGRAS rodam sempre sobre o universo inteiro, mesmo quando a extração
            # foi de um recorte. Elas comparam documentos e semestres entre si (um RIAF
            # ausente depende do contrato do mesmo aluno), e rodá-las sobre o recorte
            # produziria Parquets parciais — a tela passaria a mostrar só o que foi
            # extraído agora, apagando o resto do dashboard.
            pasta_saida = ggci.gerar_relatorio_geral(
                docs_selecionados=DOCUMENTOS,
                periodos_por_doc={doc: PERIODOS for doc in DOCUMENTOS},
                gerar_relatorio=False,
                gerar_relatorio_riaf=False,
                gerar_quantitativo=True,
                gerar_pagamentos=True,
                sems_riaf=PERIODOS,
                sems_contratos=PERIODOS,
                processo_id=processo_id,
                formato="PARQUET",
            )

            # === ETAPA 4: limpeza das pastas de insumo antigas ===
            self._limpar_processamentos_antigos()

            tempo_total = time.time() - tempo_inicio
            minutos, segundos = int(tempo_total // 60), int(tempo_total % 60)
            timing = log_capture.get_timing_report()

            print(f"\n📁 Dados disponíveis em: {pasta_saida}")
            if timing:
                print(f"\n📊 Timing por bloco:\n{timing}")
            print(f"\n🎉 Processamento concluído em {minutos}m e {segundos}s!")

            proc.refresh_from_db(fields=["log"])
            proc.status = "CONCLUIDO"
            proc.progresso = 100
            proc.data_fim = timezone.now()
            if log_capture.buffer:
                proc.log += log_capture.buffer
                log_capture.buffer = ""
            proc.save()

        except Exception:
            print(f"\n❌ FALHA CRÍTICA:\n{traceback.format_exc()}")
            proc.refresh_from_db(fields=["log"])
            proc.status = "FALHA"
            proc.data_fim = timezone.now()
            if log_capture.buffer:
                proc.log += log_capture.buffer
                log_capture.buffer = ""
            proc.save()

        finally:
            sys.stdout = original_stdout
            # Fechar o arquivo devolve a trava ao kernel. Um `kill -9` aqui no meio também
            # devolveria — é justamente por isso que ela é um flock e não um arquivo comum.
            trava.close()

    def _limpar_processamentos_antigos(self):
        """Mantém apenas as pastas proc_* mais recentes, apagando as demais."""
        base = os.path.join(
            settings.BASE_DIR, "apps", "dashboards", "dash_documentos_ia",
            "dados", "processamento",
        )
        if not os.path.exists(base):
            return
        pastas = [os.path.join(base, d) for d in os.listdir(base) if d.startswith("proc_")]
        pastas.sort(key=os.path.getctime)
        while len(pastas) > MAX_PASTAS_PROCESSAMENTO:
            try:
                shutil.rmtree(pastas.pop(0))
            except OSError:
                pass
