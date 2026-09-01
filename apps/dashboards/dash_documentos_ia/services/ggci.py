"""
=== ARQUIVO: apps/dashboards/dash_documentos_ia/services/ggci.py ===
Propósito: Núcleo do Motor de Regras e Geração de Relatórios (GGCI).
Autor: N/A
Dependências Principais: pandas, sqlalchemy, python-dotenv
"""
import os
import sys
import time
import concurrent.futures
import pandas as pd
import numpy as np
import polars as pl
import unicodedata
from portal_ggci.mantenedoras import buscar_mantenedora as _buscar_mantenedora
from portal_ggci.mantenedoras import catalogo as _catalogo_mantenedoras
import re
import datetime
import zipfile
import io
from contextlib import contextmanager
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env)
load_dotenv()

# Calcula a raiz do projeto dinamicamente para suportar múltiplos ambientes (prod/dev)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
env_suffix = "_dev" if "dev" in os.path.basename(PROJECT_ROOT).lower() else "_prod"

# Sufixo que individualiza as tabelas do SIBU e os Parquets espelhados em tabelas_sql/.
# Ver a nota em services/extrator.py: sem ele, `analise_ia` e `dash_documentos_ia`
# disputariam os mesmos nomes `sibu.PY_ggci_*` e um dropava a tabela do outro.
# Vale só para os espelhos `PY_ggci_*`; o cache do Gemini usa `env_suffix` puro,
# porque a pasta de cada app já o separa.
SUFIXO_APP = "_documentos_ia"
SUFIXO_TABELAS = f"{SUFIXO_APP}{env_suffix}"


# Desativa o aviso do futuro do Pandas para preenchimento de dados vazios
pd.set_option('future.no_silent_downcasting', True)

# ==========================================
# 1. CAMINHOS DE ENTRADA E SAÍDA
# ==========================================
# Não há constantes de caminho aqui de propósito. Todo caminho de entrada e saída
# é derivado de `base_dir` dentro de `gerar_relatorio_geral`, a partir do
# `processo_id` da execução. As constantes que existiam neste ponto eram código
# morto herdado do analise_ia — ninguém as lia, e elas ainda apontavam para as
# pastas do outro app, o que dava a falsa impressão de que este módulo dependia dele.

# ==========================================
# 2. FUNÇÕES DE LIMPEZA E FORMATAÇÃO
# ==========================================
COLS_NUM = ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Cnpj Faculdade', 'UNI_CODIGO', 'UNI_CPF', 'inscricao_ano_semestre']
COLS_MOEDA = [
    'Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 
    'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 
    'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
    'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto', 
    'valor_beneficio', 'Soma Valor Beneficio', 'valor_financiamento', 'Soma Valor Financiamento', 
    'último_valor_pago_referencia', 'total bolsa paga', 
    'MSD_SOMA', 'G_MSD_SOMA', 'MCD_SOMA', 'G_MCD_SOMA', 
    'OVG Pagou (Último Referencial)',
    'OVG Deveria Pagar (Último Referencial)', 
    'Soma OVG Pagou',
    'Soma OVG Deveria Pagar (Sistema)',
    'OVG Deveria Pagar (IA)', 
    'Soma OVG Deveria Pagar (IA)',
    'Prejuízo da OVG (R$)',
    'Soma Prejuízo da OVG (R$)',
    'Economia da OVG (R$)',
    'VALOR_CONTRATO_APURADO', 'VALOR_PAGAMENTO', 'VALOR_PAGAMENTO2', 
    'VALOR_COMPLEMENTO', 'VALOR_CANCELAMENTO', 'LAN_VALBOLSA',
    'CD_sem_desconto', 'CD_com_desconto', 'CD_beneficios', 'CD_financiamentos'
]

# Siglas que o Title Case do relatório não pode estragar: "Cpf" volta a "CPF".
# A ordem não importa (os padrões são mutuamente exclusivos por \b), mas o regex único
# alternado substitui os 6 passes sequenciais de str.replace que existiam antes.
_MAPA_SIGLAS = {'Cpf': 'CPF', 'Cnpj': 'CNPJ', 'Ies': 'IES', 'Ovg': 'OVG', 'Ia': 'IA', 'Riaf': 'RIAF'}
# Texto que representa "sem data" depois do astype(str) — NaT, nulo do pandas e afins.
_DATAS_SEM_VALOR = ['', 'nan', 'NaT', 'None', '<NA>']
# Status que este motor SINTETIZA para quem está na lista de pendentes e não entregou o
# documento. Não vêm do Gemini nem do ScriptCase, então não podem ser memorizados no
# cache local: ali eles sobreviveriam à chegada do documento.
_STATUS_SEM_DOCUMENTO = ['Ausente', 'Ausentes']
_RE_SIGLAS = r'\b(' + '|'.join(_MAPA_SIGLAS) + r')\b'

DOC_CONTRATO = "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"
DOC_FINANC = "COMPROVANTE DE FINANCIAMENTO"
DOC_BENEF = "COMPROVANTE OUTROS BENEFÍCIOS"
DOC_RIAF = "RIAF – RESUMO DE INFORMAÇÕES ACADÊMICAS E FINANCEIRAS"
DOC_HISTORICO = "HISTÓRICO ESCOLAR"

# Ordem e conjunto de colunas das abas de documento (Contrato, Benefício, Financiamento,
# Histórico). Estava duplicada em 8 pontos sob 5 nomes distintos; todos os usos são de
# leitura (filtram contra as colunas presentes no DataFrame), então uma constante única
# atende a todos sem risco de aliasing.
#
# REGRA DE NEGÓCIO: uma coluna `gemini_*` é o que a IA leu DENTRO daquele documento, então
# só faz sentido na aba do documento que carrega aquela informação. Por isso `gemini_valor_beneficio`
# e `gemini_valor_financiamento` NÃO estão nesta lista: contrato e histórico escolar não
# trazem esses valores, e nas abas Benefício e Financiamento eles viriam 100% vazios porque
# a IA hoje não processa esses dois tipos de documento — os espelhos do banco vêm com
# `gemini_cpf` e `gemini_status` zerados (contra 31.702 de 31.795 no espelho de contrato).
# Quando a IA passar a processá-los, basta acrescentar os dois nomes AQUI e recortar Contrato
# e Histórico com uma lista sem eles. Atenção: `colunas_contrato_exp` precisa usar a MESMA
# lista da aba Contrato, porque traduz posição em letra de coluna para as fórmulas.
#
# Não confundir com `valor_beneficio` / `valor_financiamento` (sem prefixo): esses são dado
# de cadastro do beneficiário, valem em qualquer documento e seguem em todas as abas.
COLUNAS_ABA_DOCUMENTO = [
    'tipo_documento', 'status_ia', 'gemini_inconsistencia', 'semestre', 'gemini_semestre',
    'bolsista', 'inscricao', 'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf',
    'tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior', 'bolsa_posterior', 'faculdade',
    'mudou_ies', 'ies_anterior', 'ies_posterior', 'curso', 'ultimo_valor_pago_ref',
    'total_bolsa_paga', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'mensalidade_sem_desc',
    'gemini_mensalidade_sem_desc', 'msd_doc', 'mensalidade_com_desc',
    'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio', 'soma_valor_beneficio',
    'beneficio', 'valor_financiamento', 'soma_valor_financiamento',
    'financiamento', 'soma_ovg_devia_pagar_sis',
    'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg', 'soma_economia_ovg',
    'diagnostico_financeiro_final', 'data_coleta', 'data_coleta_atual_sistema', 'data_create',
    'data_processamento', 'processado', 'processar', 'qtd_token', 'qtd_disciplinas_matriculadas',
    'qtd_disciplinas_reprovadas', 'perfil', 'status_vinculo', 'situacao_motivo',
    'observacao_situacao', 'email', 'telefone_1', 'telefone_2', 'data_nascimento', 'matricula',
    'periodo_atual', 'qtd_periodos', 'modalidade', 'documento_ausente', 'veredito_documento'
]


SEMESTRES_PADRAO = ["2025-1", "2025-2", "2026-1"]

def limpar_texto_geral(texto):
    """
    O QUE FAZ: Remove acentuação, caracteres especiais e converte o texto para maiúsculas.
    POR QUÊ EXISTE: Padronização de dados textuais extraídos de fontes sujas (HTML/XLS).
    COMO FUNCIONA: Usa `unicodedata` para decomposição e `re` para remover não alfanuméricos.
    PARÂMETROS: texto (str ou NaN)
    RETORNO: string limpa.
    """
    if pd.isna(texto) or str(texto).lower() in ['nan', 'none']: return ""
    texto = str(texto).strip().upper()
    texto = texto.replace("ADMINISTRAÃO", "ADMINISTRACAO")
    texto = texto.replace("ADMINISTRAAAO", "ADMINISTRACAO")
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^A-Z0-9 ]', '', texto)
    return " ".join(texto.split())

# Rótulos que a coleta usa quando o benefício/financiamento não é especificado.
# "Não informado" era o rótulo antigo e ainda chega de parquets em cache gerados
# pelo SQL anterior — por isso continua na lista de origem.
ROTULOS_OUTROS = [
    'Outros', 'outros', 'OUTROS',
    'Não informado', 'Não Informado', 'NÃO INFORMADO',
    'Nao informado', 'Nao Informado', 'NAO INFORMADO'
]

def padronizar_rotulo_outros(df, colunas):
    """
    O QUE FAZ: Unifica em 'Outros' os rótulos genéricos de benefício/financiamento.
    POR QUÊ EXISTE: O relatório final precisa de um rótulo único para a coleta que não
    especifica o benefício/financiamento, sem depender de quando o parquet do SQL for regerado.
    COMO FUNCIONA: Faz replace exato das variações conhecidas, localizando a coluna sem
    diferenciar caixa no nome.
    PARÂMETROS: df (DataFrame), colunas (lista de nomes de coluna alvo)
    RETORNO: o próprio df, alterado in-place.
    """
    if df is None or df.empty: return df
    mapa_cols = {str(c).strip().lower(): c for c in df.columns}
    for col in colunas:
        col_real = mapa_cols.get(str(col).strip().lower())
        if col_real is not None:
            df[col_real] = df[col_real].replace(ROTULOS_OUTROS, 'Outros')
    return df

def caminho_cache_gemini():
    """
    O QUE FAZ: Devolve o caminho do cache local dos resultados do Gemini, criando a pasta
    e migrando o arquivo legado `tabelas_sql/historico_ia_local.parquet` se ele ainda existir.
    POR QUÊ EXISTE: O cache não é espelho de SQL nenhum — não pertence a `tabelas_sql/` nem ao
    prefixo `PY_ggci_`, que identifica tabelas materializadas no SIBU. Também precisa do sufixo
    de ambiente para não misturar dev e prod caso os diretórios sejam copiados.
    COMO FUNCIONA: Monta o caminho a partir de PROJECT_ROOT e move o arquivo antigo uma única vez.
    PARÂMETROS: nenhum
    RETORNO: caminho absoluto do parquet de cache.
    """
    pasta = os.path.join(PROJECT_ROOT, "apps", "dashboards", "dash_documentos_ia", "dados", "cache")
    os.makedirs(pasta, exist_ok=True)
    novo = os.path.join(pasta, f"cache_gemini_documentos{env_suffix}.parquet")

    legado = os.path.join(PROJECT_ROOT, "apps", "dashboards", "dash_documentos_ia", "dados", "tabelas_sql", "historico_ia_local.parquet")
    if os.path.exists(legado) and not os.path.exists(novo):
        try:
            os.replace(legado, novo)
            print(f"[GGCI       | INFO          | CACHE LOCAL] Cache do Gemini migrado para {os.path.basename(novo)}.")
        except OSError as e:
            print(f"[GGCI       | AVISO         | CACHE LOCAL] Falha ao migrar cache legado: {e}")
            return legado
    return novo

def adquirir_lock_cache(caminho_lock, espera_max=60, idade_stale=600):
    """
    O QUE FAZ: Adquire um lock de arquivo para serializar o ciclo ler-mesclar-gravar do cache.
    POR QUÊ EXISTE: Duas gerações de relatório simultâneas sobrescreviam o cache uma da outra,
    perdendo silenciosamente os registros da execução concorrente.
    COMO FUNCIONA: Cria o lock com O_EXCL (atômico). Se já existe, espera; remove locks órfãos
    acima de `idade_stale` segundos e desiste após `espera_max` segundos.
    PARÂMETROS: caminho_lock (str), espera_max (seg), idade_stale (seg)
    RETORNO: True se adquiriu o lock, False se desistiu.
    """
    inicio = time.time()
    while True:
        try:
            fd = os.open(caminho_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(time.time()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(caminho_lock) > idade_stale:
                    print(f"[GGCI       | INFO          | CACHE LOCAL] Lock stale (> {idade_stale}s). Removendo.")
                    os.remove(caminho_lock)
                    continue
            except OSError:
                continue
            if time.time() - inicio > espera_max:
                return False
            time.sleep(1)
        except OSError:
            return False

def gravar_parquet_atomico(df, caminho):
    """
    O QUE FAZ: Grava o DataFrame em parquet sem deixar o arquivo em estado parcial.
    POR QUÊ EXISTE: `to_parquet` direto no destino permite que um leitor concorrente
    (ou uma queda no meio da escrita) encontre um arquivo truncado e ilegível.
    COMO FUNCIONA: Escreve num temporário no mesmo diretório e faz os.replace, que é atômico no POSIX.
    PARÂMETROS: df (DataFrame), caminho (str)
    RETORNO: None
    """
    tmp = f"{caminho}.tmp{os.getpid()}"
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, caminho)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass

def converter_colunas_para_salvamento(df):
    """
    O QUE FAZ: Converte cada coluna para o tipo com que ela deve ser gravada.
    POR QUÊ EXISTE: Os dados chegam de origens sujas (scraping, planilha, banco) e tudo vira
    texto pelo caminho; sem esta normalização o Excel recebe número como string e a
    formatação de moeda e o alinhamento não se aplicam.
    COMO FUNCIONA: Decide pelo nome da coluna — inteiros para as de COLS_NUM e contagens,
    float para percentuais, moeda para COLS_MOEDA e para nomes com VALOR/SOMA/DIF e afins.
    PARÂMETROS: df (DataFrame)
    RETORNO: o DataFrame com os tipos ajustados.
    """
    for col in df.columns:
        col_upper = str(col).upper()
        if col in COLS_NUM or col_upper in ['QTD_PAGTOS', 'QTD_PAGTOS_RETROATIVOS', 'QTD_PERIODOS', 'GEMINI_QTD_PERIODOS', 'GEMINI_NUMERO_SEMESTRES', 'GEMINI_SEMESTRES_FEITOS', 'GEMINI_SEMESTRES_FINANCIADOS', 'QTD_TOKEN', 'QTDE_TOKEN']:
            s = df[col].astype(str).str.strip().str.lower()
            s = s.replace({'nan': '', 'none': '', '<na>': ''})
            s = s.str.replace(r'\.0+$', '', regex=True)
            s = s.str.replace(r'\D', '', regex=True)
            s_num = pd.to_numeric(s, errors='coerce')
            s_num = s_num.where((s_num >= -9223372036854775800) & (s_num <= 9223372036854775800))
            df[col] = s_num.astype('Int64')
        elif '%' in col_upper or col_upper.startswith('PERC_'):
            s = df[col].astype(str).str.replace('%', '', regex=False).str.strip()
            s = s.str.replace(',', '.', regex=False)
            df[col] = pd.to_numeric(s, errors='coerce').astype(float)
        elif col_upper in ['MATRICULA', 'GEMINI_MATRICULA', 'GEMINI MATRICULA']:
            s = df[col].astype(str).str.strip().str.lower()
            s = s.replace({'nan': '', 'none': '', '<na>': ''})
            s = s.str.replace(r'\D', '', regex=True)
            s = s.str.lstrip('0')
            s = s.replace({'': '-'})
            s = s.fillna('-')
            df[col] = s
        elif col in COLS_MOEDA or any(x in col_upper for x in ['DIF.', 'DIF_', 'BOLSA PAGA', 'BOLSA_PAGA', 'VALOR', 'SOMA', 'PAGOU', 'PAGAR', 'PREJUIZO', 'ECONOMIA']) or col_upper.endswith('_DESC') or col_upper.endswith('_DOC') or 'DESCONTO' in col_upper:
            s = df[col].astype(str).str.replace('R$', '', regex=False).str.strip()
            mask_has_both = s.str.contains(r'\.', regex=True) & s.str.contains(r'\,', regex=True)
            s.loc[mask_has_both] = s.loc[mask_has_both].str.replace('.', '', regex=False)
            s = s.str.replace(',', '.', regex=False)
            df[col] = pd.to_numeric(s, errors='coerce').astype(float)
    return df

# Formato de data que o pd.ExcelWriter aplica por padrão (parâmetro datetime_format).
# Precisa ser replicado célula a célula: sem ele o Excel mostra o número serial (46037).
_FORMATO_DATA_PANDAS = 'YYYY-MM-DD HH:MM:SS'


@contextmanager
def cronometrar(etapa):
    """
    Imprime quanto durou um trecho, para o log da execução guardar a decomposição.

    POR QUÊ EXISTE: as métricas `⏱` do motor medem blocos grandes demais —
    `GGCI_EXCEL_INIT` cobre 72s entre o fim da auditoria e a primeira aba escrita, sem
    dizer onde. Perfilar com py-spy exige estar atachado no momento certo e `sudo`
    (o `ptrace_scope` deste servidor é 1); um print resolve, custa nada e fica gravado
    no log do processamento para ser lido depois, de qualquer execução.

    O rótulo evita de propósito as palavras que o `executar_motor_ia` usa como gatilho
    de progresso ("Lido:", "Injetados", "Adicionado", "base carregada"), senão a barra
    da tela andaria sozinha.
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        cronometrar_fim(etapa, t0)


def cronometrar_fim(etapa, t0):
    """
    Versão sem `with` do `cronometrar`, para blocos longos já indentados.

    Envolver um trecho de 90 linhas num `with` obriga a reindentar tudo e polui o diff
    de uma mudança que é só de medição. Aqui basta guardar o `time.perf_counter()` no
    começo e chamar isto no fim.
    """
    # print(f"[GGCI       | PERFIL        | {str(etapa)[:26]:<26}] {time.perf_counter() - t0:7.2f}s")
    pass


def aplicar_por_distintos(s, fn):
    """
    Equivale a `s.apply(fn)`, mas chama `fn` uma vez por valor DISTINTO.

    POR QUÊ EXISTE: as colunas categóricas do relatório repetem muito — a aba Pagamentos
    tem 310 mil linhas e 105 nomes de IES, 24 competências de mês. O `apply` chama a
    função uma vez por linha; aqui ela roda uma vez por valor e o resultado volta pelos
    códigos do factorize. Medido: `padronizar_ies` 2,33s -> 0,11s, `buscar_mantenedora`
    2,47s -> 0,11s, com resultado idêntico.

    Nulo entra como sentinela -1 no factorize (None e NaN caem juntos, que é como o
    `pd.isna` das funções deste módulo já os trata) e recebe uma única chamada de `fn`.

    PARÂMETROS: s (Series), fn (callable de um argumento)
    RETORNO: Series de object, com o mesmo índice de `s`.
    """
    codigos, distintos = pd.factorize(s, use_na_sentinel=True)
    convertidos = np.array([fn(v) for v in distintos], dtype=object)
    saida = np.empty(len(s), dtype=object)
    conhecidos = codigos >= 0
    saida[conhecidos] = convertidos[codigos[conhecidos]]
    if (~conhecidos).any():
        saida[~conhecidos] = fn(np.nan)
    return pd.Series(saida, index=s.index)


def texto_por_distintos(s, fn):
    """
    Equivale a `s.apply(lambda x: fn(str(x)) if pd.notna(x) else x)`, por valor distinto.

    POR QUÊ EXISTE: esse lambda aparece em vários pontos de `mesclar_sql_e_reordenar`
    sobre colunas muito repetitivas (Faculdade tem 105 valores em 167 mil linhas).

    O nulo NÃO passa por `fn` — o lambda original também não o passava. Mas a saída é
    montada do zero em vez de copiar a entrada, de propósito: o `.apply()` do pandas
    reconstrói a Series e no caminho normaliza `None` para `NaN`. Preservar o `None`
    original pareceria mais correto e faria a coluna divergir da versão anterior.

    PARÂMETROS: s (Series), fn (callable de um argumento, recebe texto)
    RETORNO: Series de object, com o mesmo índice de `s`.
    """
    resultado = pd.Series(np.nan, index=s.index, dtype=object)
    preenchidos = s.notna()
    if preenchidos.any():
        resultado[preenchidos] = aplicar_por_distintos(s[preenchidos], lambda v: fn(str(v)))
    return resultado


def remover_caixa_alta_df(df):
    """
    Title Case nas colunas de texto, preservando as siglas (CPF, CNPJ, IES, OVG, IA, RIAF).

    O resultado é idêntico ao da versão anterior (apply célula a célula), mas a
    transformação roda sobre os valores DISTINTOS da coluna e volta por map().
    As colunas de texto do relatório são altamente repetitivas — nome de IES, status,
    curso, diagnóstico — então o número de distintos é ordens de magnitude menor que
    o de linhas. Medido em 166.849 x 62: 28,9s -> 8,6s, com .equals() == True.
    """
    if df is None or df.empty: return df
    colunas_protegidas = ['tipo_documento', 'Documento Tipo', 'Faculdade', 'MANTENEDORA', 'IES']
    for col in df.columns:
        if col in colunas_protegidas:
            continue
        if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
            try:
                s = df[col]
                # Só as células que são realmente str são tocadas — igual ao
                # isinstance(x, str) do apply original. Número solto ou NaN numa
                # coluna object continua intacto.
                eh_str = s.map(type).eq(str)
                if not eh_str.any():
                    continue
                distintos = pd.unique(s[eh_str])
                convertidos = pd.Series(distintos, dtype=object).astype(str)
                if col == 'gemini_inconsistencia':
                    convertidos = convertidos.str.capitalize()
                else:
                    convertidos = convertidos.str.title()
                convertidos = convertidos.str.replace(
                    _RE_SIGLAS, lambda m: _MAPA_SIGLAS[m.group(1)], regex=True
                )
                df.loc[eh_str, col] = s[eh_str].map(dict(zip(distintos, convertidos)))
            except:
                pass
    return df


def escrever_aba(writer, nome_aba, df, fmt_header=None):
    """
    O QUE FAZ: Escreve um DataFrame numa aba nova, produzindo exatamente as mesmas células
    que `df.to_excel(writer, sheet_name=nome_aba, index=False)` produzia.
    POR QUÊ EXISTE: o `to_excel` do pandas monta um objeto por célula antes de repassar ao
    XlsxWriter. Nas abas grandes do relatório isso domina o tempo de geração: medido em
    64.682 x 62, a escrita cai de 44,0s para 12,5s (3,5x) escrevendo por coluna.
    COMO FUNCIONA: cria a worksheet direto no workbook, registra em writer.sheets (para
    `aplicar_formatacao_visual` continuar achando a aba pelo nome) e usa write_column,
    normalizando os tipos do pandas do mesmo jeito que o pandas normalizava:
      - NaN / pd.NA / NaT  -> célula em branco
      - +inf / -inf        -> texto 'inf' / '-inf'
      - datetime64         -> datetime nativo COM num_format de data na célula
    PARÂMETROS: writer (pd.ExcelWriter), nome_aba (str), df (DataFrame), fmt_header (Format|None)
    RETORNO: a worksheet criada
    """
    worksheet = writer.book.add_worksheet(nome_aba)
    writer.sheets[nome_aba] = worksheet

    for i, nome in enumerate(df.columns):
        if fmt_header is not None:
            worksheet.write(0, i, str(nome), fmt_header)
        else:
            worksheet.write(0, i, str(nome))

    fmt_data = None
    for i, nome in enumerate(df.columns):
        s = df[nome]

        if pd.api.types.is_datetime64_any_dtype(s):
            if fmt_data is None:
                fmt_data = writer.book.add_format({'num_format': _FORMATO_DATA_PANDAS})
            worksheet.write_column(1, i, [None if pd.isna(v) else v.to_pydatetime() for v in s], fmt_data)
            continue

        # Coluna numérica sai por máscara, não por laço. O py-spy mostrou 22s de uma
        # execução gastos só chamando np.isnan e np.isinf uma vez por célula — numa aba
        # de 310 mil linhas isso é milhões de chamadas para responder algo que o NumPy
        # resolve na coluna inteira de uma vez. O caso comum (nenhum NaN, nenhum inf)
        # nem chega a montar lista nova.
        # O teste é pelo dtype do NumPy, não por is_float_dtype: os tipos anuláveis do
        # pandas (Float64, Int64) também respondem como float/int, mas guardam pd.NA e
        # estouram num to_numpy(dtype=float). Eles seguem pelo laço, como antes.
        dtype_numpy = isinstance(s.dtype, np.dtype)

        if dtype_numpy and s.dtype.kind == 'f':
            arr = s.to_numpy(copy=False)
            limpos = arr.tolist()
            nulos = np.isnan(arr)
            if nulos.any():
                for j in np.flatnonzero(nulos):
                    limpos[j] = None
            infinitos = np.isinf(arr)
            if infinitos.any():
                for j in np.flatnonzero(infinitos):
                    limpos[j] = 'inf' if arr[j] > 0 else '-inf'
        elif dtype_numpy and s.dtype.kind in 'iub':
            # Não admitem NaN nem inf: o laço não teria o que fazer.
            limpos = s.tolist()
        else:
            # Coluna object: pode misturar texto, None, pd.NA e float solto.
            limpos = []
            for v in s.tolist():
                if v is None or v is pd.NA:
                    limpos.append(None)
                elif isinstance(v, float):
                    if np.isnan(v):
                        limpos.append(None)
                    elif np.isinf(v):
                        limpos.append('inf' if v > 0 else '-inf')
                    else:
                        limpos.append(v)
                else:
                    limpos.append(v)
        worksheet.write_column(1, i, limpos)

    return worksheet


def aplicar_formatacao_visual(writer, nome_aba, df):
    """
    O QUE FAZ: Adiciona estilos visuais (cores, negrito, larguras, tabelas nativas) às abas do Excel.
    POR QUÊ EXISTE: O relatório final deve ser entregue em padrão gerencial pronto para leitura humana.
    COMO FUNCIONA: Acessa o objeto workbook/worksheet interno do pandas (XlsxWriter). 
    Injeta larguras calculadas dinamicamente e formatações condicionais (Semáforos Vermelho/Amarelo/Verde).
    PARÂMETROS: writer (pd.ExcelWriter), nome_aba (str), df (DataFrame pandas)
    """
    workbook = writer.book
    worksheet = writer.sheets[nome_aba]
    
    if nome_aba == 'Envios & Pendências':
        worksheet.set_tab_color('#CDC0D9')
    elif nome_aba == 'Pagamentos':
        worksheet.set_tab_color('#F8C4B4')
    elif nome_aba in ['Contrato', 'Contratos', 'Riaf', 'Benefício', 'Benefícios', 'Financiamento', 'Histórico']:
        worksheet.set_tab_color('#DAEEF3')
    
    # --- 1. Definição de Formatos Numéricos Base ---
    fmt_cpf = workbook.add_format({'num_format': '00000000000', 'valign': 'vcenter', 'align': 'center'})
    fmt_cnpj = workbook.add_format({'num_format': '00000000000000', 'valign': 'vcenter', 'align': 'center'}) 
    fmt_num = workbook.add_format({'num_format': '0', 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda = workbook.add_format({'num_format': 'R$ #,##0.00;[Red]-R$ #,##0.00', 'valign': 'vcenter', 'align': 'center'}) 
    fmt_pct = workbook.add_format({'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    fmt_padrao = workbook.add_format({'valign': 'vcenter', 'align': 'center'})
    fmt_wrap = workbook.add_format({'valign': 'vcenter', 'align': 'center', 'text_wrap': True})
    fmt_esq = workbook.add_format({'valign': 'vcenter', 'align': 'left'})
    fmt_esq_wrap = workbook.add_format({'valign': 'vcenter', 'align': 'left', 'text_wrap': True})
    
    # --- 2. Cabeçalho Blindado (Tudo Branco no Fundo Azul Escuro) ---
    fmt_header = workbook.add_format({
        'bold': True,
        'font_color': '#FFFFFF',
        'bg_color': '#1F497D',
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True
    })

    f_verde = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_verm  = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    
    # Formatos de Porcentagem para Envios & Pendências
    f_pct_verm = workbook.add_format({'bg_color': '#E6B8B7', 'font_color': '#000000', 'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    f_pct_amar = workbook.add_format({'bg_color': '#FAEFA0', 'font_color': '#000000', 'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    f_pct_verd = workbook.add_format({'bg_color': '#D8E4BC', 'font_color': '#000000', 'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    f_amar  = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_cinza = workbook.add_format({'bg_color': '#D9D9D9', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_laranja = workbook.add_format({'bg_color': '#FCD5B4', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    
    f_st_valido = workbook.add_format({'bg_color': '#92D050', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_st_invalido = workbook.add_format({'bg_color': '#C0504D', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_st_f_valido = workbook.add_format({'bg_color': '#CCC0DA', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_st_f_invalido = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})
    f_st_nao_proc = workbook.add_format({'bg_color': '#B8CCE4', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center'})

    max_row = len(df)
    max_col = len(df.columns) - 1

    # --- 4. Aplicar Tabela Oficial (Com o nosso cabeçalho forçado) ---
    col_settings = [{'header': str(col), 'header_format': fmt_header} for col in df.columns]
    
    worksheet.add_table(0, 0, max_row, max_col, {
        'columns': col_settings,
        'style': None # Tema base sem zebrado para deixar o fundo limpo
    })
    
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(1, 0)
    worksheet.set_row(0, 35) 

    # --- 5. Ajustar Larguras das Colunas Dinamicamente (Auto-Fit Inteligente) ---
    for i, col in enumerate(df.columns):
        col_upper = str(col).upper()
        
        mapa_larguras_fixas = {
            'MANTENEDORA': (51.29, fmt_esq),
            'IES': (86.57, fmt_esq),
            'SEMESTRE': (13.29, None),
            'TOTAL BENEFICIÁRIOS': (21.57, None),
            'ATIVOS': (10.43, None),
            'DESLIGADOS': (14.43, None),
            'ENV. CONTRATO': (19.0, None),
            'PEND. CONTRATO': (20.43, None),
            '% CONTRATO': (16.71, fmt_pct),
            'CONTRATO PROC.': (19.71, None),
            'CONTRATO NÃO PROC.': (24.43, None),
            '% CONTRATO PROC.': (21.86, fmt_pct),
            'ENV. FINANCIAMENTO': (24.71, None),
            'PEND. FINANCIAMENTO': (26.29, None),
            '% FINANCIAMENTO': (22.57, fmt_pct),
            'FINANCIAMENTO PROC.': (25.57, None),
            'FINANCIAMENTO NÃO PROC.': (30.29, None),
            '% FINANCIAMENTO PROC.': (27.57, fmt_pct),
            'ENV. BENEFÍCIOS': (19.43, None),
            'PEND. BENEFÍCIOS': (20.86, None),
            '% BENEFÍCIOS': (17.29, fmt_pct),
            'BENEFÍCIOS PROC.': (20.14, None),
            'BENEFÍCIOS NÃO PROC.': (24.86, None),
            '% BENEFÍCIOS PROC.': (22.29, fmt_pct),
            'ENV. RIAF': (13.0, None),
            'PEND. RIAF': (14.43, None),
            '% RIAF': (10.86, fmt_pct),
            'RIAF PROC.': (13.71, None),
            'RIAF NÃO PROC.': (18.43, None),
            '% RIAF PROC.': (15.71, fmt_pct),
            'ENV. HISTÓRICO': (18.71, None),
            'PEND. HISTÓRICO': (20.14, None),
            '% HISTÓRICO': (16.43, fmt_pct),
            'HISTÓRICO PROC.': (19.43, None),
            'HISTÓRICO NÃO PROC.': (24.14, None),
            '% HISTÓRICO PROC.': (21.57, fmt_pct),
            'TIPO_DOCUMENTO': (82.86, fmt_esq),
            'STATUS_IA': (14.43, None),
            'GEMINI_INCONSISTENCIA': (54.57, fmt_esq_wrap),
            'GEMINI_SEMESTRE': (20.43, None),
            'BOLSISTA': (46.0, fmt_esq),
            'INSCRICAO': (12.57, fmt_num),
            'INSCRICAO_ANTERIOR': (20.86, fmt_num),
            'INSCRICAO_POSTERIOR': (22.0, fmt_num),
            'CPF': (11.29, fmt_cpf),
            'GEMINI_CPF': (14.71, fmt_cpf),
            'MUDOU_BOLSA': (17.0, None),
            'TIPO_BOLSA_FINAL': (19.29, None),
            'GEMINI_TIPO_BOLSA_FINAL': (26.71, None),
            'BOLSA_ANTERIOR': (17.86, None),
            'BOLSA_POSTERIOR': (18.86, None),
            'EMAIL': (46.43, fmt_esq),
            'GEMINI_EMAIL': (51.43, fmt_esq),
            'TELEFONE_1': (14.57, fmt_num),
            'TELEFONE_2': (14.57, fmt_num),
            'DATA_NASCIMENTO': (20.14, None),
            'FACULDADE': (74.29, None),
            'CNPJ_IES': (14.43, fmt_cnpj),
            'GEMINI_NOME_FACULDADE': (74.29, None),
            'CURSO': (43.0, None),
            'GEMINI_CURSO': (43.0, None),
            'GEMINI_ASSINATURA_ALUNO': (27.43, None),
            'GEMINI_ASSINATURA_IES': (24.86, None),
            'STATUS_VINCULO': (17.71, None),
            'SITUACAO_MOTIVO': (45.14, None),
            'OBSERVACAO_SITUACAO': (81.29, None),
            'MUDOU_IES': (14.71, None),
            'IES_ANTERIOR': (70.43, None),
            'IES_POSTERIOR': (73.29, None),
            'MATRICULA': (18.57, fmt_num),
            'PERIODO_ATUAL': (17.43, None),
            'GEMINI_PERIODO': (19.14, None),
            'QTD_PERIODOS': (16.71, None),
            'GEMINI_QTD_PERIODOS': (24.14, None),
            'MODALIDADE': (15.43, None),
            'VALOR_BENEFICIO': (18.86, fmt_moeda),
            'SOMA_VALOR_BENEFICIO': (24.71, fmt_moeda),
            'VALOR_FINANCIAMENTO': (23.43, fmt_moeda),
            'SOMA_VALOR_FINANCIAMENTO': (29.43, fmt_moeda),
            'MATRICULA_SEM_DESC': (23.14, fmt_moeda),
            'GEMINI_MATRICULA_SEM_DESC': (30.57, fmt_moeda),
            'MATRICULA_SD_DOC': (35.57, None),
            'MATRICULA_COM_DESC': (23.14, fmt_moeda),
            'GEMINI_MATRICULA_COM_DESC': (30.57, fmt_moeda),
            'MATRICULA_CD_DOC': (35.57, None),
            'MENSALIDADE_SEM_DESC': (26.43, fmt_moeda),
            'GEMINI_MENSALIDADE_SEM_DESC': (33.86, fmt_moeda),
            'DIF_SEM_DESC': (17.14, fmt_moeda),
            'PERC_DIF_SEM_DESC': (22.14, fmt_pct),
            'TOTAL_DIF_SEM_DESC': (22.43, fmt_moeda),
            'MSD_SOMA': (14.29, fmt_moeda),
            'G_MSD_SOMA': (16.29, fmt_moeda),
            'MSD_DOC': (35.57, None),
            'MENSALIDADE_COM_DESC': (26.43, fmt_moeda),
            'GEMINI_MENSALIDADE_COM_DESC': (33.86, fmt_moeda),
            'DIF_COM_DESC': (17.14, fmt_moeda),
            'PERC_DIF_COM_DESC': (22.14, fmt_pct),
            'TOTAL_DIF_COM_DESC': (22.43, fmt_moeda),
            'MCD_SOMA': (14.29, fmt_moeda),
            'G_MCD_SOMA': (16.29, fmt_moeda),
            'MCD_DOC': (35.57, None),
            'ULTIMO_VALOR_PAGO_REF': (25.43, fmt_moeda),
            'TOTAL_BOLSA_PAGA': (20.0, fmt_moeda),
            'QTD_PAGTOS': (14.71, None),
            'QTD_PAGTOS_RETROATIVOS': (25.86, None),
            'BENEFICIO': (21.29, None),
            'FINANCIAMENTO': (19.86, None),
            'SOMA_OVG_DEVIA_PAGAR_SIS': (29.14, fmt_moeda),
            'SOMA_OVG_DEVIA_PAGAR_IA': (28.43, fmt_moeda),
            'SOMA_PREJUIZO_OVG': (22.29, fmt_moeda),
            'SOMA_ECONOMIA_OVG': (23.71, fmt_moeda),
            'DIAGNOSTICO_FINANCEIRO_FINAL': (30.57, None),
            'DATA_COLETA': (15.14, None),
            'DATA_COLETA_ATUAL_SISTEMA': (28.86, None),
            'DATA_CREATE': (17.86, None),
            'DATA_PROCESSAMENTO': (23.57, None),
            'PROCESSADO': (14.86, None),
            'PROCESSAR': (13.29, None),
            'QTD_TOKEN': (14.0, None),
            'QTD_DISCIPLINAS_MATRICULADAS': (31.0, None),
            'QTD_DISCIPLINAS_REPROVADAS': (29.57, None),
            'PERFIL': (9.71, None),
        }
        
        if nome_aba == 'Benefícios':
            mapa_larguras_fixas['STATUS_IA'] = (12.71, None)
            mapa_larguras_fixas['GEMINI_INCONSISTENCIA'] = (24.86, fmt_esq_wrap)
            mapa_larguras_fixas['MSD_DOC'] = (33.14, None)
            mapa_larguras_fixas['MCD_DOC'] = (33.14, None)
            mapa_larguras_fixas['DATA_CREATE'] = (15.29, None)
        elif nome_aba == 'Financiamento':
            mapa_larguras_fixas['STATUS_IA'] = (12.71, None)
            mapa_larguras_fixas['GEMINI_INCONSISTENCIA'] = (24.86, fmt_esq_wrap)
            mapa_larguras_fixas['IES_ANTERIOR'] = (69.71, None)
            mapa_larguras_fixas['IES_POSTERIOR'] = (71.43, None)
            mapa_larguras_fixas['CURSO'] = (41.86, None)
            mapa_larguras_fixas['MSD_DOC'] = (33.14, None)
            mapa_larguras_fixas['MCD_DOC'] = (33.14, None)
            mapa_larguras_fixas['BENEFICIO'] = (18.71, None)
            mapa_larguras_fixas['DATA_CREATE'] = (15.29, None)
            mapa_larguras_fixas['EMAIL'] = (44.86, fmt_esq)
            mapa_larguras_fixas['MATRICULA'] = (14.43, None)
        elif nome_aba == 'Histórico':
            mapa_larguras_fixas['GEMINI_INCONSISTENCIA'] = (47.43, fmt_esq_wrap)
            mapa_larguras_fixas['MSD_DOC'] = (33.14, None)
            mapa_larguras_fixas['MCD_DOC'] = (33.14, None)
            
        if col_upper in mapa_larguras_fixas:
            l_fixa, fmt_fixo = mapa_larguras_fixas[col_upper]
            fmt_uso = fmt_fixo if fmt_fixo else fmt_padrao
            worksheet.set_column(i, i, l_fixa, fmt_uso)
            continue
            
        # OTIMIZAÇÃO: Só calcula auto-fit se a coluna NÃO estiver no mapa de fixas. Faz amostragem para evitar gargalo.
        max_len = 0
        if not df.empty:
            amostra = df[col].dropna()
            if len(amostra) > 1000:
                amostra = amostra.sample(1000)
            if not amostra.empty:
                max_len = amostra.astype(str).str.len().max()
                
        tamanho_conteudo = int(max_len) if pd.notna(max_len) else 0
        largura_ideal = max(tamanho_conteudo, len(str(col))) + 3 # +3 de respiro para a seta do filtro
        if largura_ideal > 50: largura_ideal = 50 # Trava em 50 para não estourar a tela
            
        # Aplica a largura ideal calculada com a formatação correta
        if '%' in col_upper or col_upper.startswith('PERC_'):
            worksheet.set_column(i, i, max(12, largura_ideal), fmt_pct)
        elif 'CNPJ' in col_upper:
            worksheet.set_column(i, i, max(18, largura_ideal), fmt_cnpj)
        elif 'CPF' in col_upper:
            worksheet.set_column(i, i, max(16, largura_ideal), fmt_cpf)
        elif col in COLS_NUM or col_upper in ['QTD_PAGTOS', 'QTD_PAGTOS_RETROATIVOS', 'QTD_PERIODOS', 'GEMINI_QTD_PERIODOS', 'GEMINI_NUMERO_SEMESTRES', 'GEMINI_SEMESTRES_FEITOS', 'GEMINI_SEMESTRES_FINANCIADOS', 'QTD_TOKEN', 'QTDE_TOKEN']:
            worksheet.set_column(i, i, max(12, largura_ideal), fmt_num)
        elif col in COLS_MOEDA or any(x in col_upper for x in ['DIF.', 'DIF_', 'BOLSA PAGA', 'BOLSA_PAGA', 'VALOR', 'SOMA', 'PAGOU', 'PAGAR', 'PREJUIZO', 'ECONOMIA']) or col_upper.endswith('_DESC') or col_upper.endswith('_DOC'): 
            worksheet.set_column(i, i, max(18, largura_ideal), fmt_moeda) 
        elif 'INCONSISTENCIA' in col_upper or 'INCONSISTÊNCIAS' in col_upper:
            worksheet.set_column(i, i, max(30, largura_ideal), fmt_wrap)
        else:
            worksheet.set_column(i, i, largura_ideal, fmt_padrao)

    # --- 6. Formatação Condicional (O Semáforo Padronizado) ---
    # --- 6. Formatação Estática (Substitui Condicional para permitir edição manual) ---
    for i, col in enumerate(df.columns):
        if col in ['Status_IA', 'status_ia']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Válido"', 'format': f_st_valido})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Inválido"', 'format': f_st_invalido})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Ausente"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Falso Válido"', 'format': f_st_f_valido})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Falso Inválido"', 'format': f_st_f_invalido})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Não Processado"', 'format': f_st_nao_proc})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Corrompido"', 'format': f_laranja})

        elif col in ['Diagnóstico Financeiro Final', 'diagnostico_financeiro_final']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Pagamento correto"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a mais"', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a menos"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não localizado', 'format': f_laranja})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não realizado', 'format': f_cinza})

        # Alertas de OVG DEVERIA PAGAR (Pinta de vermelho o bloco se for menor que 0)
        elif col in ['OVG Deveria Pagar (Último Referencial)', 'OVG Deveria Pagar (IA)', 'ovg_devia_pagar_ult_ref', 'ovg_devia_pagar_ia']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '<', 'value': 0, 'format': f_verm})

        # Alerta para Diferenças de Mensalidade (Qualquer divergência acende o bloco vermelho)
        elif col in ['Dif. s/Desc.', 'Total Dif. s/Desc.', 'Dif. c/Desc.', 'Total Dif. c/Desc.']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '!=', 'value': 0, 'format': f_verm})
        
        # Alerta Financeiro Vermelho (Prejuízos gritam em vermelho se for maior que 0)
        elif col in ['Prejuízo da OVG (R$)', 'Soma Prejuízo da OVG (R$)']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verm})
            
        # NOVA COLUNA: Economia da OVG (Grita em VERDE se for maior que 0)
        elif col == 'Economia da OVG (R$)':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verde})
            
        # Regra de Cores para Porcentagens na aba Envios & Pendências
        elif nome_aba == 'Envios & Pendências' and ('%' in str(col).upper() or str(col).upper().startswith('PERC_')):
            from xlsxwriter.utility import xl_col_to_name
            c_let = xl_col_to_name(i)
            col_u = str(col).upper()
            
            # Verde: 100% ou mais
            worksheet.conditional_format(1, i, max_row, i, {'type': 'formula', 'criteria': f'={c_let}2>=1.0', 'format': f_pct_verd})
            
            # Amarelo: Entre 50% e 99%
            worksheet.conditional_format(1, i, max_row, i, {'type': 'formula', 'criteria': f'=AND(ISNUMBER({c_let}2), {c_let}2>=0.50, {c_let}2<1.0)', 'format': f_pct_amar})
            
            # Vermelho: Menor que 50%
            if 'FINANCIAMENTO' in col_u or 'BENEFÍCIO' in col_u or 'BENEFICIO' in col_u:
                # Exceção pedida: não pintar 0% para Financiamento e Benefício
                worksheet.conditional_format(1, i, max_row, i, {'type': 'formula', 'criteria': f'=AND(ISNUMBER({c_let}2), {c_let}2>0, {c_let}2<0.50)', 'format': f_pct_verm})
            else:
                # Demais colunas: pintar 0%, mas ignorar células vazias
                worksheet.conditional_format(1, i, max_row, i, {'type': 'formula', 'criteria': f'=AND(ISNUMBER({c_let}2), {c_let}2<0.50)', 'format': f_pct_verm})

    worksheet.ignore_errors({
        'number_stored_as_text': 'A1:XFD1048576',
        'eval_error': 'A1:XFD1048576',
        'formula_differs': 'A1:XFD1048576',
        'formula_range': 'A1:XFD1048576',
        'formula_unlocked': 'A1:XFD1048576',
        'empty_cell_reference': 'A1:XFD1048576',
        'list_data_validation': 'A1:XFD1048576',
        'calculated_column': 'A1:XFD1048576',
        'two_digit_text_year': 'A1:XFD1048576'
    })
        
# ==========================================
# 3. EXTRAÇÃO FINANCEIRA VIA SQL
# ==========================================
_ENGINE_CACHE = None

def get_engine():
    """
    O QUE FAZ: Devolve a engine SQLAlchemy do banco SIBU, criando-a na primeira chamada.
    POR QUÊ EXISTE: A geração do relatório abre várias consultas em massa; recriar a engine
    a cada uma descartaria o pool de conexões.
    COMO FUNCIONA: Guarda a instância em _ENGINE_CACHE e lê as credenciais do .env. Usa o
    driver mysql-connector (o ORM do Django usa mysqlclient — os dois convivem de propósito).
    PARÂMETROS: nenhum
    RETORNO: sqlalchemy.Engine
    """
    global _ENGINE_CACHE
    if _ENGINE_CACHE is None:
        DB_HOST = os.getenv('SIBU_BANCO_DADOS_HOST')
        DB_USER = os.getenv('SIBU_BANCO_DADOS_USER')
        DB_PASS = os.getenv('SIBU_BANCO_DADOS_PASS')
        DB_NAME = os.getenv('SIBU_BANCO_DADOS_NAME')
        
        _ENGINE_CACHE = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}/{DB_NAME}',
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            connect_args={'connect_timeout': 30}
        )
    return _ENGINE_CACHE

def buscar_dados_financeiros_sql(semestres_presentes, inscricoes=None):
    """
    O QUE FAZ: Busca a situação cadastral cruzando via Polars SQLContext no Parquet Local (Stateless Database).
    """
    if not semestres_presentes: return pd.DataFrame()
    
    sems_banco = [str(x).strip().replace('-', '/') for x in semestres_presentes]
    sems_formatados = ",".join([f"'{x}'" for x in sems_banco])
    
    caminho_beneficiarios = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_coleta_de_dados_beneficiarios_temp_d1{SUFIXO_TABELAS}.parquet")
    caminho_pagamentos = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_coleta_de_dados_pagamentos_temp_d1{SUFIXO_TABELAS}.parquet")
    
    if not (os.path.exists(caminho_beneficiarios) and os.path.exists(caminho_pagamentos)):
        print(f"[GGCI       | ERRO          | POLARS  ] Arquivos Parquet base não encontrados.")
        print("[GGCI       | ERRO          | ABORTO  ] Abortando execução.")
        sys.exit(1)
        
    # ATENÇÃO ao nome de `qtd_pagtos_retroativos`: apesar de "retroativo", ela conta os
    # pagamentos CANCELADOS A 100%, ou seja, bolsa devolvida. Cancelamento parcial (40%,
    # 60%...) NÃO entra nessa contagem — aquele caso aparece como valor cancelado na aba
    # Pagamentos e o pagamento segue valendo. "Retroativo" na aba Pagamentos é outra coisa
    # e não implica devolução; são conceitos distintos com nomes parecidos.
    # Consequência prática: `qtd_pagtos == qtd_pagtos_retroativos` significa "todo o repasse
    # do semestre foi devolvido". Isso NÃO é motivo para esconder o beneficiário do
    # relatório — ver o comentário sobre o descarte removido em `calcular_auditoria_ia`.
    query = f"""
        SELECT 
            b.codigo_aluno AS uni_codigo, b.semestre, b.tipo_bolsa AS tipo_bolsa_final,
            SUM(p.qtd_pagtos) AS qtd_pagtos, SUM(p.qtd_pagtos_retroativos) AS qtd_pagtos_retroativos, MAX(p.bolsa_paga) AS último_valor_pago_referencia,
            MAX(p.valor_mensalidade_sem_desconto) AS valor_mensalidade_sem_desconto, MAX(p.valor_mensalidade_com_desconto) AS valor_mensalidade_com_desconto,
            b.status_vinculo AS situacao, b.status_vinculo AS situacao_atual_sistema, b.data_inclusao AS sit_data_atual_sistema, b.ultima_observacao AS sit_obs_atual_sistema,
            b.ultimo_motivo AS sit_motivos, b.ultima_observacao AS sit_obs,
            MAX(p.valor_beneficio) AS valor_beneficio, MAX(p.desc_outro_beneficio) AS qual_beneficio, MAX(p.valor_financiamento) AS valor_financiamento, MAX(p.desc_financiamento) AS qual_financiamento,
            MAX(p.data_atualizacao_coleta) AS data_coleta, MAX(p.data_atualizacao_coleta) AS data_coleta_atual_sistema,
            b.inclusao AS inscricao_ano_semestre, b.flag_deficiencia AS uni_deficiencia, b.sexo AS uni_sexo, 'N/A' AS tipo_bolsista_renovacao, b.perfil AS perfil,
            b.data_nascimento, b.email_aluno AS email, b.telefone_principal AS telefone_1, b.telefone_secundario AS telefone_2, b.periodo_atual, b.periodo_quantidade, 
            b.matricula_ies AS matricula, 
            b.modalidade_curso AS modalidade,
            b.ins_cnpj, b.ins_razao_social, b.ins_nome_fantasia, b.ins_mantenedora, b.nome_faculdade_sql, MAX(p.valor_matricula_sem_desconto) AS valor_matricula_sem_desconto, MAX(p.valor_matricula_com_desconto) AS valor_matricula_com_desconto,
            b.nome_aluno AS Bolsista_sql, b.cpf_aluno AS UNI_CPF, b.curso_aluno AS CUR_NOME,
            b.qtd_disciplinas_matriculadas, b.qtd_disciplinas_reprovadas
        FROM beneficiarios b
        LEFT JOIN pagamentos p ON b.codigo_aluno = p.codigo_aluno AND b.semestre = p.semestre_referencia_analise
        WHERE (b.semestre IN ({sems_formatados}) {f"OR b.codigo_aluno IN ({','.join(map(str, inscricoes))})" if inscricoes else ""})
        GROUP BY b.codigo_aluno, b.semestre, b.tipo_bolsa, b.status_vinculo, b.data_inclusao, b.ultima_observacao, b.ultimo_motivo, b.inclusao, b.flag_deficiencia, b.sexo, b.perfil, b.data_nascimento, b.email_aluno, b.telefone_principal, b.telefone_secundario, b.periodo_atual, b.periodo_quantidade, b.matricula_ies, b.modalidade_curso, b.ins_cnpj, b.ins_razao_social, b.ins_nome_fantasia, b.ins_mantenedora, b.nome_faculdade_sql, b.nome_aluno, b.cpf_aluno, b.curso_aluno, b.qtd_disciplinas_matriculadas, b.qtd_disciplinas_reprovadas
    """
    
    try:
        start_time = time.time()
        lf_benef = pl.scan_parquet(caminho_beneficiarios)
        lf_pag = pl.scan_parquet(caminho_pagamentos)
        
        ctx = pl.SQLContext(beneficiarios=lf_benef, pagamentos=lf_pag)
        df_sql_pl = ctx.execute(query).collect()
        df_sql = df_sql_pl.to_pandas()
            
        end_time = time.time()
        print(f"[GGCI       | POLARS SQL    | FINANC] Carregado ({end_time - start_time:.2f}s)")
        
        if not df_sql.empty:
            df_sql['uni_codigo'] = pd.to_numeric(df_sql['uni_codigo'], errors='coerce').astype('Int64')
            df_sql = df_sql.dropna(subset=['uni_codigo']) 
            df_sql['semestre'] = df_sql['semestre'].astype(str).str.strip()
            
            alunos_unicos = df_sql['uni_codigo'].unique()
            index = pd.MultiIndex.from_product([alunos_unicos, sems_banco], names=['uni_codigo', 'semestre'])
            df_skeleton = pd.DataFrame(index=index).reset_index()
            
            df_merged = pd.merge(df_skeleton, df_sql, on=['uni_codigo', 'semestre'], how='outer')
            # Sort by uni_codigo and semestre to ensure chronological order before ffill/bfill
            df_merged = df_merged.sort_values(by=['uni_codigo', 'semestre']).reset_index(drop=True)
            
            if 'tipo_bolsa_final' in df_merged.columns:
                df_merged['tipo_bolsa_final'] = df_merged.groupby('uni_codigo')['tipo_bolsa_final'].ffill().bfill()
                
            cols_absolutas = [
                'situacao', 'sit_motivos', 'sit_obs', 'nome_faculdade_sql',
                'valor_mensalidade_sem_desconto', 'valor_mensalidade_com_desconto',
                'valor_beneficio', 'valor_financiamento', 'qual_beneficio', 'qual_financiamento',
                'valor_matricula_sem_desconto', 'valor_matricula_com_desconto',
                'situacao_atual_sistema', 'sit_data_atual_sistema', 'data_coleta_atual_sistema', 
                'sit_obs_atual_sistema', 'inscricao_ano_semestre', 'uni_deficiencia', 'uni_sexo', 
                'tipo_bolsista_renovacao', 'perfil', 'data_nascimento', 'email', 'telefone_1', 
                'telefone_2', 'periodo_atual', 'periodo_quantidade', 'matricula', 'modalidade', 
                'ins_cnpj', 'ins_razao_social', 'ins_nome_fantasia', 'ins_mantenedora', 
                'Bolsista_sql', 'UNI_CPF', 'CUR_NOME', 'qtd_disciplinas_matriculadas', 
                'qtd_disciplinas_reprovadas'
            ]
            
            # OTIMIZAÇÃO: ffill e bfill vetorizado de todas as colunas simultaneamente
            cols_presentes = [c for c in cols_absolutas if c in df_merged.columns]
            if cols_presentes:
                df_merged[cols_presentes] = df_merged[cols_presentes].replace(['', None, 'nan', 'NaN'], np.nan)
                df_merged[cols_presentes] = df_merged.groupby('uni_codigo')[cols_presentes].ffill()
                df_merged[cols_presentes] = df_merged.groupby('uni_codigo')[cols_presentes].bfill()
                
            valores_para_zerar = {
                'qtd_pagtos': 0, 'último_valor_pago_referencia': 0.0,
                'valor_mensalidade_sem_desconto': 0.0, 'valor_mensalidade_com_desconto': 0.0,
                'situacao': '', 'situacao_atual_sistema': '',
                'sit_data_atual_sistema': '', 'sit_obs_atual_sistema': '',
                'valor_beneficio': 0.0, 'valor_financiamento': 0.0,
                'qual_beneficio': 'Sem Benefícios', 'qual_financiamento': 'Sem Financiamento',
                'data_coleta': '',
                'inscricao_ano_semestre': '', 'uni_deficiencia': '', 'uni_sexo': '', 'tipo_bolsista_renovacao': '', 'perfil': '',
                'data_nascimento': '', 'email': '', 'telefone_1': '', 'telefone_2': '', 'periodo_atual': '', 'periodo_quantidade': '', 'matricula': '', 'modalidade': '',
                'ins_cnpj': '', 'ins_razao_social': '', 'ins_nome_fantasia': '', 'ins_mantenedora': '', 'valor_matricula_sem_desconto': 0.0, 'valor_matricula_com_desconto': 0.0
            }
            df_merged.fillna(valores_para_zerar, inplace=True)
            
            if 'tipo_bolsa_final' in df_merged.columns:
                df_merged['tipo_bolsa_final'] = df_merged['tipo_bolsa_final'].fillna("SEM DADOS")
                
            if 'data_coleta' in df_merged.columns:
                df_merged['data_coleta'] = pd.to_datetime(df_merged['data_coleta'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                
            df_sql = df_merged.copy()
            
            df_sql['semestre'] = df_sql['semestre'].str.replace('/', '-')
            df_sql['qtd_pagtos'] = pd.to_numeric(df_sql['qtd_pagtos'], errors='coerce').fillna(0).astype(int)
            df_sql['último_valor_pago_referencia'] = pd.to_numeric(df_sql['último_valor_pago_referencia'], errors='coerce').fillna(0.0)
            def parse_money(series):
                if series.dtype == 'object':
                    s = series.astype(str).str.replace('R$', '', regex=False).str.strip()
                    mask_has_both = s.str.contains(r'\.', regex=True) & s.str.contains(r'\,', regex=True)
                    s.loc[mask_has_both] = s.loc[mask_has_both].str.replace('.', '', regex=False)
                    s = s.str.replace(',', '.', regex=False)
                    return pd.to_numeric(s, errors='coerce')
                return pd.to_numeric(series, errors='coerce')
                
            df_sql['valor_mensalidade_sem_desconto'] = parse_money(df_sql['valor_mensalidade_sem_desconto']).fillna(0.0)
            df_sql['valor_mensalidade_com_desconto'] = parse_money(df_sql['valor_mensalidade_com_desconto']).fillna(0.0)
            df_sql['valor_beneficio'] = parse_money(df_sql['valor_beneficio']).fillna(0.0)
            df_sql['valor_financiamento'] = parse_money(df_sql['valor_financiamento']).fillna(0.0)
            
            df_sql = df_sql.drop_duplicates(subset=['uni_codigo', 'semestre'], keep='last')
            #             print("[GGCI       | SQL           | FINANC] Sucesso.")
            
        return df_sql
    except Exception as e:
        print(f"[GGCI       | ERRO          | SQL   ] Conexão falhou.")
        print(f"[GGCI       | ERRO          | DETALH] {e}")
        print("[GGCI       | ERRO          | ABORTO] Abortando execução.")
        sys.exit(1)
        
def buscar_dados_pagamentos_mes_a_mes_sql(semestres_presentes):
    """
    O QUE FAZ: Busca o histórico de repasses mensais usando o Parquet Local via Polars.
    """
    if not semestres_presentes: return pd.DataFrame()
    
    sems_banco = [str(x).strip().replace('-', '/') for x in semestres_presentes]
    sems_formatados = ",".join([f"'{x}'" for x in sems_banco])
    
    caminho_pagamentos = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_coleta_de_dados_pagamentos_temp_d1{SUFIXO_TABELAS}.parquet")
    if not os.path.exists(caminho_pagamentos):
        return pd.DataFrame()
        
    query = f"""
        SELECT 
            codigo_aluno AS uni_codigo, ano_mes_pagto AS lan_anomes, semestre_referencia_analise AS semestre, bolsa_paga AS valr_bolsa, lan_dtlanc,
            valor_mensalidade_sem_desconto AS CD_sem_desconto, valor_mensalidade_com_desconto AS CD_com_desconto, valor_beneficio AS CD_beneficios, valor_financiamento AS CD_financiamentos, data_atualizacao_coleta AS data_coleta,
            qtd_pagtos, qtd_pagtos_retroativos,
            valor_matricula_sem_desconto AS CD_mat_sem_desconto, valor_matricula_com_desconto AS CD_mat_com_desconto,
            lan_valor_complemento, lan_valor_cancelamento
        FROM pagamentos
        WHERE semestre_referencia_analise IN ({sems_formatados})
    """
    
    try:
        start_time = time.time()
        print("[GGCI       | POLARS SQL    | HIST  ] Buscando...")
        
        ctx = pl.SQLContext(pagamentos=pl.scan_parquet(caminho_pagamentos))
        df_sql_mes_pl = ctx.execute(query).collect()
        df_sql_mes = df_sql_mes_pl.to_pandas()
            
        end_time = time.time()
        print(f"[GGCI       | POLARS SQL    | HIST  ] Carregado ({end_time - start_time:.2f}s)")
        
        if not df_sql_mes.empty:
            df_sql_mes['uni_codigo'] = pd.to_numeric(df_sql_mes['uni_codigo'], errors='coerce').astype('Int64')
            # Padroniza "2025/1" para "2025-1" igual ao Excel
            df_sql_mes['semestre'] = df_sql_mes['semestre'].astype(str).str.replace('/', '-').str.strip()
            
        return df_sql_mes
    except Exception as e:
        print(f"[GGCI       | ERRO          | HIST  ] Detalhes: {e}")
        return pd.DataFrame()

def mesclar_sql_e_reordenar(df, df_sql, df_pag=None, df_mes_a_mes=None):
    """
    O QUE FAZ: Concatena a base extraída pelo scraper (df) com os dados lidos do banco (df_sql).
    POR QUÊ EXISTE: Núcleo do processamento de dados cruzados. Junta "O que o portal diz" com "O que o banco diz".
    COMO FUNCIONA: Realiza `pd.merge` pelas chaves (Inscrição + Semestre). Recalcula regras de pagamento teto (Bolsa Parcial x Integral).
    """
    if df.empty: return df
    
    if not df_sql.empty:
        df['Inscrição'] = pd.to_numeric(df['Inscrição'], errors='coerce').astype('Int64')
        df['Semestre'] = df['Semestre'].astype(str).str.strip().str.replace('/', '-')
        
        df_sql['uni_codigo'] = pd.to_numeric(df_sql['uni_codigo'], errors='coerce').astype('Int64')
        df_sql['semestre'] = df_sql['semestre'].astype(str).str.strip().str.replace('/', '-')

        # Merge seguro usando Pandas puro
        df['orig_idx_merge'] = df.index
        df = pd.merge(df, df_sql, left_on=['Inscrição', 'Semestre'], right_on=['uni_codigo', 'semestre'], how='left', suffixes=('', '_sql'))
        
        # Fallback para o último semestre disponível (resolve alunos com semestre divergente no Excel que sumiriam no BD)
        mask = df['uni_codigo'].isna() & df['Inscrição'].notna()
        if mask.any():
            sql_cols = [c for c in df_sql.columns if c not in ['uni_codigo', 'semestre']]
            cols_to_drop = [c for c in sql_cols] + [f"{c}_sql" for c in sql_cols] + ['uni_codigo', 'semestre']
            df_unmatched = df[mask].drop(columns=cols_to_drop, errors='ignore')
            
            # Encontra o último semestre registrado para cada aluno no banco de dados
            df_sql_latest = df_sql.sort_values(by=['uni_codigo', 'semestre']).drop_duplicates(subset=['uni_codigo'], keep='last')
            
            df_remapped = pd.merge(df_unmatched, df_sql_latest, left_on=['Inscrição'], right_on=['uni_codigo'], how='inner', suffixes=('', '_sql'))
            
            if not df_remapped.empty:
                if 'periodo_atual' in df_remapped.columns and 'semestre' in df_remapped.columns and 'Semestre' in df_remapped.columns:
                    def calc_diff(row):
                        try:
                            t_ano, t_sem = str(row['Semestre']).strip().replace('/', '-').split('-')
                            l_ano, l_sem = str(row['semestre']).strip().replace('/', '-').split('-')
                            diff = (int(t_ano) - int(l_ano)) * 2 + (int(t_sem) - int(l_sem))
                            novo_p = int(row['periodo_atual']) + diff
                            return novo_p if novo_p > 0 else row['periodo_atual']
                        except:
                            return row['periodo_atual']
                    df_remapped['periodo_atual'] = df_remapped.apply(calc_diff, axis=1)

                df_remapped.set_index('orig_idx_merge', inplace=True)
                df.set_index('orig_idx_merge', inplace=True)
                df.update(df_remapped)
                df.reset_index(inplace=True)
                
        if 'orig_idx_merge' in df.columns:
            df.drop(columns=['orig_idx_merge'], inplace=True)
            
        # Marca se o semestre existe de fato nas views oficiais do BD (Beneficiarios/Pagamentos)
        df['Semestre_Valido_BD'] = df['uni_codigo'].notna()
        
        # --- PREENCHIMENTO DE DADOS CADASTRAIS FALTANTES (Bolsista, CPF, Faculdade, Curso) ---
        if df_pag is not None and not df_pag.empty:
            df_ativos_temp = df_pag[['SEMESTRE', 'UNI_CODIGO', 'UNI_CPF', 'UNI_NOME', 'INS_NOME', 'CUR_NOME']].drop_duplicates(subset=['UNI_CODIGO', 'SEMESTRE'], keep='last').copy()
            df_ativos_temp['UNI_CODIGO'] = pd.to_numeric(df_ativos_temp['UNI_CODIGO'], errors='coerce').astype('Int64')
            df_ativos_temp['SEMESTRE'] = df_ativos_temp['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
            
            df = pd.merge(df, df_ativos_temp, left_on=['Inscrição', 'Semestre'], right_on=['UNI_CODIGO', 'SEMESTRE'], how='left')
            
            mapping_ativos = {'UNI_NOME': 'Bolsista', 'UNI_CPF': 'CPF', 'INS_NOME': 'Faculdade', 'CUR_NOME': 'Curso'}
            for col_pag, col_df in mapping_ativos.items():
                if col_pag in df.columns:
                    if col_df not in df.columns:
                        df[col_df] = df[col_pag]
                    else:
                        df[col_df] = df[col_df].replace(['', 'nan', 'NaN', 'NAN', 'None', '<NA>', 'NÃO INFORMADO', 'NAO INFORMADO', 'Não Informado'], np.nan)
                        df[col_df] = df[col_df].fillna(df[col_pag])
                    df.drop(columns=[col_pag], inplace=True)
            
            if 'Bolsista' in df.columns:
                df['Bolsista'] = texto_por_distintos(df['Bolsista'], limpar_texto_geral)
                
        if 'Bolsista_sql' in df.columns:
            # The database name (Bolsista_sql) is the source of truth. 
            # We overwrite any existing 'Bolsista' but we only replace if it's not null to avoid dropping existing data when SQL misses it.
            if 'Bolsista' not in df.columns:
                df['Bolsista'] = df['Bolsista_sql']
            else:
                df['Bolsista'] = df['Bolsista_sql'].fillna(df['Bolsista'])
            df.drop(columns=['Bolsista_sql'], inplace=True)
            if 'Bolsista' in df.columns:
                df['Bolsista'] = texto_por_distintos(df['Bolsista'], limpar_texto_geral)
                
        if 'nome_faculdade_sql' in df.columns:
            if 'Faculdade' not in df.columns:
                df['Faculdade'] = df['nome_faculdade_sql']
            else:
                df['Faculdade'] = df['nome_faculdade_sql'].fillna(df['Faculdade'])
            df.drop(columns=['nome_faculdade_sql'], inplace=True)
            if 'Faculdade' in df.columns:
                df['Faculdade'] = texto_por_distintos(df['Faculdade'], padronizar_ies)
        
        # --- PREENCHIMENTO DE DADOS COMPLEMENTARES ---
        mapping_sql_para_df = {
            'data_nascimento': 'Data nascimento',
            'email': 'E-mail',
            'telefone_1': 'Telefone 1',
            'telefone_2': 'Telefone 2',
            'periodo_atual': 'Período atual',
            'periodo_quantidade': 'Período quantidade',
            'matricula': 'Matricula',
            'ins_cnpj': 'Ins. CNPJ',
            'ins_razao_social': 'Ins. Razão Social',
            'ins_nome_fantasia': 'Ins. Nome Fantasia',
            'ins_mantenedora': 'Ins. Mantenedora',
            'modalidade': 'Modalidade',
            'valor_matricula_com_desconto': 'Matricula C/ Desconto',
            'valor_matricula_sem_desconto': 'Matricula S/ Desconto',
            'qtd_disciplinas_matriculadas': 'Qtd Disciplinas Matriculadas',
            'qtd_disciplinas_reprovadas': 'Qtd Disciplinas Reprovadas',
            'uni_sexo': 'uni sexo',
            'uni_deficiencia': 'uni_deficiencia',
            'situacao': 'Status_Vínculo',
            'sit_obs': 'Observação da Situação',
            'sit_motivos': 'Situação do Motivo',
            'sit_data_atual_sistema': 'data ingresso',
            'valor_beneficio': 'valor_beneficio',
            'qual_beneficio': 'qual_beneficio',
            'valor_financiamento': 'valor_financiamento',
            'qual_financiamento': 'qual_financiamento',
            'valor_mensalidade_sem_desconto': 'Mensalidade S/ Desconto',
            'valor_mensalidade_com_desconto': 'Mensalidade C/ Desconto'
        }

        for col_sql, col_df in mapping_sql_para_df.items():
            actual_col_sql = col_sql + '_sql' if col_sql + '_sql' in df.columns else col_sql
            if actual_col_sql in df.columns:
                if col_df not in df.columns:
                    df[col_df] = df[actual_col_sql]
                else:
                    if col_df == 'Matricula':
                        df[col_df] = df[col_df].replace(r'^\s*[-]*\s*$', np.nan, regex=True)
                    df[col_df] = df[col_df].replace(['', ' ', '-', 'nan', 'NaN', 'NAN', 'None', '<NA>', 'NÃO INFORMADO', 'NAO INFORMADO', 'Não Informado'], np.nan)
                    df[col_df] = df[col_df].fillna(df[actual_col_sql])
                
                # Opcional: remover a coluna SQL para não sujar o export
                if actual_col_sql != col_df:
                    df.drop(columns=[actual_col_sql], inplace=True, errors='ignore')
                if col_sql in df.columns and col_sql != col_df:
                    df.drop(columns=[col_sql], inplace=True, errors='ignore')
                
        # --- PREENCHIMENTO FALLBACK POR INSCRIÇÃO (para Semestres Ausentes sem match direto) ---
        df_sql_sorted = df_sql.sort_values(by=['uni_codigo', 'semestre'])
        df_sql_last = df_sql_sorted.drop_duplicates(subset=['uni_codigo'], keep='last')
            
        df_fallback = pd.merge(df[['Inscrição']], df_sql_last, left_on='Inscrição', right_on='uni_codigo', how='left')
        
        mapping_fallback = {
            'Bolsista_sql': 'Bolsista',
            'UNI_CPF': 'CPF',
            'nome_faculdade_sql': 'Faculdade',
            'ins_nome_fantasia': 'Ins. Nome Fantasia',
            'CUR_NOME': 'Curso',
            'data_nascimento': 'Data nascimento',
            'email': 'E-mail',
            'telefone_1': 'Telefone 1',
            'telefone_2': 'Telefone 2',
            'matricula': 'Matricula',
            # Estas tres seguiam de fora do fallback embora estejam no mapping_sql_para_df:
            # o aluno cujo semestre do documento nao existe em `beneficiarios` recebia
            # matricula e e-mail pelo ultimo semestre conhecido, mas perdia a modalidade e
            # os periodos, que sao dado de cadastro e nao mudam com o semestre. `modalidade`
            # nunca e nula na origem (4 valores distintos em 95.538 linhas), entao coluna
            # vazia no relatorio so pode ser merge sem match — exatamente o que o fallback
            # existe para cobrir. `periodo_atual` propaga o ultimo valor conhecido; o ajuste
            # por diferenca de semestre continua sendo feito no remapeamento acima (calc_diff).
            'modalidade': 'Modalidade',
            'periodo_atual': 'Período atual',
            'periodo_quantidade': 'Período quantidade',
            'qtd_disciplinas_matriculadas': 'Qtd Disciplinas Matriculadas',
            'qtd_disciplinas_reprovadas': 'Qtd Disciplinas Reprovadas',
            'sit_motivos': 'Situação do Motivo',
            'sit_obs': 'Observação da Situação',
            'situacao': 'Status_Vínculo',
            'perfil': 'Perfil do Beneficiario'
        }
        
        for col_sql, col_df in mapping_fallback.items():
            if col_sql in df_fallback.columns:
                if col_df not in df.columns:
                    df[col_df] = df_fallback[col_sql]
                else:
                    if col_df == 'Matricula':
                        df[col_df] = df[col_df].replace(r'^\s*[-]*\s*$', np.nan, regex=True)
                    df[col_df] = df[col_df].replace(['', ' ', '-', 'nan', 'NaN', 'NAN', 'None', '<NA>', 'NÃO INFORMADO', 'NAO INFORMADO', 'Não Informado'], np.nan)
                    if col_df == 'Faculdade':
                        df[col_df] = df_fallback[col_sql].fillna(df[col_df])
                    else:
                        df[col_df] = df[col_df].fillna(df_fallback[col_sql])
        
        if 'Bolsista' in df.columns:
            df['Bolsista'] = texto_por_distintos(df['Bolsista'], limpar_texto_geral)

        # Limpar telefones lixo
        for col_tel in ['Telefone 1', 'Telefone 2']:
            if col_tel in df.columns:
                df[col_tel] = df[col_tel].astype(str).str.strip()
                df[col_tel] = df[col_tel].replace(['nan', 'NaN', 'None', '<NA>'], '')
                df[col_tel] = df[col_tel].replace(r'^[0\-\(\)\s]*$', 'Não informado', regex=True)
                df[col_tel] = df[col_tel].replace('', 'Não informado')
        
    for col in ['tipo_bolsa_final', 'qtd_pagtos', 'último_valor_pago_referencia']:
        if col not in df.columns: df[col] = "SEM DADOS" if col == 'tipo_bolsa_final' else 0

    # ffill+bfill por inscrição, com as rotinas nativas do groupby em vez de um
    # transform(lambda): o lambda roda uma vez por grupo, em Python, e são ~25 mil grupos
    # no df_docs e ~15 mil no df_riaf. As nativas resolvem a coluna inteira de uma vez.
    # Medido com a cardinalidade real: 8,69s -> 0,06s no docs e 4,91s -> 0,02s no riaf.
    _bolsa_preenchida = df.groupby('Inscrição')['tipo_bolsa_final'].ffill()
    df['tipo_bolsa_final'] = _bolsa_preenchida.groupby(df['Inscrição']).bfill().fillna("SEM DADOS")
    df['qtd_pagtos'] = pd.to_numeric(df['qtd_pagtos'], errors='coerce').fillna(0).astype(int)

    # --- NOVO PERFIL DO BENEFICIARIO --- (Lógica movida para o SQL)

    df['último_valor_pago_referencia'] = pd.to_numeric(df['último_valor_pago_referencia'], errors='coerce').fillna(0.0)
    
    # --- FALLBACK INTELIGENTE PARA data_coleta ---
    if 'data_coleta' in df.columns:
        df['data_coleta_dt'] = pd.to_datetime(df['data_coleta'], format='%d/%m/%Y', errors='coerce')
        
        # 1. Fallback df_pag (Descompactada) - Múltiplos pagamentos por semestre
        if df_pag is not None and not df_pag.empty and 'data_coleta' in df_pag.columns and 'uni_codigo' in df_pag.columns:
            pag_data = df_pag.copy()
            pag_data['uni_codigo'] = pd.to_numeric(pag_data['uni_codigo'], errors='coerce').astype('Int64')
            pag_data['semestre'] = pag_data['semestre'].astype(str).str.strip().str.replace('/', '-')
            pag_data['data_coleta_pag'] = pd.to_datetime(pag_data['data_coleta'], format='%d/%m/%Y', errors='coerce')
            
            # Pegamos a data mais recente do semestre corrente
            max_data_pag = pag_data.groupby(['uni_codigo', 'semestre'])['data_coleta_pag'].max().reset_index()
            max_data_pag.rename(columns={'uni_codigo': 'Inscrição', 'semestre': 'Semestre'}, inplace=True)
            
            df = pd.merge(df, max_data_pag, on=['Inscrição', 'Semestre'], how='left')
            df['data_coleta_dt'] = df['data_coleta_dt'].fillna(df['data_coleta_pag'])
            df.drop(columns=['data_coleta_pag'], inplace=True)
            
        # 2. Fallback data_coleta_atual_sistema (Completa)
        if 'data_coleta_atual_sistema' in df.columns:
            df['data_coleta_dt'] = df['data_coleta_dt'].fillna(pd.to_datetime(df['data_coleta_atual_sistema'], errors='coerce'))
            
        # 3. Fallback sit_data_atual_sistema (Completa)
        if 'sit_data_atual_sistema' in df.columns:
            df['data_coleta_dt'] = df['data_coleta_dt'].fillna(pd.to_datetime(df['sit_data_atual_sistema'], errors='coerce'))
            
        df['data_coleta'] = df['data_coleta_dt'].dt.strftime('%d/%m/%Y').fillna('')
        df.drop(columns=['data_coleta_dt'], inplace=True)

    # --- RECALCULAR pagamentos a partir do consolidado ---
    if df_mes_a_mes is not None and not df_mes_a_mes.empty:
        # Forçar uso dos dados frescos do SQL mês a mês (bolsa_paga real) ao invés do cache (parquet)
        df_pag = df_mes_a_mes.copy()
        df_pag.rename(columns={
            'uni_codigo': 'UNI_CODIGO',
            'semestre': 'SEMESTRE',
            'valr_bolsa': 'LAN_VALBOLSA',
            'lan_dtlanc': 'DATA_LANCAMENTO'
        }, inplace=True)
        
        # Puxa informações vitais do df consolidado principal
        if 'Curso' in df.columns:
            _df_curso = df[['Inscrição', 'Semestre', 'Curso']].drop_duplicates(subset=['Inscrição', 'Semestre'], keep='first')
            df_pag = pd.merge(df_pag, _df_curso, left_on=['UNI_CODIGO', 'SEMESTRE'], right_on=['Inscrição', 'Semestre'], how='left')
            df_pag.rename(columns={'Curso': 'CUR_NOME'}, inplace=True)
        else:
            df_pag['CUR_NOME'] = ''
            
        if 'tipo_bolsa_final' in df.columns:
            _df_bolsa = df[['Inscrição', 'Semestre', 'tipo_bolsa_final']].drop_duplicates(subset=['Inscrição', 'Semestre'], keep='first')
            df_pag = pd.merge(df_pag, _df_bolsa, left_on=['UNI_CODIGO', 'SEMESTRE'], right_on=['Inscrição', 'Semestre'], how='left')
            df_pag.rename(columns={'tipo_bolsa_final': 'TIPO_BOLSA'}, inplace=True)
        else:
            df_pag['TIPO_BOLSA'] = ''

    if df_pag is not None and not df_pag.empty and 'LAN_VALBOLSA' in df_pag.columns:
        print("[GGCI       | CALCULO       | PAGAMENTOS ] Matemática mês a mês...")
        df_pag_calc = df_pag.copy()
        df_pag_calc['UNI_CODIGO'] = pd.to_numeric(df_pag_calc['UNI_CODIGO'], errors='coerce').astype('Int64')
        df_pag_calc['SEMESTRE'] = df_pag_calc['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
        df_pag_calc['LAN_VALBOLSA'] = pd.to_numeric(df_pag_calc['LAN_VALBOLSA'], errors='coerce').fillna(0.0)
        
        if 'DATA_LANCAMENTO' in df_pag_calc.columns:
            df_pag_calc['DATA_ORDEM'] = pd.to_datetime(df_pag_calc['DATA_LANCAMENTO'], dayfirst=True, errors='coerce')
            df_pag_calc = df_pag_calc.sort_values(by=['UNI_CODIGO', 'SEMESTRE', 'DATA_ORDEM'])

        # =========================================================================
        # A MÁGICA: CÁLCULO DO SISTEMA MÊS A MÊS E ALINHAMENTO
        # =========================================================================
        df_pag_calc['row_idx'] = df_pag_calc.groupby(['UNI_CODIGO', 'SEMESTRE']).cumcount()
        
        if df_mes_a_mes is not None and not df_mes_a_mes.empty:
            df_mm = df_mes_a_mes.copy()
            
            # Converte a nova coluna do banco para datetime para garantir ordenação correta
            df_mm['DATA_ORDEM_DB'] = pd.to_datetime(df_mm['lan_dtlanc'], errors='coerce')
            
            # Ordena usando a data de lançamento em vez do lan_anomes bruto
            df_mm.sort_values(by=['uni_codigo', 'semestre', 'DATA_ORDEM_DB', 'lan_anomes'], inplace=True)
            df_mm['row_idx'] = df_mm.groupby(['uni_codigo', 'semestre']).cumcount()
            
            # Remove colunas que possam conflitar para priorizar as do banco de dados recente
            # Remove colunas que possam conflitar para priorizar as do banco de dados recente
            cols_to_drop = [c for c in ['qtd_pagtos', 'qtd_pagtos_retroativos', 'QTD_PAGTOS', 'QTD_PAGTOS_RETROATIVOS', 'CD_sem_desconto', 'CD_com_desconto', 'CD_mat_sem_desconto', 'CD_mat_com_desconto', 'CD_beneficios', 'CD_financiamentos'] if c in df_pag_calc.columns]
            if cols_to_drop:
                df_pag_calc.drop(columns=cols_to_drop, inplace=True)
                
            # Mesclando os dados da Coleta do mês para dentro do pagamento
            df_pag_calc = pd.merge(
                df_pag_calc, 
                df_mm[['uni_codigo', 'semestre', 'row_idx', 'CD_sem_desconto', 'CD_com_desconto', 'CD_mat_sem_desconto', 'CD_mat_com_desconto', 'CD_beneficios', 'CD_financiamentos', 'qtd_pagtos', 'qtd_pagtos_retroativos']],
                left_on=['UNI_CODIGO', 'SEMESTRE', 'row_idx'],
                right_on=['uni_codigo', 'semestre', 'row_idx'],
                how='left'
            )
            
            df_pag_calc['CD_sem_desconto'] = pd.to_numeric(df_pag_calc['CD_sem_desconto'], errors='coerce').fillna(0.0)
            df_pag_calc['CD_com_desconto'] = pd.to_numeric(df_pag_calc['CD_com_desconto'], errors='coerce').fillna(0.0)
            df_pag_calc['CD_mat_sem_desconto'] = pd.to_numeric(df_pag_calc.get('CD_mat_sem_desconto', pd.Series(0.0, index=df_pag_calc.index)), errors='coerce').fillna(0.0)
            df_pag_calc['CD_mat_com_desconto'] = pd.to_numeric(df_pag_calc.get('CD_mat_com_desconto', pd.Series(0.0, index=df_pag_calc.index)), errors='coerce').fillna(0.0)
            df_pag_calc['CD_beneficios'] = pd.to_numeric(df_pag_calc['CD_beneficios'], errors='coerce').fillna(0.0)
            df_pag_calc['CD_financiamentos'] = pd.to_numeric(df_pag_calc['CD_financiamentos'], errors='coerce').fillna(0.0)
            
            # CÁLCULO MÊS A MÊS DO TETO DO SISTEMA
            curso_str = df_pag_calc['CUR_NOME'].astype(str).str.strip().str.upper()
            is_med_odonto = curso_str.isin(['MEDICINA', 'ODONTOLOGIA'])
            bolsa_str = df_pag_calc['TIPO_BOLSA'].astype(str).str.strip().str.upper()
            
            df_pag_calc['is_202601'] = (df_pag_calc.get('lan_anomes', pd.Series('', index=df_pag_calc.index)).astype(str).str.strip() == '202601').astype(int)
            sys_base_calculo = np.where(df_pag_calc['is_202601'] == 1, df_pag_calc['CD_mat_com_desconto'], df_pag_calc['CD_com_desconto'])
            
            sys_mcd_50 = sys_base_calculo * 0.5
            sys_calc_parcial = np.where(is_med_odonto, np.minimum(sys_mcd_50, 2900.0), np.minimum(sys_mcd_50, 650.0))
            sys_calc_integral = np.where(is_med_odonto, np.minimum(sys_base_calculo, 5800.0), np.minimum(sys_base_calculo, 1500.0))
            sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
            
            sys_excedeu = (sys_bolsa_base + df_pag_calc['CD_beneficios']) > sys_base_calculo
            sys_bolsa_final_mes = np.where(sys_excedeu, sys_base_calculo - df_pag_calc['CD_beneficios'], sys_bolsa_base)
            
            lan_valor_complemento = pd.to_numeric(df_pag_calc.get('lan_valor_complemento', 0), errors='coerce').fillna(0.0)
            lan_valor_cancelamento = pd.to_numeric(df_pag_calc.get('lan_valor_cancelamento', 0), errors='coerce').fillna(0.0)
            sys_bolsa_final_mes_limit = np.maximum(sys_bolsa_final_mes, 0.0)
            sys_bolsa_final_mes_adjusted = sys_bolsa_final_mes_limit + lan_valor_complemento - lan_valor_cancelamento
            
            df_pag_calc['deveria_pagar_sistema_mes'] = np.where(df_pag_calc['LAN_VALBOLSA'].fillna(0) > 0, np.maximum(sys_bolsa_final_mes_adjusted, 0.0), 0.0)
        else:
            df_pag_calc['deveria_pagar_sistema_mes'] = 0.0
            df_pag_calc['is_202601'] = 0

        # Prepara a agregação dinâmica
        agg_dict = {
            'total_bolsa_real': ('LAN_VALBOLSA', 'sum'),
            'soma_sistema': ('deveria_pagar_sistema_mes', 'sum'),
            'soma_cd_sem_desconto': ('CD_sem_desconto', 'sum'),
            'soma_cd_com_desconto': ('CD_com_desconto', 'sum'),
            'soma_cd_beneficios': ('CD_beneficios', 'sum'),
            'soma_cd_financiamentos': ('CD_financiamentos', 'sum'),
            'qtd_202601_resumo': ('is_202601', 'sum')
        }

        
        # qtd_pagtos
        if 'QTD_PAGTOS' in df_pag_calc.columns:
            df_pag_calc['QTD_PAGTOS'] = pd.to_numeric(df_pag_calc['QTD_PAGTOS'], errors='coerce').fillna(0)
            agg_dict['qtd_pagtos_resumo'] = ('QTD_PAGTOS', 'sum')
        elif 'qtd_pagtos' in df_pag_calc.columns:
            df_pag_calc['qtd_pagtos'] = pd.to_numeric(df_pag_calc['qtd_pagtos'], errors='coerce').fillna(0)
            agg_dict['qtd_pagtos_resumo'] = ('qtd_pagtos', 'sum')
        else:
            agg_dict['qtd_pagtos_resumo'] = ('LAN_VALBOLSA', 'count')
            
        # qtd_pagtos_retroativos
        if 'QTD_PAGTOS_RETROATIVOS' in df_pag_calc.columns:
            df_pag_calc['QTD_PAGTOS_RETROATIVOS'] = pd.to_numeric(df_pag_calc['QTD_PAGTOS_RETROATIVOS'], errors='coerce').fillna(0)
            agg_dict['qtd_pagtos_retro_resumo'] = ('QTD_PAGTOS_RETROATIVOS', 'sum')
        elif 'qtd_pagtos_retroativos' in df_pag_calc.columns:
            df_pag_calc['qtd_pagtos_retroativos'] = pd.to_numeric(df_pag_calc['qtd_pagtos_retroativos'], errors='coerce').fillna(0)
            agg_dict['qtd_pagtos_retro_resumo'] = ('qtd_pagtos_retroativos', 'sum')
        else:
            agg_dict['qtd_pagtos_retro_resumo'] = ('LAN_VALBOLSA', lambda x: (x == 0).sum())

        if not df_pag_calc.empty:
            pass # Removido debug anterior
                
        df_pag_resumo = df_pag_calc.groupby(['UNI_CODIGO', 'SEMESTRE']).agg(**agg_dict).reset_index()

        # Resgata o último valor > 0 E O TIPO DE BOLSA direto do histórico financeiro
        df_lasts_bolsa = df_pag_calc.groupby(['UNI_CODIGO', 'SEMESTRE'])['TIPO_BOLSA'].last().reset_index(name='tipo_bolsa_pag')
        df_lasts_valor = df_pag_calc[df_pag_calc['LAN_VALBOLSA'] > 0].groupby(['UNI_CODIGO', 'SEMESTRE'])['LAN_VALBOLSA'].last().reset_index(name='valor_calculo_real')
        
        if 'DATA_INGRESSO' in df_pag_calc.columns:
            df_lasts_ingresso = df_pag_calc.groupby(['UNI_CODIGO', 'SEMESTRE'])['DATA_INGRESSO'].first().reset_index(name='data_ingresso')
        else:
            df_lasts_ingresso = pd.DataFrame(columns=['UNI_CODIGO', 'SEMESTRE', 'data_ingresso'])

        df_pag_resumo = pd.merge(df_pag_resumo, df_lasts_bolsa, on=['UNI_CODIGO', 'SEMESTRE'], how='left')
        df_pag_resumo = pd.merge(df_pag_resumo, df_lasts_ingresso, on=['UNI_CODIGO', 'SEMESTRE'], how='left')
        df_pag_resumo = pd.merge(df_pag_resumo, df_lasts_valor, on=['UNI_CODIGO', 'SEMESTRE'], how='left')
        df_pag_resumo['valor_calculo_real'] = df_pag_resumo['valor_calculo_real'].fillna(0.0)
        
        df = pd.merge(df, df_pag_resumo, left_on=['Inscrição', 'Semestre'], right_on=['UNI_CODIGO', 'SEMESTRE'], how='left')
        
        # --- A MÁGICA: RESGATA O TIPO DE BOLSA DA OVG SE O BANCO RETORNOU VAZIO ---
        if 'tipo_bolsa_pag' in df.columns:
            mask_sem_dados = df['tipo_bolsa_final'].isna() | (df['tipo_bolsa_final'].astype(str).str.strip().str.upper() == "SEM DADOS")
            df.loc[mask_sem_dados, 'tipo_bolsa_final'] = df.loc[mask_sem_dados, 'tipo_bolsa_pag']
            df['tipo_bolsa_final'] = df['tipo_bolsa_final'].fillna("SEM DADOS")
        
        mask_tem_pag = df['qtd_pagtos_resumo'].notna()
        df.loc[mask_tem_pag, 'qtd_pagtos'] = df.loc[mask_tem_pag, 'qtd_pagtos_resumo'].astype(int)
        df.loc[mask_tem_pag, 'último_valor_pago_referencia'] = df.loc[mask_tem_pag, 'valor_calculo_real']
        
        if 'qtd_pagtos_retro_resumo' in df.columns:
            df.loc[mask_tem_pag, 'qtd_pagtos_retroativos'] = df.loc[mask_tem_pag, 'qtd_pagtos_retro_resumo']
            
        df['qtd_pagtos_retroativos'] = pd.to_numeric(df.get('qtd_pagtos_retroativos', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0).astype(int)
        
        df['total bolsa paga'] = df['qtd_pagtos'] * df['último_valor_pago_referencia']  
        df.loc[mask_tem_pag, 'total bolsa paga'] = df.loc[mask_tem_pag, 'total_bolsa_real']
        
        # INJETANDO A SOMA DO SISTEMA (Mês a Mês calculado)
        df['soma_deveria_sistema'] = 0.0
        df.loc[mask_tem_pag, 'soma_deveria_sistema'] = df.loc[mask_tem_pag, 'soma_sistema']
        df['tem_pagamento_historico'] = mask_tem_pag
        
        df['qtd_pagtos_202601'] = 0.0
        if 'qtd_202601_resumo' in df.columns:
            df.loc[mask_tem_pag, 'qtd_pagtos_202601'] = df.loc[mask_tem_pag, 'qtd_202601_resumo']
        
        df['Soma Valor Beneficio'] = 0.0
        if 'soma_cd_beneficios' in df.columns:
            df.loc[mask_tem_pag, 'Soma Valor Beneficio'] = df.loc[mask_tem_pag, 'soma_cd_beneficios']
            
        df['Soma Valor Financiamento'] = 0.0
        if 'soma_cd_financiamentos' in df.columns:
            df.loc[mask_tem_pag, 'Soma Valor Financiamento'] = df.loc[mask_tem_pag, 'soma_cd_financiamentos']
        
        df.drop(columns=['UNI_CODIGO', 'SEMESTRE', 'qtd_pagtos_resumo', 'qtd_pagtos_retro_resumo', 'valor_calculo_real', 'total_bolsa_real', 'soma_sistema', 'tipo_bolsa_pag', 'soma_cd_beneficios', 'soma_cd_financiamentos'], errors='ignore', inplace=True)
    
    else:
        df['total bolsa paga'] = df['qtd_pagtos'] * df['último_valor_pago_referencia']
        df['qtd_pagtos_retroativos'] = pd.to_numeric(df.get('qtd_pagtos_retroativos', pd.Series(0, index=df.index)), errors='coerce').fillna(0).astype(int)
        df['soma_deveria_sistema'] = 0.0
        df['tem_pagamento_historico'] = False
        df['Soma Valor Beneficio'] = 0.0
        df['Soma Valor Financiamento'] = 0.0

    if 'Status_IA' in df.columns:
        mask_ausente = df['Status_IA'].isin(['Ausente', 'Ausentes'])
        cols_alvo = ['Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto']
        
        for c in cols_alvo:
            if c not in df.columns: df[c] = 0.0
            else: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            
        # Ensure Gemini is zeroed out for 'Ausente':
        df.loc[mask_ausente, 'Gemini Mensalidade S/ Desconto'] = 0.0
        df.loc[mask_ausente, 'Gemini Mensalidade C/ Desconto'] = 0.0
            
    
    if 'Situação do Motivo' in df.columns: df['Situação do Motivo'] = df['Situação do Motivo'].fillna("-")
    if 'Observação da Situação' in df.columns: df['Observação da Situação'] = df['Observação da Situação'].fillna("-")
    
    col_tipo = df.pop('tipo_bolsa_final')
    col_qtd = df.pop('qtd_pagtos')
    col_retro = df.pop('qtd_pagtos_retroativos')
    col_val = df.pop('último_valor_pago_referencia')
    col_tot = df.pop('total bolsa paga')
    
    try: idx_curso = df.columns.get_loc('Curso')
    except: idx_curso = len(df.columns) - 1
        
    df.insert(idx_curso + 1, 'tipo_bolsa_final', col_tipo)
    df.insert(idx_curso + 2, 'qtd_pagtos', col_qtd)
    df.insert(idx_curso + 3, 'qtd_pagtos_retroativos', col_retro)
    df.insert(idx_curso + 4, 'último_valor_pago_referencia', col_val)
    df.insert(idx_curso + 5, 'total bolsa paga', col_tot)
    
    if 'modalidade_sql' in df.columns:
        df['modalidade'] = df['modalidade_sql'].combine_first(df.get('modalidade', pd.NA))
    
    return df

# ==========================================
# 4. TRANSIÇÕES E REGRAS DE NEGÓCIO
# ==========================================
def aplicar_transicoes(df, df_pag):
    """
    O QUE FAZ: Rastreia a jornada do aluno (mudou de IES? mudou de bolsa? sua inscrição foi substituída?).
    POR QUÊ EXISTE: Regra de negócio da OVG: Se a inscrição foi migrada, a anterior deve ser classificada como 'DESLIGADO'.
    COMO FUNCIONA: Ordena os pagamentos por CPF e mapeia os shifts temporais (anterior/posterior) usando vetores do Pandas.
    """
    if df.empty: return df
    
    if 'CPF' in df.columns and 'data_coleta' in df.columns:
        # Cria colunas de espelho super limpas para garantir o agrupamento
        df['CPF_clean'] = df['CPF'].astype(str).str.replace(r'\.0$', '', regex=True).str.replace(r'\D', '', regex=True).str.zfill(11)
        df['Inscrição_clean'] = df['Inscrição'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).replace(['', 'nan', '<NA>', 'None'], '-')
        df['Semestre_clean'] = df['Semestre'].astype(str).str.strip()
        
        # Ordena o proprio df usando as chaves blindadas.
        #
        # O DESEMPATE POR INSCRIÇÃO É OBRIGATÓRIO, não cosmético. Quando o mesmo CPF tem DUAS
        # inscrições no MESMO semestre — o caso de quem troca de bolsa no meio do período,
        # parcial -> integral —, `CPF_clean` e `Semestre_clean` empatam e a ordem entre as duas
        # linhas passava a depender da ordem em que elas chegaram no DataFrame. Como
        # `shift(1)`/`shift(-1)` logo abaixo LEEM essa ordem, a mesma pessoa saía com
        # `Inscrição Anterior` e `Inscrição Posterior` apontando para a MESMA inscrição, e a aba
        # CONTRATO discordava da aba HISTÓRICO para o mesmo CPF só porque uma tinha um semestre
        # a mais que a outra e o empate caiu de outro jeito.
        #
        # A inscrição é sequencial no tempo (número maior = emitida depois), então ordenar por
        # ela dentro do semestre reconstrói a cronologia real da troca de bolsa. Ordenar pela
        # STRING não serve: os números têm comprimentos diferentes na base e a ordem
        # lexicográfica quebraria justamente nos casos antigos.
        #
        # `kind='stable'` fecha a porta: o padrão do pandas é quicksort, que não preserva a
        # `kind='stable'` fecha a porta: o padrão do pandas é quicksort, que não preserva a
        # ordem de empates remanescentes — era isso que fazia o relatório não ser reprodutível
        # entre duas execuções da MESMA entrada.
        df['Inscrição_ord'] = pd.to_numeric(df['Inscrição_clean'], errors='coerce').fillna(-1)
        
        # === SOLUÇÃO DEFINITIVA PARA MÚLTIPLOS DOCUMENTOS ===
        # Como df_docs agora contém todos os tipos de documento juntos, dar um shift() direto
        # fazia com que um Histórico apontasse para o Contrato da MESMA inscrição.
        # Precisamos isolar a "linha do tempo" real das inscrições (uma por CPF + Inscrição),
        # calcular o anterior/posterior nela, e mapear de volta.
        chaves_tempo = ['CPF_clean', 'Semestre_clean', 'Inscrição_ord', 'Inscrição_clean', 'tipo_bolsa_final', 'Faculdade']
        df_unico = df[chaves_tempo].drop_duplicates(subset=['CPF_clean', 'Inscrição_clean']).copy()
        df_unico = df_unico.sort_values(by=['CPF_clean', 'Semestre_clean', 'Inscrição_ord'], kind='stable')
        
        df_unico['Inscrição Anterior'] = df_unico.groupby('CPF_clean')['Inscrição_clean'].shift(1).astype(str).replace(['<NA>', 'nan', 'NaN', 'None'], '-').fillna("-")
        df_unico['Inscrição Posterior'] = df_unico.groupby('CPF_clean')['Inscrição_clean'].shift(-1).astype(str).replace(['<NA>', 'nan', 'NaN', 'None'], '-').fillna("-")
        
        df_unico['Bolsa Anterior'] = df_unico.groupby('CPF_clean')['tipo_bolsa_final'].shift(1).fillna("-")
        df_unico['Bolsa Posterior'] = df_unico.groupby('CPF_clean')['tipo_bolsa_final'].shift(-1).fillna("-")
        curr_b_u = df_unico.get('tipo_bolsa_final', pd.Series("-", index=df_unico.index))
        df_unico['Bolsa Anterior'] = np.where((df_unico['Bolsa Anterior'] != "-") & (df_unico['Bolsa Anterior'] != curr_b_u), df_unico['Bolsa Anterior'], "-")
        df_unico['Bolsa Posterior'] = np.where((df_unico['Bolsa Posterior'] != "-") & (df_unico['Bolsa Posterior'] != curr_b_u), df_unico['Bolsa Posterior'], "-")
        df_unico['Mudou Bolsa?'] = np.where((df_unico['Bolsa Posterior'] != "-"), "S", "N")
        
        df_unico['IES Anterior'] = df_unico.groupby('CPF_clean')['Faculdade'].shift(1).fillna("-")
        df_unico['IES Posterior'] = df_unico.groupby('CPF_clean')['Faculdade'].shift(-1).fillna("-")
        curr_ies_u = df_unico.get('Faculdade', pd.Series("-", index=df_unico.index))
        df_unico['IES Anterior'] = np.where((df_unico['IES Anterior'] != "-") & (df_unico['IES Anterior'] != curr_ies_u), df_unico['IES Anterior'], "-")
        df_unico['IES Posterior'] = np.where((df_unico['IES Posterior'] != "-") & (df_unico['IES Posterior'] != curr_ies_u), df_unico['IES Posterior'], "-")
        df_unico['Mudou IES?'] = np.where((df_unico['IES Posterior'] != "-"), "S", "N")
        
        df_unico['Tem_Semestre_Posterior'] = df_unico.groupby('CPF_clean')['Inscrição_clean'].shift(-1).notna()
        
        # Mapear de volta para o DF completo
        map_cols = ['Tem_Semestre_Posterior', 'Inscrição Anterior', 'Inscrição Posterior', 'Bolsa Anterior', 'Bolsa Posterior', 'Mudou Bolsa?', 'IES Anterior', 'IES Posterior', 'Mudou IES?']
        df_map = df_unico.set_index(['CPF_clean', 'Inscrição_clean'])[map_cols]
        
        df = df.join(df_map, on=['CPF_clean', 'Inscrição_clean'])
        
        for c in map_cols:
            df[c] = df[c].fillna("-" if c != 'Tem_Semestre_Posterior' else False)
            
        df.drop(columns=['CPF_clean', 'Inscrição_clean', 'Semestre_clean', 'Inscrição_ord'], inplace=True, errors='ignore')
    else:
        df['Inscrição Anterior'] = "-"
        df['Inscrição Posterior'] = "-"
        df['Bolsa Anterior'] = "-"
        df['Bolsa Posterior'] = "-"
        df['Mudou Bolsa?'] = "-"
        df['IES Anterior'] = "-"
        df['IES Posterior'] = "-"
        df['Mudou IES?'] = "-"
    
    if df_pag.empty or 'UNI_CPF' not in df_pag.columns or 'UNI_CODIGO' not in df_pag.columns:
        return df

    pag = df_pag.copy()
    pag['UNI_CPF'] = pag['UNI_CPF'].astype(str).str.replace('*', '', regex=False).str.replace('.', '', regex=False).str.replace('-', '', regex=False).str.zfill(11)
    pag['K_ID'] = pag['UNI_CODIGO'].astype(str).str.replace('.0', '', regex=False).str.replace('.', '', regex=False).str.strip()

    if 'INS_NOME' in pag.columns: pag['INS_NOME'] = pag['INS_NOME'].apply(padronizar_ies)
    if 'TIPO_BOLSA' not in pag.columns: pag['TIPO_BOLSA'] = '-'

    pag_trans = pag.sort_values(by=['UNI_CPF', 'SEMESTRE', 'UNI_CODIGO']).drop_duplicates(subset=['UNI_CPF', 'UNI_CODIGO'], keep='last')
    
    pag_trans['PREV_ID'] = pag_trans.groupby('UNI_CPF')['K_ID'].shift(1)
    pag_trans['PREV_BOLSA'] = pag_trans.groupby('UNI_CPF')['TIPO_BOLSA'].shift(1)
    pag_trans['PREV_IES'] = pag_trans.groupby('UNI_CPF')['INS_NOME'].shift(1)
    pag_trans['NEXT_ID'] = pag_trans.groupby('UNI_CPF')['K_ID'].shift(-1)
    pag_trans['NEXT_BOLSA'] = pag_trans.groupby('UNI_CPF')['TIPO_BOLSA'].shift(-1)
    pag_trans['NEXT_IES'] = pag_trans.groupby('UNI_CPF')['INS_NOME'].shift(-1)
    
    map_prev_id = pag_trans.set_index('K_ID')['PREV_ID'].to_dict()
    map_next_id = pag_trans.set_index('K_ID')['NEXT_ID'].to_dict()
    map_prev_b = pag_trans.set_index('K_ID')['PREV_BOLSA'].to_dict()
    map_next_b = pag_trans.set_index('K_ID')['NEXT_BOLSA'].to_dict()
    map_prev_ies = pag_trans.set_index('K_ID')['PREV_IES'].to_dict()
    map_next_ies = pag_trans.set_index('K_ID')['NEXT_IES'].to_dict()
    map_curr_b = pag_trans.set_index('K_ID')['TIPO_BOLSA'].to_dict()

    pag['KEY_SEM'] = pag['SEMESTRE'].astype(str).str.replace('/', '-').str.strip()
    pag['KEY_STR'] = pag['K_ID'] + "_" + pag['KEY_SEM']
    map_ies_semestre = pag.drop_duplicates(subset=['KEY_STR'], keep='last').set_index('KEY_STR')['INS_NOME'].to_dict()

    k_id_series = df['Inscrição'].astype(str).str.replace('.0', '', regex=False).str.strip()
    df['KEY_TEMP'] = k_id_series + "_" + df['Semestre'].astype(str).str.replace('/', '-').str.strip()
    
    if 'Faculdade' in df.columns:
        df['Faculdade'] = df['Faculdade'].replace(['', 'nan', 'NaN', 'NAN', 'None', '<NA>'], np.nan)
        df['Faculdade'] = df['Faculdade'].apply(lambda x: padronizar_ies(x) if pd.notna(x) else x).fillna(df['KEY_TEMP'].map(map_ies_semestre))
    else:
        df['Faculdade'] = df['KEY_TEMP'].map(map_ies_semestre)
    df.drop(columns=['KEY_TEMP'], inplace=True)
    
    
    ies_atual = df['Faculdade'].astype(str).str.strip()
    
    if 'CPF' in df.columns and 'data_coleta' in df.columns:
        df_ies = df[['CPF', 'data_coleta']].copy()
        df_ies['Faculdade'] = ies_atual
        df_ies['temp_data_coleta'] = pd.to_datetime(df_ies['data_coleta'], format='%d/%m/%Y', errors='coerce')
        df_ies_sorted = df_ies.sort_values(by=['CPF', 'temp_data_coleta'])
        
        df['IES Anterior'] = df_ies_sorted.groupby('CPF')['Faculdade'].shift(1).fillna("-")
        df['IES Posterior'] = df_ies_sorted.groupby('CPF')['Faculdade'].shift(-1).fillna("-")
        
        df['IES Anterior'] = np.where((df['IES Anterior'] != "-") & (df['IES Anterior'] != ies_atual), df['IES Anterior'], "-")
        df['IES Posterior'] = np.where((df['IES Posterior'] != "-") & (df['IES Posterior'] != ies_atual), df['IES Posterior'], "-")
    else:
        df['IES Anterior'] = "-"
        df['IES Posterior'] = "-"

    df['Mudou IES?'] = np.where((df['IES Anterior'] != "-") | (df['IES Posterior'] != "-"), "S", "N")
    
    # === A NOVA LÓGICA DE VÍNCULO (Histórica e Trava) ===
    # 1. TRAVA DE INSCRIÇÃO: Se a inscrição foi substituída (Inscrição Posterior existe e é diferente), a velha é DESLIGADO
    tem_insc_post = pd.notna(df['Inscrição Posterior']) & (df['Inscrição Posterior'].astype(str).str.strip() != '') & (df['Inscrição Posterior'].astype(str).str.strip() != '<NA>') & (df['Inscrição Posterior'].astype(str).str.strip() != '-')
    
    # 2. STATUS HISTÓRICO: Se não foi substituída, precisamos saber se é o último semestre da vida do aluno
    # Resolve bug quando geramos relatórios onde df_pag está vazio (como trilha de Agendamento)
    max_para_cpf = {}
    
    # 2.1 Tenta buscar diretamente do banco a verdade absoluta do último pagamento
    cpfs = df['CPF_clean'].dropna().unique().tolist()
    if cpfs:
        try:
            engine = get_engine()
            cpfs_str = ",".join([f"'{cpf}'" for cpf in cpfs])
            query_max_pag = f"""
            SELECT b.uni_cpf as CPF, MAX(l.lan_anomes) as max_anomes
            FROM sibu.universitarios b
            JOIN sibu.lancamento l ON b.uni_codigo = l.uni_codigo
            WHERE b.uni_cpf IN ({cpfs_str})
            GROUP BY b.uni_cpf
            """
            df_max_pag = pd.read_sql(query_max_pag, engine)
            for _, row in df_max_pag.iterrows():
                cpf = str(row['CPF']).zfill(11)
                anomes = str(row['max_anomes'])
                if len(anomes) == 6:
                    year = anomes[:4]
                    month = int(anomes[4:])
                    sem = f"{year}-1" if month <= 6 else f"{year}-2"
                    max_para_cpf[cpf] = sem
        except Exception as e:
            print(f"[GGCI       | AVISO         | TRANSICAO] Falha ao buscar max_pagamento no db: {e}")
            pass
            
    # 2.2 Fallback para o df_pag carregado em memória se o banco falhar
    if not max_para_cpf and not pag.empty and 'KEY_SEM' in pag.columns:
        max_sem_pag = pag.groupby('UNI_CPF')['KEY_SEM'].max().to_dict()
        for cpf, val in max_sem_pag.items():
            max_para_cpf[str(cpf).zfill(11)] = val

    max_mapped = df['CPF_clean'].map(max_para_cpf)
    sem_clean = df['Semestre'].astype(str).str.strip().str.replace('/', '-')
    e_ultimo_semestre = (sem_clean >= max_mapped) | max_mapped.isna()
        
    tem_sem_post = ~e_ultimo_semestre
    
    if 'Status_Vínculo' in df.columns:
        status_base = df['Status_Vínculo']
        
        if 'Situação do Motivo' in df.columns:
            motivo_final = df['Situação do Motivo'].astype(str).str.upper().str.strip()
            is_desligamento = ~motivo_final.isin(['INCLUSAO', 'RENOVACAO CPD', 'RENOVAÇÃO', '-', 'NAN', '<NA>', ''])
            
            # ÚLTIMO SEMESTRE: se o motivo final for de desligamento, garante DESLIGADO
            status_base = np.where(~tem_sem_post & is_desligamento, 'DESLIGADO', status_base)
            
            # SEMESTRES HISTÓRICOS: garante ATIVO e ajusta o motivo para não vazar o desligamento futuro
            status_base = np.where(tem_sem_post, 'ATIVO', status_base)
            df['Situação do Motivo'] = np.where(tem_sem_post, 'RENOVACAO CPD', df['Situação do Motivo'])
            
            if 'Observação da Situação' in df.columns:
                obs_hist = 'RENOVACAO CPD ' + df['Semestre'].astype(str).str.strip()
                df['Observação da Situação'] = np.where(tem_sem_post, obs_hist, df['Observação da Situação'])

        df['Status_Vínculo'] = np.where(tem_insc_post, 'DESLIGADO', status_base)
    
    return df


def calcular_auditoria_ia(df):
    """
    O QUE FAZ: Processa o cálculo matemático final e atualiza a coluna Status_IA (Válido, Inválido, Falso Ausente, Falso Válido, etc).
    POR QUÊ EXISTE: A Inteligência Artificial (LLM) apenas extraiu os números; este módulo executa as fórmulas que julgam quem errou (OVG x IES).
    COMO FUNCIONA: Cruza o valor da Mensalidade S/ Desconto com a IA. Compara o total pago com o total que deveria ser pago. Produz a métrica Prejuízo e Economia.
    """
    if df.empty: return df

    def atualizar_e_aplicar_cache_local(df_documentos):
        def get_d_proc(df_alvo):
            """
            Primeira das quatro colunas de data que tiver valor útil, como texto.

            Era um `apply(axis=1)`, o padrão mais caro do pandas: ele monta um objeto
            Series por linha antes de chamar a função, e isso rodava sobre as ~167 mil
            linhas x 62 colunas do df_documentos, duas vezes. É um coalesce, então sai
            por máscara: cada coluna é avaliada de uma vez e só preenche onde ainda não
            há resposta, na mesma ordem de prioridade de antes.
            """
            texto = np.full(len(df_alvo), '', dtype=object)
            se_procura = np.ones(len(df_alvo), dtype=bool)
            for c in ['Data_Processamento_Agendar', 'Data Processamento', 'Data Processamento_y', 'Data Processamento_x']:
                if c not in df_alvo.columns or not se_procura.any():
                    continue
                s = df_alvo[c]
                candidato = s.astype(str).str.strip()
                util = s.notna().to_numpy() & ~candidato.isin(_DATAS_SEM_VALOR).to_numpy()
                escolher = se_procura & util
                if escolher.any():
                    texto[escolher] = candidato.to_numpy()[escolher]
                    se_procura &= ~escolher
            return pd.Series(texto, index=df_alvo.index)

        cache_path = caminho_cache_gemini()
        cache_lock = f"{cache_path}.lock"

        # `Ausente` NÃO é resultado do Gemini: é o carimbo que este próprio motor coloca
        # em quem está na lista de pendentes e não tem documento. Guardá-lo no cache
        # tornava a ausência permanente — na execução seguinte a chave batia, `IA_Run_Date`
        # era do mesmo dia, e o `mask_newer` restaurava "Ausente" POR CIMA da linha do
        # documento recém-baixado, ainda marcando `Processado = SIM`. Quem entregasse o
        # documento continuava aparecendo como ausente por quantas atualizações fossem
        # feitas, brutas inclusive: o cache reescrevia o resultado do scraping.
        status_cacheavel = df_documentos.get('Status_IA', pd.Series('', index=df_documentos.index))
        mask_processados = (
            pd.notna(status_cacheavel) &
            (status_cacheavel != 'Não Processado') &
            (status_cacheavel != '') &
            ~status_cacheavel.isin(_STATUS_SEM_DOCUMENTO) &
            pd.notna(df_documentos.get('Inscrição')) &
            pd.notna(df_documentos.get('Semestre'))
        )
        df_novos = df_documentos[mask_processados].copy() if mask_processados.any() else pd.DataFrame()
        
        colunas_cache = [
            'Inscrição', 'Semestre', 'Documento Tipo', 'Status_IA', 'Data_Processamento_Cache', 'IA_Run_Date', 'Gemini Inconsistencias',
            'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Periodo', 
            'Gemini Quantidade Periodos', 'Gemini Cnpj Faculdade', 'Gemini Mensalidade S/ Desconto', 
            'Gemini Mensalidade C/ Desconto', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
            'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto', 'Gemini Razao Social', 
            'Gemini Nome Faculdade', 'Gemini Beneficio Nome', 'Gemini Nome Mantenedora', 
            'Gemini Nome Financiamento', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies', 
            'Gemini Modalidade', 'Gemini Email', 'Gemini Tipo Bolsa', 'Gemini Curso', 'Gemini Semestre'
        ]
        
        if not df_novos.empty:
            df_novos['str_data'] = get_d_proc(df_novos)
            # NÃO trocar para dayfirst=True. `data_processamento` vem do banco como Datetime
            # nativo, então get_d_proc devolve o str() de um Timestamp: '2026-02-09 18:13:36'
            # (ISO, ano primeiro). Com dayfirst=True o pandas lê isso como 9 de SETEMBRO e
            # ainda avisa ("Parsing dates in %Y-%m-%d format when dayfirst=True was
            # specified"). Toda data cujo dia seja <= 12 saía corrompida, e é essa data que
            # decide se o cache local sobrepõe o banco (mask_newer, abaixo).
            df_novos['Data_Processamento_Cache'] = pd.to_datetime(df_novos['str_data'], dayfirst=False, errors='coerce').fillna(pd.Timestamp.now())
            df_novos['IA_Run_Date'] = pd.Timestamp.now()
            
            cols = [c for c in colunas_cache if c in df_novos.columns]
            df_novos = df_novos[cols]
            
            # Remove any trailing /0.0 format for safety
            df_novos['Inscrição'] = df_novos['Inscrição'].astype(str).str.replace(r'\.0$', '', regex=True)
            df_novos['Semestre'] = df_novos['Semestre'].astype(str).str.strip()
        
        # O ciclo ler-mesclar-gravar precisa ser serializado: sem o lock, duas gerações
        # simultâneas sobrescreviam os registros uma da outra. Sem o lock a restauração
        # ainda acontece normalmente em memória — só a persistência é pulada.
        travado = adquirir_lock_cache(cache_lock) if not df_novos.empty else False
        try:
            if os.path.exists(cache_path):
                df_cache = pd.read_parquet(cache_path)
                # Expurgo dos "Ausente" que as versões anteriores gravaram (eram a maior
                # fatia do arquivo). Filtrar aqui limpa os dois usos de uma vez: eles não
                # participam mais da restauração em memória e somem do parquet no próximo
                # ciclo que conseguir o lock — sem passo manual e sem apagar o cache
                # inteiro, que ainda guarda os Válido/Inválido legítimos.
                if 'Status_IA' in df_cache.columns:
                    df_cache = df_cache[~df_cache['Status_IA'].isin(_STATUS_SEM_DOCUMENTO)]
                if not df_novos.empty:
                    df_cache = pd.concat([df_cache, df_novos], ignore_index=True)
                    if 'Documento Tipo' not in df_cache.columns:
                        df_cache['Documento Tipo'] = ''

                    if 'Data_Processamento_Cache' not in df_cache.columns:
                        df_cache['Data_Processamento_Cache'] = pd.Timestamp('2000-01-01')
                    else:
                        df_cache['Data_Processamento_Cache'] = pd.to_datetime(df_cache['Data_Processamento_Cache'], errors='coerce').fillna(pd.Timestamp('2000-01-01'))

                    # KEEP THE NEWEST RECORD
                    df_cache = df_cache.sort_values('Data_Processamento_Cache').drop_duplicates(subset=['Inscrição', 'Semestre', 'Documento Tipo'], keep='last')
                    if travado:
                        gravar_parquet_atomico(df_cache, cache_path)
                    else:
                        print(f"[GGCI       | AVISO         | CACHE LOCAL] Lock ocupado: cache não persistido nesta execução.")
            else:
                if not df_novos.empty:
                    if 'Documento Tipo' not in df_novos.columns:
                        df_novos['Documento Tipo'] = ''
                    if travado:
                        gravar_parquet_atomico(df_novos, cache_path)
                    else:
                        print(f"[GGCI       | AVISO         | CACHE LOCAL] Lock ocupado: cache não persistido nesta execução.")
                df_cache = df_novos
        finally:
            if travado and os.path.exists(cache_lock):
                try: os.remove(cache_lock)
                except OSError: pass
            
        if not df_cache.empty:
            df_work = df_documentos.copy()
            doc_tipo_col = df_work.get('Documento Tipo', pd.Series(['']*len(df_work), index=df_work.index)).astype(str).str.strip()
            df_work['chave_temp'] = df_work['Inscrição'].astype(str).str.replace(r'\.0$', '', regex=True) + "_" + df_work['Semestre'].astype(str).str.strip() + "_" + doc_tipo_col
            
            doc_tipo_cache = df_cache.get('Documento Tipo', pd.Series(['']*len(df_cache), index=df_cache.index)).astype(str).str.strip()
            df_cache['chave_temp'] = df_cache['Inscrição'].astype(str).str.replace(r'\.0$', '', regex=True) + "_" + df_cache['Semestre'].astype(str).str.strip() + "_" + doc_tipo_cache
            
            df_cache_idx = df_cache.drop_duplicates(subset=['chave_temp'], keep='last').set_index('chave_temp')
            df_work_idx = df_work.set_index('chave_temp')
            
            df_work_idx['str_data'] = get_d_proc(df_work_idx)
            # dayfirst=False de propósito — mesmo motivo do bloco de Data_Processamento_Cache
            # acima: a data chega em ISO (ano primeiro), não em dd/mm/aaaa.
            df_work_idx['Data_Processamento_Atual'] = pd.to_datetime(df_work_idx['str_data'], dayfirst=False, errors='coerce').fillna(pd.Timestamp('2000-01-01'))
            
            st_ia = df_work_idx.get('Status_IA', pd.Series(['']*len(df_work_idx), index=df_work_idx.index)).astype(str).str.strip().str.lower()
            mask_vazio = (st_ia == '') | (st_ia == 'não processado') | (st_ia == 'nan') | (st_ia == 'none')
            
            mask_is_in_cache = df_work_idx.index.isin(df_cache_idx.index)
            mask_newer = pd.Series(False, index=df_work_idx.index)
            common_idx = df_work_idx.index[mask_is_in_cache]
            if not common_idx.empty:
                data_cache_col = df_cache_idx.loc[common_idx, 'Data_Processamento_Cache']
                data_atual_col = df_work_idx.loc[common_idx, 'Data_Processamento_Atual']
                
                # A COMPARAÇÃO DE DATAS NÃO VALE PARA QUEM ESTÁ `AUSENTE` AGORA.
                #
                # `Data_Processamento_Atual` de uma linha ausente é a sentinela 2000-01-01 —
                # ela não tem data porque não há documento. Comparar contra isso dá SEMPRE
                # "cache mais novo", e aí qualquer veredito guardado, de qualquer época,
                # ressuscita um documento que o SIBU já não tem: a linha some dos pendentes e
                # a IES deixa de ser cobrada por um documento que nunca entregou. Aconteceu com
                # a inscrição 2194690 em 2025-2, com um `Inválido` lido em 20/08 sobrepondo uma
                # pendência real — ela era a única divergência entre os 1.004 que o site cobra
                # e os 1.003 do dashboard.
                #
                # PARA ESSAS LINHAS VALE SÓ `recent_cache`, e é o suficiente: o cache existe
                # para cobrir a latência do espelho D-1 — documento processado HOJE que o
                # espelho só mostra amanhã —, e é exatamente isso que `IA_Run_Date == hoje`
                # diz. Cache de ontem para trás não tem latência nenhuma a cobrir; se o
                # documento ainda não está no espelho depois de um dia, ele não existe mais.
                ausente_agora = st_ia.loc[common_idx].isin(
                    [s.strip().lower() for s in _STATUS_SEM_DOCUMENTO])
                cache_mais_novo = (data_cache_col > data_atual_col) & ~ausente_agora

                if 'IA_Run_Date' in df_cache_idx.columns:
                    ia_run_date_col = pd.to_datetime(df_cache_idx.loc[common_idx, 'IA_Run_Date'], errors='coerce')
                    # Sobrepõe o banco apenas se a IA rodou "hoje" (por data/dia), pois o D-1 atualiza no dia seguinte
                    recent_cache = ia_run_date_col.dt.date == pd.Timestamp.now().date()
                    mask_newer.loc[common_idx] = cache_mais_novo | recent_cache
                else:
                    mask_newer.loc[common_idx] = cache_mais_novo
            
            mask_restaurar = mask_is_in_cache & (mask_vazio | mask_newer)
            
            if mask_restaurar.any():
                cols_to_update = [c for c in colunas_cache if c in df_work_idx.columns and c in df_cache_idx.columns and c not in ['Inscrição', 'Semestre', 'Documento Tipo', 'Data_Processamento_Cache']]
                
                keys_restaurar = df_work_idx.index[mask_restaurar]
                
                for c in cols_to_update:
                    valores_restaurados = keys_restaurar.map(df_cache_idx[c])
                    df_work_idx.loc[mask_restaurar, c] = valores_restaurados.values
                
                for c in ['Processado', 'Processado_y', 'Processado_x']:
                    if c in df_work_idx.columns:
                        df_work_idx.loc[mask_restaurar, c] = 'SIM'
                        
                print(f"[GGCI       | INFO          | CACHE LOCAL] Restaurados {mask_restaurar.sum()} registros do cache (Latência superada).")
                
            return df_work_idx.drop(columns=['chave_temp', 'str_data', 'Data_Processamento_Atual'], errors='ignore').reset_index(drop=True)
        return df_documentos

    df = atualizar_e_aplicar_cache_local(df)

    def get_primeiro_valido(row, colunas):
        for col in colunas:
            if col in row.index:
                val = row[col]
                if pd.notna(val):
                    v_str = str(val).strip()
                    if v_str.lower() not in ['', 'nan', 'none', 'nat', '<na>']:
                        return v_str
        return ''

    def get_vec_col(df_obj, cols):
        res = pd.Series([np.nan]*len(df_obj), index=df_obj.index)
        for c in cols:
            if c in df_obj.columns:
                col_data = df_obj[c].astype(str).replace(['', 'nan', 'None', '<NA>', 'NaN'], np.nan)
                res = res.fillna(col_data)
        return res.fillna('').astype(str)

    ia_st = df.get('Status_IA', pd.Series(['']*len(df), index=df.index)).astype(str).str.strip()
    insc_post = df.get('Inscrição Posterior', pd.Series(index=df.index)).astype(str).str.strip()
    has_insc_post = pd.notna(df.get('Inscrição Posterior')) & ~insc_post.isin(['', 'nan', '<NA>', 'None', '-'])
    val_ultima = pd.to_numeric(df.get('último_valor_pago_referencia', pd.Series([0.0]*len(df), index=df.index)), errors='coerce').fillna(0.0)
    
    cond_falso_ausente = ia_st.isin(['Ausente', 'Ausentes']) & has_insc_post & (val_ultima == 0.0)
    
    processar = get_vec_col(df, ['Processar', 'Processar_y', 'Processar_x']).str.strip().str.upper()
    processado = get_vec_col(df, ['Processado', 'Processado_y', 'Processado_x']).str.strip().str.upper()
    d_proc = get_vec_col(df, ['Data_Processamento_Agendar', 'Data Processamento', 'Data Processamento_y', 'Data Processamento_x'])
    inc = get_vec_col(df, ['Gemini Inconsistencias'])
    g_cpf = get_vec_col(df, ['Gemini CPF'])
    g_sem = get_vec_col(df, ['Gemini Semestre'])
    
    doc_tipo = df.get('Documento Tipo', pd.Series(['']*len(df), index=df.index)).astype(str).str.upper()
    g_msd = pd.to_numeric(df.get('Gemini Mensalidade S/ Desconto', pd.Series(index=df.index)), errors='coerce').fillna(0.0)
    g_mcd = pd.to_numeric(df.get('Gemini Mensalidade C/ Desconto', pd.Series(index=df.index)), errors='coerce').fillna(0.0)
    g_fin = pd.to_numeric(df.get('Gemini Valor Financiado', pd.Series(index=df.index)), errors='coerce').fillna(0.0)
    g_ben = pd.to_numeric(df.get('Gemini Valor Beneficio', pd.Series(index=df.index)), errors='coerce').fillna(0.0)

    # Heurística agressiva de corrompido foi removida a pedido do usuário
    # para não sobrescrever os status Válido/Inválido do motor
    
    final_st = np.where(ia_st.str.contains('CORROMPIDO', case=False, na=False), 'Corrompido',
               np.where(cond_falso_ausente, 'Falso Ausente', ia_st))
    
    df['Status_IA'] = final_st
    
    mask_ausente = df['Status_IA'].isin(['Ausente', 'Ausentes', 'Falso Ausente'])
    mask_corrompido = df['Status_IA'] == 'Corrompido'

    s_processar = get_vec_col(df, ['Processar', 'Processar_y', 'Processar_x']).str.strip().str.upper()
    s_processado = get_vec_col(df, ['Processado', 'Processado_y', 'Processado_x']).str.strip().str.upper()
    
    mask_nao_processado_agendamento = (s_processado != 'SIM')
    mask_nao_processado = (~mask_ausente) & (~mask_corrompido) & mask_nao_processado_agendamento
    
    # Atualiza o Status_IA para refletir que não foi processado
    df.loc[mask_nao_processado, 'Status_IA'] = 'Não Processado'
    
    # --- REGRA DE EXCEÇÃO MAUA ---
    is_maua = df['Faculdade'].astype(str).str.contains('MAUA FACULDADE MAUA DE GOIAS', na=False, case=False)
    mcd_ia_temp = pd.to_numeric(df['Gemini Mensalidade C/ Desconto'], errors='coerce').fillna(0)
    df.loc[is_maua & (mcd_ia_temp == 0), 'Gemini Mensalidade C/ Desconto'] = df.loc[is_maua & (mcd_ia_temp == 0), 'Gemini Mensalidade S/ Desconto']
    # -----------------------------
    
    msd_sys = pd.to_numeric(df['Mensalidade S/ Desconto'], errors='coerce').fillna(0)
    msd_ia = pd.to_numeric(df['Gemini Mensalidade S/ Desconto'], errors='coerce').fillna(0)
    mcd_sys = pd.to_numeric(df['Mensalidade C/ Desconto'], errors='coerce').fillna(0)
    mcd_ia = pd.to_numeric(df['Gemini Mensalidade C/ Desconto'], errors='coerce').fillna(0)
    
    dif_s = msd_sys - msd_ia
    dif_c = np.where(mcd_ia != 0, mcd_sys - mcd_ia, 0)
    
    mask_ignorar_math = mask_ausente | mask_nao_processado | mask_corrompido
    dif_s = np.where(mask_ignorar_math, 0.0, dif_s)
    dif_c = np.where(mask_ignorar_math, 0.0, dif_c)
    
    qtd = pd.to_numeric(df.get('qtd_pagtos', pd.Series(0, index=df.index)), errors='coerce').fillna(0).astype(int)
    
    # Calculate effective months paid multiplier (to account for retroactives in total bolsa paga)
    paga_mensal = pd.to_numeric(df.get('último_valor_pago_referencia', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    total_pago = pd.to_numeric(df.get('total bolsa paga', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    qtd_pagtos_float = qtd.astype(float)
    
    # Where paga_mensal > 0, effective multiplier = total_pago / paga_mensal. Otherwise, fallback to qtd_pagtos
    multiplier = np.where(paga_mensal > 0, total_pago / paga_mensal, qtd_pagtos_float)
    
    tot_dif_s = dif_s * multiplier
    tot_dif_c = dif_c * multiplier

    soma_msd_real = pd.to_numeric(df.get('soma_cd_sem_desconto', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    soma_mcd_real = pd.to_numeric(df.get('soma_cd_com_desconto', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)

    # Use the exact historical sum if available (>0), otherwise fallback to multiplier estimation
    df['MSD_SOMA'] = np.where(soma_msd_real > 0, soma_msd_real, msd_sys * multiplier)
    df['MCD_SOMA'] = np.where(soma_mcd_real > 0, soma_mcd_real, mcd_sys * multiplier)
    
    df['G_MSD_SOMA'] = msd_ia * multiplier
    df['G_MCD_SOMA'] = mcd_ia * multiplier

    cond_msd_nao_loc = (msd_ia == 0)
    cond_msd_igual = (dif_s == 0)
    cond_msd_menor = (msd_ia < msd_sys)
    
    cond_mcd_nao_loc = (mcd_ia == 0)
    cond_mcd_igual = (dif_c == 0)
    cond_mcd_menor = (mcd_ia < mcd_sys)
    
    choices = [
        "Documento não enviado",
        "Não Processado",
        "Documento Corrompido",
        "Valor não localizado no documento",
        "Coleta de dados conforme documento",
        "Valor no documento é Menor"
    ]
    
    df['Dif. s/Desc.'] = dif_s
    df['% Dif. s/Desc.'] = np.where(msd_sys != 0, (dif_s / msd_sys), 0.0)
    df['Total Dif. s/Desc.'] = tot_dif_s
    df['MSD_DOC'] = np.select(
        [mask_ausente, mask_nao_processado, mask_corrompido, cond_msd_nao_loc, cond_msd_igual, cond_msd_menor],
        choices, default="Valor no documento é Maior"
    )
    
    df['Dif. c/Desc.'] = dif_c
    df['% Dif. c/Desc.'] = np.where(mcd_sys != 0, (dif_c / mcd_sys), 0.0)
    df['Total Dif. c/Desc.'] = tot_dif_c
    df['MCD_DOC'] = np.select(
        [mask_ausente, mask_nao_processado, mask_corrompido, cond_mcd_nao_loc, cond_mcd_igual, cond_mcd_menor],
        choices, default="Valor no documento é Maior"
    )

    mat_sd_ia = pd.to_numeric(df.get('Gemini Matricula Sem Desconto', pd.Series([0.0]*len(df), index=df.index)), errors='coerce').fillna(0.0)
    mat_cd_ia = pd.to_numeric(df.get('Gemini Matricula Com Desconto', pd.Series([0.0]*len(df), index=df.index)), errors='coerce').fillna(0.0)

    dif_mat_s = msd_sys - mat_sd_ia
    dif_mat_c = np.where(mat_cd_ia != 0, mcd_sys - mat_cd_ia, 0)
    
    dif_mat_s = np.where(mask_ignorar_math, 0.0, dif_mat_s)
    dif_mat_c = np.where(mask_ignorar_math, 0.0, dif_mat_c)

    cond_mat_sd_nao_loc = (mat_sd_ia == 0)
    cond_mat_sd_igual = (dif_mat_s == 0)
    cond_mat_sd_menor = (mat_sd_ia < msd_sys)
    
    cond_mat_cd_nao_loc = (mat_cd_ia == 0)
    cond_mat_cd_igual = (dif_mat_c == 0)
    cond_mat_cd_menor = (mat_cd_ia < mcd_sys)

    df['Matricula_SD_Doc'] = np.select(
        [mask_ausente, mask_nao_processado, mask_corrompido, cond_mat_sd_nao_loc, cond_mat_sd_igual, cond_mat_sd_menor],
        choices, default="Valor no documento é Maior"
    )

    df['Matricula_CD_Doc'] = np.select(
        [mask_ausente, mask_nao_processado, mask_corrompido, cond_mat_cd_nao_loc, cond_mat_cd_igual, cond_mat_cd_menor],
        choices, default="Valor no documento é Maior"
    )

    curso_str = df.get('Curso', pd.Series(['']*len(df), index=df.index)).astype(str).str.strip().str.upper()
    bolsa_str = df.get('tipo_bolsa_final', pd.Series(['']*len(df), index=df.index)).astype(str).str.strip().str.upper()
    beneficios = pd.to_numeric(df.get('valor_beneficio', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    paga = pd.to_numeric(df.get('último_valor_pago_referencia', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    
    df['OVG Pagou (Último Referencial)'] = paga
    df['Soma OVG Pagou'] = total_pago


    is_med_odonto = curso_str.isin(['MEDICINA', 'ODONTOLOGIA'])
    is_contrato = df['Documento Tipo'].astype(str).str.contains('CONTRATO|RIAF|RELATÓRIO', case=False, na=False)
    
    # [2] Referência do Sistema
    sys_mcd_50 = mcd_sys * 0.5
    sys_calc_parcial = np.where(is_med_odonto, np.minimum(sys_mcd_50, 2900.0), np.minimum(sys_mcd_50, 650.0))
    sys_calc_integral = np.where(is_med_odonto, np.minimum(mcd_sys, 5800.0), np.minimum(mcd_sys, 1500.0))
    sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
    
    sys_excedeu = (sys_bolsa_base + beneficios) > mcd_sys
    sys_bolsa_final = np.where(sys_excedeu, mcd_sys - beneficios, sys_bolsa_base)
    sys_bolsa_final = np.maximum(sys_bolsa_final, 0.0)

    df['OVG Deveria Pagar (Último Referencial)'] = np.where(is_contrato & (~mask_ignorar_math), sys_bolsa_final, 0.0)

    df['Soma OVG Deveria Pagar (Sistema)'] = df.get('soma_deveria_sistema', 0.0)
    if 'tem_pagamento_historico' in df.columns:
        mask_sem_pag = (~df['tem_pagamento_historico']) & (df['qtd_pagtos'].fillna(0).astype(float) > 0)
        df.loc[mask_sem_pag, 'Soma OVG Deveria Pagar (Sistema)'] = df.loc[mask_sem_pag, 'qtd_pagtos'].fillna(0).astype(float) * df.loc[mask_sem_pag, 'OVG Deveria Pagar (Último Referencial)']

    # [5] e [6] Referência da IA
    # 1. Cálculo Normal
    g_mcd_50 = mcd_ia * 0.5
    g_calc_parcial = np.where(is_med_odonto, np.minimum(g_mcd_50, 2900.0), np.minimum(g_mcd_50, 650.0))
    g_calc_integral = np.where(is_med_odonto, np.minimum(mcd_ia, 5800.0), np.minimum(mcd_ia, 1500.0))
    g_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [g_calc_parcial, g_calc_integral], default=0.0)
    
    g_excedeu = (g_bolsa_base + beneficios) > mcd_ia
    g_bolsa_final = np.where(g_excedeu, mcd_ia - beneficios, g_bolsa_base)
    g_bolsa_final = np.maximum(g_bolsa_final, 0.0)

    # 2. Cálculo Janeiro de 2026
    g_mcd_50_202601 = mat_cd_ia * 0.5
    g_calc_parcial_202601 = np.where(is_med_odonto, np.minimum(g_mcd_50_202601, 2900.0), np.minimum(g_mcd_50_202601, 650.0))
    g_calc_integral_202601 = np.where(is_med_odonto, np.minimum(mat_cd_ia, 5800.0), np.minimum(mat_cd_ia, 1500.0))
    g_bolsa_base_202601 = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [g_calc_parcial_202601, g_calc_integral_202601], default=0.0)
    
    g_excedeu_202601 = (g_bolsa_base_202601 + beneficios) > mat_cd_ia
    g_bolsa_final_202601 = np.where(g_excedeu_202601, mat_cd_ia - beneficios, g_bolsa_base_202601)
    g_bolsa_final_202601 = np.maximum(g_bolsa_final_202601, 0.0)

    df['OVG Deveria Pagar (IA)'] = np.where(is_contrato & (~mask_ignorar_math), g_bolsa_final, 0.0)

    qtd_pag_calc = df['qtd_pagtos'].fillna(0).astype(float)
    qtd_retro = df.get('qtd_pagtos_retroativos', pd.Series(0, index=df.index)).fillna(0).astype(float)
    mult_soma_ia = np.maximum(qtd_pag_calc - qtd_retro, 0.0)

    # 3. Composição da Soma (Mistos de Janeiro/2026 e Normais)
    qtd_pag_202601 = df.get('qtd_pagtos_202601', pd.Series(0.0, index=df.index)).fillna(0).astype(float)
    qtd_pag_202601 = np.minimum(qtd_pag_202601, mult_soma_ia)
    qtd_pag_normal = np.maximum(mult_soma_ia - qtd_pag_202601, 0.0)
    
    soma_ia_normal = np.where(is_contrato & (~mask_ignorar_math), g_bolsa_final * qtd_pag_normal, 0.0)
    soma_ia_202601 = np.where(is_contrato & (~mask_ignorar_math), g_bolsa_final_202601 * qtd_pag_202601, 0.0)
    
    df['Soma OVG Deveria Pagar (IA)'] = soma_ia_normal + soma_ia_202601
    
    if 'Soma Valor Financiamento' not in df.columns:
        df['Soma Valor Financiamento'] = pd.to_numeric(df.get('valor_financiamento', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0) * mult_soma_ia
    else:
        df['Soma Valor Financiamento'] = pd.to_numeric(df['Soma Valor Financiamento'], errors='coerce').fillna(0.0)
        mask_sf = (df['Soma Valor Financiamento'] == 0)
        df.loc[mask_sf, 'Soma Valor Financiamento'] = pd.to_numeric(df.get('valor_financiamento', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)[mask_sf] * mult_soma_ia[mask_sf]

    if 'Soma Valor Beneficio' not in df.columns:
        df['Soma Valor Beneficio'] = pd.to_numeric(df.get('valor_beneficio', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0) * mult_soma_ia
    else:
        df['Soma Valor Beneficio'] = pd.to_numeric(df['Soma Valor Beneficio'], errors='coerce').fillna(0.0)
        mask_sb = (df['Soma Valor Beneficio'] == 0)
        df.loc[mask_sb, 'Soma Valor Beneficio'] = pd.to_numeric(df.get('valor_beneficio', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)[mask_sb] * mult_soma_ia[mask_sb]

    if 'qual_beneficio' in df.columns:
        df['qual_beneficio'] = df['qual_beneficio'].astype(str).str.strip()
        df['qual_beneficio'] = df['qual_beneficio'].replace(['0', 'Sem outros benefícios', 'Sem Outros Benefícios', 'Sem benefícios', 'Sem beneficios'], 'Sem Benefícios')
        padronizar_rotulo_outros(df, ['qual_beneficio'])
        if 'valor_beneficio' in df.columns:
            mask_benef_zero = (pd.to_numeric(df['valor_beneficio'], errors='coerce').fillna(0.0) == 0) & (df['Soma Valor Beneficio'] == 0) & (df['qual_beneficio'] != 'Sem Benefícios')
            df.loc[mask_benef_zero, 'qual_beneficio'] = 'Sem Benefícios'

    if 'qual_financiamento' in df.columns:
        df['qual_financiamento'] = df['qual_financiamento'].astype(str).str.strip()
        df['qual_financiamento'] = df['qual_financiamento'].replace(['0', 'Sem financiamento'], 'Sem Financiamento')
        padronizar_rotulo_outros(df, ['qual_financiamento'])
        if 'valor_financiamento' in df.columns:
            mask_fin_zero = (pd.to_numeric(df['valor_financiamento'], errors='coerce').fillna(0.0) == 0) & (df['Soma Valor Financiamento'] == 0) & (df['qual_financiamento'] != 'Sem Financiamento')
            df.loc[mask_fin_zero, 'qual_financiamento'] = 'Sem Financiamento'

    # Prejuízo e Economia (IA) [7], [8] e [9]
    cond_falha_leitura = (mcd_ia == 0)
    
    # Calculate PREJUÍZO based on the TOTAL SUMS to account for floating point errors and mixed Jan-2026 calculation logic
    soma_paga = df['Soma OVG Pagou'].fillna(0.0).astype(float).round(2)
    soma_ia_total = df['Soma OVG Deveria Pagar (IA)'].fillna(0.0).astype(float).round(2)
    
    soma_prejuizo_ovg = np.maximum(soma_paga - soma_ia_total, 0.0)
    soma_economia_ovg = np.maximum(soma_ia_total - soma_paga, 0.0)
    
    # Unitary values (approximated for display backwards-compatibility)
    prejuizo_ovg = np.where(multiplier > 0, soma_prejuizo_ovg / multiplier, 0.0)

    df['Prejuízo da OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), prejuizo_ovg, 0.0)
    df['Soma Prejuízo da OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), soma_prejuizo_ovg, 0.0)
    df['Economia da OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), soma_economia_ovg, 0.0)

    df['Diagnóstico Financeiro Final'] = np.select(
        [
            (~is_contrato),
            mask_ignorar_math,
            cond_falha_leitura,
            (soma_paga > soma_ia_total),
            (soma_paga < soma_ia_total) & (soma_paga > 0),
            (soma_paga == 0) & (soma_ia_total > 0),
            (soma_paga == soma_ia_total)
        ],
        [
            "N/A",
            "Não Processado", 
            "Valor não localizado",
            "OVG pagou a mais",
            "OVG pagou a menos",
            "Pagamento não realizado",
            "Pagamento correto"
        ],
        default="Verificar"
    )
    
    ia_status_original = df.get('Status_IA', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '')
    ia_status_upper = ia_status_original.str.upper()

    sys_semestre = df.get('Semestre', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '').str.replace('-', '/')
    ia_semestre = df.get('Gemini Semestre', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '').str.replace('-', '/')
    sys_cpf = df.get('CPF', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '').str.replace(r'\.0$', '', regex=True)
    ia_cpf = df.get('Gemini CPF', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '').str.replace(r'\.0$', '', regex=True)
    inc_original = df.get('Gemini Inconsistencias', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().replace(['nan', 'None', '<NA>', 'NaN'], '')
    dif_s = pd.to_numeric(df.get('Dif. s/Desc.', pd.Series([0]*len(df), index=df.index)), errors='coerce').fillna(0)
    sys_processado = df.get('Processado', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().str.upper()
    sys_processar = df.get('Processar', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip().str.upper()
    sys_data_proc = df.get('Data Processamento', pd.Series(['']*len(df), index=df.index)).astype(object).fillna('').astype(str).str.strip()
    
    qtd_pagtos = pd.to_numeric(df.get('qtd_pagtos', pd.Series([0]*len(df), index=df.index)), errors='coerce').fillna(0)
    
    # Base de verificação de retorno vazio
    vazio_bases = (ia_cpf == '') & (ia_semestre == '') & (inc_original == '') & (sys_processado == 'SIM') & (~ia_status_upper.str.contains('NÃO PROCESSADO|NAO PROCESSADO', regex=True))
    
    # Se estava marcado para processar ou tem data de processamento real, significa que a IA tentou ler e falhou (Corrompido)
    cond_vazio_corrompido = vazio_bases & ((sys_processar == 'SIM') | ((sys_data_proc != '') & (sys_data_proc != '-')))
    
    # Se não estava marcado para processar e não tem data de processamento, apenas ficou no limbo = Não Processado
    cond_vazio_nao_processado = vazio_bases & ~cond_vazio_corrompido
    
    is_historico = doc_tipo.str.contains('HIST', case=False, na=False)

    # REGRA DE INADIMPLENTE — espelho exato de `analise_ia`, que a recebeu em 59cb881.
    #
    # A versão anterior aqui era `qtd_pagtos == 0`, e ela NUNCA disparava: na tabela de
    # pagamentos não existe uma única linha com zero lançamentos (0 de 65.197 pares
    # inscrição/semestre). O status só era atribuído por efeito colateral, a quem não tinha
    # nenhuma linha de pagamento para casar no merge.
    #
    # O que a regra precisa enxergar é o repasse LÍQUIDO. `qtd_pagtos_retroativos` conta os
    # pagamentos cancelados a 100% (bolsa devolvida), então `qtd_pagtos - retroativos <= 0`
    # significa "a OVG não custeou nada neste semestre" — o beneficiário entrou e saiu antes de
    # estudar, trocou de bolsa e migrou de inscrição, ou teve o repasse estornado por inteiro.
    # São 982 pares inscrição/semestre na base, contra os ~260 que a regra antiga pegava.
    #
    # POR QUE ISSO IMPORTA: o documento existe para auditar o valor que a OVG pagou. Sem valor
    # pago não há o que auditar, e cobrar o documento da IES vira exigência sem lastro. Todas as
    # fórmulas do relatório gerencial já filtram `"<>INADIMPLENTE"`, então marcar aqui basta
    # para tirar a linha da cobrança — sem apagá-la, que é o erro corrigido em 14324a7.
    total_bolsa = pd.to_numeric(df.get('total bolsa paga', pd.Series([0]*len(df), index=df.index)), errors='coerce').fillna(0)
    qtd_retroativos = pd.to_numeric(df.get('qtd_pagtos_retroativos', pd.Series([0]*len(df), index=df.index)), errors='coerce').fillna(0)
    cond_inadimplente = ((qtd_pagtos - qtd_retroativos) <= 0) | (total_bolsa <= 0)

    matematica_invalida_geral = (ia_cpf == '') | (sys_cpf != ia_cpf) | (ia_semestre == '') | (sys_semestre != ia_semestre)
    matematica_invalida_financeiro = (inc_original.str.contains('Valor da mensalidade integral não localizado', na=False)) | (dif_s != 0)

    # Para Histórico, ignorar regras financeiras (pois as colunas não fazem parte de sua verificação)
    matematica_invalida = np.where(is_historico, matematica_invalida_geral, matematica_invalida_geral | matematica_invalida_financeiro)
    matematica_diz = np.where(matematica_invalida, 'Inválido', 'Válido')
    
    ia_resultado = np.where(ia_status_upper.str.startswith('V'), 'Válido', 'Inválido')
    
    cond_falso_invalido = (matematica_diz == 'Válido') & (ia_resultado == 'Inválido')
    cond_falso_valido = (matematica_diz == 'Inválido') & (ia_resultado == 'Válido')

    base_resultado = np.where(cond_falso_invalido, 'Falso Inválido', np.where(cond_falso_valido, 'Falso Válido', ia_resultado))

    # O veredito da IA sobre o ARQUIVO, isolado. Não vira coluna: serve para separar, logo
    # abaixo, o inadimplente que entregou do que não entregou — dois casos opostos para quem
    # cobra a IES, e que `Status_IA` sozinho não consegue distinguir depois da sobreposição.
    veredito_documento = np.where(ia_status_upper.str.contains('AUSENTE') | (ia_status_upper == 'X'), 'Ausente',
                         np.where(ia_status_upper.str.contains('CORROMPIDO') | cond_vazio_corrompido, 'Corrompido',
                         np.where((ia_status_original == '') | ia_status_upper.str.contains('NÃO PROCESSADO|NAO PROCESSADO', regex=True) | cond_vazio_nao_processado, 'Não Processado',
                         base_resultado)))

    # `Inadimplente` SOBREPÕE o veredito da IA de propósito, e isso não é perda de informação:
    # se não houve repasse líquido, o documento nem era vigente no semestre — foi lido por
    # engano, e o resultado dessa leitura (Válido, Inválido, Falso Válido) não descreve uma
    # obrigação que existisse. Quem precisa saber que o arquivo chegou e foi lido tem
    # `Veredito Documento`, gravada logo abaixo — a informação é sobreposta aqui, não perdida.
    final_status = np.where(cond_inadimplente, 'Inadimplente', veredito_documento)

    df['Status_IA'] = final_status

    # O VEREDITO DA IA SOBREVIVE À SOBREPOSIÇÃO — é só para isso que esta coluna existe.
    #
    # A linha acima acaba de APAGAR a informação de leitura de toda linha inadimplente: onde
    # `cond_inadimplente` venceu, o que a IA disse sobre o arquivo (`Não Processado`, `Válido`,
    # `Corrompido`...) deixou de estar em coluna nenhuma do relatório. O comentário logo acima
    # afirma que "quem precisa saber que o arquivo foi lido tem a coluna `Status Doc` do
    # dashboard" — mas o dashboard MONTA essa coluna a partir daqui, então ele ficava sem
    # fonte e adivinhava por `Processado`.
    #
    # E `Processado` NÃO É VEREDITO DE LEITURA: é o carimbo que vem do espelho do SIBU e do
    # `consolidado_agendar_processamentos`, e diz apenas que aquela inscrição passou pela fila
    # em algum momento. Medido no Parquet de 31/08/2026: 20.736 linhas com `Processado = SIM`
    # cujo próprio `Status_IA` era `Não Processado`. O efeito na tela eram 83 documentos na
    # fatia "Inadimplentes Proc." sem nunca terem sido lidos — entre eles os 4 RIAF de 2026-2
    # (2185963, 2157339, 2177029, 2202104), todos sem data de processamento, sem token e sem
    # um único campo `Gemini` preenchido.
    #
    # GRAVADA SEM TRANSFORMAÇÃO, de propósito: é o MESMO `veredito_documento` que a linha
    # acima consumiu, com os mesmos sete valores possíveis. Quem lê a coluna lê o que a IA
    # disse, não uma inferência sobre isso — que era exatamente o defeito a corrigir.
    df['Veredito Documento'] = veredito_documento

    # O INADIMPLENTE QUE NÃO ENTREGOU O DOCUMENTO NÃO CHEGA MAIS ATÉ AQUI.
    #
    # Esta linha já foi descartada duas vezes NESTE ponto, e as duas vezes o descarte estava no
    # lugar errado: aqui os documentos ENTREGUES e os AUSENTES já dividem o mesmo DataFrame, e
    # uma máscara que olhasse só o pagamento levava os dois — foi o bug de 2025-2, com 223
    # históricos entregues apagados junto com 33 pendências.
    #
    # O corte passou para a ORIGEM, onde as linhas ausentes são criadas (`sem_repasse_liquido`,
    # na geração dos ausentes): lá o DataFrame só tem candidatos a `Ausente`, e apanhar um
    # documento entregue é impossível por construção. Se um dia voltar a aparecer inadimplente
    # sem documento no relatório, o conserto é naquele filtro — nunca um descarte aqui.



    # Limpa a variável temporária para não vazar no Excel
    df.drop(columns=['soma_deveria_sistema', 'tipo_bolsista_renovacao'], errors='ignore', inplace=True)

    ordem_desejada = [
        'Status_IA', 'Status_Vínculo', 
        'Situação do Motivo', 'Observação da Situação',
        'Mudou IES?', 'IES Anterior', 'IES Posterior', 'Mudou Bolsa?', 'Bolsa Anterior', 'Bolsa Posterior', 
        'Semestre', 'Gemini Semestre', 'Inscrição', 'Inscrição Anterior', 'Inscrição Posterior', 
        'Bolsista', 'CPF', 'Gemini CPF', 'Gemini Inconsistencias', 'Faculdade', 'Curso', 
        'tipo_bolsa_final', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'último_valor_pago_referencia', 'total bolsa paga', 
        
        'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Dif. s/Desc.', '% Dif. s/Desc.', 'Total Dif. s/Desc.', 'MSD_SOMA', 'G_MSD_SOMA', 'MSD_DOC', 
        
        'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Dif. c/Desc.', '% Dif. c/Desc.', 'Total Dif. c/Desc.', 'MCD_SOMA', 'G_MCD_SOMA', 'MCD_DOC', 
        
        'Gemini Matricula Sem Desconto', 'Matricula_SD_Doc',
        'Gemini Matricula Com Desconto', 'Matricula_CD_Doc',
        
        # --- O BLOCO FINANCEIRO NA ORDEM EXATA ---
        'OVG Pagou (Último Referencial)',
        'OVG Deveria Pagar (Último Referencial)', 
        'Soma OVG Pagou',
        'Soma OVG Deveria Pagar (Sistema)',
        'OVG Deveria Pagar (IA)', 
        'Soma OVG Deveria Pagar (IA)',
        'Prejuízo da OVG (R$)',
        'Soma Prejuízo da OVG (R$)',
        'Economia da OVG (R$)',
        'Diagnóstico Financeiro Final',
        
        'valor_beneficio', 'Soma Valor Beneficio', 'qual_beneficio', 'valor_financiamento', 'Soma Valor Financiamento', 'qual_financiamento', 'data_coleta',
        'Documento Tipo', 'Check Contrato', 'Check Financiamento', 'Check Benefícios', 'Check RIAF', 'Check Histórico', 
        'Processar', 'Processado', 'Documento Ausente', 'Veredito Documento', 'Data Processamento', 'Coleta ID',
        'inscricao_ano', 'uni_deficiencia', 'uni_sexo'
    ]
    
    cols_ordenadas = [col for col in ordem_desejada if col in df.columns]
    colunas_sujas = ['situacao', 'situacao_atual_sistema', 'sit_data_atual_sistema', 'sit_obs_atual_sistema']
    cols_extras = [col for col in df.columns if col not in cols_ordenadas and col not in colunas_sujas]
    
    df = df[cols_ordenadas + cols_extras]
    
    # O DESCARTE POR ESTORNO COMPLETO foi removido a pedido do dono do projeto, junto com o
    # gêmeo em apps/automacoes/analise_ia/services/ggci.py — este dashboard é espelho exato
    # do resultado do Análise IA e vai alimentar dashboards futuros, então os dois têm de
    # sumir ou permanecer juntos, nunca um só.
    #
    # Estava aqui: quando `qtd_pagtos == qtd_pagtos_retroativos` a linha era eliminada do
    # relatório inteiro, sem aviso. A leitura do dado está certa — `qtd_pagtos_retroativos`
    # conta os pagamentos CANCELADOS A 100% (bolsa devolvida); cancelamento parcial de 40%
    # ou 60% NÃO entra nessa contagem, ele aparece como valor cancelado na aba Pagamentos e
    # o pagamento continua valendo. Ou seja, a igualdade realmente significa "todo o
    # repasse do semestre foi devolvido". Não confundir com "retroativo" na aba Pagamentos,
    # onde a palavra tem outro sentido e não implica devolução.
    #
    # O erro era a AÇÃO, não a leitura: devolver a bolsa não apaga o fato de a IES ter (ou
    # não ter) entregado o documento. Como esta função roda depois que tanto os enviados
    # quanto os Ausentes já estão no df, o filtro derrubava a linha das DUAS categorias de
    # uma vez — o beneficiário sumia do relatório e ninguém percebia que o documento dele
    # nunca foi conferido. Em 2025-2 isso escondia 223 históricos enviados e 33 pendências.
    #
    # Quem precisa isolar esses casos compara `qtd_pagtos` com `qtd_pagtos_retroativos`, que
    # já saem lado a lado em todas as abas de documento — por isso não foi criada coluna nova.

    # `Documento Ausente` entra aqui junto com as de processamento: ela só é escrita na
    # injeção das cobranças do site, e sem o preenchimento as demais linhas ficariam nulas —
    # o dashboard trata nulo como "não sei", e a fatia perderia o contraste que a define.
    # Ver a injeção `COBRANÇA` em `gerar_relatorio_geral`.
    # Preencher colunas de processamento com NÃO quando estiverem vazias
    for col in ['Processado', 'Processar', 'Documento Ausente']:
        if col in df.columns:
            df[col] = df[col].replace('', 'NÃO').fillna('NÃO')

    return df
# ==========================================
# 5. GERADOR DE RESUMO QUANTITATIVO
# ==========================================
# O catálogo de mantenedoras era um dicionário de 930 linhas AQUI, duplicado byte a
# byte no `services/ggci.py` do outro app. Agora é dado versionado em
# `portal_ggci/mantenedoras.json`, com um só resolvedor em `portal_ggci/mantenedoras.py`
# — corrigir o nome de uma mantenedora deixou de exigir editar dois arquivos Python.
# Os nomes abaixo continuam existindo porque o resto deste arquivo os usa.
MANTENEDORAS = _catalogo_mantenedoras()
buscar_mantenedora = _buscar_mantenedora

def padronizar_ies(texto):
    """
    O QUE FAZ: Reduz o nome de uma instituição a uma forma comparável.
    POR QUÊ EXISTE: O mesmo nome de IES chega grafado de formas diferentes conforme a origem;
    o cruzamento com a tabela de mantenedoras só fecha sobre a forma normalizada.
    COMO FUNCIONA: Sobe para maiúsculas, remove acentos, troca o que não for letra ou número
    por espaço e colapsa os espaços.
    PARÂMETROS: texto (str ou NaN)
    RETORNO: string normalizada, ou "" para nulo.
    """
    if pd.isna(texto): return ""
    txt = str(texto).upper().strip()
    txt = ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
    txt = re.sub(r'[^A-Z0-9\s]', ' ', txt) # Remove especial chars
    return ' '.join(txt.split()) # Remove double spaces



def gerar_resumo_quantitativo(df_target, tipos_documentos):
    """
    O QUE FAZ: Conta quantos alunos existem por IES e constrói métricas (Envios vs Esperados).
    POR QUÊ EXISTE: Gerar a aba de volumetria "Resumo_Quantitativo" para painéis gerenciais.
    COMO FUNCIONA: Agrupa por `Faculdade` + `Semestre` e conta CPFs únicos ativos x desligados.

    SOBRE O DESEMPENHO: são ~420 grupos (105 IES x 4 semestres) e o laço rodava por grupo
    coisas que não dependem do grupo — `to_datetime` da mesma coluna 420 vezes, o
    `astype(str).str.lower()` do Status_IA mais de 2.000 vezes, `to_numeric` dos valores
    800 vezes, duas cópias de um DataFrame de 62 colunas por iteração. Tudo isso subiu
    para fora do laço. Medido nas dimensões reais: 22,4s -> 8,1s, saída idêntica.

    O que **não** saiu do laço é a ordenação por `temp_data`: `sort_values` não é estável,
    então ordenar de outro jeito poderia desempatar datas iguais diferente e trocar a
    linha que o `drop_duplicates(keep='first')` mantém — mudaria número no relatório.
    """
    if df_target.empty:
        return pd.DataFrame()

    # reset_index devolve um objeto novo, então as colunas auxiliares abaixo não vazam
    # para o DataFrame de quem chamou. O índice único é o que permite alinhar as séries
    # pré-calculadas com as fatias de cada grupo.
    df_target = df_target.reset_index(drop=True)

    s_status_strip = df_target['Status_IA'].astype(str).str.strip()
    s_status_low = s_status_strip.str.lower()

    tem_data = 'data_coleta' in df_target.columns
    if tem_data:
        df_target['temp_data'] = pd.to_datetime(df_target['data_coleta'], format='%d/%m/%Y', errors='coerce')

    tem_fin = 'valor_financiamento' in df_target.columns
    s_fin = pd.to_numeric(df_target['valor_financiamento'], errors='coerce').fillna(0.0) if tem_fin else None
    tem_ben = 'valor_beneficio' in df_target.columns
    s_ben = pd.to_numeric(df_target['valor_beneficio'], errors='coerce').fillna(0.0) if tem_ben else None

    STATUS_PROCESSADOS = {'inválido', 'válido', 'falso inválido', 'falso válido',
                          'invalido', 'valido', 'falso invalido', 'falso valido'}
    cache_ies, cache_mantenedora = {}, {}

    resumo_data = []

    tem_contrato_na_base = 'CONTRATO' in tipos_documentos

    # 1. Ignorar "Falso Ausente" de todo o resumo — antes era por grupo, com uma cópia cada
    base_resumo = df_target[s_status_strip != 'Falso Ausente']

    for (ies, semestre), group_raw in base_resumo.groupby(['Faculdade', 'Semestre']):

        if group_raw.empty:
            continue

        # 2. DataFrame DEDUPLICADO para os alunos (Beneficiários, Ativos, etc e Pendências Finais)
        if tem_data:
            group_benef = group_raw.sort_values(by=['temp_data'], ascending=False, na_position='last')
        else:
            group_benef = group_raw

        group_benef = group_benef.drop_duplicates(subset=['CPF', 'Documento Tipo'], keep='first')

        cpfs_validos = group_benef['CPF'].dropna().unique()

        if len(cpfs_validos) == 0:
            continue

        tot_benef = len(cpfs_validos)

        # Como o dataframe já está ordenado pela data mais recente (decrescente), pegamos o primeiro status de cada CPF
        status_por_cpf = group_benef.groupby('CPF', sort=False)['Status_Vínculo'].first()
        ativos = (status_por_cpf == 'ATIVO').sum()
        desligados = (status_por_cpf == 'DESLIGADO').sum()

        if ies not in cache_ies:
            cache_ies[ies] = padronizar_ies(ies)
            cache_mantenedora[ies] = buscar_mantenedora(ies)
        ies_padronizada = cache_ies[ies]
        mantenedora_nome = cache_mantenedora[ies]

        idx_benef = group_benef.index
        doc_tipo_benef = group_benef['Documento Tipo']

        row = {
            'MANTENEDORA': mantenedora_nome,
            'IES': ies_padronizada,
            'Semestre': semestre,
            'Total Beneficiários': tot_benef,
            'Ativos': ativos,
            'Desligados': desligados
        }
        
        for doc_k, doc_name in tipos_documentos.items():
            is_na = False
            if doc_name == DOC_RIAF and str(semestre).split('-')[0].isdigit() and int(str(semestre).split('-')[0]) < 2026:
                is_na = True
            
            if is_na:
                row[f'Env. {doc_k}'] = "N/A"
                row[f'Pend. {doc_k}'] = "N/A"
                row[f'% {doc_k}'] = "N/A"
                row[f'{doc_k} Proc.'] = "N/A"
                row[f'{doc_k} NÃO Proc.'] = "N/A"
                row[f'% {doc_k} Proc.'] = "N/A"
                continue
                
            # OTIMIZAÇÃO: Calcular base esperada de forma inteligente para Financiamento e Benefícios (usando base deduplicada)
            if doc_name == DOC_FINANC:
                base_expected = group_benef.loc[s_fin.loc[idx_benef] > 0, 'CPF'].nunique() if tem_fin else 0
            elif doc_name == DOC_BENEF:
                base_expected = group_benef.loc[s_ben.loc[idx_benef] > 0, 'CPF'].nunique() if tem_ben else 0
            else:
                base_expected = tot_benef

            # --- MATEMÁTICA CONSISTENTE (Evita somar mais que o Total de Beneficiários) ---
            # Trabalhamos APENAS com a base deduplicada para não inflar Envios
            status_ia_benef = s_status_low.loc[idx_benef[doc_tipo_benef == doc_name]]
            
            # 1. Quantos foram processados e não processados (únicos por CPF)
            proc_count = status_ia_benef.isin(STATUS_PROCESSADOS).sum()
            nao_proc_count = (status_ia_benef == 'não processado').sum()
            
            enviados = proc_count + nao_proc_count
            
            # 2. As pendências reais devem refletir exatamente os ausentes contados, que vieram da view do SIBU
            # Evita inflar pendências com matemática "cega" que causa discrepâncias com as abas de pendências
            pendentes_contados = status_ia_benef.isin(['ausente', 'ausentes', 'corrompido']).sum()
            pendentes_reais = pendentes_contados
            
            # Se a base_expected for 0, mas houver enviados (ex: financiamento não obrigatório)
            base_real = max(base_expected, enviados + pendentes_reais)
            
            row[f'Env. {doc_k}'] = enviados
            row[f'Pend. {doc_k}'] = pendentes_reais
            
            if base_real > 0:
                row[f'% {doc_k}'] = enviados / base_real
            else:
                row[f'% {doc_k}'] = 0.0
            
            row[f'{doc_k} Proc.'] = proc_count
            row[f'{doc_k} NÃO Proc.'] = nao_proc_count
            if enviados > 0:
                row[f'% {doc_k} Proc.'] = proc_count / enviados
            else:
                row[f'% {doc_k} Proc.'] = 0.0

            
        resumo_data.append(row)
        
    df_resumo = pd.DataFrame(resumo_data)
    if not df_resumo.empty:
        df_resumo.sort_values(by=['IES', 'Semestre'], ascending=[True, True], inplace=True)
        for col in df_resumo.columns:
            if df_resumo[col].dtype.name == 'Int64':
                df_resumo[col] = df_resumo[col].astype('object')
                df_resumo.loc[pd.isna(df_resumo[col]), col] = None
        
    return df_resumo

# ==========================================
# 6 GERADOR DA ABA DE RELATÓRIO IES (LAYOUT E FÓRMULAS)
# ==========================================
def gerar_aba_relatorio_contratos(writer, df_docs, sems_contratos):
    """
    O QUE FAZ: Monta a aba "Relatório Contratos", o painel gerencial por IES e semestre.
    POR QUÊ EXISTE: É a leitura executiva do relatório — quem abre o arquivo começa por ela,
    não pelas abas analíticas linha a linha.
    COMO FUNCIONA: Escreve o bloco de cada semestre em colunas de 6 e monta as linhas de
    aferição, somas e diferenças como fórmulas do Excel, não como valores calculados aqui —
    assim o painel continua consistente se alguém filtrar a planilha. col_to_letter converte
    o índice numérico em letra de coluna para essas fórmulas.
    PARÂMETROS: writer (pd.ExcelWriter), df_docs (DataFrame), sems_contratos (list)
    RETORNO: None — escreve direto no writer.
    """
    if not sems_contratos:
        sems_contratos = ["2025-1", "2025-2", "2026-1", "2026-2"]
        
    workbook = writer.book
    worksheet = workbook.add_worksheet('Relatório Contratos')
    worksheet.set_tab_color('#EB94B5')
    worksheet.hide_gridlines(2)
    worksheet.ignore_errors({
        'number_stored_as_text': 'A1:XFD1048576',
        'eval_error': 'A1:XFD1048576',
        'formula_differs': 'A1:XFD1048576',
        'formula_range': 'A1:XFD1048576',
        'formula_unlocked': 'A1:XFD1048576',
        'empty_cell_reference': 'A1:XFD1048576',
        'list_data_validation': 'A1:XFD1048576',
        'calculated_column': 'A1:XFD1048576',
        'two_digit_text_year': 'A1:XFD1048576'
    })
    
    def col_to_letter(idx):
        result = ""
        while idx >= 0:
            result = chr(idx % 26 + ord('A')) + result
            idx = idx // 26 - 1
        return result
        
    cols_list = list(df_docs.columns)
    def get_col(nome):
        if nome in cols_list:
            return col_to_letter(cols_list.index(nome))
        return None
        
    COL_FACULDADE = get_col('Faculdade') or 'T'
    COL_SEMESTRE = get_col('Semestre') or 'K'
    COL_STATUS_IA = get_col('Status_IA') or 'A'
    COL_TOTAL_BOLSA = get_col('total bolsa paga') or 'Y'
    COL_INCONSIST = get_col('Gemini Inconsistencias') or 'S'
    COL_DOC_TIPO = get_col('Documento Tipo') or 'BC'
    COL_QTD_PAGTOS = get_col('qtd_pagtos') or 'W'
    
    COL_MSD_COLETA = get_col('Mensalidade S/ Desconto') or 'Z'
    COL_MSD_CONTRATO = get_col('Gemini Mensalidade S/ Desconto') or 'AA'
    COL_MSD_DOC = get_col('MSD_DOC') or 'AG'
    COL_MSD_SOMA = get_col('MSD_SOMA') or 'AE'
    COL_G_MSD_SOMA = get_col('G_MSD_SOMA') or 'AF'
    
    COL_MCD_COLETA = get_col('Mensalidade C/ Desconto') or 'AH'
    COL_MCD_CONTRATO = get_col('Gemini Mensalidade C/ Desconto') or 'AI'
    COL_MCD_DOC = get_col('MCD_DOC') or 'AO'
    COL_MCD_SOMA = get_col('MCD_SOMA') or 'AM'
    COL_G_MCD_SOMA = get_col('G_MCD_SOMA') or 'AN'
    
    COL_BOLSA_CALC = get_col('Soma OVG Deveria Pagar (IA)') or 'AQ'
    COL_TIPO_BOLSA = get_col('tipo_bolsa_final') or 'V'
    COL_CPF = get_col('CPF') or 'Q'
    
    COL_VALOR_FINANC = get_col('valor_financiamento') or 'AZ'
    COL_SOMA_VALOR_FINANC = get_col('Soma Valor Financiamento') or 'AZ'
    COL_VALOR_BENEF = get_col('valor_beneficio') or 'AX'
    COL_SOMA_VALOR_BENEF = get_col('Soma Valor Beneficio') or 'AX'
    
    fmt_branco = workbook.add_format({'bg_color': '#FFFFFF', 'align': 'center', 'valign': 'vcenter'})
    fmt_titulo = workbook.add_format({'bold': True, 'font_size': 22, 'valign': 'vcenter', 'align': 'center'})
    fmt_input = workbook.add_format({'valign': 'vcenter', 'align': 'center', 'bold': True, 'bg_color': '#AAD176', 'font_color': '#000000'}) 
    
    fmt_header_rosa = workbook.add_format({'bold': True, 'bg_color': '#eb94b5', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_pct_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_moeda_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    
    fmt_header_laranja = workbook.add_format({'bold': True, 'bg_color': '#f8c4b4', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_laranja_red = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'font_color': 'red'})
    fmt_cell_center_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    fmt_pct_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})

    fmt_header_azul1 = workbook.add_format({'bold': True, 'bg_color': '#b9cbe2', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter'})
    fmt_titulo_diferenca = workbook.add_format({'bg_color': '#dde6f0', 'font_color': '#C0504D', 'border': 1, 'valign': 'vcenter', 'bold': True, 'italic': True})
    fmt_cell_center_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    
    fmt_header_roxo = workbook.add_format({'bold': True, 'bg_color': '#cdc0d9', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter'})
    fmt_pct_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_cell_center_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center'})

    fmt_moeda_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    fmt_pct_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})

    has_var = len(sems_contratos) >= 2
    cols_count = len(sems_contratos) + (1 if has_var else 0)
    last_col_idx = 6 * cols_count

    worksheet.set_column('A:A', 53.14)
    worksheet.set_column(1, last_col_idx, 9.14) if last_col_idx >= 1 else worksheet.set_column('B:S', 9.14)
    worksheet.set_row(0, 86.25) 
    worksheet.set_row(1, 26.25) 
    worksheet.set_row(2, 8)
    worksheet.set_row(7, 8)
    worksheet.set_row(13, 8)
    worksheet.set_row(18, 15)
    worksheet.set_row(19, 8)
    worksheet.set_row(22, 15)
    worksheet.set_row(23, 15)
    worksheet.set_row(30, 8)
    worksheet.set_row(33, 15)
    worksheet.set_row(34, 15)
    worksheet.set_row(41, 8)
    worksheet.set_row(42, 15)
    worksheet.set_row(49, 8)
    worksheet.set_row(50, 15)
    worksheet.set_row(59, 8)
    worksheet.set_row(60, 15)

    caminho_imagem = os.path.join('static', 'img', 'icones', 'relatorio.png')
    
    if not has_var:
        worksheet.write(0, 0, "Relatório Informativo das IES — CONTRATOS", fmt_titulo)
        worksheet.merge_range(0, 1, 0, last_col_idx, '', fmt_branco)
        img_col = 1
    else:
        worksheet.merge_range(0, 0, 0, 3, "Relatório Informativo das IES — CONTRATOS", fmt_titulo)
        worksheet.merge_range(0, 4, 0, last_col_idx, '', fmt_branco)
        img_col = 4
        
    if os.path.exists(caminho_imagem):
        worksheet.embed_image(0, img_col, caminho_imagem, {'cell_format': fmt_branco})
            
    col_fac = 'Faculdade' if 'Faculdade' in df_docs.columns else ('faculdade' if 'faculdade' in df_docs.columns else None)
    if col_fac and not df_docs.empty:
        ies_list = sorted(df_docs[col_fac].dropna().unique().tolist())
    else:
        ies_list = []
        
    aux_sheet = workbook.add_worksheet('Aux_IES_Contratos')
    aux_sheet.hide()
    for i, ies in enumerate(ies_list):
        aux_sheet.write(i, 0, ies)
        
    primeira_ies = "ANHANGUERA ANAPOLIS FACULDADE ANHANGUERA DE ANAPOLIS ANHANGUERA EDUCACIONA"
    worksheet.merge_range(1, 0, 1, last_col_idx, primeira_ies, fmt_input)
    
    if ies_list:
        worksheet.data_validation(1, 0, 1, last_col_idx, {
            'validate': 'list',
            'source': f"='Aux_IES_Contratos'!$A$1:$A${len(ies_list)}",
            'input_title': 'Escolha a IES',
            'input_message': 'Selecione a instituição na lista.'
        })

    def row_headers(title, fmt):
        return [(title, fmt)] + [(sem, fmt, 6) for sem in sems_contratos] + ([("Variação", fmt, 6)] if has_var else [])

    def row_headers_arquivos(title, fmt):
        return [(title, fmt, 1, 2)] + [(sem, fmt, 6) for sem in sems_contratos] + ([('Variação do "% Envio"', fmt, 6, 2)] if has_var else [])

    def row_cells(title, fmt_title, fmt_cell, merge=6, multiplier=1):
        return [(title, fmt_title)] + [("", fmt_cell, merge) for _ in range(cols_count * multiplier)]
        
    def row_cells_arquivos(title, fmt_title, fmt_cell):
        return [(title, fmt_title)] + [("", fmt_cell, 2) for _ in range(len(sems_contratos)*3)] + ([("", fmt_cell, 6)] if has_var else [])

    colunas_contrato_exp = COLUNAS_ABA_DOCUMENTO
    _cols_c = [c for c in colunas_contrato_exp if c in df_docs.columns and c not in ['tipo_documento', 'Documento Tipo']]
    def _get_col_c(n):
        if n in _cols_c: return col_to_letter(_cols_c.index(n))
        return 'A'
    c_bolsa_c = _get_col_c('tipo_bolsa_final')
    c_facul_c = _get_col_c('faculdade')
    c_sem_c = _get_col_c('semestre')
    c_status_c = _get_col_c('status_vinculo')
    c_status_ia_c = _get_col_c('status_ia')
    c_inconsistencia_c = _get_col_c('gemini_inconsistencia')
    c_curso_c = _get_col_c('curso')
    c_total_bolsa_c = _get_col_c('total_bolsa_paga')
    c_mensalidade_sem_desc_c = _get_col_c('mensalidade_sem_desc')
    c_mensalidade_com_desc_c = _get_col_c('mensalidade_com_desc')
    c_gemini_mensalidade_sem_desc_c = _get_col_c('gemini_mensalidade_sem_desc')
    c_gemini_mensalidade_com_desc_c = _get_col_c('gemini_mensalidade_com_desc')
    c_msd_doc_c = _get_col_c('msd_doc')
    c_mcd_doc_c = _get_col_c('mcd_doc')
    c_soma_valor_financiamento_c = _get_col_c('soma_valor_financiamento')
    c_soma_valor_beneficio_c = _get_col_c('soma_valor_beneficio')
    c_bolsa_calc_c = _get_col_c('soma_ovg_devia_pagar_ia')
    c_diag_c = _get_col_c('diagnostico_financeiro_final')
    c_prejuizo_c = _get_col_c('soma_prejuizo_ovg')

    if has_var:
        prev_idx = len(sems_contratos) - 2
        curr_idx = len(sems_contratos) - 1
        
        c_prev_q = col_to_letter(1 + prev_idx * 6)
        c_curr_q = col_to_letter(1 + curr_idx * 6)
        c_prev_a = col_to_letter(3 + prev_idx * 6)
        c_curr_a = col_to_letter(3 + curr_idx * 6)
        c_prev_i = col_to_letter(5 + prev_idx * 6)
        c_curr_i = col_to_letter(5 + curr_idx * 6)

        def var_f(cp, cc, r):
            return f'=IF(OR($A$2="",$A$2="Escolha a IES"),"",IFERROR(IF(AND({cp}{r}=0,{cc}{r}=0),0,IF({cp}{r}=0,1,({cc}{r}-{cp}{r})/{cp}{r})),""))'

        var_parciais = [(var_f(c_prev_q, c_curr_q, 6), fmt_pct_rosa, 2), (var_f(c_prev_a, c_curr_a, 6), fmt_pct_rosa, 2), (var_f(c_prev_i, c_curr_i, 6), fmt_pct_rosa, 2)]
        var_integrais = [(var_f(c_prev_q, c_curr_q, 7), fmt_pct_rosa, 2), (var_f(c_prev_a, c_curr_a, 7), fmt_pct_rosa, 2), (var_f(c_prev_i, c_curr_i, 7), fmt_pct_rosa, 2)]
    else:
        var_parciais = []
        var_integrais = []

    def linha_medias_c(title, r_idx):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_contratos:
            if title == "Outros Cursos":
                cond = f'Contrato!{c_curso_c}:{c_curso_c}, "<>MEDICINA", Contrato!{c_curso_c}:{c_curso_c}, "<>ODONTOLOGIA"'
            else:
                cond = f'Contrato!{c_curso_c}:{c_curso_c}, "{title.upper()}"'
            f_p = f'=IFERROR(AVERAGEIFS(Contrato!{c_total_bolsa_c}:{c_total_bolsa_c}, Contrato!{c_bolsa_c}:{c_bolsa_c}, "*PARCIAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", {cond}), 0)'
            f_i = f'=IFERROR(AVERAGEIFS(Contrato!{c_total_bolsa_c}:{c_total_bolsa_c}, Contrato!{c_bolsa_c}:{c_bolsa_c}, "*INTEGRAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", {cond}), 0)'
            linha.extend([(f_p, fmt_moeda_rosa, 3), (f_i, fmt_moeda_rosa, 3)])
        if has_var:
            cp_p = col_to_letter(1 + prev_idx * 6)
            cc_p = col_to_letter(1 + curr_idx * 6)
            cp_i = col_to_letter(4 + prev_idx * 6)
            cc_i = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_p, cc_p, r_idx), fmt_pct_rosa, 3), (var_f(cp_i, cc_i, r_idx), fmt_pct_rosa, 3)])
        return linha

    def linha_arquivos_c(title, doc_key, r_idx):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_contratos:
            f_env = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Env. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            f_esp = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Env. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}") + SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Pend. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            f_pct = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("% {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            linha.extend([(f_env, fmt_cell_center_rosa, 2), (f_esp, fmt_cell_center_rosa, 2), (f_pct, fmt_pct_rosa, 2)])
        if has_var:
            cp_pct = col_to_letter(5 + prev_idx * 6)
            cc_pct = col_to_letter(5 + curr_idx * 6)
            linha.append((var_f(cp_pct, cc_pct, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_coleta_c(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_contratos:
            if pendentes:
                f_men = f'=IFERROR(SUMIFS(Contrato!{c_mensalidade_sem_desc_c}:{c_mensalidade_sem_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            else:
                f_men = f'=IFERROR(SUMIFS(Contrato!{c_mensalidade_sem_desc_c}:{c_mensalidade_sem_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_men, fmt_moeda_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_soma_coleta_com_c(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_contratos:
            if pendentes:
                f_men = f'=IFERROR(SUMIFS(Contrato!{c_mensalidade_com_desc_c}:{c_mensalidade_com_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            else:
                f_men = f'=IFERROR(SUMIFS(Contrato!{c_mensalidade_com_desc_c}:{c_mensalidade_com_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_men, fmt_moeda_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_diferenca_c(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_azul1):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_contratos):
            col_letter = col_to_letter(1 + i * 6)
            f_diff = f'=IFERROR({col_letter}{r_minuend}-{col_letter}{r_subtrahend}, 0)'
            linha.append((f_diff, fmt_moeda_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_dif_pct_c(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_azul1):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_contratos):
            col_letter = col_to_letter(1 + i * 6)
            f_pct = f'=IFERROR(({col_letter}{r_minuend}-{col_letter}{r_subtrahend})/{col_letter}{r_subtrahend}, 0)'
            linha.append((f_pct, fmt_pct_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_soma_gemini_c(title, r_idx):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_contratos:
            f_men = f'=IFERROR(SUMIFS(Contrato!{c_gemini_mensalidade_sem_desc_c}:{c_gemini_mensalidade_sem_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_men, fmt_moeda_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_soma_gemini_com_c(title, r_idx):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_contratos:
            f_men = f'=IFERROR(SUMIFS(Contrato!{c_gemini_mensalidade_com_desc_c}:{c_gemini_mensalidade_com_desc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_men, fmt_moeda_azul1, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_azul1, 6))
        return linha

    def linha_diferenca_rosa_c(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_rosa):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_contratos):
            col_letter = col_to_letter(1 + i * 6)
            f_diff = f'=IFERROR({col_letter}{r_minuend}-{col_letter}{r_subtrahend}, 0)'
            linha.append((f_diff, fmt_moeda_rosa, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_financiamento_c(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_contratos:
            if pendentes:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_soma_valor_financiamento_c}:{c_soma_valor_financiamento_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            else:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_soma_valor_financiamento_c}:{c_soma_valor_financiamento_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_rosa, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_beneficio_c(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_contratos:
            if pendentes:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_soma_valor_beneficio_c}:{c_soma_valor_beneficio_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            else:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_soma_valor_beneficio_c}:{c_soma_valor_beneficio_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_rosa, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_bolsas_recalc_diag_c(title, r_idx, diag_val, fmt_t=fmt_cell_laranja):
        linha = [(title, fmt_t)]
        for sem in sems_contratos:
            f_val = f'=IFERROR(SUMIFS(Contrato!{c_bolsa_calc_c}:{c_bolsa_calc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_diag_c}:{c_diag_c}, "{diag_val}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_prejuizo_real_c(title, r_idx, fmt_t=fmt_cell_laranja_red):
        linha = [(title, fmt_t)]
        for sem in sems_contratos:
            f_val = f'=IFERROR(SUMIFS(Contrato!{c_prejuizo_c}:{c_prejuizo_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_diag_c}:{c_diag_c}, "OVG pagou a mais", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_soma_bolsas_recalc_c(title, r_idx):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_contratos:
            f_val = f'=IFERROR(SUMIFS(Contrato!{c_bolsa_calc_c}:{c_bolsa_calc_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_soma_bolsas_pagas_c(title, r_idx, pendentes=False, enviados=False):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_contratos:
            if pendentes:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_total_bolsa_c}:{c_total_bolsa_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            elif enviados:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_total_bolsa_c}:{c_total_bolsa_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>Ausente", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            else:
                f_val = f'=IFERROR(SUMIFS(Contrato!{c_total_bolsa_c}:{c_total_bolsa_c}, Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_inconsistencia_c(title, string_match, r_idx):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_contratos:
            f_val = f'=COUNTIFS(Contrato!{c_inconsistencia_c}:{c_inconsistencia_c}, "*{string_match}*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")'
            linha.append((f_val, fmt_cell_center_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_afericao_c(title, c_doc, r_idx):
        linha = [(title, fmt_cell_roxo)]
        for sem in sems_contratos:
            f_conf = f'=COUNTIFS(Contrato!{c_doc}:{c_doc}, "Coleta de dados conforme documento", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")'
            f_div = f'=SUM(COUNTIFS(Contrato!{c_doc}:{c_doc}, "Valor no documento é Maior", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), COUNTIFS(Contrato!{c_doc}:{c_doc}, "Valor no documento é Menor", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"))'
            f_sv = f'=SUM(COUNTIFS(Contrato!{c_doc}:{c_doc}, "Valor não localizado no documento", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), COUNTIFS(Contrato!{c_doc}:{c_doc}, "Documento não enviado", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), COUNTIFS(Contrato!{c_doc}:{c_doc}, "Não Processado", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"), COUNTIFS(Contrato!{c_doc}:{c_doc}, "Documento Corrompido", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE"))'
            linha.extend([(f_conf, fmt_cell_center_roxo, 2), (f_div, fmt_cell_center_roxo, 2), (f_sv, fmt_cell_center_roxo, 2)])
        if has_var:
            cp_conf = col_to_letter(1 + prev_idx * 6)
            cc_conf = col_to_letter(1 + curr_idx * 6)
            cp_div = col_to_letter(3 + prev_idx * 6)
            cc_div = col_to_letter(3 + curr_idx * 6)
            cp_sv = col_to_letter(5 + prev_idx * 6)
            cc_sv = col_to_letter(5 + curr_idx * 6)
            linha.extend([
                (var_f(cp_conf, cc_conf, r_idx), fmt_pct_roxo, 2),
                (var_f(cp_div, cc_div, r_idx), fmt_pct_roxo, 2),
                (var_f(cp_sv, cc_sv, r_idx), fmt_pct_roxo, 2)
            ])
        return linha

    def linha_diferenca_laranja_c(title, r_idx, r_minuend, r_subtrahend):
        linha = [(title, fmt_cell_laranja)]
        for i, sem in enumerate(sems_contratos):
            col_letter = col_to_letter(1 + i * 6)
            f_diff = f'=IFERROR({col_letter}{r_minuend}-{col_letter}{r_subtrahend}, 0)'
            linha.append((f_diff, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    layout = [
        [("Números da IES", fmt_header_rosa, 1, 2)] + [(sem, fmt_header_rosa, 6) for sem in sems_contratos] + ([("Variação", fmt_header_rosa, 6)] if has_var else []),
        [None] + [("Qtd.", fmt_header_rosa, 2), ("Ativos", fmt_header_rosa, 2), ("Inativos", fmt_header_rosa, 2)] * cols_count,
        [("Beneficiários Parciais", fmt_cell_rosa)] + sum([[(f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*PARCIAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*PARCIAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_c}:{c_status_c}, "*ATIVO*", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*PARCIAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_c}:{c_status_c}, "*DESLIGADO*", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2)] for sem in sems_contratos], []) + var_parciais,
        [("Beneficiários Integrais", fmt_cell_rosa)] + sum([[(f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*INTEGRAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*INTEGRAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_c}:{c_status_c}, "*ATIVO*", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Contrato!{c_bolsa_c}:{c_bolsa_c}, "*INTEGRAL*", Contrato!{c_facul_c}:{c_facul_c}, $A$2, Contrato!{c_sem_c}:{c_sem_c}, "{sem}", Contrato!{c_status_c}:{c_status_c}, "*DESLIGADO*", Contrato!{c_status_ia_c}:{c_status_ia_c}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2)] for sem in sems_contratos], []) + var_integrais,
        [],
        [("Bolsas", fmt_header_rosa, 1, 2)] + [(sem, fmt_header_rosa, 6) for sem in sems_contratos] + ([("Variação", fmt_header_rosa, 6)] if has_var else []),
        [None] + [("Valor Médio Parcial", fmt_header_rosa, 3), ("Valor Médio Integral", fmt_header_rosa, 3)] * cols_count,
        linha_medias_c("Medicina", 11),
        linha_medias_c("Odontologia", 12),
        linha_medias_c("Outros Cursos", 13),
        [],
        row_headers_arquivos("Arquivos", fmt_header_rosa),
        [None] + [("Enviados", fmt_header_rosa, 2), ("Esperados", fmt_header_rosa, 2), ("% Envio", fmt_header_rosa, 2)] * len(sems_contratos) + ([None]*6 if has_var else []),
        linha_arquivos_c("Contrato de Prestação de Serviços Educacionais / Matrícula", "CONTRATO", 17),
        linha_arquivos_c("Comprovante de Financiamento", "FINANCIAMENTO", 18),
        linha_arquivos_c("Comprovante de Outros Benefícios", "BENEFÍCIOS", 19),
        [],
        row_headers("Mensalidade SEM Desconto", fmt_header_azul1),
        linha_soma_coleta_c("Soma na Coleta", 22),
        linha_soma_coleta_c("Soma na Coleta (Pendentes)", 23, pendentes=True),
        linha_diferenca_c("Total na Coleta (Enviados)", 24, 22, 23),
        linha_soma_gemini_c("Soma dos Contratos Analisados", 25),
        linha_diferenca_c("Diferença: Contratos x Coleta", 26, 24, 25, fmt_title=fmt_titulo_diferenca),
        linha_dif_pct_c("Diferença %: Contratos x Coleta", 27, 24, 25, fmt_title=fmt_titulo_diferenca),
        [("Aferição dos Documentos com a Coleta de Dados", fmt_header_roxo, 1, 2)] + [(sem, fmt_header_roxo, 6) for sem in sems_contratos] + ([("Variação", fmt_header_roxo, 6)] if has_var else []),
        [None] + [("Conforme", fmt_header_roxo, 2), ("Divergente", fmt_header_roxo, 2), ("Sem Valor", fmt_header_roxo, 2)] * cols_count,
        linha_afericao_c("Qtd. de Contratos Analisados", c_msd_doc_c, 30),
        [],
        row_headers("Mensalidade COM Desconto", fmt_header_azul1),
        linha_soma_coleta_com_c("Soma na Coleta", 33),
        linha_soma_coleta_com_c("Soma na Coleta (Pendentes)", 34, pendentes=True),
        linha_diferenca_c("Total na Coleta (Enviados)", 35, 33, 34),
        linha_soma_gemini_com_c("Soma dos Contratos Analisados", 36),
        linha_diferenca_c("Diferença: Contratos x Coleta", 37, 35, 36, fmt_title=fmt_titulo_diferenca),
        linha_dif_pct_c("Diferença %: Contratos x Coleta", 38, 35, 36, fmt_title=fmt_titulo_diferenca),
        [("Aferição dos Documentos com a Coleta de Dados", fmt_header_roxo, 1, 2)] + [(sem, fmt_header_roxo, 6) for sem in sems_contratos] + ([("Variação", fmt_header_roxo, 6)] if has_var else []),
        [None] + [("Conforme", fmt_header_roxo, 2), ("Divergente", fmt_header_roxo, 2), ("Sem Valor", fmt_header_roxo, 2)] * cols_count,
        linha_afericao_c("Qtd. de Contratos Analisados", c_mcd_doc_c, 41),
        [],
        row_headers("Benefícios e Financiamento", fmt_header_rosa),
        linha_soma_beneficio_c("Soma na Coleta de Benefícios", 44),
        linha_soma_beneficio_c("Soma na Coleta de Benefícios (Pendentes)", 45, pendentes=True),
        linha_diferenca_rosa_c("Soma na Coleta de Benefícios (Enviados)", 46, 44, 45),
        linha_soma_financiamento_c("Soma na Coleta de Financiamentos", 47),
        linha_soma_financiamento_c("Soma na Coleta de Financiamentos (Pendentes)", 48, pendentes=True),
        linha_diferenca_rosa_c("Soma na Coleta de Financiamentos (Enviados)", 49, 47, 48),
        [],
        row_headers("Análise Financeira", fmt_header_laranja),
        linha_soma_bolsas_pagas_c("Soma na Coleta das Bolsas Pagas", 52),
        linha_soma_bolsas_pagas_c("Soma na Coleta das Bolsas Pagas (Pendentes / Glosa)", 53, pendentes=True),
        linha_soma_bolsas_pagas_c("Soma na Coleta das Bolsas Pagas (Enviados)", 54, enviados=True),
        linha_soma_bolsas_recalc_c("Soma das Bolsas Pagas - Recálculo", 55),
        linha_soma_bolsas_recalc_diag_c("Soma das Bolsas Pagas - Recálculo (Em Conformidade)", 56, "Pagamento correto"),
        linha_soma_bolsas_recalc_diag_c("Soma das Bolsas Pagas - Recálculo (Acima do Esperado)", 57, "OVG pagou a mais"),
        linha_soma_bolsas_recalc_diag_c("Soma das Bolsas Pagas - Recálculo (Abaixo do Esperado)", 58, "OVG pagou a menos"),
        linha_prejuizo_real_c("Soma do Valor Excedente Pago", 59, fmt_t=fmt_cell_laranja_red),
        [],
        row_headers("Resultado da Análise Acadêmica", fmt_header_laranja),
        linha_inconsistencia_c("Qtd. de Contratos com Inconsistências de CPF", "CPF", 62),
        linha_inconsistencia_c("Qtd. de Contratos com Inconsistências de Semestre Letivo", "Semestre", 63),
        linha_inconsistencia_c("Qtd. de Contratos com Inconsistências de Curso", "Curso", 64),
        linha_inconsistencia_c("Qtd. de Contratos com Inconsistências de Mensalidade", "Mensal", 65)
    ]

    row_idx = 3
    for row_data in layout:
        if not row_data:
            worksheet.merge_range(row_idx, 0, row_idx, last_col_idx, "", fmt_branco)
            row_idx += 1
            continue
        col_idx = 0
        for cell in row_data:
            if cell is None:
                col_idx += 1
                continue
            if len(cell) == 4:
                val, fmt, merge_cols, merge_rows = cell
                if merge_cols > 1 or merge_rows > 1:
                    if str(val).startswith('='):
                        worksheet.merge_range(row_idx, col_idx, row_idx + merge_rows - 1, col_idx + merge_cols - 1, '', fmt)
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.merge_range(row_idx, col_idx, row_idx + merge_rows - 1, col_idx + merge_cols - 1, val, fmt)
                else:
                    if str(val).startswith('='):
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += merge_cols
            elif len(cell) == 3:
                val, fmt, merge_len = cell
                if merge_len > 1:
                    if str(val).startswith('='):
                        worksheet.merge_range(row_idx, col_idx, row_idx, col_idx + merge_len - 1, '', fmt)
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.merge_range(row_idx, col_idx, row_idx, col_idx + merge_len - 1, val, fmt)
                else:
                    if str(val).startswith('='):
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += merge_len
            else:
                val, fmt = cell
                if str(val).startswith('='):
                    worksheet.write_formula(row_idx, col_idx, val, fmt)
                else:
                    worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += 1
        row_idx += 1

    worksheet.write_comment(54, 0, "puxar valores de matriculas das coleta de dados para ajustar 2026-jan, observar se contratos tem valor de matricula pois agora é um requisito necessario para recalculo de bolsas")

def gerar_aba_relatorio_riaf(writer, df_riaf, sems_riaf):
    """
    O QUE FAZ: Monta a aba "Relatório RIAF", equivalente gerencial da aba de contratos.
    POR QUÊ EXISTE: O RIAF tem conjunto de colunas e regras de aferição próprios e não cabe
    no painel de contratos.
    COMO FUNCIONA: Mesma estratégia da aba de contratos — blocos por semestre e linhas
    escritas como fórmulas do Excel. As funções linha_* daqui espelham as de lá com sufixo
    _riaf; a duplicação entre as duas é conhecida e ainda não foi unificada.
    PARÂMETROS: writer (pd.ExcelWriter), df_riaf (DataFrame), sems_riaf (list)
    RETORNO: None — escreve direto no writer.
    """
    if not sems_riaf:
        sems_riaf = ["2025-1", "2025-2", "2026-1", "2026-2"]

    workbook = writer.book
    worksheet = workbook.add_worksheet('Relatório RIAF')
    worksheet.set_tab_color('#EB94B5')
    
    worksheet.hide_gridlines(2)
    worksheet.ignore_errors({
        'number_stored_as_text': 'A1:XFD1048576',
        'eval_error': 'A1:XFD1048576',
        'formula_differs': 'A1:XFD1048576',
        'formula_range': 'A1:XFD1048576',
        'formula_unlocked': 'A1:XFD1048576',
        'empty_cell_reference': 'A1:XFD1048576',
        'list_data_validation': 'A1:XFD1048576',
        'calculated_column': 'A1:XFD1048576',
        'two_digit_text_year': 'A1:XFD1048576'
    })
    
    fmt_branco = workbook.add_format({'bg_color': '#FFFFFF', 'align': 'center', 'valign': 'vcenter'})
    fmt_titulo = workbook.add_format({'bold': True, 'font_size': 22, 'valign': 'vcenter', 'align': 'center'})
    fmt_input = workbook.add_format({'valign': 'vcenter', 'align': 'center', 'bold': True, 'bg_color': '#AAD176', 'font_color': '#000000'}) 
    
    fmt_header_rosa = workbook.add_format({'bold': True, 'bg_color': '#eb94b5', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_bold_red_rosa = workbook.add_format({'bold': True, 'font_color': '#FF0000', 'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter'})
    fmt_pct_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_moeda_rosa = workbook.add_format({'bg_color': '#f7d2df', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    
    fmt_header_laranja = workbook.add_format({'bold': True, 'bg_color': '#f8c4b4', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_laranja_red = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'font_color': 'red'})
    fmt_cell_center_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    fmt_pct_laranja = workbook.add_format({'bg_color': '#fceae3', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})

    fmt_header_azul_pastel = workbook.add_format({'bold': True, 'bg_color': '#b4d4ff', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_azul_pastel = workbook.add_format({'bg_color': '#e6f0ff', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_azul_pastel = workbook.add_format({'bg_color': '#e6f0ff', 'border': 1, 'valign': 'vcenter', 'align': 'center'})

    fmt_header_lavanda = workbook.add_format({'bold': True, 'bg_color': '#d1c4e9', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_lavanda = workbook.add_format({'bg_color': '#f1eef6', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_lavanda = workbook.add_format({'bg_color': '#f1eef6', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    
    fmt_header_azul1 = workbook.add_format({'bold': True, 'bg_color': '#b9cbe2', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter'})
    fmt_titulo_diferenca = workbook.add_format({'bg_color': '#dde6f0', 'font_color': '#C0504D', 'border': 1, 'valign': 'vcenter', 'bold': True, 'italic': True})
    fmt_cell_center_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'num_format': '_("R$"* #,##0.00_);_("R$"* -#,##0.00_);_("R$"* "-"??_);_(@_)'})
    fmt_pct_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    
    fmt_header_roxo = workbook.add_format({'bold': True, 'bg_color': '#cdc0d9', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter'})
    fmt_pct_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_cell_center_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    
    fmt_header_cinza = workbook.add_format({'bold': True, 'bg_color': '#bfbfbf', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    
    has_var = len(sems_riaf) >= 2
    cols_count = len(sems_riaf) + (1 if has_var else 0)
    last_col_idx = 6 * cols_count
    
    def col_to_letter(idx):
        result = ""
        while idx >= 0:
            result = chr(idx % 26 + ord('A')) + result
            idx = idx // 26 - 1
        return result
    worksheet.set_column('A:A', 70)
    worksheet.set_column(1, last_col_idx, 9.14) if last_col_idx >= 1 else worksheet.set_column('B:S', 9.14)
    worksheet.set_row(0, 86.25) 
    worksheet.set_row(1, 26.25) 
    worksheet.set_row(2, 8) 
    worksheet.set_row(7, 8) 
    worksheet.set_row(13, 8) 
    worksheet.set_row(17, 8) 
    worksheet.set_row(29, 8) 
    worksheet.set_row(41, 8)
    worksheet.set_row(51, 8)
    worksheet.set_row(61, 8)
    worksheet.set_row(62, 15)



    caminho_imagem = os.path.join('static', 'img', 'icones', 'relatorio.png')
    
    if not has_var:
        worksheet.write(0, 0, "Relatório Informativo das IES — RIAF'S", fmt_titulo)
        worksheet.merge_range(0, 1, 0, last_col_idx, '', fmt_branco)
        img_col = 1
    else:
        worksheet.merge_range(0, 0, 0, 3, "Relatório Informativo das IES — RIAF'S", fmt_titulo)
        worksheet.merge_range(0, 4, 0, last_col_idx, '', fmt_branco)
        img_col = 4
        
    if os.path.exists(caminho_imagem):
        worksheet.embed_image(0, img_col, caminho_imagem, {'cell_format': fmt_branco})
            
    col_fac = 'Faculdade' if 'Faculdade' in df_riaf.columns else ('faculdade' if 'faculdade' in df_riaf.columns else None)
    if col_fac and not df_riaf.empty:
        ies_list = sorted(df_riaf[col_fac].dropna().unique().tolist())
    else:
        ies_list = []
        
    aux_sheet = workbook.add_worksheet('Aux_IES_RIAF')
    aux_sheet.hide()
    for i, ies in enumerate(ies_list):
        aux_sheet.write(i, 0, ies)
        
    primeira_ies = "ANHANGUERA ANAPOLIS FACULDADE ANHANGUERA DE ANAPOLIS ANHANGUERA EDUCACIONA"
    worksheet.merge_range(1, 0, 1, last_col_idx, primeira_ies, fmt_input)
    
    if ies_list:
        worksheet.data_validation(1, 0, 1, last_col_idx, {
            'validate': 'list',
            'source': f"='Aux_IES_RIAF'!$A$1:$A${len(ies_list)}",
            'input_title': 'Escolha a IES',
            'input_message': 'Selecione a instituição na lista.'
        })

    def row_headers(title, fmt):
        return [(title, fmt)] + [(sem, fmt, 6) for sem in sems_riaf] + ([("Variação", fmt, 6)] if has_var else [])

    def row_headers_arquivos(title, fmt):
        return [(title, fmt, 1, 2)] + [(sem, fmt, 6) for sem in sems_riaf] + ([('Variação do "% Envio"', fmt, 6, 2)] if has_var else [])

    def row_cells(title, fmt_title, fmt_cell, merge=6, multiplier=1):
        return [(title, fmt_title)] + [("", fmt_cell, merge) for _ in range(cols_count * multiplier)]
        
    def row_cells_arquivos(title, fmt_title, fmt_cell):
        # Arquivos has subcolumns, so the Variação is merged, meaning it has 6 None below it
        return [(title, fmt_title)] + [("", fmt_cell, 2) for _ in range(len(sems_riaf)*3)] + ([("", fmt_cell, 6)] if has_var else [])

    colunas_riaf_exp = ['status_ia', 'gemini_inconsistencia', 'semestre', 'gemini_semestre', 'bolsista', 'inscricao', 'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf', 'tipo_bolsa_final', 'gemini_tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior', 'bolsa_posterior', 'faculdade', 'cnpj_ies', 'mudou_ies', 'ies_anterior', 'ies_posterior', 'curso', 'gemini_assinatura_aluno', 'gemini_assinatura_ies', 'ultimo_valor_pago_ref', 'total_bolsa_paga', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'matricula_sem_desc', 'gemini_matricula_sem_desc', 'matricula_sd_doc', 'matricula_com_desc', 'gemini_matricula_com_desc', 'matricula_cd_doc', 'mensalidade_sem_desc', 'gemini_mensalidade_sem_desc', 'msd_doc', 'mensalidade_com_desc', 'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio', 'soma_valor_beneficio', 'gemini_valor_beneficio', 'beneficio', 'valor_financiamento', 'soma_valor_financiamento', 'gemini_valor_financiamento', 'financiamento', 'soma_ovg_devia_pagar_sis', 'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg', 'soma_economia_ovg', 'diagnostico_financeiro_final', 'data_coleta', 'data_coleta_atual_sistema', 'data_create', 'data_processamento', 'processado', 'processar', 'qtd_token', 'qtd_disciplinas_matriculadas', 'qtd_disciplinas_reprovadas', 'perfil', 'status_vinculo', 'situacao_motivo', 'observacao_situacao', 'email', 'gemini_email', 'telefone_1', 'telefone_2', 'data_nascimento', 'matricula', 'periodo_atual', 'qtd_periodos', 'modalidade', 'documento_ausente', 'veredito_documento']
    _cols_riaf_final = [c for c in colunas_riaf_exp if c in df_riaf.columns and c not in ['tipo_documento', 'Documento Tipo']]
    
    def _get_col_r(n):
        if n in _cols_riaf_final: return col_to_letter(_cols_riaf_final.index(n))
        if str(n).lower() in _cols_riaf_final: return col_to_letter(_cols_riaf_final.index(str(n).lower()))
        if str(n).capitalize() in _cols_riaf_final: return col_to_letter(_cols_riaf_final.index(str(n).capitalize()))
        return 'A'
        
    c_bolsa_riaf = _get_col_r('tipo_bolsa_final')
    c_facul_riaf = _get_col_r('faculdade')
    c_sem_riaf = _get_col_r('semestre')
    c_status_riaf = _get_col_r('status_vinculo')
    c_status_ia_riaf = _get_col_r('status_ia')
    c_inconsistencia_riaf = _get_col_r('gemini_inconsistencia')
    c_curso_riaf = _get_col_r('curso')
    c_total_bolsa_riaf = _get_col_r('total_bolsa_paga')
    c_mensalidade_sem_desc_riaf = _get_col_r('mensalidade_sem_desc')
    c_matricula_sem_desc_riaf = _get_col_r('matricula_sem_desc')
    c_mensalidade_com_desc_riaf = _get_col_r('mensalidade_com_desc')
    c_matricula_com_desc_riaf = _get_col_r('matricula_com_desc')
    c_gemini_matricula_sem_desc_riaf = _get_col_r('gemini_matricula_sem_desc')
    c_gemini_mensalidade_sem_desc_riaf = _get_col_r('gemini_mensalidade_sem_desc')
    c_gemini_matricula_com_desc_riaf = _get_col_r('gemini_matricula_com_desc')
    c_gemini_mensalidade_com_desc_riaf = _get_col_r('gemini_mensalidade_com_desc')
    c_msd_doc_riaf = _get_col_r('msd_doc')
    c_mcd_doc_riaf = _get_col_r('mcd_doc')
    c_soma_valor_beneficio_riaf = _get_col_r('soma_valor_beneficio')
    c_soma_valor_financiamento_riaf = _get_col_r('soma_valor_financiamento')
    c_gemini_valor_beneficio_riaf = _get_col_r('gemini_valor_beneficio')
    c_gemini_valor_financiamento_riaf = _get_col_r('gemini_valor_financiamento')
    c_bolsa_calc_riaf = _get_col_r('soma_ovg_devia_pagar_ia')
    c_diag_riaf = _get_col_r('diagnostico_financeiro_final')
    c_prejuizo_riaf = _get_col_r('soma_prejuizo_ovg')

    if has_var:
        prev_idx = len(sems_riaf) - 2
        curr_idx = len(sems_riaf) - 1
        
        c_prev_q = col_to_letter(1 + prev_idx * 6)
        c_curr_q = col_to_letter(1 + curr_idx * 6)
        c_prev_a = col_to_letter(3 + prev_idx * 6)
        c_curr_a = col_to_letter(3 + curr_idx * 6)
        c_prev_i = col_to_letter(5 + prev_idx * 6)
        c_curr_i = col_to_letter(5 + curr_idx * 6)

        def var_f(cp, cc, r):
            return f'=IF(OR($A$2="",$A$2="Escolha a IES"),"",IFERROR(IF(AND({cp}{r}=0,{cc}{r}=0),0,IF({cp}{r}=0,1,({cc}{r}-{cp}{r})/{cp}{r})),""))'

        var_parciais = [(var_f(c_prev_q, c_curr_q, 6), fmt_pct_rosa, 2), (var_f(c_prev_a, c_curr_a, 6), fmt_pct_rosa, 2), (var_f(c_prev_i, c_curr_i, 6), fmt_pct_rosa, 2)]
        var_integrais = [(var_f(c_prev_q, c_curr_q, 7), fmt_pct_rosa, 2), (var_f(c_prev_a, c_curr_a, 7), fmt_pct_rosa, 2), (var_f(c_prev_i, c_curr_i, 7), fmt_pct_rosa, 2)]
    else:
        var_parciais = []
        var_integrais = []

    def linha_medias_r(title, r_idx):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_riaf:
            if title == "Outros Cursos":
                cond = f'Riaf!{c_curso_riaf}:{c_curso_riaf}, "<>MEDICINA", Riaf!{c_curso_riaf}:{c_curso_riaf}, "<>ODONTOLOGIA"'
            else:
                cond = f'Riaf!{c_curso_riaf}:{c_curso_riaf}, "{title.upper()}"'
            f_p = f'=IFERROR(AVERAGEIFS(Riaf!{c_total_bolsa_riaf}:{c_total_bolsa_riaf}, Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*PARCIAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", {cond}), 0)'
            f_i = f'=IFERROR(AVERAGEIFS(Riaf!{c_total_bolsa_riaf}:{c_total_bolsa_riaf}, Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*INTEGRAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", {cond}), 0)'
            linha.extend([(f_p, fmt_moeda_rosa, 3), (f_i, fmt_moeda_rosa, 3)])
        if has_var:
            cp_p = col_to_letter(1 + prev_idx * 6)
            cc_p = col_to_letter(1 + curr_idx * 6)
            cp_i = col_to_letter(4 + prev_idx * 6)
            cc_i = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_p, cc_p, r_idx), fmt_pct_rosa, 3), (var_f(cp_i, cc_i, r_idx), fmt_pct_rosa, 3)])
        return linha

    def linha_arquivos_r(title, doc_key, r_idx):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_riaf:
            f_env = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Env. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            f_esp = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Env. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}") + SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("Pend. {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            f_pct = f'=IFERROR(SUMIFS(INDEX(\'Envios & Pendências\'!$A:$ZZ, 0, MATCH("% {doc_key}", \'Envios & Pendências\'!$1:$1, 0)), \'Envios & Pendências\'!$B:$B, $A$2, \'Envios & Pendências\'!$C:$C, "{sem}"), "")'
            linha.extend([(f_env, fmt_cell_center_rosa, 2), (f_esp, fmt_cell_center_rosa, 2), (f_pct, fmt_pct_rosa, 2)])
        if has_var:
            cp_pct = col_to_letter(5 + prev_idx * 6)
            cc_pct = col_to_letter(5 + curr_idx * 6)
            linha.append((var_f(cp_pct, cc_pct, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_coleta_riaf(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_riaf:
            if pendentes:
                f_mat = f'=IFERROR(SUMIFS(Riaf!{c_matricula_sem_desc_riaf}:{c_matricula_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
                f_men = f'=IFERROR(SUMIFS(Riaf!{c_mensalidade_sem_desc_riaf}:{c_mensalidade_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            else:
                f_mat = f'=IFERROR(SUMIFS(Riaf!{c_matricula_sem_desc_riaf}:{c_matricula_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
                f_men = f'=IFERROR(SUMIFS(Riaf!{c_mensalidade_sem_desc_riaf}:{c_mensalidade_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.extend([(f_mat, fmt_moeda_azul1, 3), (f_men, fmt_moeda_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_soma_coleta_com_riaf(title, r_idx, pendentes=False):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_riaf:
            if pendentes:
                f_mat = f'=IFERROR(SUMIFS(Riaf!{c_matricula_com_desc_riaf}:{c_matricula_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
                f_men = f'=IFERROR(SUMIFS(Riaf!{c_mensalidade_com_desc_riaf}:{c_mensalidade_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            else:
                f_mat = f'=IFERROR(SUMIFS(Riaf!{c_matricula_com_desc_riaf}:{c_matricula_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
                f_men = f'=IFERROR(SUMIFS(Riaf!{c_mensalidade_com_desc_riaf}:{c_mensalidade_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.extend([(f_mat, fmt_moeda_azul1, 3), (f_men, fmt_moeda_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_soma_gemini_riaf(title, r_idx):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_riaf:
            f_mat = f'=IFERROR(SUMIFS(Riaf!{c_gemini_matricula_sem_desc_riaf}:{c_gemini_matricula_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            f_men = f'=IFERROR(SUMIFS(Riaf!{c_gemini_mensalidade_sem_desc_riaf}:{c_gemini_mensalidade_sem_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.extend([(f_mat, fmt_moeda_azul1, 3), (f_men, fmt_moeda_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_soma_gemini_com_riaf(title, r_idx):
        linha = [(title, fmt_cell_azul1)]
        for sem in sems_riaf:
            f_mat = f'=IFERROR(SUMIFS(Riaf!{c_gemini_matricula_com_desc_riaf}:{c_gemini_matricula_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            f_men = f'=IFERROR(SUMIFS(Riaf!{c_gemini_mensalidade_com_desc_riaf}:{c_gemini_mensalidade_com_desc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.extend([(f_mat, fmt_moeda_azul1, 3), (f_men, fmt_moeda_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_diferenca_riaf(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_azul1):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_riaf):
            col_mat = col_to_letter(1 + i * 6)
            col_men = col_to_letter(4 + i * 6)
            f_diff_mat = f'=IFERROR({col_mat}{r_minuend}-{col_mat}{r_subtrahend}, 0)'
            f_diff_men = f'=IFERROR({col_men}{r_minuend}-{col_men}{r_subtrahend}, 0)'
            linha.extend([(f_diff_mat, fmt_moeda_azul1, 3), (f_diff_men, fmt_moeda_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_dif_pct_riaf(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_azul1):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_riaf):
            col_mat = col_to_letter(1 + i * 6)
            col_men = col_to_letter(4 + i * 6)
            f_pct_mat = f'=IFERROR(({col_mat}{r_minuend}-{col_mat}{r_subtrahend})/{col_mat}{r_subtrahend}, 0)'
            f_pct_men = f'=IFERROR(({col_men}{r_minuend}-{col_men}{r_subtrahend})/{col_men}{r_subtrahend}, 0)'
            linha.extend([(f_pct_mat, fmt_pct_azul1, 3), (f_pct_men, fmt_pct_azul1, 3)])
        if has_var:
            cp_mat = col_to_letter(1 + prev_idx * 6)
            cc_mat = col_to_letter(1 + curr_idx * 6)
            cp_men = col_to_letter(4 + prev_idx * 6)
            cc_men = col_to_letter(4 + curr_idx * 6)
            linha.extend([(var_f(cp_mat, cc_mat, r_idx), fmt_pct_azul1, 3), (var_f(cp_men, cc_men, r_idx), fmt_pct_azul1, 3)])
        return linha

    def linha_diferenca_rosa_riaf(title, r_idx, r_minuend, r_subtrahend, fmt_title=fmt_cell_rosa):
        linha = [(title, fmt_title)]
        for i, sem in enumerate(sems_riaf):
            col_letter = col_to_letter(1 + i * 6)
            f_diff = f'=IFERROR({col_letter}{r_minuend}-{col_letter}{r_subtrahend}, 0)'
            linha.append((f_diff, fmt_moeda_rosa, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_soma_beneficios_riaf(title, col_soma, r_idx, pendentes=False):
        linha = [(title, fmt_cell_rosa)]
        for sem in sems_riaf:
            if pendentes:
                f_val = f'=IFERROR(SUMIFS(Riaf!{col_soma}:{col_soma}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            else:
                f_val = f'=IFERROR(SUMIFS(Riaf!{col_soma}:{col_soma}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_rosa, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_rosa, 6))
        return linha

    def linha_inconsistencia_riaf(title, string_match, r_idx):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_riaf:
            f_val = f'=COUNTIFS(Riaf!{c_inconsistencia_riaf}:{c_inconsistencia_riaf}, "*{string_match}*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")'
            linha.append((f_val, fmt_cell_center_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_afericao_riaf(title, c_doc, r_idx):
        linha = [(title, fmt_cell_roxo)]
        for sem in sems_riaf:
            f_conf = f'=COUNTIFS(Riaf!{c_doc}:{c_doc}, "Coleta de dados conforme documento", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")'
            f_div = f'=SUM(COUNTIFS(Riaf!{c_doc}:{c_doc}, "Valor no documento é Maior", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), COUNTIFS(Riaf!{c_doc}:{c_doc}, "Valor no documento é Menor", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"))'
            f_sv = f'=SUM(COUNTIFS(Riaf!{c_doc}:{c_doc}, "Valor não localizado no documento", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), COUNTIFS(Riaf!{c_doc}:{c_doc}, "Documento não enviado", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), COUNTIFS(Riaf!{c_doc}:{c_doc}, "Não Processado", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), COUNTIFS(Riaf!{c_doc}:{c_doc}, "Documento Corrompido", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"))'
            linha.extend([(f_conf, fmt_cell_center_roxo, 2), (f_div, fmt_cell_center_roxo, 2), (f_sv, fmt_cell_center_roxo, 2)])
        if has_var:
            cp_conf = col_to_letter(1 + prev_idx * 6)
            cc_conf = col_to_letter(1 + curr_idx * 6)
            cp_div = col_to_letter(3 + prev_idx * 6)
            cc_div = col_to_letter(3 + curr_idx * 6)
            cp_sv = col_to_letter(5 + prev_idx * 6)
            cc_sv = col_to_letter(5 + curr_idx * 6)
            linha.extend([
                (var_f(cp_conf, cc_conf, r_idx), fmt_pct_roxo, 2),
                (var_f(cp_div, cc_div, r_idx), fmt_pct_roxo, 2),
                (var_f(cp_sv, cc_sv, r_idx), fmt_pct_roxo, 2)
            ])
        return linha

    def linha_soma_bolsas_recalc_diag_riaf(title, r_idx, diag_val, fmt_t=fmt_cell_laranja):
        linha = [(title, fmt_t)]
        for sem in sems_riaf:
            f_val = f'=IFERROR(SUMIFS(Riaf!{c_bolsa_calc_riaf}:{c_bolsa_calc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_diag_riaf}:{c_diag_riaf}, "{diag_val}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_prejuizo_real_riaf(title, r_idx, fmt_t=fmt_cell_laranja_red):
        linha = [(title, fmt_t)]
        for sem in sems_riaf:
            f_val = f'=IFERROR(SUMIFS(Riaf!{c_prejuizo_riaf}:{c_prejuizo_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_diag_riaf}:{c_diag_riaf}, "OVG pagou a mais", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_soma_bolsas_recalc_riaf(title, r_idx):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_riaf:
            f_val = f'=IFERROR(SUMIFS(Riaf!{c_bolsa_calc_riaf}:{c_bolsa_calc_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_soma_bolsas_pagas_riaf(title, r_idx, pendentes=False, enviados=False):
        linha = [(title, fmt_cell_laranja)]
        for sem in sems_riaf:
            if pendentes:
                f_val = f'=IFERROR(SUMIFS(Riaf!{c_total_bolsa_riaf}:{c_total_bolsa_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            elif enviados:
                f_val = f'=IFERROR(SUMIFS(Riaf!{c_total_bolsa_riaf}:{c_total_bolsa_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>Ausente", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            else:
                f_val = f'=IFERROR(SUMIFS(Riaf!{c_total_bolsa_riaf}:{c_total_bolsa_riaf}, Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE"), 0)'
            linha.append((f_val, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    def linha_diferenca_laranja_riaf(title, r_idx, r_minuend, r_subtrahend):
        linha = [(title, fmt_cell_laranja)]
        for i, sem in enumerate(sems_riaf):
            col_letter = col_to_letter(1 + i * 6)
            f_diff = f'=IFERROR({col_letter}{r_minuend}-{col_letter}{r_subtrahend}, 0)'
            linha.append((f_diff, fmt_moeda_laranja, 6))
        if has_var:
            cp = col_to_letter(1 + prev_idx * 6)
            cc = col_to_letter(1 + curr_idx * 6)
            linha.append((var_f(cp, cc, r_idx), fmt_pct_laranja, 6))
        return linha

    layout = [
        [("Números da IES", fmt_header_rosa, 1, 2)] + [(sem, fmt_header_rosa, 6) for sem in sems_riaf] + ([("Variação", fmt_header_rosa, 6)] if has_var else []),
        [None] + [("Qtd.", fmt_header_rosa, 2), ("Ativos", fmt_header_rosa, 2), ("Inativos", fmt_header_rosa, 2)] * cols_count,
        [("Beneficiários Parciais", fmt_cell_rosa)] + sum([[(f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*PARCIAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*PARCIAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_riaf}:{c_status_riaf}, "*ATIVO*", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*PARCIAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_riaf}:{c_status_riaf}, "*DESLIGADO*", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2)] for sem in sems_riaf], []) + var_parciais,
        [("Beneficiários Integrais", fmt_cell_rosa)] + sum([[(f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*INTEGRAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*INTEGRAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_riaf}:{c_status_riaf}, "*ATIVO*", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2), (f'=COUNTIFS(Riaf!{c_bolsa_riaf}:{c_bolsa_riaf}, "*INTEGRAL*", Riaf!{c_facul_riaf}:{c_facul_riaf}, $A$2, Riaf!{c_sem_riaf}:{c_sem_riaf}, "{sem}", Riaf!{c_status_riaf}:{c_status_riaf}, "*DESLIGADO*", Riaf!{c_status_ia_riaf}:{c_status_ia_riaf}, "<>INADIMPLENTE")', fmt_cell_center_rosa, 2)] for sem in sems_riaf], []) + var_integrais,
        [],
        [("Bolsas", fmt_header_rosa, 1, 2)] + [(sem, fmt_header_rosa, 6) for sem in sems_riaf] + ([("Variação", fmt_header_rosa, 6)] if has_var else []),
        [None] + [("Valor Médio Parcial", fmt_header_rosa, 3), ("Valor Médio Integral", fmt_header_rosa, 3)] * cols_count,
        linha_medias_r("Medicina", 11),
        linha_medias_r("Odontologia", 12),
        linha_medias_r("Outros Cursos", 13),
        [],
        row_headers_arquivos("Arquivos", fmt_header_rosa),
        [None] + [("Enviados", fmt_header_rosa, 2), ("Esperados", fmt_header_rosa, 2), ("% Envio", fmt_header_rosa, 2)] * len(sems_riaf) + ([None]*6 if has_var else []),
        linha_arquivos_r("RIAF - Resumo de Informações Acadêmicas e Financeiras", "RIAF", 17),
        [],
        [("Matrícula/Mensalidade SEM Desconto", fmt_header_azul1, 1, 2)] + [(sem, fmt_header_azul1, 6) for sem in sems_riaf] + ([("Variação", fmt_header_azul1, 6)] if has_var else []),
        [None] + [("Matrícula", fmt_header_azul1, 3), ("Mensalidade", fmt_header_azul1, 3)] * cols_count,
        linha_soma_coleta_riaf("Soma na Coleta", 21),
        linha_soma_coleta_riaf("Soma na Coleta (Pendentes)", 22, pendentes=True),
        linha_diferenca_riaf("Soma na Coleta (Analisados)", 23, 21, 22),
        linha_soma_gemini_riaf("Soma dos RIAF's Analisados", 24),
        linha_diferenca_riaf("Diferença: RIAF's x Coleta", 25, 23, 24, fmt_title=fmt_titulo_diferenca),
        linha_dif_pct_riaf("Diferença %: RIAF's x Coleta", 26, 23, 24, fmt_title=fmt_titulo_diferenca),
        [("Aferição dos Documentos com a Coleta de Dados", fmt_header_roxo, 1, 2)] + [(sem, fmt_header_roxo, 6) for sem in sems_riaf] + ([("Variação", fmt_header_roxo, 6)] if has_var else []),
        [None] + [("Conforme", fmt_header_roxo, 2), ("Divergente", fmt_header_roxo, 2), ("Sem Valor", fmt_header_roxo, 2)] * cols_count,
        linha_afericao_riaf("Qtd. de RIAFs Analisados", c_msd_doc_riaf, 29),
        [],
        [("Matrícula/Mensalidade Com Desconto", fmt_header_azul1, 1, 2)] + [(sem, fmt_header_azul1, 6) for sem in sems_riaf] + ([("Variação", fmt_header_azul1, 6)] if has_var else []),
        [None] + [("Matrícula", fmt_header_azul1, 3), ("Mensalidade", fmt_header_azul1, 3)] * cols_count,
        linha_soma_coleta_com_riaf("Soma na Coleta", 33),
        linha_soma_coleta_com_riaf("Soma na Coleta (Pendentes)", 34, pendentes=True),
        linha_diferenca_riaf("Soma na Coleta (Analisados)", 35, 33, 34),
        linha_soma_gemini_com_riaf("Soma dos RIAF's Analisados", 36),
        linha_diferenca_riaf("Diferença: RIAF's x Coleta", 37, 35, 36, fmt_title=fmt_titulo_diferenca),
        linha_dif_pct_riaf("Diferença %: RIAF's x Coleta", 38, 35, 36, fmt_title=fmt_titulo_diferenca),
        [("Aferição dos Documentos com a Coleta de Dados", fmt_header_roxo, 1, 2)] + [(sem, fmt_header_roxo, 6) for sem in sems_riaf] + ([("Variação", fmt_header_roxo, 6)] if has_var else []),
        [None] + [("Conforme", fmt_header_roxo, 2), ("Divergente", fmt_header_roxo, 2), ("Sem Valor", fmt_header_roxo, 2)] * cols_count,
        linha_afericao_riaf("Qtd. de RIAFs Analisados", c_mcd_doc_riaf, 41),
        [],
        row_headers("Benefícios e Financiamento", fmt_header_rosa),
        linha_soma_beneficios_riaf("Soma na Coleta de Benefícios", c_soma_valor_beneficio_riaf, 44),
        linha_soma_beneficios_riaf("Soma na Coleta de Benefícios (Pendentes)", c_soma_valor_beneficio_riaf, 45, pendentes=True),
        linha_diferenca_rosa_riaf("Soma na Coleta de Benefícios (Enviados)", 46, 44, 45),
        linha_soma_beneficios_riaf("Soma dos Benefícios (Analisados)", c_gemini_valor_beneficio_riaf, 47),
        linha_soma_beneficios_riaf("Soma na Coleta de Financiamentos", c_soma_valor_financiamento_riaf, 48),
        linha_soma_beneficios_riaf("Soma na Coleta de Financiamentos (Pendentes)", c_soma_valor_financiamento_riaf, 49, pendentes=True),
        linha_diferenca_rosa_riaf("Soma na Coleta de Financiamentos (Enviados)", 50, 48, 49),
        linha_soma_beneficios_riaf("Soma dos Financiamentos (Analisados)", c_gemini_valor_financiamento_riaf, 51),
        [],
        row_headers("Análise Financeira", fmt_header_laranja),
        linha_soma_bolsas_pagas_riaf("Soma na Coleta das Bolsas Pagas", 52),
        linha_soma_bolsas_pagas_riaf("Soma na Coleta das Bolsas Pagas (Pendentes / Glosa)", 53, pendentes=True),
        linha_soma_bolsas_pagas_riaf("Soma na Coleta das Bolsas Pagas (Enviados)", 54, enviados=True),
        linha_soma_bolsas_recalc_riaf("Soma das Bolsas Pagas - Recálculo", 55),
        linha_soma_bolsas_recalc_diag_riaf("Soma das Bolsas Pagas - Recálculo (Em Conformidade)", 56, "Pagamento correto"),
        linha_soma_bolsas_recalc_diag_riaf("Soma das Bolsas Pagas - Recálculo (Acima do Esperado)", 57, "OVG pagou a mais"),
        linha_soma_bolsas_recalc_diag_riaf("Soma das Bolsas Pagas - Recálculo (Abaixo do Esperado)", 58, "OVG pagou a menos"),
        linha_prejuizo_real_riaf("Soma do Valor Excedente Pago", 59, fmt_t=fmt_cell_laranja_red),
        [],
        row_headers("Resultado da Análise Acadêmica", fmt_header_laranja),
        linha_inconsistencia_riaf("Qtd. de RIAF's com CPF divergente", "CPF", 62),
        linha_inconsistencia_riaf("Qtd. de RIAF's com CNPJ divergente", "CNPJ", 63),
        linha_inconsistencia_riaf("Qtd. de RIAF's com Semestre Letivo divergente", "Semestre", 64),
        linha_inconsistencia_riaf("Qtd. de RIAF's com Curso divergente", "Curso", 65),
        linha_inconsistencia_riaf("Qtd. de RIAF's com Mensalidade divergente", "Mensal", 66),
        linha_inconsistencia_riaf("Qtd. de RIAF's com Matrícula divergente", "Matr", 67)
    ]

    row_idx = 3
    for row_data in layout:
        if not row_data:
            # Merges the empty row with a clean white background to avoid breaks in the layout
            worksheet.merge_range(row_idx, 0, row_idx, last_col_idx, "", fmt_branco)
            row_idx += 1
            continue
        col_idx = 0
        for cell in row_data:
            if cell is None:
                col_idx += 1
                continue
            if len(cell) == 4:
                val, fmt, merge_cols, merge_rows = cell
                if merge_cols > 1 or merge_rows > 1:
                    if str(val).startswith('='):
                        worksheet.merge_range(row_idx, col_idx, row_idx + merge_rows - 1, col_idx + merge_cols - 1, '', fmt)
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.merge_range(row_idx, col_idx, row_idx + merge_rows - 1, col_idx + merge_cols - 1, val, fmt)
                else:
                    if str(val).startswith('='):
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += merge_cols
            elif len(cell) == 3:
                val, fmt, merge_len = cell
                if merge_len > 1:
                    if str(val).startswith('='):
                        worksheet.merge_range(row_idx, col_idx, row_idx, col_idx + merge_len - 1, '', fmt)
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.merge_range(row_idx, col_idx, row_idx, col_idx + merge_len - 1, val, fmt)
                else:
                    if str(val).startswith('='):
                        worksheet.write_formula(row_idx, col_idx, val, fmt)
                    else:
                        worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += merge_len
            else:
                val, fmt = cell
                if str(val).startswith('='):
                    worksheet.write_formula(row_idx, col_idx, val, fmt)
                else:
                    worksheet.write(row_idx, col_idx, val, fmt)
                col_idx += 1
        row_idx += 1


def recalcular_bolsas_ia(df, is_riaf=False):
    """
    O QUE FAZ: Recalcula, a partir dos valores que a IA leu no documento, quanto a OVG
    deveria ter pago de bolsa a cada beneficiário.
    POR QUÊ EXISTE: É a base das colunas de prejuízo e economia — o valor apurado aqui é
    confrontado com o que a OVG efetivamente pagou.
    COMO FUNCIONA: Bolsa parcial vale 50% da mensalidade, limitada a R$ 650 (R$ 2.900 em
    Medicina e Odontologia); bolsa integral vale a mensalidade, limitada a R$ 1.500
    (R$ 5.800 nesses mesmos cursos). Quando bolsa somada aos benefícios ultrapassa a
    mensalidade, o excedente é descontado para não pagar acima do devido. Semestres a
    partir de 2026/1 usam base de cálculo própria.
    PARÂMETROS: df (DataFrame), is_riaf (bool — alterna a origem das colunas de valor)
    RETORNO: o DataFrame com as colunas de bolsa recalculada.
    """
    if df.empty: return df
    
    mens = df.get('gemini_mensalidade_com_desc', pd.Series(0, index=df.index))
    mens_desc = pd.to_numeric(mens.astype(str).str.replace(r'[R$\s]', '', regex=True).str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce').fillna(0.0)
    
    matr = df.get('gemini_matricula_com_desc', pd.Series(0, index=df.index))
    matr_desc = pd.to_numeric(matr.astype(str).str.replace(r'[R$\s]', '', regex=True).str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce').fillna(0.0)
    
    beneficios = pd.to_numeric(df.get('valor_beneficio', pd.Series(0.0, index=df.index)), errors='coerce').fillna(0.0)
    qtd_pagtos = pd.to_numeric(df.get('qtd_pagtos', pd.Series(1.0, index=df.index)), errors='coerce').fillna(1.0)
    
    curso_str = df.get('curso', df.get('Curso', pd.Series('', index=df.index))).astype(str).str.upper()
    is_med_odonto = curso_str.str.contains('MEDICINA|ODONTOLOGIA', regex=True)
    
    tipo_bolsa = df.get('tipo_bolsa_final', df.get('tipo_bolsa', pd.Series('', index=df.index))).astype(str).str.upper()
    is_parcial = tipo_bolsa.str.contains('PARCIAL', regex=True)
    is_integral = tipo_bolsa.str.contains('INTEGRAL', regex=True)
    
    semestre_str = df.get('semestre', df.get('Semestre', pd.Series('', index=df.index))).astype(str).str.upper()
    ano_sem = pd.to_numeric(semestre_str.str.extract(r'(\d{4})')[0], errors='coerce').fillna(0)
    is_primeiro_semestre = semestre_str.str.contains(r'\.1$|/1$|-1$', regex=True)
    is_2026_em_diante = (ano_sem >= 2026) & is_primeiro_semestre
    
    def calc_valor_bolsa(base_calc):
        mensalidade_50 = base_calc * 0.5
        limite_parcial = np.where(is_med_odonto, 2900.0, 650.0)
        bolsa_parcial = np.minimum(mensalidade_50, limite_parcial)
        
        limite_integral = np.where(is_med_odonto, 5800.0, 1500.0)
        bolsa_integral = np.minimum(base_calc, limite_integral)
        
        valor_bolsa = np.zeros(len(df))
        valor_bolsa = np.where(is_parcial, bolsa_parcial, valor_bolsa)
        valor_bolsa = np.where(is_integral, bolsa_integral, valor_bolsa)
        
        ajuste_necessario = (valor_bolsa + beneficios) > base_calc
        valor_bolsa = np.where(ajuste_necessario, np.maximum(base_calc - beneficios, 0.0), valor_bolsa)
        return valor_bolsa

    # Calcula unitários
    valor_bolsa_mens = calc_valor_bolsa(mens_desc)
    valor_bolsa_matr = calc_valor_bolsa(matr_desc)
    
    # Se for RIAF E for 2026.1: Janeiro paga Matrícula, restantes Mensalidade
    # Se não, ou se não for RIAF, tudo paga Mensalidade (contratos não possuem info financeira de matrícula)
    # Soma total = (1 * valor_bolsa_matr Se riaf_2026_1) + ((qtd_pagtos - 1) * valor_bolsa_mens Se riaf_2026_1)
    
    if is_riaf:
        cond_aplicar_matricula = is_2026_em_diante & (qtd_pagtos > 0)
        soma = np.where(
            cond_aplicar_matricula,
            valor_bolsa_matr + (valor_bolsa_mens * (qtd_pagtos - 1)),
            valor_bolsa_mens * qtd_pagtos
        )
    else:
        soma = valor_bolsa_mens * qtd_pagtos

    df['soma_ovg_devia_pagar_ia'] = soma
    return df

def normalizar_tipos_para_parquet(df):
    """
    O QUE FAZ: Deixa o DataFrame gravável em Parquet mexendo no mínimo possível de colunas.
    POR QUÊ EXISTE: A versão anterior fazia `df[col].astype(str)` em TODAS as colunas antes
        de gravar. Funcionava — nada quebra ao virar texto —, mas as sete abas geradas
        ficaram 100% string: 493 mil linhas em que valor, data e contagem eram texto. Todo
        gráfico teria que reconverter tudo a cada leitura, e ordenação numérica sairia
        errada ('10' < '9'). O único motivo real do astype era a coluna `object` com tipos
        misturados, que o pyarrow recusa.
    COMO FUNCIONA: Só as colunas `object` são candidatas — as demais já têm tipo definido e
        passam intactas. Para cada candidata, tenta construir o array do pyarrow: se o tipo
        é homogêneo, passa direto; se o pyarrow recusa por mistura, aí sim a coluna vira
        texto. O custo da tentativa é uma conversão que o `to_parquet` faria de qualquer forma.
    PARÂMETROS: df (DataFrame)
    RETORNO: o mesmo DataFrame, com as colunas realmente problemáticas convertidas.
    EFEITOS COLATERAIS: altera o DataFrame recebido (é descartado logo após a gravação).
    """
    import pyarrow as pa

    for col in df.columns:
        if df[col].dtype != object:
            continue
        try:
            pa.array(df[col])
        except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError):
            df[col] = df[col].astype(str)
    return df


def gerar_relatorio_geral(docs_selecionados=None, periodos_por_doc=None, gerar_relatorio=False, gerar_relatorio_riaf=False, gerar_quantitativo=True, gerar_pagamentos=True, sems_riaf=None, sems_contratos=None, processo_id=None, formato="EXCEL"):
    """
    O QUE FAZ: Ponto de entrada final do fluxo de transformação (ETAPA 3). Lê os CSVs temporários, aplica regras, cria o Excel Final.
    POR QUÊ EXISTE: O Controller `views.py` e `management/command` invocam este método após extração e consolidação.
    COMO FUNCIONA: Abre os datasets -> Conecta SQL -> Faz as fusões (mesclar_sql) -> Aplica transições -> Gera Resumos -> Escreve no disco com `pd.ExcelWriter`.
    RETORNO: String com o caminho do arquivo gerado.
    """
    print(f"[GGCI       | INICIANDO     | GERAL ] Gerando Relatório Geral...\n")
    t_inicio_ggci = time.time()
    
    if not processo_id:
        raise ValueError("O processo_id é obrigatório.")
    base_dir = f"apps/dashboards/dash_documentos_ia/dados/processamento/proc_{processo_id}"
    pasta_consolidados = os.path.join(base_dir, "analise_documentos_processados", "CONSOLIDADO")
    arq_processados = os.path.join(pasta_consolidados, "consolidado_processados.parquet")
    arq_riaf = os.path.join(pasta_consolidados, "consolidado_processados_riaf.parquet")
    arq_agendar = os.path.join(base_dir, "analise_documentos_agendar_processamentos", "CONSOLIDADO", "consolidado_agendar_processamentos.parquet")
    pasta_pag = os.path.join(base_dir, "analise_pagamentos", "CONSOLIDADO")
    arq_pagamentos = os.path.join(pasta_pag, "consolidado_pagamentos.parquet")
    arq_cobranca_site = os.path.join(base_dir, "cobranca_do_site", "CONSOLIDADO", "consolidado_cobranca_do_site.parquet")
    arquivo_geral_saida = os.path.join(base_dir, f"relatorio_geral.xlsx")
    

    
    if not docs_selecionados or "TODOS" in docs_selecionados:
        docs_selecionados = ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF", "HISTORICO"]
        
    if periodos_por_doc is None:
        periodos_por_doc = {}
        
    check_contrato = "CONTRATOS" in docs_selecionados
    check_financ = "FINANCIAMENTO" in docs_selecionados
    check_benef = "BENEFICIOS" in docs_selecionados
    check_riaf = "RIAF" in docs_selecionados
    check_historico = "HISTORICO" in docs_selecionados
    
    # Check if there are multiple periods across any relevant documents
    todos_periodos_usados = set()
    docs_para_validar = ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF"]
    for doc in docs_para_validar:
        if doc in docs_selecionados and doc in periodos_por_doc:
            todos_periodos_usados.update(periodos_por_doc[doc])
            
    tem_multiplos_periodos = len(todos_periodos_usados) > 1
    
    pode_gerar_relatorio = (check_contrato and check_financ and check_benef and tem_multiplos_periodos and gerar_quantitativo and gerar_pagamentos)
    pode_gerar_relatorio_riaf = (check_riaf and check_financ and check_benef and tem_multiplos_periodos and gerar_quantitativo and gerar_pagamentos)
    
    if gerar_relatorio and not pode_gerar_relatorio:
        gerar_relatorio = False
        
    if gerar_relatorio_riaf and not pode_gerar_relatorio_riaf:
        gerar_relatorio_riaf = False
    sems_alvo = []
    # Collect all targeted semesters to pull from the DB
    for doc in docs_selecionados:
        sems = periodos_por_doc.get(doc, [])
        if not sems: 
            sems = ["2025-1", "2025-2", "2026-1", "2026-2"]
        sems_alvo.extend(sems)
        
    sems_alvo = list(set(sems_alvo))
    
    df_docs = pd.DataFrame()
    df_riaf = pd.DataFrame()
    df_pag = pd.DataFrame()

    if os.path.exists(arq_processados):
        df_docs = converter_colunas_para_salvamento(pd.read_parquet(arq_processados))
        if 'Faculdade' in df_docs.columns:
            df_docs = df_docs[~df_docs['Faculdade'].astype(str).str.upper().str.contains('FACULDADE TESTE', na=False)]
        print(f"[GGCI       | LIDO          | DOCS  ] {len(df_docs)} linhas base.")
        
    arq_historico = os.path.join(pasta_consolidados, "consolidado_processados_historico.parquet")
    if check_historico and os.path.exists(arq_historico):
        df_hist = converter_colunas_para_salvamento(pd.read_parquet(arq_historico))
        if 'Faculdade' in df_hist.columns:
            df_hist = df_hist[~df_hist['Faculdade'].astype(str).str.upper().str.contains('FACULDADE TESTE', na=False)]
        df_docs = pd.concat([df_docs, df_hist], ignore_index=True) if not df_docs.empty else df_hist
        print(f"[GGCI       | LIDO          | HIST  ] Carregados históricos extras.")
        
    try:
        if check_historico and sems_alvo:
            
            dfs = []
            for ano in ['2025', '2026']:
                if any(ano in str(s) for s in sems_alvo):
                    p = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_espelho_historico_d1_{ano}{SUFIXO_TABELAS}.parquet")
                    if os.path.exists(p):
                        df_ano = pl.read_parquet(p).filter(pl.col("semestre").is_in(sems_alvo)).to_pandas()
                        dfs.append(df_ano)
            
            if dfs:
                df_espelho_hist_pd = pd.concat(dfs, ignore_index=True)
                if not df_espelho_hist_pd.empty:
                    mapa_colunas_hist = {
                        'uni_codigo': 'Inscrição', 'semestre': 'Semestre', 'gemini_status': 'Status_IA',
                        'gemini_inconsistencias': 'Gemini Inconsistencias', 'processar': 'Processar', 'processado': 'Processado',
                        'data_processamento': 'Data Processamento', 'coleta_dados_id': 'Coleta ID', 'gemini_cpf': 'Gemini CPF',
                        'cpf': 'CPF', 'gemini_curso': 'Gemini Curso', 'curso': 'Curso', 'gemini_nome_faculdade': 'Gemini Nome Faculdade',
                        'nome_faculdade': 'Faculdade', 'gemini_mensalidade_sem_desconto': 'Gemini Mensalidade S/ Desconto',
                        'mensalidade_sem_desconto': 'Mensalidade S/ Desconto', 'gemini_mensalidade_com_desconto': 'Gemini Mensalidade C/ Desconto',
                        'mensalidade_com_desconto': 'Mensalidade C/ Desconto', 'gemini_concluiu_curso': 'gemini_concluiu_curso',
                        'gemini_semestre': 'Gemini Semestre', 'data_create': 'data_create', 'qtde_token': 'Qtde Token'
                    }
                    df_espelho_hist_pd = df_espelho_hist_pd.rename(columns=mapa_colunas_hist)
                    df_espelho_hist_pd['Semestre'] = df_espelho_hist_pd['Semestre'].astype(str).str.replace('/', '-')
                    df_espelho_hist_pd['Documento Tipo'] = DOC_HISTORICO
                    
                    if 'Status_IA' in df_espelho_hist_pd.columns:
                        df_espelho_hist_pd['Status_IA'] = df_espelho_hist_pd['Status_IA'].replace({1: 'Válido', 0: 'Inválido', '1': 'Válido', '0': 'Inválido'})
                    for c_bool in ['Processado', 'Processar']:
                        if c_bool in df_espelho_hist_pd.columns:
                            df_espelho_hist_pd[c_bool] = df_espelho_hist_pd[c_bool].replace({1: 'SIM', 0: 'NÃO', '1': 'SIM', '0': 'NÃO', 'S': 'SIM', 'N': 'NÃO'}).fillna('NÃO')
                    
                    df_docs = pd.concat([df_docs, df_espelho_hist_pd], ignore_index=True) if not df_docs.empty else df_espelho_hist_pd
                    df_docs = converter_colunas_para_salvamento(df_docs)
                    print(f"[GGCI       | LIDO          | HIST BD] +{len(df_espelho_hist_pd)} linhas espelhadas da view (via Pandas).")
    except Exception as e:
        print(f"[GGCI       | ERRO          | HIST BD] Falha critica no historico: {e}")


    try:
        if check_contrato and sems_alvo:
            dfs = []
            for ano in ['2025', '2026']:
                if any(ano in str(s) for s in sems_alvo):
                    p = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_espelho_contrato_temp_d1_{ano}{SUFIXO_TABELAS}.parquet")
                    if os.path.exists(p):
                        df_ano = pl.read_parquet(p).filter(pl.col("semestre").is_in(sems_alvo)).to_pandas()
                        dfs.append(df_ano)

            if dfs:
                df_esp_cont_pd = pd.concat(dfs, ignore_index=True)
                if not df_esp_cont_pd.empty:
                    mapa_cont = {
                        'uni_codigo': 'Inscrição', 'semestre': 'Semestre', 'gemini_status': 'Status_IA',
                        'gemini_inconsistencias': 'Gemini Inconsistencias', 'processar': 'Processar', 'processado': 'Processado',
                        'data_processamento': 'Data Processamento', 'coleta_dados_id': 'Coleta ID', 'gemini_cpf': 'Gemini CPF',
                        'cpf': 'CPF', 'gemini_curso': 'Gemini Curso', 'curso': 'Curso', 'gemini_nome_faculdade': 'Gemini Nome Faculdade',
                        'nome_faculdade': 'Faculdade', 'gemini_mensalidade_sem_desconto': 'Gemini Mensalidade S/ Desconto',
                        'gemini_mensalidade_com_desconto': 'Gemini Mensalidade C/ Desconto', 'gemini_semestre': 'Gemini Semestre',
                        'gemini_cnpj_faculdade': 'Gemini Cnpj Faculdade', 'gemini_cnpj_mantenedora': 'Gemini Cnpj Mantenedora',
                        'gemini_assinatura_aluno': 'Gemini Assinatura Aluno', 'gemini_assinatura_ies': 'Gemini Assinatura Ies',
                        'gemini_cnpj_banco': 'Gemini Cnpj Banco', 'qtde_token': 'Qtde Token', 'data_create': 'data_create'
                    }
                    df_esp_cont_pd = df_esp_cont_pd.rename(columns=mapa_cont)
                    df_esp_cont_pd['Semestre'] = df_esp_cont_pd['Semestre'].astype(str).str.replace('/', '-')
                    df_esp_cont_pd['Documento Tipo'] = DOC_CONTRATO
                    
                    if 'Status_IA' in df_esp_cont_pd.columns:
                        df_esp_cont_pd['Status_IA'] = df_esp_cont_pd['Status_IA'].replace({1: 'Válido', 0: 'Inválido', '1': 'Válido', '0': 'Inválido'})
                    for c_bool in ['Processado', 'Processar']:
                        if c_bool in df_esp_cont_pd.columns:
                            df_esp_cont_pd[c_bool] = df_esp_cont_pd[c_bool].replace({1: 'SIM', 0: 'NÃO', '1': 'SIM', '0': 'NÃO', 'S': 'SIM', 'N': 'NÃO'}).fillna('NÃO')
                            
                    df_docs = pd.concat([df_esp_cont_pd, df_docs], ignore_index=True) if not df_docs.empty else df_esp_cont_pd
                    df_docs = converter_colunas_para_salvamento(df_docs)
                    print(f"[GGCI       | LIDO          | CONT BD ] +{len(df_esp_cont_pd)} linhas espelhadas da view (via Pandas).")
    except Exception as e:
        print(f"[GGCI       | AVISO         | CONT BD ] Falha espelho contrato: {e}")

    # OTIMIZAÇÃO: Injeção direta dos dados históricos de FINANCIAMENTO
    try:
        if check_financ and sems_alvo:
            dfs_fin = []
            for ano in ['2025', '2026']:
                if any(ano in str(s) for s in sems_alvo):
                    p = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_espelho_financiamento_d1_{ano}{SUFIXO_TABELAS}.parquet")
                    if os.path.exists(p):
                        df_ano = pl.read_parquet(p).filter(pl.col("semestre").is_in(sems_alvo)).to_pandas()
                        dfs_fin.append(df_ano)

            if dfs_fin:
                df_esp_fin_pd = pd.concat(dfs_fin, ignore_index=True)
                if not df_esp_fin_pd.empty:
                    mapa_fin = {
                        'uni_codigo': 'Inscrição', 'semestre': 'Semestre', 'gemini_status': 'Status_IA',
                        'gemini_inconsistencias': 'Gemini Inconsistencias', 'processar': 'Processar', 'processado': 'Processado',
                        'data_processamento': 'Data Processamento', 'coleta_dados_id': 'Coleta ID', 'gemini_cpf': 'Gemini CPF',
                        'cpf': 'CPF', 'gemini_curso': 'Gemini Curso', 'curso': 'Curso', 'gemini_nome_faculdade': 'Gemini Nome Faculdade',
                        'nome_faculdade': 'Faculdade', 'gemini_semestre': 'Gemini Semestre',
                        'gemini_nome_financiamento': 'Gemini Nome Financiamento',
                        'gemini_valor_financiado': 'Gemini Valor Financiado',
                        'gemini_semestres_financiados': 'gemini_semestres_financiados',
                        'nome_financiamento': 'qual_financiamento',
                        'valor_financiamento': 'valor_financiamento',
                        'qtde_token': 'Qtde Token', 'data_create': 'data_create'
                    }
                    df_esp_fin_pd = df_esp_fin_pd.rename(columns=mapa_fin)
                    df_esp_fin_pd['Semestre'] = df_esp_fin_pd['Semestre'].astype(str).str.replace('/', '-')
                    df_esp_fin_pd['Documento Tipo'] = DOC_FINANC
                    
                    if 'Status_IA' in df_esp_fin_pd.columns:
                        df_esp_fin_pd['Status_IA'] = df_esp_fin_pd['Status_IA'].replace({1: 'Válido', 0: 'Inválido', '1': 'Válido', '0': 'Inválido'})
                    for c_bool in ['Processado', 'Processar']:
                        if c_bool in df_esp_fin_pd.columns:
                            df_esp_fin_pd[c_bool] = df_esp_fin_pd[c_bool].replace({1: 'SIM', 0: 'NÃO', '1': 'SIM', '0': 'NÃO', 'S': 'SIM', 'N': 'NÃO'}).fillna('NÃO')
                            
                    df_docs = pd.concat([df_esp_fin_pd, df_docs], ignore_index=True) if not df_docs.empty else df_esp_fin_pd
                    df_docs = converter_colunas_para_salvamento(df_docs)
                    print(f"[GGCI       | LIDO          | FIN  BD ] +{len(df_esp_fin_pd)} linhas espelhadas da view (via Pandas).")
    except Exception as e:
        print(f"[GGCI       | AVISO         | FIN  BD ] Falha espelho financiamento: {e}")


    # OTIMIZAÇÃO: Injeção direta dos dados históricos de BENEFICIOS
    try:
        if check_benef and sems_alvo:
            dfs_ben = []
            for ano in ['2025', '2026']:
                if any(ano in str(s) for s in sems_alvo):
                    p = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_espelho_beneficio_temp_d1_{ano}{SUFIXO_TABELAS}.parquet")
                    if os.path.exists(p):
                        df_ano = pl.read_parquet(p).filter(pl.col("semestre").is_in(sems_alvo)).to_pandas()
                        dfs_ben.append(df_ano)

            if dfs_ben:
                df_esp_ben_pd = pd.concat(dfs_ben, ignore_index=True)
                if not df_esp_ben_pd.empty:
                    mapa_ben = {
                        'uni_codigo': 'Inscrição', 'semestre': 'Semestre', 'gemini_status': 'Status_IA',
                        'gemini_inconsistencias': 'Gemini Inconsistencias', 'processar': 'Processar', 'processado': 'Processado',
                        'data_processamento': 'Data Processamento', 'coleta_dados_id': 'Coleta ID', 'gemini_cpf': 'Gemini CPF',
                        'cpf': 'CPF', 'gemini_curso': 'Gemini Curso', 'curso': 'Curso', 'gemini_nome_faculdade': 'Gemini Nome Faculdade',
                        'nome_faculdade': 'Faculdade', 'gemini_semestre': 'Gemini Semestre',
                        'gemini_beneficio_nome': 'Gemini Beneficio Nome',
                        'gemini_valor_beneficio': 'Gemini Valor Beneficio',
                        'nome_beneficio': 'qual_beneficio',
                        'valor_beneficio': 'valor_beneficio',
                        'qtde_token': 'Qtde Token', 'data_create': 'data_create'
                    }
                    df_esp_ben_pd = df_esp_ben_pd.rename(columns=mapa_ben)
                    df_esp_ben_pd['Semestre'] = df_esp_ben_pd['Semestre'].astype(str).str.replace('/', '-')
                    df_esp_ben_pd['Documento Tipo'] = DOC_BENEF
                    
                    if 'Status_IA' in df_esp_ben_pd.columns:
                        df_esp_ben_pd['Status_IA'] = df_esp_ben_pd['Status_IA'].replace({1: 'Válido', 0: 'Inválido', '1': 'Válido', '0': 'Inválido'})
                    for c_bool in ['Processado', 'Processar']:
                        if c_bool in df_esp_ben_pd.columns:
                            df_esp_ben_pd[c_bool] = df_esp_ben_pd[c_bool].replace({1: 'SIM', 0: 'NÃO', '1': 'SIM', '0': 'NÃO', 'S': 'SIM', 'N': 'NÃO'}).fillna('NÃO')
                            
                    df_docs = pd.concat([df_esp_ben_pd, df_docs], ignore_index=True) if not df_docs.empty else df_esp_ben_pd
                    df_docs = converter_colunas_para_salvamento(df_docs)
                    print(f"[GGCI       | LIDO          | BEN  BD ] +{len(df_esp_ben_pd)} linhas espelhadas da view (via Pandas).")
    except Exception as e:
        print(f"[GGCI       | AVISO         | BEN  BD ] Falha espelho beneficio: {e}")


    if check_riaf and os.path.exists(arq_riaf):
        df_riaf = converter_colunas_para_salvamento(pd.read_parquet(arq_riaf))
        if 'Faculdade' in df_riaf.columns:
            df_riaf = df_riaf[~df_riaf['Faculdade'].astype(str).str.upper().str.contains('FACULDADE TESTE', na=False)]
        print(f"[GGCI       | LIDO          | RIAF  ] {len(df_riaf)} linhas base.")

    # OTIMIZAÇÃO: Injeção direta dos dados históricos do RIAF usando Parquets locais
    try:
        if check_riaf and sems_alvo:
            dfs = []
            for ano in ['2026']:
                if any(ano in str(s) for s in sems_alvo):
                    p = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_espelho_riaf_d1_{ano}{SUFIXO_TABELAS}.parquet")
                    if os.path.exists(p):
                        df_ano = pl.read_parquet(p).filter(pl.col("semestre").is_in(sems_alvo)).to_pandas()
                        dfs.append(df_ano)
            
            if dfs:
                df_espelho_pd = pd.concat(dfs, ignore_index=True)
                if not df_espelho_pd.empty:
                    mapa_colunas = {
                        'uni_codigo': 'Inscrição', 'semestre': 'Semestre', 'gemini_status': 'Status_IA',
                        'gemini_inconsistencias': 'Gemini Inconsistencias', 'processar': 'Processar', 'processado': 'Processado',
                        'data_processamento': 'Data Processamento', 'data_create': 'data_create', 'coleta_dados_id': 'Coleta ID',
                        'gemini_cpf': 'Gemini CPF', 'gemini_matricula': 'Gemini Matricula', 'gemini_telefone': 'Gemini Telefone',
                        'gemini_periodo': 'Gemini Periodo', 'gemini_quantidade_periodos': 'Gemini Quantidade Periodos',
                        'gemini_cnpj_faculdade': 'Gemini Cnpj Faculdade', 'gemini_mensalidade_sem_desconto': 'Gemini Mensalidade S/ Desconto',
                        'gemini_mensalidade_com_desconto': 'Gemini Mensalidade C/ Desconto', 'gemini_valor_beneficio': 'Gemini Valor Beneficio',
                        'gemini_valor_financiado': 'Gemini Valor Financiado', 'gemini_valor_financiamento': 'Gemini Valor Financiado', 'gemini_matricula_sem_desconto': 'Gemini Matricula Sem Desconto',
                        'gemini_matricula_com_desconto': 'Gemini Matricula Com Desconto', 'gemini_razao_social': 'Gemini Razao Social',
                        'gemini_nome_faculdade': 'Gemini Nome Faculdade', 'gemini_beneficio_nome': 'Gemini Beneficio Nome',
                        'gemini_nome_mantenedora': 'Gemini Nome Mantenedora', 'gemini_nome_financiamento': 'Gemini Nome Financiamento',
                        'gemini_assinatura_aluno': 'Gemini Assinatura Aluno', 'gemini_assinatura_ies': 'Gemini Assinatura Ies',
                        'gemini_modalidade': 'Gemini Modalidade', 'gemini_email': 'Gemini Email', 'gemini_tipo_bolsa': 'Gemini Tipo Bolsa',
                        'gemini_curso': 'Gemini Curso', 'gemini_semestre': 'Gemini Semestre', 'qtde_token': 'Qtde Token'
                    }
                    df_espelho_pd = df_espelho_pd.rename(columns=mapa_colunas)
                    df_espelho_pd['Semestre'] = df_espelho_pd['Semestre'].astype(str).str.replace('/', '-')
                    df_espelho_pd['Documento Tipo'] = DOC_RIAF
                    
                    if 'Status_IA' in df_espelho_pd.columns:
                        df_espelho_pd['Status_IA'] = df_espelho_pd['Status_IA'].replace({1: 'Válido', 0: 'Inválido', '1': 'Válido', '0': 'Inválido'})
                        
                    for c_bool in ['Processado', 'Processar']:
                        if c_bool in df_espelho_pd.columns:
                            df_espelho_pd[c_bool] = df_espelho_pd[c_bool].replace({1: 'SIM', 0: 'NÃO', '1': 'SIM', '0': 'NÃO', 'S': 'SIM', 'N': 'NÃO'}).fillna('NÃO')
                    
                    df_riaf = pd.concat([df_riaf, df_espelho_pd], ignore_index=True)
                    df_riaf = converter_colunas_para_salvamento(df_riaf)
                    
                    print(f"[GGCI       | LIDO          | RIAF BD] +{len(df_espelho_pd)} linhas espelhadas da view (via Pandas).")
    except Exception as e:
        print(f"[GGCI       | ERRO          | RIAF BD] Falha critica no riaf: {e}")

    mapa_docs_oficiais = {
        limpar_texto_geral(DOC_CONTRATO): DOC_CONTRATO,
        limpar_texto_geral(DOC_FINANC): DOC_FINANC,
        limpar_texto_geral(DOC_BENEF): DOC_BENEF,
        limpar_texto_geral(DOC_RIAF): DOC_RIAF,
        limpar_texto_geral(DOC_HISTORICO): DOC_HISTORICO
    }

    # Filtra as linhas para EXATAMENTE os semestres escolhidos na tela
    if not df_docs.empty and 'Semestre' in df_docs.columns:
        df_docs['Semestre'] = df_docs['Semestre'].astype(str).str.strip()
        df_docs = df_docs[df_docs['Semestre'].isin(sems_alvo)]
        
        permitidos = []
        if check_contrato: permitidos.append(limpar_texto_geral(DOC_CONTRATO))
        if check_financ: permitidos.append(limpar_texto_geral(DOC_FINANC))
        if check_benef: permitidos.append(limpar_texto_geral(DOC_BENEF))
        if check_historico: permitidos.append(limpar_texto_geral(DOC_HISTORICO))
        
        if 'Documento Tipo' in df_docs.columns:
            df_docs['Documento Tipo'] = df_docs['Documento Tipo'].apply(limpar_texto_geral).map(mapa_docs_oficiais).fillna(df_docs['Documento Tipo'])
            df_docs['DOC_LIMPO'] = df_docs['Documento Tipo'].apply(limpar_texto_geral)
            df_docs = df_docs[df_docs['DOC_LIMPO'].isin(permitidos)]
            df_docs.drop(columns=['DOC_LIMPO'], inplace=True)
            
    if not df_riaf.empty and 'Semestre' in df_riaf.columns:
        df_riaf['Semestre'] = df_riaf['Semestre'].astype(str).str.strip()
        df_riaf = df_riaf[df_riaf['Semestre'].isin(sems_alvo)]
        if 'Documento Tipo' in df_riaf.columns:
            df_riaf['Documento Tipo'] = df_riaf['Documento Tipo'].apply(limpar_texto_geral).map(mapa_docs_oficiais).fillna(df_riaf['Documento Tipo'])

    # --- DEDUPLICAÇÃO GLOBAL (Garante que alunos com múltiplos uploads não dupliquem linhas) ---
    def deduplicar_dataset(df_entrada):
        if df_entrada.empty: return df_entrada
        if 'data_coleta' in df_entrada.columns:
            df_entrada['temp_data'] = pd.to_datetime(df_entrada['data_coleta'], format='%d/%m/%Y', errors='coerce')
            df_entrada.sort_values(by=['temp_data'], ascending=False, inplace=True, na_position='last')
            df_entrada.drop(columns=['temp_data'], inplace=True)
            
        if all(c in df_entrada.columns for c in ['Inscrição', 'Semestre', 'Documento Tipo']):
            df_entrada.drop_duplicates(subset=['Inscrição', 'Semestre', 'Documento Tipo'], keep='first', inplace=True)
        return df_entrada

    df_docs = deduplicar_dataset(df_docs)
    df_riaf = deduplicar_dataset(df_riaf)
    
    # Padroniza todas as colunas de IES
    for col in ['Faculdade', 'IES Anterior', 'IES Posterior', 'Gemini Nome Faculdade']:
        if not df_docs.empty and col in df_docs.columns:
            df_docs[col] = df_docs[col].apply(padronizar_ies)
        if not df_riaf.empty and col in df_riaf.columns:
            df_riaf[col] = df_riaf[col].apply(padronizar_ies)

    # --- CRUZAMENTO COM O AGENDAR PROCESSAMENTOS ---
    if os.path.exists(arq_agendar):
        df_agendar = pd.read_parquet(arq_agendar)
        print(f"[GGCI       | LIDO          | AGENDAMENTO] Validação rigorosa.")
        df_agendar['Semestre'] = df_agendar['Semestre'].astype(str).str.strip().str.replace('/', '-')
        
        if 'Documento Tipo' in df_agendar.columns:
            df_agendar['Documento Tipo'] = df_agendar['Documento Tipo'].apply(limpar_texto_geral).map(mapa_docs_oficiais).fillna(df_agendar['Documento Tipo'])
        
        col_data = 'Data processamento' if 'Data processamento' in df_agendar.columns else 'Data Processamento'
        if col_data not in df_agendar.columns: df_agendar[col_data] = ''
        if 'Processar' not in df_agendar.columns: df_agendar['Processar'] = ''
        if 'Processado' not in df_agendar.columns: df_agendar['Processado'] = ''
        
        df_ag_merge = df_agendar[['Inscrição', 'Semestre', 'Documento Tipo', 'Processar', 'Processado', col_data]].copy()
        df_ag_merge.rename(columns={col_data: 'Data_Processamento_Agendar', 'Processar': 'Processar_y', 'Processado': 'Processado_y'}, inplace=True)
        df_ag_merge = df_ag_merge.drop_duplicates(subset=['Inscrição', 'Semestre', 'Documento Tipo'], keep='last')
        
        if not df_docs.empty:
            df_docs = pd.merge(df_docs, df_ag_merge, on=['Inscrição', 'Semestre', 'Documento Tipo'], how='left')
        if not df_riaf.empty:
            df_riaf = pd.merge(df_riaf, df_ag_merge, on=['Inscrição', 'Semestre', 'Documento Tipo'], how='left')

    if os.path.exists(arq_pagamentos):
        df_pag = converter_colunas_para_salvamento(pd.read_parquet(arq_pagamentos))
        print(f"[GGCI       | LIDO          | PAGAMENTOS ] Cruzamento financeiro.")

    df_financas = pd.DataFrame()
    df_mes_a_mes = pd.DataFrame()
    
    print("[GGCI       | CONECTANDO    | BD SIBU    ] Gerando tabelas temporárias (Pagamentos, Benefícios, Pendentes)...")
    # O recriar tabelas foi movido para o início da extração (extrator.py)
    # para resolver o problema de latência dos logs e garantir que as tabelas sejam criadas no início e removidas no final.
        
    print("[GGCI       | CONECTANDO    | BD SIBU    ] Buscando base (cadastro e financeiro)...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_fin = executor.submit(buscar_dados_financeiros_sql, sems_alvo)
        future_mes = executor.submit(buscar_dados_pagamentos_mes_a_mes_sql, sems_alvo)
        
        df_financas = future_fin.result()
        df_mes_a_mes = future_mes.result()
        
    if df_pag is not None and not df_pag.empty and 'INS_NOME' in df_pag.columns:
        df_pag['INS_NOME'] = df_pag['INS_NOME'].apply(padronizar_ies)
    if df_financas is not None and not df_financas.empty and 'nome_faculdade_sql' in df_financas.columns:
        df_financas['nome_faculdade_sql'] = df_financas['nome_faculdade_sql'].apply(padronizar_ies)

    df_sql = df_financas.copy() if not df_financas.empty else pd.DataFrame()

    if (not df_pag.empty or not df_sql.empty) and (check_contrato or check_financ or check_benef or check_riaf or check_historico):
        print("[GGCI       | IDENTIFICAR   | AUSENTES   ] Buscando...")
        _t_pend = time.perf_counter()
        
        if not df_pag.empty:
            df_pag_tmp = df_pag.copy()
            df_pag_tmp['SEMESTRE_NORM'] = df_pag_tmp['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
            df_ativos = df_pag_tmp[df_pag_tmp['SEMESTRE_NORM'].isin(sems_alvo)].copy()
            df_ativos['SEMESTRE'] = df_ativos['SEMESTRE_NORM']
            df_ativos = df_ativos[['SEMESTRE', 'UNI_CODIGO', 'UNI_CPF', 'UNI_NOME', 'INS_NOME', 'CUR_NOME']].drop_duplicates(subset=['UNI_CODIGO', 'SEMESTRE'], keep='last')
        else:
            cols_to_extract = ['semestre', 'uni_codigo', 'UNI_CPF', 'Bolsista_sql', 'ins_razao_social', 'CUR_NOME']
            cols_to_extract = [c for c in cols_to_extract if c in df_sql.columns]
            df_ativos = df_sql[cols_to_extract].copy()
            df_ativos.rename(columns={'semestre': 'SEMESTRE', 'uni_codigo': 'UNI_CODIGO', 'Bolsista_sql': 'UNI_NOME', 'ins_razao_social': 'INS_NOME'}, inplace=True)
            df_ativos = df_ativos.drop_duplicates(subset=['UNI_CODIGO', 'SEMESTRE'], keep='last')

        # 'Documento Tipo' tem 5 valores distintos em ~167 mil linhas: limpar_texto_geral
        # roda por valor, não por linha (ver aplicar_por_distintos).
        chaves_docs_entregues = set(zip(df_docs['Inscrição'].astype(str).str.split('.').str[0].str.strip(), df_docs['Semestre'].astype(str).str.strip().str.replace('/', '-'), aplicar_por_distintos(df_docs['Documento Tipo'], limpar_texto_geral))) if not df_docs.empty else set()
        chaves_riaf_entregues = set(zip(df_riaf['Inscrição'].astype(str).str.split('.').str[0].str.strip(), df_riaf['Semestre'].astype(str).str.strip().str.replace('/', '-'))) if not df_riaf.empty else set()

        cronometrar_fim('pend preparar base', _t_pend)
        _t_pend = time.perf_counter()

        if not df_ativos.empty:
            df_ativos['uni_codigo'] = pd.to_numeric(df_ativos['UNI_CODIGO'], errors='coerce').astype('Int64')
            df_ativos['semestre'] = df_ativos['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
            
            if not df_financas.empty:
                # `qtd_pagtos_retroativos` e `último_valor_pago_referencia` entram por causa de
                # `sem_repasse_liquido`, logo abaixo: sem elas o filtro só sabe QUANTOS lançamentos
                # existem, não quanto sobrou depois dos cancelamentos.
                cols_fin = ['uni_codigo', 'semestre', 'valor_financiamento', 'valor_beneficio', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'último_valor_pago_referencia', 'matricula', 'modalidade', 'email', 'telefone_1', 'telefone_2', 'data_nascimento', 'periodo_atual', 'periodo_quantidade']
                cols_fin = [c for c in cols_fin if c in df_financas.columns and (c not in df_ativos.columns or c in ['uni_codigo', 'semestre'])]
                df_fin_reduzido = df_financas[cols_fin].drop_duplicates(subset=['uni_codigo', 'semestre'], keep='last').copy()
                df_fin_reduzido['semestre'] = df_fin_reduzido['semestre'].astype(str).str.strip().str.replace('/', '-')
                df_ativos = pd.merge(df_ativos, df_fin_reduzido, on=['uni_codigo', 'semestre'], how='left')
            
            if 'valor_financiamento' not in df_ativos.columns: df_ativos['valor_financiamento'] = 0.0
            if 'valor_beneficio' not in df_ativos.columns: df_ativos['valor_beneficio'] = 0.0

            df_ativos['valor_financiamento'] = pd.to_numeric(df_ativos['valor_financiamento'], errors='coerce').fillna(0.0)
            df_ativos['valor_beneficio'] = pd.to_numeric(df_ativos['valor_beneficio'], errors='coerce').fillna(0.0)

            def sem_repasse_liquido(df_alvo):
                """
                O QUE FAZ: diz, por linha, se a OVG NÃO custeou aquele semestre.

                É O MESMO CRITÉRIO de `cond_inadimplente` (ver `calcular_auditoria_ia`), escrito
                com as colunas que existem aqui: sobrou zero lançamento depois dos cancelamentos,
                ou o valor de referência do repasse é zero. Os dois termos porque um pagamento
                pode existir com valor zerado e um valor pode existir com o lançamento estornado.

                POR QUE PRECISA SER O MESMO: se este filtro for mais frouxo, a linha nasce aqui e
                é `calcular_auditoria_ia` que a carimba `Inadimplente` — cobrança sem lastro na
                tela, que é o erro mais caro que este relatório pode causar. Era exatamente o que
                acontecia: o filtro antigo testava `qtd_pagtos <= 0`, que não desconta estorno
                nem olha valor. Em 2025-2 isso deixava passar 33 históricos de inscrições
                migradas, todas com o lançamento cancelado a 100% e a cobrança real já na
                inscrição nova. Medido nas cinco abas: o critério certo apanha 100% dos casos
                sem repasse e ZERO das 82.052 pendências legítimas.
                """
                vazio = pd.Series(np.nan, index=df_alvo.index)
                pagos = pd.to_numeric(df_alvo.get('qtd_pagtos', vazio), errors='coerce')
                estornados = pd.to_numeric(df_alvo.get('qtd_pagtos_retroativos', vazio), errors='coerce').fillna(0)
                referencia = pd.to_numeric(df_alvo.get('último_valor_pago_referencia', vazio), errors='coerce')

                # CADA TERMO SÓ FALA DO QUE SABE, e o DESCONHECIDO NÃO BARRA. `df_ativos` pode
                # vir do consolidado de pagamentos em vez do financeiro (ver os dois caminhos
                # logo acima), e aí o merge é `how='left'`: quem não tem contrapartida fica com
                # nulo. Tratar nulo como zero faria "não sei se houve repasse" virar "não houve",
                # e a pendência sumiria sem deixar rastro — subcontagem silenciosa, que é pior
                # que a sobrecontagem: a IES deixa de ser cobrada e ninguém percebe. Na dúvida a
                # linha nasce e fica visível, que é revisável.
                liquido_zerado = pagos.notna() & ((pagos - estornados) <= 0)
                referencia_zerada = referencia.notna() & (referencia <= 0)
                return liquido_zerado | referencia_zerada

            tipos_obrigatorios_geral = []
            if check_contrato: tipos_obrigatorios_geral.append((limpar_texto_geral(DOC_CONTRATO), DOC_CONTRATO, 'sempre'))
            if check_financ: tipos_obrigatorios_geral.append((limpar_texto_geral(DOC_FINANC), DOC_FINANC, 'financ'))
            if check_benef: tipos_obrigatorios_geral.append((limpar_texto_geral(DOC_BENEF), DOC_BENEF, 'benef'))
            if check_historico: tipos_obrigatorios_geral.append((limpar_texto_geral(DOC_HISTORICO), DOC_HISTORICO, 'sempre'))

            novos_ausentes_docs, novos_ausentes_riaf = [], []

            if tipos_obrigatorios_geral:
                df_tipos = pd.DataFrame(tipos_obrigatorios_geral, columns=['tipo_limpo', 'tipo_original', 'condicao'])
                df_cross = df_ativos.merge(df_tipos, how='cross')
                
                try:
                    pendentes_map = {}
                    
                    def fetch_pendentes(nome_doc, path_parquet):
                        try:
                            if not os.path.exists(path_parquet): return nome_doc, set()
                            df_pend = pl.read_parquet(path_parquet).to_pandas()
                            
                            if df_pend.empty or 'semestre' not in df_pend.columns: return nome_doc, set()
                            df_pend['chave'] = df_pend['uni_codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip() + "_" + df_pend['semestre'].astype(str).str.strip().str.replace('/', '-')
                            return nome_doc, set(df_pend['chave'])
                        except Exception as e:
                            print(f"[GGCI       | ERRO          | AUSENTES] Falha ao consultar {nome_doc}: {e}")
                            return nome_doc, set()
                            
                    # Nome próprio de propósito: esta linha reatribuía `base_dir`, que é a
                    # pasta do processamento (proc_N) definida no topo da função. Depois
                    # daqui `base_dir` passava a apontar para tabelas_sql, e o ZIP do modo
                    # CSV — cujo caminho é montado mais adiante — ia para tabelas_sql em vez
                    # da pasta do processo, sendo sobrescrito a cada execução. O XLSX
                    # escapava só porque o caminho dele é montado antes deste ponto.
                    dir_tabelas_sql = os.path.join(PROJECT_ROOT, "apps/dashboards/dash_documentos_ia/dados/tabelas_sql")
                    pend_tasks = [
                        (DOC_CONTRATO, f"{dir_tabelas_sql}/PY_ggci_pendentes_contrato_temp_d1_geral{SUFIXO_TABELAS}.parquet"),
                        (DOC_FINANC, f"{dir_tabelas_sql}/PY_ggci_pendentes_financiamento_temp_d1_geral{SUFIXO_TABELAS}.parquet"),
                        (DOC_BENEF, f"{dir_tabelas_sql}/PY_ggci_pendentes_beneficio_temp_d1_geral{SUFIXO_TABELAS}.parquet"),
                        (DOC_HISTORICO, f"{dir_tabelas_sql}/PY_ggci_pendentes_historico_geral{SUFIXO_TABELAS}.parquet")
                    ]
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        futures = [executor.submit(fetch_pendentes, doc, q) for doc, q in pend_tasks]
                        for f in concurrent.futures.as_completed(futures):
                            doc, res = f.result()
                            if res:
                                pendentes_map[doc] = res
                    
                    df_cross['UNI_CODIGO_STR'] = df_cross['UNI_CODIGO'].astype(str).str.split('.').str[0].str.strip()
                    df_cross['chave_ativos'] = df_cross['UNI_CODIGO_STR'] + "_" + df_cross['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
                    
                    mask_db = pd.Series(False, index=df_cross.index)
                    for tipo_orig, pend_set in pendentes_map.items():
                        mask_db |= (df_cross['tipo_original'] == tipo_orig) & (df_cross['chave_ativos'].isin(pend_set) | df_cross['UNI_CODIGO_STR'].isin(pend_set))
                        
                    df_cross = df_cross[mask_db].copy()
                except Exception as e:
                    print(f"[GGCI       | AVISO         | AUSENTES] Fallback nas regras de pendentes: {e}")
                    mask_valido = pd.Series(True, index=df_cross.index)
                    mask_valido &= ~((df_cross['condicao'] == 'financ') & (df_cross['valor_financiamento'] <= 0.0))
                    mask_valido &= ~((df_cross['condicao'] == 'benef') & (df_cross['valor_beneficio'] <= 0.0))
                    df_cross = df_cross[mask_valido].copy()
                
                # REGRA DA OVG: sem repasse líquido no semestre não se cobra documento nenhum.
                #
                # VALE PARA OS CINCO, e antes valia só para o Histórico. Não havia razão para a
                # diferença: a regra é sobre o SEMESTRE ter sido custeado, não sobre o tipo de
                # papel. Contrato, Benefício e Financiamento acumulavam o mesmo resíduo.
                #
                # ESTE É O LUGAR CERTO DO CORTE, e é o que faz dele seguro. `df_cross` contém
                # APENAS candidatos a `Ausente` — o que foi entregue está em `df_docs` e nunca
                # passa por aqui. Cortar em `calcular_auditoria_ia`, onde entregues e ausentes já
                # dividem o mesmo DataFrame, é o que produziu o bug de 2025-2 (223 históricos
                # ENTREGUES apagados junto com 33 pendências). Aqui isso é impossível por
                # construção, e não por cuidado de quem escreve a máscara.
                if 'qtd_pagtos' in df_cross.columns:
                    df_cross = df_cross[~sem_repasse_liquido(df_cross)].copy()
                
                df_cross['chave_temp'] = list(zip(
                    df_cross['UNI_CODIGO'].astype(str).str.split('.').str[0].str.strip(),
                    df_cross['SEMESTRE'].astype(str).str.strip().str.replace('/', '-'),
                    df_cross['tipo_limpo']
                ))
                df_cross = df_cross[~df_cross['chave_temp'].isin(chaves_docs_entregues)]

                cronometrar_fim('pend cruzar e filtrar', _t_pend)
                _t_pend = time.perf_counter()

                docs_records = df_cross.to_dict('records')
                for row in docs_records:
                        novo_ausente = {
                            'Status_IA': 'Ausente', 'Inscrição': row['UNI_CODIGO'], 
                            'Bolsista': limpar_texto_geral(row['UNI_NOME']), 'CPF': row['UNI_CPF'], 
                            'Semestre': row['SEMESTRE'], 'Faculdade': limpar_texto_geral(row['INS_NOME']), 
                            'Curso': limpar_texto_geral(row['CUR_NOME']), 'Documento Tipo': row['tipo_original']
                        }
                        for col_orig, col_dest in [
                            ('matricula', 'Matricula'), ('modalidade', 'modalidade'), 
                            ('email', 'E-mail'), ('telefone_1', 'Telefone 1'), ('telefone_2', 'Telefone 2'),
                            ('data_nascimento', 'Data nascimento'), ('periodo_atual', 'Período atual'),
                            ('periodo_quantidade', 'Período quantidade')
                        ]:
                            if col_orig in row and pd.notna(row[col_orig]):
                                novo_ausente[col_dest] = row[col_orig]
                        novos_ausentes_docs.append(novo_ausente)

            cronometrar_fim('pend montar ausentes docs', _t_pend)
            _t_pend = time.perf_counter()

            if check_riaf:
                df_ativos_riaf = df_ativos.copy()
                try:
                    df_ativos_riaf['ano'] = df_ativos_riaf['SEMESTRE'].str.split('-').str[0].astype(int)
                    df_ativos_riaf = df_ativos_riaf[df_ativos_riaf['ano'] >= 2026]
                    
                    # REGRA DA OVG: não gerar Ausente pro RIAF se a competência não teve repasse
                    # confirmado. Mesmo critério dos documentos — ver `sem_repasse_liquido`.
                    if 'qtd_pagtos' in df_ativos_riaf.columns:
                        df_ativos_riaf = df_ativos_riaf[~sem_repasse_liquido(df_ativos_riaf)]
                    
                    if not df_ativos_riaf.empty:
                        # OTIMIZAÇÃO/PEDIDO: Filtra para gerar Ausentes *apenas* para os alunos da view pendente
                        try:
                            caminho_riaf = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_pendentes_riaf_geral{SUFIXO_TABELAS}.parquet")
                            if os.path.exists(caminho_riaf):
                                df_pend = pl.read_parquet(caminho_riaf).to_pandas()
                            else:
                                df_pend = pd.DataFrame()
                            
                            if 'semestre' in df_pend.columns:
                                pend_set = set(df_pend['uni_codigo'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip() + "_" + df_pend['semestre'].astype(str).str.strip().str.replace('/', '-'))
                                df_ativos_riaf['UNI_CODIGO_STR'] = df_ativos_riaf['UNI_CODIGO'].astype(str).str.split('.').str[0].str.strip()
                                df_ativos_riaf['chave_ativos'] = df_ativos_riaf['UNI_CODIGO_STR'] + "_" + df_ativos_riaf['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
                                df_ativos_riaf = df_ativos_riaf[df_ativos_riaf['chave_ativos'].isin(pend_set) | df_ativos_riaf['UNI_CODIGO_STR'].isin(pend_set)]
                            else:
                                pend_list = df_pend['uni_codigo'].dropna().astype(str).str.replace(r'\.0$', '', regex=True).tolist()
                                df_ativos_riaf['UNI_CODIGO_STR'] = df_ativos_riaf['UNI_CODIGO'].astype(str).str.split('.').str[0].str.strip()
                                df_ativos_riaf = df_ativos_riaf[df_ativos_riaf['UNI_CODIGO_STR'].isin(pend_list)]
                        except Exception as e:
                            print(f"[GGCI       | ERRO          | RIAF  ] Falha ao filtrar pendentes: {e}")
                            df_ativos_riaf['UNI_CODIGO_STR'] = df_ativos_riaf['UNI_CODIGO'].astype(str).str.split('.').str[0].str.strip()
                            
                        df_ativos_riaf['chave_temp'] = list(zip(
                            df_ativos_riaf['UNI_CODIGO_STR'],
                            df_ativos_riaf['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
                        ))
                        df_ativos_riaf = df_ativos_riaf[~df_ativos_riaf['chave_temp'].isin(chaves_riaf_entregues)]

                        riaf_records = df_ativos_riaf.to_dict('records')
                        for row in riaf_records:
                            novo_ausente = {
                                'Status_IA': 'Ausente', 'Inscrição': row['UNI_CODIGO'], 
                                'Bolsista': limpar_texto_geral(row['UNI_NOME']), 'CPF': row['UNI_CPF'], 
                                'Semestre': row['SEMESTRE'], 'Faculdade': limpar_texto_geral(row['INS_NOME']), 
                                'Curso': limpar_texto_geral(row['CUR_NOME']), 'Documento Tipo': DOC_RIAF
                            }
                            for col_orig, col_dest in [
                                ('matricula', 'Matricula'), ('modalidade', 'modalidade'), 
                                ('email', 'E-mail'), ('telefone_1', 'Telefone 1'), ('telefone_2', 'Telefone 2'),
                                ('data_nascimento', 'Data nascimento'), ('periodo_atual', 'Período atual'),
                                ('periodo_quantidade', 'Período quantidade')
                            ]:
                                if col_orig in row and pd.notna(row[col_orig]):
                                    novo_ausente[col_dest] = row[col_orig]
                            novos_ausentes_riaf.append(novo_ausente)
                except: pass

            cronometrar_fim('pend montar ausentes riaf', _t_pend)

            if novos_ausentes_docs:
                df_docs = pd.concat([df_docs, converter_colunas_para_salvamento(pd.DataFrame(novos_ausentes_docs))], ignore_index=True)
                print(f"[GGCI       | INJETADOS     | DOCS  ] {len(novos_ausentes_docs)} ausentes.")
            if novos_ausentes_riaf:
                df_riaf = pd.concat([df_riaf, converter_colunas_para_salvamento(pd.DataFrame(novos_ausentes_riaf))], ignore_index=True)
                print(f"[GGCI       | INJETADOS     | RIAF  ] {len(novos_ausentes_riaf)} ausentes.")

            # ==========================================================================
            # A COBRANÇA QUE O SITE FAZ E NÃO DEVERIA — a fatia `Inadimplentes`.
            # ==========================================================================
            # As linhas acima são as pendências REAIS: alunos com repasse no semestre que
            # não entregaram o documento. Esta injeção é o avesso — o que o SIBU cobra sem
            # que houvesse repasse, e que portanto não é cobrável de ninguém.
            #
            # POR QUE PRECISA VIR DE UM ARQUIVO, e não de uma consulta: a regra do site não
            # deriva de nenhuma tabela de vínculo semestral. Medido em 2025-2, no histórico:
            # dos 6.555 documentos que a tela pede, 5.551 são de bolsistas que só existem a
            # partir de 2026 — 0 de 5.551 têm lançamento no semestre e 0 de 5.551 aparecem em
            # `id_coleta_documentos`. Três tentativas de reproduzir a lista em SQL falharam
            # (a melhor cobria 6.550 de 6.555 e trazia 10.549 a mais). A única fonte fiel é a
            # própria tela, que o extrator agora baixa pelo menu `Relatório de Contratos`.
            #
            # QUEM DECIDE é a coluna `Lançamento`, que vem do site: `Não` significa que não
            # houve repasse naquele semestre. O site tem esse dado e cobra assim mesmo.
            #
            # `Status_IA = Inadimplente` de propósito, e não um valor novo: as fórmulas do
            # relatório gerencial filtram `"<>INADIMPLENTE"`, então estas linhas aparecem nas
            # abas de dados e ficam FORA das somas de cobrança — que é exatamente o que se
            # quer de uma cobrança indevida. `Documento Ausente` as separa, no dashboard, do
            # inadimplente que entregou o documento.
            if os.path.exists(arq_cobranca_site):
                try:
                    df_cobranca = pd.read_parquet(arq_cobranca_site)
                    col_lancamento = next((c for c in df_cobranca.columns
                                           if c.strip().lower().startswith('lan')), None)
                    if col_lancamento is None:
                        raise KeyError("coluna de lançamento não encontrada no relatório do site")

                    sem_lancamento = (df_cobranca[col_lancamento].astype(str).str.strip()
                                      .str.upper().isin(['NÃO', 'NAO', 'N']))
                    df_indevidas = df_cobranca[sem_lancamento].copy()

                    # Quem JÁ ESTÁ no relatório sai daqui: a linha dele é a de verdade, com o
                    # documento e o veredito da IA. Sem esta checagem a mesma inscrição
                    # apareceria duas vezes no mesmo semestre e a rosca contaria em dobro.
                    ja_no_relatorio = set(zip(
                        df_docs['Inscrição'].astype(str).str.split('.').str[0].str.strip(),
                        df_docs['Semestre'].astype(str).str.strip().str.replace('/', '-'),
                        aplicar_por_distintos(df_docs['Documento Tipo'], limpar_texto_geral),
                    )) if not df_docs.empty else set()

                    # O CONSOLIDADOR NORMALIZA o texto das colunas (sem acento, maiúsculas),
                    # então o `Documento` chega como `HISTORICO ESCOLAR` e não bateria com o
                    # `DOC_HISTORICO` do sistema — a linha cairia numa aba que não existe.
                    # O mapa devolve a constante canônica, comparando pela forma normalizada.
                    doc_por_forma_limpa = {
                        limpar_texto_geral(d): d
                        for d in (DOC_CONTRATO, DOC_FINANC, DOC_BENEF, DOC_RIAF, DOC_HISTORICO)
                    }

                    novas_cobrancas = []
                    for row in df_indevidas.to_dict('records'):
                        semestre_row = str(row.get('Semestre', '')).strip().replace('/', '-')
                        documento_row = str(row.get('Documento', '')).strip()
                        inscricao_row = str(row.get('Inscrição', '')).split('.')[0].strip()
                        if not inscricao_row or not semestre_row or not documento_row:
                            continue
                        documento_canonico = doc_por_forma_limpa.get(limpar_texto_geral(documento_row))
                        if documento_canonico is None:
                            # Documento que este relatório não cobre: ignorar é mais seguro
                            # que inventar uma aba nova a partir de texto do site.
                            continue
                        if (inscricao_row, semestre_row, limpar_texto_geral(documento_row)) in ja_no_relatorio:
                            continue
                        novas_cobrancas.append({
                            'Status_IA': 'Inadimplente',
                            'Documento Ausente': 'SIM',
                            'Inscrição': inscricao_row,
                            'Semestre': semestre_row,
                            'Documento Tipo': documento_canonico,
                            'Bolsista': limpar_texto_geral(str(row.get('Beneficiário', ''))),
                            'CPF': row.get('CPF', ''),
                            'Faculdade': limpar_texto_geral(str(row.get('Instituição', ''))),
                        })

                    if novas_cobrancas:
                        df_docs = pd.concat(
                            [df_docs, converter_colunas_para_salvamento(pd.DataFrame(novas_cobrancas))],
                            ignore_index=True)
                        print(f"[GGCI       | INJETADOS     | COBRANÇA] {len(novas_cobrancas)} "
                              f"cobranças do site sem lançamento no semestre.")
                except Exception as erro_cobranca:
                    # Falhar aqui não pode derrubar o relatório: a fatia fica vazia e todo o
                    # resto continua correto. É informação adicional, não a base.
                    print(f"[GGCI       | AVISO         | COBRANÇA] Relatório do site não pôde "
                          f"ser cruzado: {erro_cobranca}")

    else:
        # Fallback caso não haja pagamentos mas seja necessário sql
        if not df_docs.empty or not df_riaf.empty:
            sem_docs = df_docs['Semestre'].dropna().unique().tolist() if not df_docs.empty else []
            sem_riaf = df_riaf['Semestre'].dropna().unique().tolist() if not df_riaf.empty else []
            semestres_presentes = list(set(sem_docs + sem_riaf))
            print("[GGCI       | CONEXAO       | SQL   ] Inicializando busca...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as db_executor:
                future_financas = db_executor.submit(buscar_dados_financeiros_sql, semestres_presentes)
                future_mes = db_executor.submit(buscar_dados_pagamentos_mes_a_mes_sql, semestres_presentes)
                df_financas = future_financas.result()
                df_mes_a_mes = future_mes.result()
            print("[GGCI       | SUCESSO       | SQL   ] Consultas finalizadas.")

    def gerar_checks_documentos(df_target, df_fin_map):
        if df_target.empty: return df_target
        
        df_target['KEY_TEMP'] = df_target['Inscrição'].astype(str) + "_" + df_target['Semestre'].astype(str)
        mapa_status = {}
        
        for doc_nome in [DOC_CONTRATO, DOC_FINANC, DOC_BENEF, DOC_RIAF, DOC_HISTORICO]:
            entregues = set(df_target[(df_target['Documento Tipo'] == doc_nome) & (~df_target['Status_IA'].isin(['Ausente', 'Ausentes']))]['KEY_TEMP'])
            mapa_status[doc_nome] = entregues

        uni_series = pd.to_numeric(df_target['Inscrição'].astype(str).str.split('.').str[0].str.strip(), errors='coerce')
        sem_series = df_target['Semestre'].astype(str).str.strip()
        
        def val_fin_map(row_uni, row_sem):
            try: return df_fin_map.get((int(row_uni), row_sem), {}).get('valor_financiamento', 0.0)
            except: return 0.0
            
        def val_ben_map(row_uni, row_sem):
            try: return df_fin_map.get((int(row_uni), row_sem), {}).get('valor_beneficio', 0.0)
            except: return 0.0

        val_fin_series = pd.Series([val_fin_map(u, s) for u, s in zip(uni_series, sem_series)], index=df_target.index)
        val_ben_series = pd.Series([val_ben_map(u, s) for u, s in zip(uni_series, sem_series)], index=df_target.index)
        
        df_target['Check Contrato'] = np.where(df_target['KEY_TEMP'].isin(mapa_status.get(DOC_CONTRATO, set())), "PRESENTE", "PENDENTE")
        df_target['Check Financiamento'] = np.where(val_fin_series <= 0.0, "N/A", np.where(df_target['KEY_TEMP'].isin(mapa_status.get(DOC_FINANC, set())), "PRESENTE", "PENDENTE"))
        df_target['Check Benefícios'] = np.where(val_ben_series <= 0.0, "N/A", np.where(df_target['KEY_TEMP'].isin(mapa_status.get(DOC_BENEF, set())), "PRESENTE", "PENDENTE"))
        
        ano_sem_num = pd.to_numeric(df_target['Semestre'].astype(str).str.split('-').str[0], errors='coerce').fillna(9999)
        df_target['Check RIAF'] = np.where(ano_sem_num < 2026, "N/A", np.where(df_target['KEY_TEMP'].isin(mapa_status.get(DOC_RIAF, set())), "PRESENTE", "PENDENTE"))
        
        df_target['Check Histórico'] = np.where(df_target['KEY_TEMP'].isin(mapa_status.get(DOC_HISTORICO, set())), "PRESENTE", "PENDENTE")
        
        doc_tipo = df_target.get('Documento Tipo', '')
        val_fin_num = pd.to_numeric(df_target.get('valor_financiamento', pd.Series(0.0, index=df_target.index)), errors='coerce').fillna(0.0)
        val_ben_num = pd.to_numeric(df_target.get('valor_beneficio', pd.Series(0.0, index=df_target.index)), errors='coerce').fillna(0.0)
        
        cond_fin = (doc_tipo == DOC_FINANC)
        cond_ben = (doc_tipo == DOC_BENEF)
        
        check_benef_doc = pd.Series("N/A", index=df_target.index)
        check_benef_doc = np.where(cond_fin, np.where(val_fin_num > 0, "SIM", "NÃO"), check_benef_doc)
        check_benef_doc = np.where(cond_ben, np.where(val_ben_num > 0, "SIM", "NÃO"), check_benef_doc)
        df_target['Check Doc beneficios'] = check_benef_doc
        
        df_target.drop(columns=['KEY_TEMP'], inplace=True)
        return df_target

    df_fin_map = {}
    if 'df_financas' in locals() and not df_financas.empty:
        df_fin_map = df_financas.set_index(['uni_codigo', 'semestre'])[['valor_financiamento', 'valor_beneficio']].to_dict('index')

    if not df_docs.empty:
        print("[GGCI       | AUDITORIA     | DOCS  ] Cruzando financeiro...")
        
        # O PRE-FILTRO de elegibilidade do HISTÓRICO ESCOLAR foi removido a pedido do dono do
        # projeto — "o espelho deve mostrar todos, mesmo sem pagamento". O que sobrou aqui era
        # o cálculo inteiro sem o filtro: duas colunas temporárias sobre as ~167 mil linhas do
        # df_docs, um merge completo e uma máscara, tudo descartado no drop da linha seguinte.
        # A única consequência que o merge deixava era reindexar o df_docs, e é isso que o
        # reset_index preserva.
        if 'df_financas' in locals() and not df_financas.empty:
            df_docs = df_docs.reset_index(drop=True)

        if not df_docs.empty:
            with cronometrar('docs mesclar_sql'):
                df_docs = mesclar_sql_e_reordenar(df_docs, df_financas, df_pag, df_mes_a_mes)
            with cronometrar('docs transicoes'):
                df_docs = aplicar_transicoes(df_docs, df_pag)
            with cronometrar('docs auditoria_ia'):
                df_docs = calcular_auditoria_ia(df_docs)
            with cronometrar('docs checks'):
                df_docs = gerar_checks_documentos(df_docs, df_fin_map)
        
    if not df_riaf.empty:
        print("[GGCI       | AUDITORIA     | RIAF  ] Cruzando financeiro...")
        
        # Mesmo caso do bloco de documentos acima: o PRE-FILTRO de elegibilidade foi removido a
        # pedido do dono do projeto e sobrou só o custo. ATENÇÃO ao que NÃO pode sair daqui — a
        # normalização de 'Semestre' ('2026/1' -> '2026-1') é permanente, essa coluna não era
        # descartada e alimenta o relatório inteiro. Ela fica; o merge e a coluna auxiliar saem.
        if 'df_financas' in locals() and not df_financas.empty:
            df_riaf['Semestre'] = df_riaf['Semestre'].astype(str).str.strip().str.replace('/', '-')
            df_riaf = df_riaf.reset_index(drop=True)

        if not df_riaf.empty:
            with cronometrar('riaf mesclar_sql'):
                df_riaf = mesclar_sql_e_reordenar(df_riaf, df_financas, df_pag, df_mes_a_mes)
            with cronometrar('riaf transicoes'):
                df_riaf = aplicar_transicoes(df_riaf, df_pag)
            with cronometrar('riaf auditoria_ia'):
                df_riaf = calcular_auditoria_ia(df_riaf)
            with cronometrar('riaf checks'):
                df_riaf = gerar_checks_documentos(df_riaf, df_fin_map)

    # REGRA: Ignorar Inadimplentes nos Relatórios (Descartados)
    if not df_docs.empty and 'Status_IA' in df_docs.columns:
        df_docs = recalcular_bolsas_ia(df_docs, is_riaf=False)
        # df_docs = df_docs[df_docs['Status_IA'].astype(str).str.upper() != 'INADIMPLENTE'].copy()
        
    if not df_riaf.empty and 'Status_IA' in df_riaf.columns:
        df_riaf = recalcular_bolsas_ia(df_riaf, is_riaf=True)
        # df_riaf = df_riaf[df_riaf['Status_IA'].astype(str).str.upper() != 'INADIMPLENTE'].copy()


    for df_target in [df_docs, df_riaf]:
        if not df_target.empty:
            if 'Data_Processamento_Agendar' in df_target.columns:
                if 'Data Processamento' in df_target.columns:
                    df_target['Data Processamento'] = df_target['Data_Processamento_Agendar'].replace(['', None], np.nan).fillna(df_target['Data Processamento'])
                else:
                    df_target['Data Processamento'] = df_target['Data_Processamento_Agendar']
                df_target.drop(columns=['Data_Processamento_Agendar'], inplace=True)
            
            # --- Formatações Específicas Solicitadas ---
            if 'Matricula' in df_target.columns:
                # Remove letras, símbolos e zeros à esquerda
                mat_str = df_target['Matricula'].astype(str).str.replace(r'\.0$', '', regex=True).str.replace(r'[^\d]', '', regex=True).str.lstrip('0')
                # Verifica numérico e se é > 0
                mat_num = pd.to_numeric(mat_str, errors='coerce').fillna(0)
                df_target['Matricula'] = np.where((mat_num > 0) & (mat_str != ''), mat_str, '-')    
            
            if 'Data Processamento' in df_target.columns: 
                df_target['Data Processamento'] = df_target['Data Processamento'].fillna('')
            
            colunas_remover = ['situacao', 'situacao_atual_sistema', 
                               'sit_data_atual_sistema', 'sit_obs_atual_sistema', 'soma_cd_sem_desconto', 'soma_cd_com_desconto',
                               'Coleta ID', 'Tipo Bolsa', 'Valor Financiamentos', 'Valor Beneficios', 'Ins. Razão Social']
            df_target.drop(columns=colunas_remover, inplace=True, errors='ignore')

            if 'Ins. Cnpj' in df_target.columns:
                # Remove '.0' se o pandas tiver convertido para float
                df_target['Ins. Cnpj'] = df_target['Ins. Cnpj'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
            
            if 'Data nascimento' in df_target.columns:
                # Transforma para dt e formata ignorando horas
                df_target['Data nascimento'] = pd.to_datetime(df_target['Data nascimento'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                


    if not df_docs.empty or not df_riaf.empty or gerar_relatorio_riaf or gerar_relatorio:
        print(f"[GGCI       | RELATORIO     | GERAL ] Finalizando...")
        os.makedirs(base_dir, exist_ok=True)
        # No modo CSV não existe workbook: antes o writer era aberto de qualquer jeito e nunca
        # fechado, deixando um relatorio_geral.xlsx vazio no disco e o handle pendurado.
        writer = None
        if formato not in ("CSV", "PARQUET"):
            writer = pd.ExcelWriter(arquivo_geral_saida, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_formulas': False}})
        
        # 1. Master Resumo para pagamentos e quantitativo
        df_master_resumo = pd.DataFrame()
        if not df_docs.empty and not df_riaf.empty:
            df_master_resumo = pd.concat([df_docs, df_riaf], ignore_index=True)
        elif not df_docs.empty:
            df_master_resumo = df_docs.copy()
        elif not df_riaf.empty:
            df_master_resumo = df_riaf.copy()
            
        tipos_resumo = {}
        if check_contrato: tipos_resumo['CONTRATO'] = DOC_CONTRATO
        if check_financ: tipos_resumo['FINANCIAMENTO'] = DOC_FINANC
        if check_benef: tipos_resumo['BENEFÍCIOS'] = DOC_BENEF
        if check_riaf: tipos_resumo['RIAF'] = DOC_RIAF
        if check_historico: tipos_resumo['HISTÓRICO'] = DOC_HISTORICO

        # Processar Pagamentos (só cálculos por enquanto)
        # `gerar_pagamentos` entra na condição de propósito: df_pag_filt só alimenta as abas
        # Pagamentos. Sem a flag, este enriquecimento de
        # ~331 mil linhas era calculado e jogado fora.
        df_pag_filt = pd.DataFrame()
        if gerar_pagamentos and df_pag is not None and not df_pag.empty:
            _t_pag = time.perf_counter()
            inscricoes_relatorio = pd.to_numeric(df_master_resumo['Inscrição'], errors='coerce').dropna().astype('Int64').unique()
            df_pag_filt = df_pag.copy()
            df_pag_filt['UNI_CODIGO'] = pd.to_numeric(df_pag_filt['UNI_CODIGO'], errors='coerce').astype('Int64')
            df_pag_filt = df_pag_filt[df_pag_filt['UNI_CODIGO'].isin(inscricoes_relatorio)]
            
            if 'DATA_LANCAMENTO' in df_pag_filt.columns:
                df_pag_filt['DATA_ORDEM'] = pd.to_datetime(df_pag_filt['DATA_LANCAMENTO'], dayfirst=True, errors='coerce')
                df_pag_filt['DATA_ORDEM_NORM'] = df_pag_filt['DATA_ORDEM'].dt.normalize()
                df_pag_filt.sort_values(by=['UNI_CODIGO', 'SEMESTRE', 'DATA_ORDEM'], inplace=True)

            if 'df_mes_a_mes' in locals() and not df_mes_a_mes.empty:
                if 'DATA_LANCAMENTO' in df_pag_filt.columns:
                    df_pag_filt['sub_idx'] = df_pag_filt.groupby(['UNI_CODIGO', 'SEMESTRE', 'DATA_ORDEM_NORM']).cumcount()
                    
                    df_mes_a_mes['DATA_ORDEM_DB'] = pd.to_datetime(df_mes_a_mes['lan_dtlanc'], errors='coerce')
                    df_mes_a_mes['DATA_ORDEM_DB_NORM'] = df_mes_a_mes['DATA_ORDEM_DB'].dt.normalize()
                    df_mes_a_mes.sort_values(by=['uni_codigo', 'semestre', 'DATA_ORDEM_DB', 'lan_anomes'], inplace=True)
                    df_mes_a_mes['sub_idx'] = df_mes_a_mes.groupby(['uni_codigo', 'semestre', 'DATA_ORDEM_DB_NORM']).cumcount()
                    
                    df_pag_filt = pd.merge(
                        df_pag_filt, 
                        df_mes_a_mes[['uni_codigo', 'semestre', 'DATA_ORDEM_DB_NORM', 'sub_idx', 'lan_anomes', 'CD_sem_desconto', 'CD_com_desconto', 'CD_beneficios', 'CD_financiamentos', 'data_coleta']],
                        left_on=['UNI_CODIGO', 'SEMESTRE', 'DATA_ORDEM_NORM', 'sub_idx'],
                        right_on=['uni_codigo', 'semestre', 'DATA_ORDEM_DB_NORM', 'sub_idx'],
                        how='left'
                    )
                    df_pag_filt.drop(columns=['uni_codigo', 'semestre', 'sub_idx', 'DATA_ORDEM', 'DATA_ORDEM_NORM', 'DATA_ORDEM_DB', 'DATA_ORDEM_DB_NORM'], errors='ignore', inplace=True)
                else:
                    df_pag_filt['row_idx'] = df_pag_filt.groupby(['UNI_CODIGO', 'SEMESTRE']).cumcount()
                    df_mes_a_mes['DATA_ORDEM_DB'] = pd.to_datetime(df_mes_a_mes['lan_dtlanc'], errors='coerce')
                    df_mes_a_mes.sort_values(by=['uni_codigo', 'semestre', 'DATA_ORDEM_DB', 'lan_anomes'], inplace=True)
                    df_mes_a_mes['row_idx'] = df_mes_a_mes.groupby(['uni_codigo', 'semestre']).cumcount()
                    
                    df_pag_filt = pd.merge(
                        df_pag_filt, 
                        df_mes_a_mes[['uni_codigo', 'semestre', 'row_idx', 'lan_anomes', 'CD_sem_desconto', 'CD_com_desconto', 'CD_beneficios', 'CD_financiamentos', 'data_coleta']],
                        left_on=['UNI_CODIGO', 'SEMESTRE', 'row_idx'],
                        right_on=['uni_codigo', 'semestre', 'row_idx'],
                        how='left'
                    )
                    df_pag_filt.drop(columns=['uni_codigo', 'semestre', 'row_idx', 'DATA_ORDEM', 'DATA_ORDEM_DB'], errors='ignore', inplace=True)
            
            if 'DATA_LANCAMENTO' in df_pag_filt.columns:
                df_pag_filt['DATA_LANCAMENTO'] = pd.to_datetime(df_pag_filt['DATA_LANCAMENTO'], dayfirst=True, errors='coerce').dt.strftime('%d/%m/%Y')
            if 'data_coleta' in df_pag_filt.columns:
                df_pag_filt['data_coleta'] = pd.to_datetime(df_pag_filt['data_coleta'], errors='coerce').dt.strftime('%d/%m/%Y')
                
            cols_remover_pag = ['VALOR_CONTRATO_APURADO', 'FAIXA', 'TIPO_BOLSISTA']
            df_pag_filt.drop(columns=cols_remover_pag, inplace=True, errors='ignore')
            
            if 'tipo_bolsa_final' in df_master_resumo.columns:
                mapa_bolsa = df_master_resumo.drop_duplicates(subset=['Inscrição']).set_index('Inscrição')['tipo_bolsa_final']
                df_pag_filt['TIPO_BOLSA'] = df_pag_filt['UNI_CODIGO'].map(mapa_bolsa).fillna("SEM DADOS").str.upper()

            if 'INS_NOME' in df_pag_filt.columns:
                # 310 mil linhas para ~105 IES distintas: ver aplicar_por_distintos.
                df_pag_filt['INS_NOME'] = aplicar_por_distintos(df_pag_filt['INS_NOME'], padronizar_ies)
                df_pag_filt['MANTENEDORA'] = aplicar_por_distintos(df_pag_filt['INS_NOME'], buscar_mantenedora)
                
            if 'lan_anomes' in df_pag_filt.columns:
                meses_map = {
                    '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
                    '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
                    '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez'
                }
                def formatar_mes(val):
                    if pd.isna(val) or val == "": return ""
                    val_str = str(val).split('.')[0].strip()
                    if len(val_str) >= 6 and val_str[:4].isdigit() and val_str[4:6].isdigit():
                        return meses_map.get(val_str[4:6], val_str)
                    return val_str
                df_pag_filt['lan_anomes'] = aplicar_por_distintos(df_pag_filt['lan_anomes'], formatar_mes)
                df_pag_filt.rename(columns={'lan_anomes': 'Mês de Pagamento'}, inplace=True)
                
            cols = list(df_pag_filt.columns)
            if 'MANTENEDORA' in cols and 'CID_NOME' in cols:
                cols.remove('MANTENEDORA')
                idx_cid = cols.index('CID_NOME')
                cols.insert(idx_cid + 1, 'MANTENEDORA')
                
            if 'TIPO_BOLSA' in cols:
                cols.remove('TIPO_BOLSA')
                cols.insert(1, 'TIPO_BOLSA')
                
            df_pag_filt = df_pag_filt[cols]
            padronizar_rotulo_outros(df_pag_filt, ['desc_outro_beneficio', 'desc_financiamento'])
            cronometrar_fim('preparar pagamentos', _t_pag)

        # Gerar Resumo Quantitativo (só cálculos por enquanto)
        # Mesmo raciocínio do bloco de Pagamentos: df_resumo_geral só alimenta a aba
        # 'Envios & Pendências'. Os relatórios Contratos/RIAF não o consomem — e já ficam
        # bloqueados quando gerar_quantitativo é False (ver pode_gerar_relatorio acima).
        df_resumo_geral = pd.DataFrame()
        if gerar_quantitativo:
            with cronometrar('resumo quantitativo'):
                df_resumo_geral = gerar_resumo_quantitativo(df_master_resumo, tipos_resumo)


        # --- LIMPEZA DE COLUNAS LIXO (APENAS AS SOLICITADAS PELO USUÁRIO) ---
        colunas_do_relatorio = [
            'Status_IA', 'Status_Vínculo', 'Situação do Motivo', 'Observação da Situação', 'Mudou IES?',
            'IES Anterior', 'IES Posterior', 'Mudou Bolsa?', 'Bolsa Anterior', 'Bolsa Posterior',
            'Semestre', 'Gemini Semestre', 'Inscrição', 'Inscrição Anterior', 'Inscrição Posterior',
            'Bolsista', 'CPF', 'Gemini CPF', 'Gemini Inconsistencias', 'Faculdade', 'Curso',
            'tipo_bolsa_final', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'último_valor_pago_referencia',
            'total bolsa paga', 'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Dif. s/Desc.',
            '% Dif. s/Desc.', 'Total Dif. s/Desc.', 'MSD_SOMA', 'G_MSD_SOMA', 'MSD_DOC',
            'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Dif. c/Desc.', '% Dif. c/Desc.',
            'Total Dif. c/Desc.', 'MCD_SOMA', 'G_MCD_SOMA', 'MCD_DOC', 'Gemini Matricula Sem Desconto',
            'Matricula_SD_Doc', 'Gemini Matricula Com Desconto', 'Matricula_CD_Doc',
            'OVG Pagou (Último Referencial)', 'OVG Deveria Pagar (Último Referencial)',
            'Soma OVG Pagou', 'Soma OVG Deveria Pagar (Sistema)', 'OVG Deveria Pagar (IA)',
            'Soma OVG Deveria Pagar (IA)', 'Prejuízo da OVG (R$)', 'Soma Prejuízo da OVG (R$)',
            'Economia da OVG (R$)', 'Diagnóstico Financeiro Final', 'valor_beneficio',
            'Soma Valor Beneficio', 'qual_beneficio', 'valor_financiamento', 'Soma Valor Financiamento',
            'qual_financiamento', 'data_coleta', 'Documento Tipo', 'Data Processamento', 'uni_deficiencia',
            'uni_sexo', 'Gemini Matricula', 'Gemini Nome Faculdade', 'Gemini Curso', 'Gemini Razao Social',
            'Gemini Cnpj Faculdade', 'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies',
            'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 'Gemini Nome Financiamento',
            'Gemini Modalidade', 'Gemini Email', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos',
            'Gemini Tipo Bolsa', 'Data nascimento', 'E-mail', 'Telefone 1', 'Telefone 2', 'Período atual',
            'Período quantidade', 'Matricula', 'Ins. Cnpj', 'Ins. Nome Fantasia', 'Ins. Mantenedora',
            'Modalidade', 'Matricula C/ Desconto', 'Matricula S/ Desconto', 'data_create', 'Processado',
            'Documento Ausente',
            'Veredito Documento',
            'Qtde Token', 'gemini_vigencia', 'gemini_clausulas', 'gemini_recisao', 'gemini_cnpj_mantenedora',
            'gemini_documentos_beneficio', 'gemini_cnpj_banco', 'gemini_numero', 'gemini_numero_semestres',
            'gemini_semestres_feitos', 'gemini_semestres_financiados', 'gemini_valor_limite_credito',
            'gemini_valor_semestralidade', 'gemini_valor_coparticipacao', 'Processar', 'gemini_concluiu_curso',
            'data_coleta_atual_sistema', 'inscricao_ano_semestre', 'data_ingresso', 'Check Contrato',
            'Check Financiamento', 'Check Benefícios', 'Check RIAF', 'Check Histórico', 'Check Doc beneficios',
            'Duração Total Semestres', 'Qtd Disciplinas Matriculadas', 'Qtd Disciplinas Reprovadas', 'Perfil do Beneficiario'
        ]
        
        # Mapeamento case-insensitive e trim
        colunas_do_relatorio_por_chave = {c.strip().lower(): c for c in colunas_do_relatorio}
        
        def selecionar_colunas_do_relatorio(df_entrada):
            cols_to_keep = []
            for col in df_entrada.columns:
                col_limpa = str(col).strip().lower()
                if col_limpa in colunas_do_relatorio_por_chave or col in colunas_do_relatorio:
                    cols_to_keep.append(col)
            
            cols_ordenadas = []
            for col_pedida in colunas_do_relatorio:
                for col_real in cols_to_keep:
                    if str(col_real).strip().lower() == col_pedida.strip().lower():
                        cols_ordenadas.append(col_real)
                        break
            
            for c in cols_to_keep:
                if c not in cols_ordenadas: cols_ordenadas.append(c)
                
            cols_ordenadas_limpas = []
            cols_ordenadas_lower = set()
            for c in cols_ordenadas:
                c_low = str(c).strip().lower()
                if c_low not in cols_ordenadas_lower:
                    cols_ordenadas_limpas.append(c)
                    cols_ordenadas_lower.add(c_low)
                    
            return df_entrada[cols_ordenadas_limpas]
        if not df_docs.empty: df_docs = selecionar_colunas_do_relatorio(df_docs)
        if not df_riaf.empty: df_riaf = selecionar_colunas_do_relatorio(df_riaf)
        # Nomes internos -> nomes finais das colunas do relatório.
        mapa_colunas_padrao = {
            'Documento Tipo': 'tipo_documento',
            'Status_IA': 'status_ia',
            'Gemini Inconsistencias': 'gemini_inconsistencia',
            'Bolsista': 'bolsista',
            'CPF': 'cpf',
            'Gemini CPF': 'gemini_cpf',
            'E-mail': 'email',
            'Gemini Email': 'gemini_email',
            'Telefone 1': 'telefone_1',
            'Telefone 2': 'telefone_2',
            'Gemini Telefone': 'gemini_telefone',
            'Data nascimento': 'data_nascimento',
            'uni sexo': 'uni_sexo',
            'uni_deficiencia': 'uni_deficiencia',
            'Gemini Assinatura Aluno': 'gemini_assinatura_aluno',
            'Faculdade': 'faculdade',
            'Gemini Nome Faculdade': 'gemini_nome_faculdade',
            'Curso': 'curso',
            'Gemini Curso': 'gemini_curso',
            'Ins. CNPJ': 'ins_cnpj',
            'Gemini Cnpj Faculdade': 'gemini_cnpj_faculdade',
            'Ins. Nome Fantasia': 'ins_nome_fantasia',
            'Gemini Razao Social': 'gemini_razao_social',
            'Ins. Mantenedora': 'ins_mantenedora',
            'Gemini Nome Mantenedora': 'gemini_nome_mantenedora',
            'gemini_cnpj_mantenedora': 'gemini_cnpj_mantenedora',
            'Gemini Assinatura Ies': 'gemini_assinatura_ies',
            'Status_Vínculo': 'status_vinculo',
            'Situação do Motivo': 'situacao_motivo',
            'Observação da Situação': 'observacao_situacao',
            'IES Anterior': 'ies_anterior',
            'IES Posterior': 'ies_posterior',
            'Mudou IES?': 'mudou_ies',
            'Matricula': 'matricula',
            'Gemini Matricula': 'gemini_matricula',
            'Semestre': 'semestre',
            'Gemini Semestre': 'gemini_semestre',
            'Período atual': 'periodo_atual',
            'Gemini Período': 'gemini_periodo',
            'Período quantidade': 'qtd_periodos',
            'Gemini Quantidade Periodos': 'gemini_qtd_periodos',
            'gemini_numero_semestres': 'gemini_numero_semestres',
            'gemini_semestres_feitos': 'gemini_semestres_feitos',
            'gemini_concluiu_curso': 'gemini_concluiu_curso',
            'Inscrição': 'inscricao',
            'inscricao_ano_semestre': 'inscricao_ano_semestre',
            'Inscrição Anterior': 'inscricao_anterior',
            'Inscrição Posterior': 'inscricao_posterior',
            'data ingresso': 'data_ingresso',
            'Mudou Bolsa?': 'mudou_bolsa',
            'Bolsa Anterior': 'bolsa_anterior',
            'Bolsa Posterior': 'bolsa_posterior',
            'tipo_bolsa_final': 'tipo_bolsa_final',
            'Gemini Tipo Bolsa': 'gemini_tipo_bolsa',
            'Modalidade': 'modalidade',
            'Gemini Modalidade': 'gemini_modalidade',
            'qual_beneficio': 'qual_beneficio',
            'Gemini Beneficio Nome': 'gemini_nome_beneficio',
            'valor_beneficio': 'valor_beneficio',
            'Gemini Valor Beneficio': 'gemini_valor_beneficio',
            'Soma Valor Beneficio': 'soma_valor_beneficio',
            'qual_financiamento': 'qual_financiamento',
            'Gemini Nome Financiamento': 'gemini_nome_financiamento',
            'valor_financiamento': 'valor_financiamento',
            'Gemini Valor Financiado': 'gemini_valor_financiamento',
            'Soma Valor Financiamento': 'soma_valor_financiamento',
            'gemini_semestres_financiados': 'gemini_semestres_financiados',
            'gemini_valor_limite_credito': 'gemini_valor_limite_credito',
            'gemini_valor_semestralidade': 'gemini_valor_semestralidade',
            'gemini_valor_coparticipacao': 'gemini_valor_coparticipacao',
            'Matricula S/ Desconto': 'matricula_sem_desc',
            'Gemini Matricula Sem Desconto': 'gemini_matricula_sem_desc',
            'Matricula_SD_Doc': 'matricula_sd_doc',
            'Matricula C/ Desconto': 'matricula_com_desc',
            'Gemini Matricula Com Desconto': 'gemini_matricula_com_desc',
            'Matricula_CD_Doc': 'matricula_cd_doc',
            'Mensalidade S/ Desconto': 'mensalidade_sem_desc',
            'Gemini Mensalidade S/ Desconto': 'gemini_mensalidade_sem_desc',
            'MSD_DOC': 'msd_doc',
            'Mensalidade C/ Desconto': 'mensalidade_com_desc',
            'Gemini Mensalidade C/ Desconto': 'gemini_mensalidade_com_desc',
            'MCD_DOC': 'mcd_doc',
            'total bolsa paga': 'total_bolsa_paga',
            'qtd_pagtos': 'qtd_pagtos',
            'qtd_pagtos_retroativos': 'qtd_pagtos_retroativos',
            'último_valor_pago_referencia': 'ultimo_valor_pago_ref',
            'OVG Pagou (Último Referencial)': 'ovg_pagou_ult_ref',
            'Soma OVG Pagou': 'soma_ovg_pagou',
            'OVG Deveria Pagar (Último Referencial)': 'ovg_devia_pagar_ult_ref',
            'Soma OVG Deveria Pagar (Sistema)': 'soma_ovg_devia_pagar_sis',
            'OVG Deveria Pagar (IA)': 'ovg_devia_pagar_ia',
            'Soma OVG Deveria Pagar (IA)': 'soma_ovg_devia_pagar_ia',
            'Prejuízo da OVG (R$)': 'prejuizo_ovg',
            'Soma Prejuízo da OVG (R$)': 'soma_prejuizo_ovg',
            'Economia da OVG (R$)': 'economia_ovg',
            'Diagnóstico Financeiro Final': 'diagnostico_financeiro_final',
            'Check Contrato': 'check_contrato',
            'Check Financiamento': 'check_financiamento',
            'Check Benefícios': 'check_beneficios',
            'Check RIAF': 'check_riaf',
            'Check Histórico': 'check_historico',
            'Check Doc beneficios': 'check_doc_beneficios',
            'data_coleta': 'data_coleta',
            'data_coleta_atual_sistema': 'data_coleta_atual_sistema',
            'data_create': 'data_create',
            'Data Processamento': 'data_processamento',
            'Processado': 'processado',
            'Documento Ausente': 'documento_ausente',
            'Veredito Documento': 'veredito_documento',
            'Processar': 'processar',
            'Qtde Token': 'qtd_token',
            'Qtd Disciplinas Matriculadas': 'qtd_disciplinas_matriculadas',
            'Qtd Disciplinas Reprovadas': 'qtd_disciplinas_reprovadas',
            'Perfil do Beneficiario': 'perfil',
        }
        ordem_finais = COLUNAS_ABA_DOCUMENTO

        if not df_docs.empty:
            df_docs = df_docs.rename(columns=mapa_colunas_padrao)
            df_docs['beneficio'] = df_docs['qual_beneficio'] if 'qual_beneficio' in df_docs.columns else '-'
            df_docs['financiamento'] = df_docs['qual_financiamento'] if 'qual_financiamento' in df_docs.columns else '-'
            df_docs = df_docs.rename(columns={'economia_ovg': 'soma_economia_ovg'})
            
            for col_tel in ['telefone_1', 'telefone_2']:
                if col_tel in df_docs.columns:
                    s_nums = df_docs[col_tel].astype(str).str.replace(r'\D', '', regex=True)
                    df_docs[col_tel] = pd.to_numeric(s_nums, errors='coerce').astype('Int64')
                    
            colunas_finais_docs = [c for c in ordem_finais if c in df_docs.columns]
            df_docs = df_docs[colunas_finais_docs]

        if not df_riaf.empty:
            df_riaf = df_riaf.rename(columns=mapa_colunas_padrao)
            df_riaf['beneficio'] = df_riaf['qual_beneficio'] if 'qual_beneficio' in df_riaf.columns else '-'
            df_riaf['financiamento'] = df_riaf['qual_financiamento'] if 'qual_financiamento' in df_riaf.columns else '-'
            df_riaf = df_riaf.rename(columns={
                'economia_ovg': 'soma_economia_ovg',
                'ins_cnpj': 'cnpj_ies',
                'gemini_tipo_bolsa': 'gemini_tipo_bolsa_final'
            })
            
            for col_tel in ['telefone_1', 'telefone_2']:
                if col_tel in df_riaf.columns:
                    s_nums = df_riaf[col_tel].astype(str).str.replace(r'\D', '', regex=True)
                    df_riaf[col_tel] = pd.to_numeric(s_nums, errors='coerce').astype('Int64')
                    
            colunas_riaf = [
                'status_ia', 'gemini_inconsistencia', 'semestre', 'gemini_semestre', 'bolsista', 
                'inscricao', 'inscricao_anterior', 'inscricao_posterior', 'cpf', 'gemini_cpf', 
                'tipo_bolsa_final', 'gemini_tipo_bolsa_final', 'mudou_bolsa', 'bolsa_anterior', 
                'bolsa_posterior', 'faculdade', 'cnpj_ies', 'mudou_ies', 'ies_anterior', 'ies_posterior', 
                'curso', 'gemini_assinatura_aluno', 'gemini_assinatura_ies', 'ultimo_valor_pago_ref', 
                'total_bolsa_paga', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'matricula_sem_desc', 
                'gemini_matricula_sem_desc', 'matricula_sd_doc', 'matricula_com_desc', 
                'gemini_matricula_com_desc', 'matricula_cd_doc', 'mensalidade_sem_desc', 
                'gemini_mensalidade_sem_desc', 'msd_doc', 'mensalidade_com_desc', 
                'gemini_mensalidade_com_desc', 'mcd_doc', 'valor_beneficio', 'soma_valor_beneficio', 
                'gemini_valor_beneficio', 'beneficio', 'valor_financiamento', 'soma_valor_financiamento', 
                'gemini_valor_financiamento', 'financiamento', 
                'soma_ovg_devia_pagar_sis', 'soma_ovg_devia_pagar_ia', 'soma_prejuizo_ovg', 
                'soma_economia_ovg', 'diagnostico_financeiro_final', 'data_coleta', 
                'data_coleta_atual_sistema', 'data_create', 'data_processamento', 'processado', 
                'processar', 'qtd_token', 'qtd_disciplinas_matriculadas', 'qtd_disciplinas_reprovadas', 
                'perfil', 'status_vinculo', 'situacao_motivo', 'observacao_situacao', 'email', 
                'gemini_email', 'telefone_1', 'telefone_2', 'data_nascimento', 'matricula', 
                'periodo_atual', 'qtd_periodos', 'modalidade', 'documento_ausente', 'veredito_documento'
            ]
            
            for c in colunas_riaf:
                if c not in df_riaf.columns:
                    df_riaf[c] = None
                    
            df_riaf = df_riaf[colunas_riaf]

        
        # --- FORÇAR FORMATAÇÃO DE DATAS COMO TEXTO PARA MANTER ALINHAMENTO ---
        if not df_docs.empty: df_docs = df_docs.copy()
        if not df_riaf.empty: df_riaf = df_riaf.copy()
        for df_saida in [df_docs, df_riaf]:
            if not df_saida.empty:
                for col in ['data_coleta', 'data_coleta_atual_sistema', 'data_create', 'data_processamento']:
                    if col in df_saida.columns:
                        if col in ['data_coleta', 'data_coleta_atual_sistema']:
                            df_saida[col] = pd.to_datetime(df_saida[col], errors='coerce', dayfirst=True).dt.strftime('%d/%m/%Y').fillna('-')
                        else:
                            df_saida[col] = pd.to_datetime(df_saida[col], errors='coerce', dayfirst=True).dt.strftime('%d/%m/%Y %H:%M:%S').fillna('-')
                
                if 'data_nascimento' in df_saida.columns:
                    df_saida['data_nascimento'] = df_saida['data_nascimento'].replace(['-', 'Não informado'], pd.NA)

                for c_clean in ['telefone_1', 'telefone_2', 'matricula', 'inscricao', 'inscricao_anterior', 'inscricao_posterior']:
                    if c_clean in df_saida.columns:
                        df_saida[c_clean] = pd.to_numeric(df_saida[c_clean].astype(str).str.replace(r'\D', '', regex=True), errors='coerce').astype('Int64').astype(object).fillna('-')

                for c_num in ['gemini_mensalidade_com_desc', 'gemini_mensalidade_sem_desc', 'gemini_valor_beneficio', 'gemini_valor_financiamento']:
                    if c_num in df_saida.columns:
                        df_saida[c_num] = pd.to_numeric(df_saida[c_num], errors='coerce').fillna(0.0)
        

        with cronometrar('title case final'):
            if not df_docs.empty: df_docs = remover_caixa_alta_df(df_docs)
            if not df_riaf.empty: df_riaf = remover_caixa_alta_df(df_riaf)
            if not df_resumo_geral.empty: df_resumo_geral = remover_caixa_alta_df(df_resumo_geral)
        
        # --- MONTAR AS ABAS DE DADOS (FONTE ÚNICA PARA XLSX E CSV) ---
        # O ZIP de CSV tem que ser o mesmo conteúdo do XLSX, aba por aba: mesmas colunas, na
        # mesma ordem, com as mesmas linhas na mesma ordem e o mesmo Title Case. Antes cada
        # formato preparava os DataFrames por conta própria e os dois tinham divergido — o CSV
        # mantinha `tipo_documento`, ordenava sem o semestre e não normalizava Pagamentos.
        # Ficam fora daqui só as abas com fórmula do Excel (Relatório Contratos / Relatório
        # RIAF e suas Aux_IES_*), que não têm equivalente em CSV.
        COLS_CHECK = [
            'check_contrato', 'check_financiamento', 'check_beneficios', 'check_riaf',
            'check_historico', 'check_doc_beneficios', 'Check Contrato', 'Check Financiamento',
            'Check Benefícios', 'Check RIAF', 'Check Histórico', 'Check Doc beneficios'
        ]
        AVISO_VAZIO = "Nenhum documento encontrado ou processado para este tipo"

        def ordenar_para_saida(df):
            """Ordena por faculdade/semestre/bolsista, ignorando caixa (ordem oficial das abas)."""
            candidatas = (['faculdade', 'semestre', 'bolsista'] if 'faculdade' in df.columns
                          else ['Faculdade', 'Semestre', 'Bolsista'])
            cols = [c for c in candidatas if c in df.columns]
            if cols:
                df.sort_values(by=cols, key=lambda col: col.astype(str).str.lower(), inplace=True)
            return df

        def preparar_aba_pagamentos():
            """
            Aba Pagamentos. Prefere o df_pag_filt enriquecido; se não houver, cai no Parquet
            fiel do SQL. Devolve None quando não há nada a escrever.
            """
            def finalizar(df):
                if 'origem_dado' in df.columns:
                    df = df[df['origem_dado'] == '1_REALIZADO']
                    df = df.drop(columns=['origem_dado'])
                for col in ['lan_dtlanc', 'LAN_DTLANC']:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                df = remover_caixa_alta_df(df)
                cols_ordem = []
                for c in ['codigo_aluno', 'semestre_referencia_analise', 'ano_mes_pagto']:
                    if c in df.columns: cols_ordem.append(c)
                    elif c.upper() in df.columns: cols_ordem.append(c.upper())
                if cols_ordem:
                    df.sort_values(by=cols_ordem, inplace=True)
                return df

            if df_pag is not None and not df_pag.empty:
                print(f"[GGCI       | GERANDO       | PAGTO ] Enriquecida...")
                return finalizar(df_pag_filt.copy())

            print(f"[GGCI       | GERANDO       | PAGTO ] Via SQL (100% Fiel)...")
            try:
                caminho = os.path.join(PROJECT_ROOT, f"apps/dashboards/dash_documentos_ia/dados/tabelas_sql/PY_ggci_coleta_de_dados_pagamentos_temp_d1{SUFIXO_TABELAS}.parquet")
                if not os.path.exists(caminho):
                    return None
                df_fiel = pl.read_parquet(caminho).filter(
                    pl.col("semestre_referencia_analise").is_in([str(x).strip().replace('-', '/') for x in sems_alvo])
                ).to_pandas()
                if df_fiel.empty:
                    return None
                padronizar_rotulo_outros(df_fiel, ['desc_outro_beneficio', 'desc_financiamento'])
                return finalizar(df_fiel)
            except Exception as e:
                print(f"Erro ao carregar Pagamentos Fiel: {e}")
                return None

        def montar_abas_de_dados():
            """
            Gera (nome_aba, DataFrame) na ordem oficial do relatório.

            É um GERADOR de propósito, não uma lista. Montar todas as abas de uma vez deixa
            vivos ao mesmo tempo o df_docs inteiro (~167 mil linhas x 62), uma cópia por tipo
            de documento (que somadas repetem essas mesmas linhas), o RIAF e as ~310 mil
            linhas de Pagamentos — e o processo morre por falta de memória, sem traceback,
            levado pelo OOM killer. Com yield, cada aba é preparada, escrita e liberada antes
            da seguinte, que era o perfil de memória do código original.
            """

            if gerar_quantitativo and not df_resumo_geral.empty:
                print(f"[GGCI       | GERANDO       | RESUMO] Quantitativo (Envio & Pendências)...")
                yield ('Envios & Pendências', df_resumo_geral)

            doc_order = [
                (DOC_CONTRATO, "Contrato", check_contrato),
                (None, "Riaf", True),  # Especial para o df_riaf
                (DOC_BENEF, "Benefício", check_benef),
                (DOC_FINANC, "Financiamento", check_financ),
                (DOC_HISTORICO, "Histórico", check_historico)
            ]

            docs_processados = set()
            col_tipo = 'tipo_documento' if 'tipo_documento' in df_docs.columns else 'Documento Tipo'

            if not df_docs.empty:
                ordenar_para_saida(df_docs)

            for doc_original, tab_name, is_enabled in doc_order:
                if tab_name == "Riaf":
                    if not df_riaf.empty:
                        print(f"[GGCI       | GERANDO       | RIAF  ] {len(df_riaf)} linhas...")
                        ordenar_para_saida(df_riaf)
                        yield ('Riaf', df_riaf.drop(columns=COLS_CHECK, errors='ignore'))
                    continue

                df_tipo = pd.DataFrame()
                if not df_docs.empty and col_tipo in df_docs.columns:
                    df_tipo = df_docs[df_docs[col_tipo] == doc_original].copy()

                if not df_tipo.empty:
                    print(f"[GGCI       | GERANDO       | DOCS  ] {tab_name} ({len(df_tipo)} linhas)...")
                    if doc_original == DOC_HISTORICO:
                        df_tipo = df_tipo.drop(columns=COLS_CHECK, errors='ignore')
                    if doc_original in (DOC_CONTRATO, DOC_BENEF, DOC_FINANC):
                        df_tipo = df_tipo[[c for c in COLUNAS_ABA_DOCUMENTO if c in df_tipo.columns]]
                    df_tipo = df_tipo.drop(columns=['tipo_documento', 'Documento Tipo'], errors='ignore')
                    yield (tab_name, df_tipo)
                    docs_processados.add(doc_original)
                elif is_enabled:
                    yield (tab_name, pd.DataFrame([{"Aviso": AVISO_VAZIO}]))
                    docs_processados.add(doc_original)

            # Aba extra para outros documentos não mapeados (se existirem)
            if not df_docs.empty and col_tipo in df_docs.columns:
                mapeados = [d[0] for d in doc_order]
                for doc_original in df_docs[col_tipo].dropna().unique():
                    if doc_original not in docs_processados and doc_original not in mapeados:
                        df_tipo = df_docs[df_docs[col_tipo] == doc_original].copy()
                        tab_name = str(doc_original)[:31].replace('/', '_').replace('\\', '_')
                        df_tipo = df_tipo.drop(columns=['tipo_documento', 'Documento Tipo'], errors='ignore')
                        yield (tab_name, df_tipo)

            if gerar_pagamentos:
                df_pagamentos = preparar_aba_pagamentos()
                if df_pagamentos is not None and not df_pagamentos.empty:
                    yield ('Pagamentos', df_pagamentos)


        abas_dados = montar_abas_de_dados()

        # --- ESCREVER ABAS NA ORDEM EXATA ---
        if formato == "CSV":
            arquivo_geral_saida = os.path.join(base_dir, f"relatorio_geral.zip")
            print(f"[GGCI       | FINALIZAR     | CSV   ] Gerando arquivos...")
            with zipfile.ZipFile(arquivo_geral_saida, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for nome_aba, df_aba in abas_dados:
                    nome_arquivo = str(nome_aba).replace('/', '_').replace('\\', '_')
                    csv_str = df_aba.to_csv(index=False, sep=';')
                    # BOM na frente para o Excel abrir o UTF-8 com acento certo.
                    zipf.writestr(f'{nome_arquivo}.csv', '﻿'.encode('utf8') + csv_str.encode('utf8'))
            print(f"[GGCI       | CONCLUIDO     | FINAL ] Salvo com sucesso.")
            t_total = time.time() - t_inicio_ggci
            print(f"🎉 Regras aplicadas: Relatório gerado em {int(t_total // 60)}m e {int(t_total % 60)}s.")
        elif formato == "PARQUET":
            # Saída nativa do Documentos IA. Este app não entrega arquivo para o usuário —
            # ele só precisa dos dados prontos para virar gráfico. Parquet em vez de CSV
            # porque a diferença medida na aba Pagamentos (310 mil linhas x 22 colunas) é
            # de 0,37s para 0,02s na leitura e de 47,5 MB para 2,9 MB em disco, e porque o
            # CSV perderia os tipos que o dashboard precisa somar e ordenar.
            #
            # A pedido, as abas em parquet agora são salvas individualmente na pasta do processo,
            # seguindo a mesma estrutura e isolamento adotados no analise_ia.
            pasta_saida = os.path.join(base_dir, "relatorio_geral")
            os.makedirs(pasta_saida, exist_ok=True)
            print(f"[GGCI       | FINALIZAR     | PARQUET] Gravando abas...")

            escritos = set()
            for nome_aba, df_aba in abas_dados:
                nome_arquivo = str(nome_aba).replace('/', '_').replace('\\', '_')
                destino = os.path.join(pasta_saida, f"{nome_arquivo}.parquet")

                df_aba = normalizar_tipos_para_parquet(df_aba)

                # Grava em arquivo temporário e só então renomeia. os.replace é atômico no
                # mesmo sistema de arquivos, então o dashboard nunca abre um Parquet pela
                # metade caso alguém carregue a tela no meio de uma atualização.
                temporario = f"{destino}.tmp"
                df_aba.to_parquet(temporario, index=False, compression='zstd')
                os.replace(temporario, destino)

                escritos.add(f"{nome_arquivo}.parquet")
                print(f"[GGCI       | GRAVADO       | PARQUET] {nome_arquivo}: {len(df_aba)} linhas x {len(df_aba.columns)} colunas.")

            # Remove abas de execuções anteriores que não vieram nesta. Sem isso, um
            # documento que deixasse de ser extraído continuaria no dashboard para sempre,
            # com os números da última vez em que apareceu.
            for antigo in os.listdir(pasta_saida):
                if antigo.endswith('.parquet') and antigo not in escritos:
                    try:
                        os.remove(os.path.join(pasta_saida, antigo))
                        print(f"[GGCI       | REMOVIDO      | PARQUET] {antigo} (ausente nesta execução).")
                    except OSError:
                        pass

            arquivo_geral_saida = pasta_saida
            print(f"[GGCI       | CONCLUIDO     | FINAL ] Salvo com sucesso.")
            t_total = time.time() - t_inicio_ggci
            print(f"🎉 Regras aplicadas: Relatório gerado em {int(t_total // 60)}m e {int(t_total % 60)}s.")
        else:
            # 1. Relatório Contratos (Unificado) — só no Excel, usa fórmulas
            if gerar_relatorio:
                print(f"[GGCI       | GERANDO       | RELATORIO  ] Contratos...")
                if sems_contratos:
                    gerar_aba_relatorio_contratos(writer, df_docs, sems_contratos)
                else:
                    print(f"[GGCI       | AVISO         | CONTRATOS] Nenhum semestre configurado.")

            # 2. Relatório RIAF — idem
            if gerar_relatorio_riaf:
                print(f"[GGCI       | GERANDO       | RIAF  ] Relatório RIAF IES...")
                if sems_riaf:
                    gerar_aba_relatorio_riaf(writer, df_riaf, sems_riaf)
                else:
                    print(f"[GGCI       | AVISO         | RIAF  ] Nenhum semestre configurado para RIAF.")

            # 3. Envios & Pendências, documentos e Pagamentos
            for nome_aba, df_aba in abas_dados:
                escrever_aba(writer, nome_aba, df_aba)
                aplicar_formatacao_visual(writer, nome_aba, df_aba)

            import threading
            def monitor_save(stop_event):
                while not stop_event.is_set():
                    time.sleep(5)
                    if not stop_event.is_set():
                        print("[GGCI_SILENT_WAIT]")

            print(f"[GGCI       | SALVANDO      | ARQUIV] Compilando e compactando...")
            
            stop_save_event = threading.Event()
            t_monitor = threading.Thread(target=monitor_save, args=(stop_save_event,))
            t_monitor.start()

            try:
                writer.close()
            finally:
                stop_save_event.set()
                t_monitor.join()
            # print(f"[GGCI       | CONCLUIDO     | FINAL ] Salvo com sucesso.")
            t_total = time.time() - t_inicio_ggci
            minutos = int(t_total // 60)
            segundos = int(t_total % 60)
            print(f"🎉 Regras aplicadas: Relatório gerado em {minutos}m e {segundos}s.")
    else:
        print("[GGCI       | ERRO          | VAZIO ] Nenhum dado.")

    # As tabelas PY_ggci_* são mantidas no banco de dados. 
    # O cache de 2 horas no extrator.py decide quando recriá-las.

    return arquivo_geral_saida