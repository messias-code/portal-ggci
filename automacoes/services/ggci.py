import os
import sys
import pandas as pd
import numpy as np
import unicodedata
import re
import datetime
from urllib.parse import quote_plus
from sqlalchemy import create_engine

# Desativa o aviso do futuro do Pandas para preenchimento de dados vazios
pd.set_option('future.no_silent_downcasting', True)

# ==========================================
# 1. CAMINHOS DE ENTRADA E SAÍDA
# ==========================================
PASTA_CONSOLIDADOS = os.path.join("dados_analise", "analise_documentos_processados", "CONSOLIDADO")
ARQ_PROCESSADOS = os.path.join(PASTA_CONSOLIDADOS, "consolidado_processados.xlsx")
ARQ_RIAF = os.path.join(PASTA_CONSOLIDADOS, "consolidado_processados_riaf.xlsx")

ARQ_AGENDAR = os.path.join("dados_analise", "analise_documentos_agendar_processamentos", "CONSOLIDADO", "consolidado_agendar_processamentos.xlsx")

PASTA_PAGAMENTOS = os.path.join("dados_analise", "analise_pagamentos", "CONSOLIDADO")
ARQ_PAGAMENTOS = os.path.join(PASTA_PAGAMENTOS, "consolidado_pagamentos.xlsx")

ARQUIVO_GERAL_SAIDA = "relatorio_geral.xlsx"

# ==========================================
# 2. FUNÇÕES DE LIMPEZA E FORMATAÇÃO
# ==========================================
COLS_NUM = ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Cnpj Faculdade', 'UNI_CODIGO', 'UNI_CPF']
COLS_MOEDA = [
    'Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 
    'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 
    'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
    'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto', 
    'valor_beneficio', 'valor_financiamento', 
    'valor_calculo_bolsa_paga', 'total bolsa paga', 
    'MSD_SOMA', 'G_MSD_SOMA', 'MCD_SOMA', 'G_MCD_SOMA', 
    '[1] OVG PAGOU (Bolsa Mês)',
    '[2] OVG DEVERIA PAGAR (SISTEMA)', 
    '[3] OVG DEVERIA PAGAR (IA)', 
    '[4] SOMA OVG DEVERIA PAGAR (IA)',
    '[5] SALDO RESTANTE (MCD - Benefícios)', 
    '[6] PREJUÍZO DA OVG (R$)', 
    '[7] LUCRO INDEVIDO IES (R$)',
    '[8] ECONOMIA DA OVG (R$)'
]

DOC_CONTRATO = "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"
DOC_FINANC = "COMPROVANTE DE FINANCIAMENTO"
DOC_BENEF = "COMPROVANTE OUTROS BENEFÍCIOS"
DOC_RIAF = "RIAF – RESUMO DE INFORMAÇÕES ACADÊMICAS E FINANCEIRAS"
DOC_HISTORICO = "HISTÓRICO ESCOLAR"

SEMESTRES_PADRAO = ["2025-1", "2025-2", "2026-1"]

def limpar_texto_geral(texto):
    if pd.isna(texto) or str(texto).lower() in ['nan', 'none']: return ""
    texto = str(texto).strip().upper()
    texto = texto.replace("ADMINISTRAÃO", "ADMINISTRACAO")
    texto = texto.replace("ADMINISTRAAAO", "ADMINISTRACAO")
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^A-Z0-9 ]', '', texto)
    return " ".join(texto.split())

def converter_colunas_para_salvamento(df):
    for col in COLS_NUM:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    for col in COLS_MOEDA:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
    return df

def aplicar_formatacao_visual(writer, nome_aba, df):
    workbook = writer.book
    worksheet = writer.sheets[nome_aba]
    
    # --- 1. Definição de Formatos Numéricos Base ---
    fmt_cpf = workbook.add_format({'num_format': '00000000000', 'valign': 'vcenter'})
    fmt_cnpj = workbook.add_format({'num_format': '00000000000000', 'valign': 'vcenter'}) 
    fmt_num = workbook.add_format({'num_format': '0', 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda = workbook.add_format({'num_format': 'R$ #,##0.00;[Red]-R$ #,##0.00', 'valign': 'vcenter'}) 
    fmt_pct = workbook.add_format({'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    fmt_padrao = workbook.add_format({'valign': 'vcenter'})
    
    # --- 2. Cabeçalho Blindado (Tudo Branco no Fundo Azul Escuro) ---
    fmt_header = workbook.add_format({
        'bold': True,
        'font_color': '#FFFFFF',
        'bg_color': '#1F497D',
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True
    })

    # --- 3. Cores Padronizadas (Fundo + Texto para TUDO) ---
    f_verde = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
    f_verm  = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
    f_amar  = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'})
    f_cinza = workbook.add_format({'bg_color': '#D9D9D9', 'font_color': '#595959'})

    max_row = len(df)
    max_col = len(df.columns) - 1

    # --- 4. Aplicar Tabela Oficial (Com o nosso cabeçalho forçado) ---
    col_settings = [{'header': str(col), 'header_format': fmt_header} for col in df.columns]
    worksheet.add_table(0, 0, max_row, max_col, {
        'columns': col_settings,
        'style': 'Table Style Light 1' # Tema base mais limpo para destacar nossas cores
    })
    
    worksheet.freeze_panes(1, 0)
    worksheet.set_row(0, 35) 

    # --- 5. Ajustar Larguras das Colunas Dinamicamente (Auto-Fit Inteligente) ---
    for i, col in enumerate(df.columns):
        # A mágica: lê a maior string DENTRO da coluna e compara com o título
        tamanho_conteudo = df[col].astype(str).map(len).max() if not df.empty else 0
        largura_ideal = max(tamanho_conteudo, len(str(col))) + 3 # +3 de respiro para a seta do filtro
        
        if largura_ideal > 50: largura_ideal = 50 # Trava em 50 para colunas como "Inconsistências" não ocuparem a tela toda
        
        col_upper = str(col).upper()
        
        # Aplica a largura ideal calculada com a formatação correta
        if '%' in col_upper:
            worksheet.set_column(i, i, max(12, largura_ideal), fmt_pct)
        elif 'CNPJ' in col_upper:
            worksheet.set_column(i, i, max(18, largura_ideal), fmt_cnpj)
        elif 'CPF' in col_upper:
            worksheet.set_column(i, i, max(16, largura_ideal), fmt_cpf)
        elif col in COLS_NUM or col == 'qtd_pagtos':
            worksheet.set_column(i, i, max(12, largura_ideal), fmt_num)
        elif col in COLS_MOEDA or 'DIF.' in col_upper or 'BOLSA PAGA' in col_upper: 
            worksheet.set_column(i, i, max(18, largura_ideal), fmt_moeda) 
        else:
            worksheet.set_column(i, i, largura_ideal, fmt_padrao)

    # --- 6. Formatação Condicional (O Semáforo Padronizado) ---
    for i, col in enumerate(df.columns):
        
        # Status da IA
        if col == 'Status_IA':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Válido"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Inválido"', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Ausente"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Corrompido"', 'format': f_verm})
        
        # Auditoria Lógica da IA (Agora cobrindo o N/A em cinza)
        elif col == 'Auditoria IA':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Alinhado"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'Falso', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"N/A"', 'format': f_cinza})
            
        # Validação Financeira
        elif col == 'Validação Financeira':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OK"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'Sem Pagamento', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'Migrado', 'format': f_verm})

        # Diagnóstico Financeiro Final
        elif col == 'Diagnóstico Financeiro Final':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Pagamento correto"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a mais"', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a menos"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não localizado', 'format': f_cinza})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não realizado', 'format': f_cinza})

        # Alertas de OVG DEVERIA PAGAR (Pinta de vermelho o bloco se for menor que 0)
        elif col in ['[2] OVG DEVERIA PAGAR (SISTEMA)', '[3] OVG DEVERIA PAGAR (IA)']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '<', 'value': 0, 'format': f_verm})

        # [5] SALDO RESTANTE (Fica Vermelho para QUALQUER valor positivo ou negativo, exceto zero exato)
        elif col == '[5] SALDO RESTANTE (MCD - Benefícios)':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '!=', 'value': 0, 'format': f_verm})

        # Alerta para Diferenças de Mensalidade (Qualquer divergência acende o bloco vermelho)
        elif col in ['Dif. s/Desc.', 'Total Dif. s/Desc.', 'Dif. c/Desc.', 'Total Dif. c/Desc.']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '!=', 'value': 0, 'format': f_verm})
        
        # Alerta Financeiro Vermelho (Prejuízos e Lucros Indevidos gritam em vermelho se for maior que 0)
        elif col in ['[6] PREJUÍZO DA OVG (R$)', '[7] LUCRO INDEVIDO IES (R$)']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verm})
            
        # NOVA COLUNA: Economia da OVG (Grita em VERDE se for maior que 0)
        elif col == '[8] ECONOMIA DA OVG (R$)':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verde})

# ==========================================
# 3. EXTRAÇÃO FINANCEIRA VIA SQL
# ==========================================
def buscar_dados_financeiros_sql(semestres_presentes):
    if not semestres_presentes: return pd.DataFrame()
    
    DB_HOST, DB_USER, DB_PASS, DB_NAME = "10.237.1.16", "bi_ovg", "bi_ovg@#$124as65", "sibu"
    
    sems_banco = [str(x).strip().replace('-', '/') for x in semestres_presentes]
    sems_formatados = ",".join([f"'{x}'" for x in sems_banco])
    
    query = f"""
        SELECT 
            uni_codigo, semestre, tipo_bolsa_final, qtd_pagtos, valor_ultima_bolsa_paga AS valor_calculo_bolsa_paga,
            valor_mensalidade_sem_desconto, valor_mensalidade_com_desconto,
            situacao, situacao_atual_sistema, sit_data_atual_sistema, sit_tipo_atual_sistema, sit_obs_atual_sistema,
            valor_beneficio, qual_beneficio, valor_financiamento, qual_financiamento,
            data_create AS data_coleta
        FROM sibu.PY_ggci_analise_IA
        WHERE semestre IN ({sems_formatados})
    """
    
    try:
        engine = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}/{DB_NAME}',
            connect_args={'connect_timeout': 30, 'read_timeout': 300} 
        )
        print("   🗄️ Conectando ao sistema de pagamentos...")
        df_sql = pd.read_sql(query, engine)
        
        if not df_sql.empty:
            df_sql['uni_codigo'] = pd.to_numeric(df_sql['uni_codigo'], errors='coerce').astype('Int64')
            df_sql = df_sql.dropna(subset=['uni_codigo']) 
            df_sql['semestre'] = df_sql['semestre'].astype(str).str.strip()
            
            alunos_unicos = df_sql['uni_codigo'].unique()
            index = pd.MultiIndex.from_product([alunos_unicos, sems_banco], names=['uni_codigo', 'semestre'])
            df_skeleton = pd.DataFrame(index=index).reset_index()
            
            df_merged = pd.merge(df_skeleton, df_sql, on=['uni_codigo', 'semestre'], how='left')
            
            if 'tipo_bolsa_final' in df_merged.columns:
                df_merged['tipo_bolsa_final'] = df_merged.groupby('uni_codigo')['tipo_bolsa_final'].transform(lambda x: x.ffill().bfill())
                
            cols_absolutas = ['situacao_atual_sistema', 'sit_data_atual_sistema', 'sit_tipo_atual_sistema', 'sit_obs_atual_sistema']
            for col in cols_absolutas:
                if col in df_merged.columns:
                    df_merged[col] = df_merged[col].replace(['', None, 'nan', 'NaN'], np.nan)
                    df_merged[col] = df_merged.groupby('uni_codigo')[col].transform(lambda x: x.ffill().bfill())
                
            valores_para_zerar = {
                'qtd_pagtos': 0, 'valor_calculo_bolsa_paga': 0.0,
                'valor_mensalidade_sem_desconto': 0.0, 'valor_mensalidade_com_desconto': 0.0,
                'situacao': '', 'situacao_atual_sistema': '',
                'sit_data_atual_sistema': '', 'sit_tipo_atual_sistema': '', 'sit_obs_atual_sistema': '',
                'valor_beneficio': 0.0, 'valor_financiamento': 0.0,
                'qual_beneficio': 'Sem outros benefícios', 'qual_financiamento': 'Sem financiamento',
                'data_coleta': ''
            }
            df_merged.fillna(valores_para_zerar, inplace=True)
            
            if 'tipo_bolsa_final' in df_merged.columns:
                df_merged['tipo_bolsa_final'] = df_merged['tipo_bolsa_final'].fillna("SEM DADOS")
                
            if 'data_coleta' in df_merged.columns:
                df_merged['data_coleta'] = pd.to_datetime(df_merged['data_coleta'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                
            df_sql = df_merged.copy()
            
            df_sql['semestre'] = df_sql['semestre'].str.replace('/', '-')
            df_sql['qtd_pagtos'] = pd.to_numeric(df_sql['qtd_pagtos'], errors='coerce').fillna(0).astype(int)
            df_sql['valor_calculo_bolsa_paga'] = pd.to_numeric(df_sql['valor_calculo_bolsa_paga'], errors='coerce').fillna(0.0)
            df_sql['valor_mensalidade_sem_desconto'] = pd.to_numeric(df_sql['valor_mensalidade_sem_desconto'], errors='coerce').fillna(0.0)
            df_sql['valor_mensalidade_com_desconto'] = pd.to_numeric(df_sql['valor_mensalidade_com_desconto'], errors='coerce').fillna(0.0)
            
            # Formatação numérica nativa
            df_sql['valor_beneficio'] = pd.to_numeric(df_sql['valor_beneficio'], errors='coerce').fillna(0.0)
            df_sql['valor_financiamento'] = pd.to_numeric(df_sql['valor_financiamento'], errors='coerce').fillna(0.0)
            
            df_sql = df_sql.drop_duplicates(subset=['uni_codigo', 'semestre'], keep='last')
            print("   ✅ Dados financeiros carregados com sucesso.")
            
        return df_sql
    except Exception as e:
        print(f"\n   🚨 ERRO CRÍTICO: Não foi possível conectar ao banco de dados SQL.")
        print(f"   Detalhes do erro: {e}")
        print("   Abortando a execução do GGCI pois os dados do banco são indispensáveis para o relatório.")
        sys.exit(1)

def mesclar_sql_e_reordenar(df, df_sql, df_pag=None):
    if df.empty: return df
    
    if not df_sql.empty:
        df['Inscrição'] = pd.to_numeric(df['Inscrição'], errors='coerce').astype('Int64')
        df['Semestre'] = df['Semestre'].astype(str).str.strip().str.replace('/', '-')
        
        df_sql['uni_codigo'] = pd.to_numeric(df_sql['uni_codigo'], errors='coerce').astype('Int64')
        df_sql['semestre'] = df_sql['semestre'].astype(str).str.strip().str.replace('/', '-')

        df = pd.merge(df, df_sql, left_on=['Inscrição', 'Semestre'], right_on=['uni_codigo', 'semestre'], how='left')
        df.drop(columns=['uni_codigo', 'semestre'], errors='ignore', inplace=True)
        
    for col in ['tipo_bolsa_final', 'qtd_pagtos', 'valor_calculo_bolsa_paga']:
        if col not in df.columns: df[col] = "SEM DADOS" if col == 'tipo_bolsa_final' else 0

    df['tipo_bolsa_final'] = df.groupby('Inscrição')['tipo_bolsa_final'].transform(lambda x: x.ffill().bfill()).fillna("SEM DADOS")
    df['qtd_pagtos'] = pd.to_numeric(df['qtd_pagtos'], errors='coerce').fillna(0).astype(int)
    df['valor_calculo_bolsa_paga'] = pd.to_numeric(df['valor_calculo_bolsa_paga'], errors='coerce').fillna(0.0)
    
    # --- RECALCULAR pagamentos a partir do consolidado, ignorando cancelamentos (LAN_VALBOLSA = 0) ---
    if df_pag is not None and not df_pag.empty and 'LAN_VALBOLSA' in df_pag.columns:
        print("   📊 Recalculando pagamentos efetivos (excluindo cancelamentos com LAN_VALBOLSA=0)...")
        df_pag_calc = df_pag.copy()
        df_pag_calc['UNI_CODIGO'] = pd.to_numeric(df_pag_calc['UNI_CODIGO'], errors='coerce').astype('Int64')
        df_pag_calc['SEMESTRE'] = df_pag_calc['SEMESTRE'].astype(str).str.strip().str.replace('/', '-')
        df_pag_calc['LAN_VALBOLSA'] = pd.to_numeric(df_pag_calc['LAN_VALBOLSA'], errors='coerce').fillna(0.0)
        
        # Filtra apenas pagamentos efetivos (LAN_VALBOLSA > 0)
        df_pag_efetivos = df_pag_calc[df_pag_calc['LAN_VALBOLSA'] > 0].copy()
        
        # Agrupa por aluno + semestre: conta pagamentos, pega último valor e SOMA REAL
        df_pag_resumo = df_pag_efetivos.groupby(['UNI_CODIGO', 'SEMESTRE']).agg(
            qtd_pagtos_real=('LAN_VALBOLSA', 'count'),
            valor_calculo_real=('LAN_VALBOLSA', 'last'),
            total_bolsa_real=('LAN_VALBOLSA', 'sum')
        ).reset_index()
        
        # Merge com o DataFrame principal e substitui os valores do SQL pelos recalculados
        df = pd.merge(df, df_pag_resumo, left_on=['Inscrição', 'Semestre'], right_on=['UNI_CODIGO', 'SEMESTRE'], how='left')
        
        # Onde temos dados do consolidado, usa os valores recalculados; senão mantém o SQL
        mask_tem_pag = df['qtd_pagtos_real'].notna()
        df.loc[mask_tem_pag, 'qtd_pagtos'] = df.loc[mask_tem_pag, 'qtd_pagtos_real'].astype(int)
        df.loc[mask_tem_pag, 'valor_calculo_bolsa_paga'] = df.loc[mask_tem_pag, 'valor_calculo_real']
        
        # total bolsa paga = SOMA REAL dos pagamentos efetivos (não qtd × valor)
        df['total bolsa paga'] = df['qtd_pagtos'] * df['valor_calculo_bolsa_paga']  # fallback
        df.loc[mask_tem_pag, 'total bolsa paga'] = df.loc[mask_tem_pag, 'total_bolsa_real']
        
        df.drop(columns=['UNI_CODIGO', 'SEMESTRE', 'qtd_pagtos_real', 'valor_calculo_real', 'total_bolsa_real'], errors='ignore', inplace=True)
    else:
        # Fallback quando não há consolidado: usa multiplicação simples
        df['total bolsa paga'] = df['qtd_pagtos'] * df['valor_calculo_bolsa_paga']

    if 'Status_IA' in df.columns:
        mask_ausente = df['Status_IA'].isin(['Ausente', 'Ausentes'])
        cols_alvo = ['Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto']
        
        for c in cols_alvo:
            if c not in df.columns: df[c] = 0.0
            else: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            
        if 'valor_mensalidade_sem_desconto' in df.columns:
            df.loc[mask_ausente, 'Mensalidade S/ Desconto'] = df.loc[mask_ausente, 'valor_mensalidade_sem_desconto']
            df.loc[mask_ausente, 'Gemini Mensalidade S/ Desconto'] = 0.0
            df.drop(columns=['valor_mensalidade_sem_desconto'], inplace=True)

        if 'valor_mensalidade_com_desconto' in df.columns:
            df.loc[mask_ausente, 'Mensalidade C/ Desconto'] = df.loc[mask_ausente, 'valor_mensalidade_com_desconto']
            df.loc[mask_ausente, 'Gemini Mensalidade C/ Desconto'] = 0.0
            df.drop(columns=['valor_mensalidade_com_desconto'], inplace=True)
            
    col_tipo = df.pop('tipo_bolsa_final')
    col_qtd = df.pop('qtd_pagtos')
    col_val = df.pop('valor_calculo_bolsa_paga')
    col_tot = df.pop('total bolsa paga')
    
    try: idx_curso = df.columns.get_loc('Curso')
    except: idx_curso = len(df.columns) - 1
        
    df.insert(idx_curso + 1, 'tipo_bolsa_final', col_tipo)
    df.insert(idx_curso + 2, 'qtd_pagtos', col_qtd)
    df.insert(idx_curso + 3, 'valor_calculo_bolsa_paga', col_val)
    df.insert(idx_curso + 4, 'total bolsa paga', col_tot)
    
    return df

# ==========================================
# 4. TRANSIÇÕES E REGRAS DE NEGÓCIO
# ==========================================
def aplicar_transicoes(df, df_pag):
    if df.empty: return df
    
    col_trans = ['Mudou IES?', 'IES Anterior', 'IES Posterior', 'Mudou Bolsa?', 'Bolsa Anterior', 'Bolsa Posterior', 'Inscrição Anterior', 'Inscrição Posterior']
    if df_pag.empty or 'UNI_CPF' not in df_pag.columns or 'UNI_CODIGO' not in df_pag.columns:
        for c in col_trans: df[c] = "-"
        df['Inscrição Anterior'] = pd.NA
        df['Inscrição Posterior'] = pd.NA
        return df

    pag = df_pag.copy()
    pag['UNI_CPF'] = pag['UNI_CPF'].astype(str).str.replace('*', '', regex=False).str.replace('.', '', regex=False).str.replace('-', '', regex=False).str.zfill(11)
    pag['K_ID'] = pag['UNI_CODIGO'].astype(str).str.replace('.0', '', regex=False).str.replace('.', '', regex=False).str.strip()
    
    def padronizar_ies(texto):
        if pd.isna(texto): return ""
        txt = str(texto).upper().strip()
        txt = ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
        return ' '.join(txt.replace('-', ' ').split())

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
        df['Faculdade'] = df['KEY_TEMP'].map(map_ies_semestre).fillna(df['Faculdade'].apply(padronizar_ies))
    df.drop(columns=['KEY_TEMP'], inplace=True)
    
    df['Inscrição Anterior'] = pd.to_numeric(k_id_series.map(map_prev_id), errors='coerce').astype('Int64')
    df['Inscrição Posterior'] = pd.to_numeric(k_id_series.map(map_next_id), errors='coerce').astype('Int64')
    
    ies_atual = df['Faculdade'].astype(str).str.strip()
    curr_bolsa = k_id_series.map(map_curr_b).fillna("-").astype(str).str.strip()
    
    prev_ies = k_id_series.map(map_prev_ies).fillna("-").astype(str).str.strip()
    next_ies = k_id_series.map(map_next_ies).fillna("-").astype(str).str.strip()
    prev_bolsa = k_id_series.map(map_prev_b).fillna("-").astype(str).str.strip()
    next_bolsa = k_id_series.map(map_next_b).fillna("-").astype(str).str.strip()
    
    df['IES Anterior'] = np.where((prev_ies != "-") & (prev_ies != ies_atual), prev_ies, "-")
    df['IES Posterior'] = np.where((next_ies != "-") & (next_ies != ies_atual), next_ies, "-")
    
    df['Bolsa Anterior'] = np.where((prev_bolsa != "-") & (prev_bolsa != curr_bolsa), prev_bolsa, "-")
    df['Bolsa Posterior'] = np.where((next_bolsa != "-") & (next_bolsa != curr_bolsa), next_bolsa, "-")
    
    df['Mudou IES?'] = np.where((df['IES Anterior'] != "-") | (df['IES Posterior'] != "-"), "SIM", "NÃO")
    df['Mudou Bolsa?'] = np.where((df['Bolsa Anterior'] != "-") | (df['Bolsa Posterior'] != "-"), "SIM", "NÃO")
    
    # === A NOVA LÓGICA DE VÍNCULO (Com Trava de Inscrição Substituída) ===
    ano_atual_str = str(datetime.datetime.now().year)
    inscricoes_ativas = set(pag[pag['SEMESTRE'].astype(str).str.startswith(ano_atual_str)]['K_ID'])
    if not inscricoes_ativas:
        ano_anterior_str = str(datetime.datetime.now().year - 1)
        inscricoes_ativas = set(pag[pag['SEMESTRE'].astype(str).str.startswith(ano_anterior_str)]['K_ID'])
    
    # 1. Se a Inscrição teve faturamento no ano, a princípio ela está Ativa
    status_base = np.where(k_id_series.isin(inscricoes_ativas), 'ATIVO', 'DESLIGADO')
    
    # 2. A TRAVA: Se existe uma "Inscrição Posterior", a inscrição velha morre obrigatoriamente
    tem_post = pd.notna(df['Inscrição Posterior']) & (df['Inscrição Posterior'].astype(str).str.strip() != '') & (df['Inscrição Posterior'].astype(str).str.strip() != '<NA>')
    df['Status_Vínculo'] = np.where(tem_post, 'DESLIGADO', status_base)
    
    return df


def calcular_auditoria_ia(df):
    if df.empty: return df

    def get_primeiro_valido(row, colunas):
        for col in colunas:
            if col in row.index:
                val = row[col]
                if pd.notna(val):
                    v_str = str(val).strip()
                    if v_str.lower() not in ['', 'nan', 'none', 'nat', '<na>']:
                        return v_str
        return ''

    def get_corrompido(row):
        ia_st = str(row.get('Status_IA', '')).strip()
        if ia_st == 'Corrompido': return ia_st
        
        # --- A NOVA REGRA DE NEGÓCIO: FALSO AUSENTE ---
        insc_post = str(row.get('Inscrição Posterior', '')).strip()
        has_insc_post = pd.notna(row.get('Inscrição Posterior')) and insc_post not in ['', 'nan', '<NA>', 'None', '-']
        val_ultima = pd.to_numeric(row.get('valor_calculo_bolsa_paga', 0), errors='coerce')
        if pd.isna(val_ultima): val_ultima = 0.0
        
        # Se a IA listou como Ausente, mas migrou de IES e o pgto é retroativo/zero -> Falso Ausente!
        if ia_st in ['Ausente', 'Ausentes']:
            if has_insc_post and val_ultima == 0.0:
                return 'Falso Ausente'
        
        # --- REGRA DO CORROMPIDO ---
        processar = get_primeiro_valido(row, ['Processar', 'Processar_y', 'Processar_x']).upper()
        processado = get_primeiro_valido(row, ['Processado', 'Processado_y', 'Processado_x']).upper()
        d_proc = get_primeiro_valido(row, ['Data_Processamento_Agendar', 'Data Processamento', 'Data Processamento_y', 'Data Processamento_x'])
        inc = get_primeiro_valido(row, ['Gemini Inconsistencias'])
        
        if processar == 'SIM' and processado == 'SIM' and d_proc != '' and inc == '':
            g_cpf = get_primeiro_valido(row, ['Gemini CPF'])
            g_sem = get_primeiro_valido(row, ['Gemini Semestre'])
            if g_cpf == '' or g_sem == '': 
                return 'Corrompido'
                
            doc_tipo = str(row.get('Documento Tipo', '')).upper()
            
            g_msd = pd.to_numeric(row.get('Gemini Mensalidade S/ Desconto'), errors='coerce')
            g_mcd = pd.to_numeric(row.get('Gemini Mensalidade C/ Desconto'), errors='coerce')
            g_fin = pd.to_numeric(row.get('Gemini Valor Financiado'), errors='coerce')
            g_ben = pd.to_numeric(row.get('Gemini Valor Beneficio'), errors='coerce')
            
            if "CONTRATO" in doc_tipo:
                if (pd.isna(g_msd) or g_msd == 0.0) and (pd.isna(g_mcd) or g_mcd == 0.0): return 'Corrompido'
            elif "FINANCIAMENTO" in doc_tipo:
                if pd.isna(g_fin) or g_fin == 0.0: return 'Corrompido'
            elif "BENEF" in doc_tipo:
                if pd.isna(g_ben) or g_ben == 0.0: return 'Corrompido'
                
        return ia_st
        
    df['Status_IA'] = df.apply(get_corrompido, axis=1)

    # Criação das máscaras vetorizadas (O Falso Ausente entra aqui para não bugar a matemática contábil)
    mask_ausente = df['Status_IA'].isin(['Ausente', 'Ausentes', 'Falso Ausente'])
    mask_corrompido = df['Status_IA'] == 'Corrompido'
    
    d_proc_series = df.get('Data_Processamento_Agendar', df.get('Data Processamento', pd.Series(['']*len(df), index=df.index)))
    data_proc_str = d_proc_series.astype(str).str.strip().str.lower()
    mask_data_vazia = data_proc_str.isin(['', 'nan', 'none', 'nat', '<na>'])
    
    mask_nao_processado = (~mask_ausente) & mask_data_vazia & (~mask_corrompido)
    
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
    
    qtd = pd.to_numeric(df.get('qtd_pagtos', 0), errors='coerce').fillna(0).astype(int)
    tot_dif_s = dif_s * qtd
    tot_dif_c = dif_c * qtd

    df['MSD_SOMA'] = msd_sys * qtd
    df['G_MSD_SOMA'] = msd_ia * qtd
    df['MCD_SOMA'] = mcd_sys * qtd
    df['G_MCD_SOMA'] = mcd_ia * qtd

    cond_msd_nao_loc = (msd_ia == 0)
    cond_msd_igual = (dif_s == 0)
    cond_msd_menor = (msd_ia < msd_sys)
    
    cond_mcd_nao_loc = (mcd_ia == 0)
    cond_mcd_igual = (dif_c == 0)
    cond_mcd_menor = (mcd_ia < mcd_sys)
    
    choices = [
        "Documento não enviado",
        "Documento não processado",
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

    curso_str = df.get('Curso', pd.Series(['']*len(df), index=df.index)).astype(str).str.strip().str.upper()
    bolsa_str = df.get('tipo_bolsa_final', pd.Series(['']*len(df), index=df.index)).astype(str).str.strip().str.upper()
    beneficios = pd.to_numeric(df.get('valor_beneficio', 0), errors='coerce').fillna(0.0)
    paga = pd.to_numeric(df.get('valor_calculo_bolsa_paga', 0), errors='coerce').fillna(0.0)
    
    df['[1] OVG PAGOU (Bolsa Mês)'] = paga

    is_med_odonto = curso_str.isin(['MEDICINA', 'ODONTOLOGIA'])
    is_contrato = df['Documento Tipo'] == 'CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA'
    
    sys_mcd_50 = mcd_sys * 0.5
    sys_calc_parcial = np.where(is_med_odonto, np.minimum(sys_mcd_50, 2900.0), np.minimum(sys_mcd_50, 650.0))
    sys_calc_integral = np.where(is_med_odonto, np.minimum(mcd_sys, 5800.0), np.minimum(mcd_sys, 1500.0))
    sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
    
    sys_excedeu = (sys_bolsa_base + beneficios) > mcd_sys
    sys_bolsa_final = np.where(sys_excedeu, mcd_sys - beneficios, sys_bolsa_base)
    sys_bolsa_final = np.maximum(sys_bolsa_final, 0.0)

    df['[2] OVG DEVERIA PAGAR (SISTEMA)'] = np.where(is_contrato & (~mask_ignorar_math), sys_bolsa_final, 0.0)

    g_mcd_50 = mcd_ia * 0.5
    g_calc_parcial = np.where(is_med_odonto, np.minimum(g_mcd_50, 2900.0), np.minimum(g_mcd_50, 650.0))
    g_calc_integral = np.where(is_med_odonto, np.minimum(mcd_ia, 5800.0), np.minimum(mcd_ia, 1500.0))
    g_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [g_calc_parcial, g_calc_integral], default=0.0)
    
    g_excedeu = (g_bolsa_base + beneficios) > mcd_ia
    g_bolsa_final = np.where(g_excedeu, mcd_ia - beneficios, g_bolsa_base)
    g_bolsa_final = np.maximum(g_bolsa_final, 0.0)

    df['[3] OVG DEVERIA PAGAR (IA)'] = np.where(is_contrato & (~mask_ignorar_math), g_bolsa_final, 0.0)
    df['[4] SOMA OVG DEVERIA PAGAR (IA)'] = df['[3] OVG DEVERIA PAGAR (IA)'] * df['qtd_pagtos'].fillna(0).astype(float)

    cond_falha_leitura = (mcd_ia == 0)
    saldo_restante = mcd_ia - beneficios
    df['[5] SALDO RESTANTE (MCD - Benefícios)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), saldo_restante, 0.0)

    prejuizo_ovg = np.maximum(paga - g_bolsa_final, 0.0)
    lucro_ies = np.maximum((paga + beneficios) - mcd_ia, 0.0)
    economia_ovg = np.maximum(g_bolsa_final - paga, 0.0)

    df['[6] PREJUÍZO DA OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), prejuizo_ovg, 0.0)
    df['[7] LUCRO INDEVIDO IES (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), lucro_ies, 0.0)
    df['[8] ECONOMIA DA OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), economia_ovg, 0.0)

    cond_ignorar = (~is_contrato) | mask_ignorar_math
    df['Diagnóstico Financeiro Final'] = np.select(
        [
            cond_ignorar,
            cond_falha_leitura,
            (paga > g_bolsa_final),
            (paga < g_bolsa_final) & (paga > 0),
            (paga == 0) & (g_bolsa_final > 0),
            (paga == g_bolsa_final)
        ],
        [
            "N/A", 
            "Valor não localizado",
            "OVG pagou a mais",
            "OVG pagou a menos",
            "Pagamento não realizado",
            "Pagamento correto"
        ],
        default="Verificar"
    )
    
    def auditar_linha(row):
        ia_status = str(row.get('Status_IA', '')).upper()
        if "AUSENTE" in ia_status or "X" in ia_status or "CORROMPIDO" in ia_status: return "N/A"
            
        ia_resultado = "Válido" if ia_status.startswith("V") else "Inválido"
        sys_semestre = str(row.get('Semestre', '')).strip().replace('-', '/')
        ia_semestre = str(row.get('Gemini Semestre', '')).strip().replace('-', '/')
        sys_cpf = str(row.get('CPF', '')).strip().replace('.0', '')
        ia_cpf = str(row.get('Gemini CPF', '')).strip().replace('.0', '')
        
        if not ia_cpf or sys_cpf != ia_cpf: matematica_diz = "Inválido"
        elif not ia_semestre or sys_semestre != ia_semestre: matematica_diz = "Inválido"
        elif "Valor da mensalidade integral não localizado" in str(row.get('Gemini Inconsistencias', '')).strip(): matematica_diz = "Inválido"
        elif pd.to_numeric(row.get('Dif. s/Desc.', 0), errors='coerce') != 0: matematica_diz = "Inválido"
        else: matematica_diz = "Válido"

        if matematica_diz == "Válido" and ia_resultado == "Inválido": return "Falso Inválido"
        elif matematica_diz == "Inválido" and ia_resultado == "Válido": return "Falso Válido"
        return "Alinhado"
        
    df['Auditoria IA'] = df.apply(auditar_linha, axis=1)

    ultimo_semestre_aluno = df.groupby('Inscrição')['Semestre'].max().to_dict()

    def classificar_vinculo(row):
        insc = row.get('Inscrição')
        sem_atual = row.get('Semestre')
        sit_pt = str(row.get('situacao', '')).strip().upper()
        sit_abs = str(row.get('situacao_atual_sistema', '')).strip().upper()
        insc_post = row.get('Inscrição Posterior')
        
        if pd.notna(insc_post) and str(insc_post).strip() not in ['', 'nan', '<NA>', 'None', '-']:
            return 'DESLIGADO'
        
        desligados = ['A', 'C', 'F', 'N', 'T', 'V', 'D'] 
        
        if sit_pt in desligados: return 'DESLIGADO'
        
        if sit_abs in desligados:
            if sem_atual == ultimo_semestre_aluno.get(insc): return 'DESLIGADO'
            else: return 'ATIVO'
            
        return 'ATIVO'

    df['Status_Vínculo'] = df.apply(classificar_vinculo, axis=1)

    def get_val_fin(row):
        qtd = pd.to_numeric(row.get('qtd_pagtos', 0), errors='coerce')
        if pd.notna(qtd) and qtd > 0: return "OK"
            
        st_vinc = str(row.get('Status_Vínculo', '')).strip().upper()
        st_ia = str(row.get('Status_IA', '')).strip()
        
        insc_post = row.get('Inscrição Posterior')
        if pd.notna(insc_post) and str(insc_post).strip() not in ['', 'nan', '<NA>', 'None', '-']:
            return "Migrado (Inscrição Substituída)"
            
        # Essa regra 'Ausente' também engloba o Falso Ausente
        if st_vinc == 'ATIVO' and st_ia in ['Ausente', 'Ausentes', 'Falso Ausente']: 
            return "Sem Pagamento (Ativo Novo)"
            
        return "Sem Pagamento (Desligado/Fantasma)"
        
    df['Validação Financeira'] = df.apply(get_val_fin, axis=1)

    ordem_desejada = [
        'Status_IA', 'Auditoria IA', 'Validação Financeira', 'Status_Vínculo', 
        'Mudou IES?', 'IES Anterior', 'IES Posterior', 'Mudou Bolsa?', 'Bolsa Anterior', 'Bolsa Posterior', 
        'Semestre', 'Gemini Semestre', 'Inscrição', 'Inscrição Anterior', 'Inscrição Posterior', 
        'Bolsista', 'CPF', 'Gemini CPF', 'Gemini Inconsistencias', 'Faculdade', 'Curso', 
        'tipo_bolsa_final', 'qtd_pagtos', 'valor_calculo_bolsa_paga', 'total bolsa paga', 
        
        'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Dif. s/Desc.', '% Dif. s/Desc.', 'Total Dif. s/Desc.', 'MSD_SOMA', 'G_MSD_SOMA', 'MSD_DOC', 
        
        'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Dif. c/Desc.', '% Dif. c/Desc.', 'Total Dif. c/Desc.', 'MCD_SOMA', 'G_MCD_SOMA', 'MCD_DOC', 
        
        '[1] OVG PAGOU (Bolsa Mês)',
        '[2] OVG DEVERIA PAGAR (SISTEMA)', 
        '[3] OVG DEVERIA PAGAR (IA)', 
        '[4] SOMA OVG DEVERIA PAGAR (IA)',
        '[5] SALDO RESTANTE (MCD - Benefícios)', 
        '[6] PREJUÍZO DA OVG (R$)', 
        '[7] LUCRO INDEVIDO IES (R$)', 
        '[8] ECONOMIA DA OVG (R$)',
        'Diagnóstico Financeiro Final',
        
        'valor_beneficio', 'qual_beneficio', 'valor_financiamento', 'qual_financiamento', 'data_coleta',
        'Documento Tipo', 'Check Contrato', 'Check Financiamento', 'Check Benefícios', 'Check RIAF', 'Check Histórico', 
        'Processar', 'Processado', 'Data Processamento', 'Coleta ID'
    ]
    
    cols_ordenadas = [col for col in ordem_desejada if col in df.columns]
    colunas_sujas = ['situacao', 'situacao_atual_sistema', 'sit_data_atual_sistema', 'sit_tipo_atual_sistema', 'sit_obs_atual_sistema']
    cols_extras = [col for col in df.columns if col not in cols_ordenadas and col not in colunas_sujas]
    
    df = df[cols_ordenadas + cols_extras]

    return df

# ==========================================
# 5. GERADOR DE RESUMO QUANTITATIVO
# ==========================================
def gerar_resumo_quantitativo(df_target, tipos_documentos):
    if df_target.empty:
        return pd.DataFrame()
        
    resumo_data = []
    
    for (ies, semestre), group in df_target.groupby(['Faculdade', 'Semestre']):
        
        cpfs_validos = group['CPF'].dropna().unique()
        tot_benef = len(cpfs_validos)
        
        status_por_cpf = group.groupby('CPF')['Status_Vínculo'].apply(lambda x: 'ATIVO' if (x == 'ATIVO').any() else 'DESLIGADO')
        ativos = (status_por_cpf == 'ATIVO').sum()
        desligados = (status_por_cpf == 'DESLIGADO').sum()
        
        row = {
            'IES': ies,
            'Semestre': semestre,
            'Total Beneficiários': tot_benef,
            'Ativos': ativos,
            'Desligados': desligados
        }
        
        for doc_k, doc_name in tipos_documentos.items():
            is_na = False
            if doc_name == DOC_RIAF and str(semestre).split('-')[0].isdigit() and int(str(semestre).split('-')[0]) < 2026:
                is_na = True
            elif doc_name == DOC_HISTORICO and str(semestre).strip() in ["2025-1", "2026-1"]:
                is_na = True
            
            if is_na:
                row[f'Env. {doc_k}'] = "N/A"
                row[f'Pend. {doc_k}'] = "N/A"
                row[f'% {doc_k}'] = "N/A"
                continue
                
            mask_doc = group['Documento Tipo'] == doc_name
            group_doc = group[mask_doc]
            
            # --- A MATEMÁTICA AGORA É LITERAL E TRANSPARENTE ---
            # Conta exatamente as linhas que têm "Ausente" real ou "Corrompido"
            ausentes_reais = group_doc['Status_IA'].isin(['Ausente', 'Ausentes']).sum()
            corrompidos = group_doc['Status_IA'].isin(['Corrompido']).sum()
            
            pendentes_reais = ausentes_reais + corrompidos
            
            # O restante que cumpriu o requisito (ou é Falso Ausente) conta como resolvido/enviado
            enviados = max(0, tot_benef - pendentes_reais)
            
            row[f'Env. {doc_k}'] = enviados
            row[f'Pend. {doc_k}'] = pendentes_reais
            row[f'% {doc_k}'] = enviados / tot_benef if tot_benef > 0 else 0.0
            
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
def gerar_aba_relatorio_ies(writer, df_docs, ano):
    if df_docs.empty or 'Faculdade' not in df_docs.columns:
        return

    workbook = writer.book
    worksheet = workbook.add_worksheet(f'Relatório {ano}')
    
    # Esconde as linhas de grade cinzas de fundo do Excel
    worksheet.hide_gridlines(2)
    
    # --- HELPER: Converte índice de coluna (0-based) para letra Excel ---
    def col_to_letter(idx):
        result = ""
        while idx >= 0:
            result = chr(idx % 26 + ord('A')) + result
            idx = idx // 26 - 1
        return result
    
    # --- MAPEAMENTO DINÂMICO: posição real de cada coluna no DataFrame ---
    cols_list = list(df_docs.columns)
    def get_col(nome):
        if nome in cols_list:
            return col_to_letter(cols_list.index(nome))
        return None
    
    # Colunas-chave para as fórmulas
    COL_FACULDADE = get_col('Faculdade') or 'T'
    COL_SEMESTRE = get_col('Semestre') or 'K'
    COL_STATUS_IA = get_col('Status_IA') or 'A'
    COL_TOTAL_BOLSA = get_col('total bolsa paga') or 'Y'
    COL_INCONSIST = get_col('Gemini Inconsistencias') or 'S'
    COL_DOC_TIPO = get_col('Documento Tipo') or 'BC'
    
    # Mensalidade SEM Desconto (usa valor mensal bruto, não a soma semestral)
    COL_MSD_COLETA = get_col('Mensalidade S/ Desconto') or 'Z'
    COL_MSD_CONTRATO = get_col('Gemini Mensalidade S/ Desconto') or 'AA'
    COL_MSD_DOC = get_col('MSD_DOC') or 'AG'
    COL_MSD_SOMA = get_col('MSD_SOMA') or 'AE'
    COL_G_MSD_SOMA = get_col('G_MSD_SOMA') or 'AF'
    
    # Mensalidade COM Desconto (usa valor mensal bruto, não a soma semestral)
    COL_MCD_COLETA = get_col('Mensalidade C/ Desconto') or 'AH'
    COL_MCD_CONTRATO = get_col('Gemini Mensalidade C/ Desconto') or 'AI'
    COL_MCD_DOC = get_col('MCD_DOC') or 'AO'
    COL_MCD_SOMA = get_col('MCD_SOMA') or 'AM'
    COL_G_MCD_SOMA = get_col('G_MCD_SOMA') or 'AN'
    
    # Bolsa calculada conforme contrato = [2] OVG DEVERIA PAGAR (SISTEMA)
    COL_BOLSA_CALC = get_col('[4] SOMA OVG DEVERIA PAGAR (IA)') or 'AQ'
    
    # Tipo de Bolsa e CPF
    COL_TIPO_BOLSA = get_col('tipo_bolsa_final') or 'V'
    COL_CPF = get_col('CPF') or 'Q'
    
    # Benefícios Extras
    COL_VALOR_FINANC = get_col('valor_financiamento') or 'AZ'
    COL_VALOR_BENEF = get_col('valor_beneficio') or 'AX'
    
    # --- 1. Formatadores Visuais ---
    fmt_branco = workbook.add_format({'bg_color': '#FFFFFF', 'align': 'center', 'valign': 'vcenter'})
    
    fmt_titulo = workbook.add_format({'bold': True, 'font_size': 14, 'valign': 'vcenter', 'align': 'center'})
    fmt_input = workbook.add_format({'valign': 'vcenter', 'align': 'center', 'bold': True}) 

    # 1. Azul Claro (Números e Arquivos)
    fmt_header_azul1 = workbook.add_format({'bold': True, 'bg_color': '#b9cbe2', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_pct_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_money_azul1 = workbook.add_format({'bg_color': '#dde6f0', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': 'R$ #,##0.00'})

    # 2. Roxo (Mensalidades)
    fmt_header_roxo = workbook.add_format({'bold': True, 'bg_color': '#cdc0d9', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_pct_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_money_roxo = workbook.add_format({'bg_color': '#e4dfec', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': 'R$ #,##0.00'})

    # 3. Cinza (Inconsistências)
    fmt_header_cinza = workbook.add_format({'bold': True, 'bg_color': '#bfbfbf', 'font_color': '#000000', 'valign': 'vcenter', 'align': 'center', 'border': 1})
    fmt_cell_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter'})
    fmt_cell_center_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter', 'align': 'center'})
    fmt_pct_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': '0.00%'})
    fmt_money_cinza = workbook.add_format({'bg_color': '#d9d9d9', 'border': 1, 'valign': 'vcenter', 'align': 'center', 'num_format': 'R$ #,##0.00'})

    # --- 2. Ajuste de Largura e Altura ---
    worksheet.set_column('A:A', 65) 
    worksheet.set_column('B:D', 20) 
    worksheet.set_row(0, 90) 
    worksheet.set_row(1, 25) 
    worksheet.set_row(2, 25) 

    # --- 3. Inserir Imagem ---
    worksheet.merge_range('A1:D1', '', fmt_branco)
    
    caminho_imagem = os.path.join('static', 'sources', 'relatorio.png')
    if os.path.exists(caminho_imagem):
        try:
            worksheet.embed_image('A1', caminho_imagem, {'cell_format': fmt_branco})
        except Exception:
            worksheet.insert_image('A1', caminho_imagem, {'object_position': 1, 'x_offset': 5, 'y_offset': 5, 'x_scale': 0.9, 'y_scale': 0.9})

    # --- 4. Menu Suspenso e Títulos ---
    ies_list = sorted(df_docs['Faculdade'].dropna().unique().tolist())
    
    aux_sheet = workbook.add_worksheet(f'Aux_IES_{ano}')
    aux_sheet.hide()
    for i, ies in enumerate(ies_list):
        aux_sheet.write(i, 0, ies)
        
    worksheet.merge_range('A2:D2', 'Relatório Informativo sobre Instituição de Ensino Superior', fmt_titulo)
    
    primeira_ies = ies_list[0] if ies_list else "Selecione a IES..."
    worksheet.merge_range('A3:D3', primeira_ies, fmt_input)
    
    if ies_list:
        worksheet.data_validation('A3', {
            'validate': 'list',
            'source': f'=Aux_IES_{ano}!$A$1:$A${len(ies_list)}',
            'input_title': 'Escolha a IES',
            'input_message': 'Selecione a instituição na lista.'
        })

    # --- 5. Mapeamento das Colunas da Aba Resumo_Quantitativo ---
    mapa_colunas = {
        "Beneficiários Ativos": "D",
        "Beneficiários Inativos": "E",
        "Quantidade de Contratos": "F",
        "Beneficiários sem Contratos Enviados": "G",
        "Quantidade de Financiamentos": "I",
        "Quantidade de Outros Benefícios": "L",
    }

    # --- 6. Estrutura do Relatório ---
    estrutura = [
        ("", False, 0),
        ("Números da IES", True, 1),
        ("Quantidade de Beneficiários", False, 1),
        ("Beneficiários Ativos", False, 1),
        ("Beneficiários Inativos", False, 1),
        ("Valor Total de Bolsas Pagas", False, 1),
        ("Valor Médio da Bolsa (Mensal)", False, 1),
        ("Quantidade de Parciais", False, 1),
        ("Quantidade de Integrais", False, 1),
        ("", False, 0),
        ("Arquivos Enviados", True, 1),
        ("Quantidade de Contratos", False, 1),
        ("Quantidade de Financiamentos", False, 1),
        ("Quantidade de Outros Benefícios", False, 1),
        ("Beneficiários sem Contratos Enviados", False, 1),
        ("", False, 0),
        ("Mensalidade SEM Desconto", True, 2),
        ("Soma na Coleta de Dados", False, 2),
        ("Soma na Coleta de Dados de Contratos Não Enviados", False, 2),
        ("Soma na Coleta de Dados de Contratos Enviados", False, 2),
        ("Soma no Contrato", False, 2),
        ("Diferença entre Contrato e Coleta", False, 2),
        ("Porcentagem de Diferença entre Coleta de Dados (enviados) e Contrato", False, 2),
        ("Qtd. de Contratos com Valores de Acordo com a Coleta de Dados", False, 2),
        ("Qtd. de Contratos com Valor Não Localizado", False, 2),
        ("Qtd. de Contratos com Valor Maior que a Coleta", False, 2),
        ("Qtd. de Contratos com Valor Menor que a Coleta", False, 2),
        ("", False, 0),
        ("Mensalidade COM Desconto", True, 2),
        ("Soma na Coleta de Dados", False, 2),
        ("Soma na Coleta de Dados de Contratos Não Enviados", False, 2),
        ("Soma na Coleta de Dados de Contratos Enviados", False, 2),
        ("Soma no Contrato", False, 2),
        ("Diferença entre Contrato e Coleta", False, 2),
        ("Porcentagem de Diferença entre Coleta de Dados (enviados) e Contrato", False, 2),
        ("Soma Valor de Bolsas Calculadas conforme o Contrato", False, 2),
        ("Porcentagem do Total Pago acima do Valor do Contrato", False, 2),
        ("Qtd. de Contratos com Valores de Acordo com a Coleta de Dados", False, 2),
        ("Qtd. de Contratos com Valor Não Localizado", False, 2),
        ("Qtd. de Contratos com Valor Maior que a Coleta", False, 2),
        ("Qtd. de Contratos com Valor Menor que a Coleta", False, 2),
        ("", False, 0),
        ("Benefícios Extras", True, 1),
        ("Soma de Financiamento", False, 1),
        ("Soma de Outros Benefícios", False, 1),
        ("", False, 0),
        ("Inconsistências", True, 3),
        ("Qtd. de Contratos com Inconsistências de CPF", False, 3),
        ("Qtd. de Contratos com Inconsistências de Semestre Letivo", False, 3)
    ]

    row_idx = 3 
    current_category = ""
    row_valor_total_bolsas = None  # Rastreia a linha do "Valor Total de Bolsas Pagas" para referências dinâmicas
    
    for label, is_header, id_cor in estrutura:
        if is_header:
            current_category = label
            
        if label == "" and not is_header:
            row_idx += 1
            continue
            
        # Define a paleta de cores correta para a linha
        if id_cor == 1:
            cur_fmt_header, cur_fmt_cell, cur_fmt_center, cur_fmt_pct, cur_fmt_money = fmt_header_azul1, fmt_cell_azul1, fmt_cell_center_azul1, fmt_pct_azul1, fmt_money_azul1
        elif id_cor == 2:
            cur_fmt_header, cur_fmt_cell, cur_fmt_center, cur_fmt_pct, cur_fmt_money = fmt_header_roxo, fmt_cell_roxo, fmt_cell_center_roxo, fmt_pct_roxo, fmt_money_roxo
        elif id_cor == 3:
            cur_fmt_header, cur_fmt_cell, cur_fmt_center, cur_fmt_pct, cur_fmt_money = fmt_header_cinza, fmt_cell_cinza, fmt_cell_center_cinza, fmt_pct_cinza, fmt_money_cinza

        if is_header:
            worksheet.write(row_idx, 0, label, cur_fmt_header)
            worksheet.write(row_idx, 1, f'{ano}-1', cur_fmt_header)
            worksheet.write(row_idx, 2, f'{ano}-2', cur_fmt_header)
            worksheet.write(row_idx, 3, 'Variação', cur_fmt_header)
        else:
            excel_row = row_idx + 1 # Linha real no Excel
            worksheet.write(row_idx, 0, label, cur_fmt_cell)
            
            # FÓRMULA DE VARIAÇÃO À PROVA DE FALHAS E DIVISÃO POR ZERO
            form_var = f'=IF($A$3="Selecione a IES...", "", IFERROR(IF(AND(B{excel_row}=0,C{excel_row}=0),0,IF(B{excel_row}=0,1,(C{excel_row}-B{excel_row})/B{excel_row})),""))'

            # 1. Quantidade de Beneficiários
            if label == "Quantidade de Beneficiários":
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUM(B{excel_row+1}:B{excel_row+2}))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUM(C{excel_row+1}:C{excel_row+2}))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            # 2. Valor Total de Bolsas Pagas
            elif label == "Valor Total de Bolsas Pagas":
                row_valor_total_bolsas = excel_row  # Salva para referência dinâmica
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

            # 3. Valor Médio da Bolsa (Mensal)
            elif label == "Valor Médio da Bolsa (Mensal)":
                # Divide o Total de Bolsas Pagas (linha acima) pela Qtd de Beneficiários (que fica engessada na B6/C6 do Excel)
                form_1 = f'=IF($A$3="Selecione a IES...", "", IFERROR((B{excel_row-1}/B6)/6, 0))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", IFERROR((C{excel_row-1}/C6)/6, 0))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

            # 3b. Quantidade de Parciais / Integrais (por CPF único, apenas Ausente/Válido/Inválido)
            elif label in ["Quantidade de Parciais", "Quantidade de Integrais"]:
                tipo_valor = "PARCIAL" if label == "Quantidade de Parciais" else "INTEGRAL"
                doc_cond_bolsa = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                # COUNTIFS por status (Ausente + Válido + Inválido) para ignorar Falso Ausente
                def _count_tipo(per, st):
                    return f'COUNTIFS(Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-{per}", {doc_cond_bolsa}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{st}")'
                form_1 = f'=IF($A$3="Selecione a IES...", "", {_count_tipo(1, "Ausente")} + {_count_tipo(1, "Válido")} + {_count_tipo(1, "Inválido")})'
                form_2 = f'=IF($A$3="Selecione a IES...", "", {_count_tipo(2, "Ausente")} + {_count_tipo(2, "Válido")} + {_count_tipo(2, "Inválido")})'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

            # 4. Casos diretos mapeados no Resumo_Quantitativo
            elif label in mapa_colunas:
                l_col = mapa_colunas[label]
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Resumo_Quantitativo!{l_col}:{l_col}, Resumo_Quantitativo!A:A, $A$3, Resumo_Quantitativo!B:B, "{ano}-1"))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Resumo_Quantitativo!{l_col}:{l_col}, Resumo_Quantitativo!A:A, $A$3, Resumo_Quantitativo!B:B, "{ano}-2"))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            # 5. BLOCO: Mensalidade (SEM Desconto e COM Desconto)
            elif label in [
                "Soma na Coleta de Dados",
                "Soma na Coleta de Dados de Contratos Não Enviados",
                "Soma na Coleta de Dados de Contratos Enviados",
                "Soma no Contrato",
                "Diferença entre Contrato e Coleta",
                "Porcentagem de Diferença entre Coleta de Dados (enviados) e Contrato",
                "Soma Valor de Bolsas Calculadas conforme o Contrato",
                "Porcentagem do Total Pago acima do Valor do Contrato",
                "Qtd. de Contratos com Valores de Acordo com a Coleta de Dados",
                "Qtd. de Contratos com Valor Não Localizado",
                "Qtd. de Contratos com Valor Maior que a Coleta",
                "Qtd. de Contratos com Valor Menor que a Coleta"
            ]:
                # O Python lê dinamicamente se estamos no bloco 'Mensalidade SEM Desconto' ou 'Mensalidade COM Desconto'
                if current_category == "Mensalidade SEM Desconto":
                    col_coleta = COL_MSD_SOMA
                    col_contrato = COL_G_MSD_SOMA
                    col_doc = COL_MSD_DOC
                else:
                    col_coleta = COL_MCD_SOMA
                    col_contrato = COL_G_MCD_SOMA
                    col_doc = COL_MCD_DOC
                
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                def _s(c_sum, per, st=None):
                    if st is None:
                        st = ["Ausente", "Válido", "Inválido"]
                    return " + ".join([f'SUMIFS(Documentos!{c_sum}:{c_sum}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-{per}", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{s}")' for s in st])

                def _c(c_crit, val, per, st=None):
                    if st is None:
                        st = ["Ausente", "Válido", "Inválido"]
                    return " + ".join([f'COUNTIFS(Documentos!{c_crit}:{c_crit}, "{val}", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-{per}", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{s}")' for s in st])

                if label == "Soma na Coleta de Dados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Soma na Coleta de Dados de Contratos Não Enviados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 1, ["Ausente"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 2, ["Ausente"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Soma na Coleta de Dados de Contratos Enviados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 1, ["Válido", "Inválido"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, 2, ["Válido", "Inválido"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Soma no Contrato":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_contrato, 1, ["Válido", "Inválido"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_contrato, 2, ["Válido", "Inválido"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Diferença entre Contrato e Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", B{excel_row-1}-B{excel_row-2})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", C{excel_row-1}-C{excel_row-2})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Porcentagem de Diferença entre Coleta de Dados (enviados) e Contrato":
                    f1 = f'=IF($A$3="Selecione a IES...", "", IFERROR((B{excel_row-2}-B{excel_row-3})/B{excel_row-3}, 0))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", IFERROR((C{excel_row-2}-C{excel_row-3})/C{excel_row-3}, 0))'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Porcentagem do Total Pago acima do Valor do Contrato":
                    # Referência dinâmica à linha do "Valor Total de Bolsas Pagas"
                    ref_bolsas = row_valor_total_bolsas or 9
                    f1 = f'=IF($A$3="Selecione a IES...", "", IFERROR(1-(B{excel_row-1}/B{ref_bolsas}), 0))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", IFERROR(1-(C{excel_row-1}/C{ref_bolsas}), 0))'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Soma Valor de Bolsas Calculadas conforme o Contrato":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(COL_BOLSA_CALC, 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(COL_BOLSA_CALC, 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valores de Acordo com a Coleta de Dados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Coleta de dados conforme documento", 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Coleta de dados conforme documento", 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Não Localizado":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor não localizado no documento", 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor não localizado no documento", 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Maior que a Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Maior", 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Maior", 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Menor que a Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Menor", 1)})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Menor", 2)})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)

            # 6. INCONSISTÊNCIAS (Coringas '*')
            elif label == "Qtd. de Contratos com Inconsistências de CPF":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                c1 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond})'
                c2 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond})'
                f1 = f'=IF($A$3="Selecione a IES...", "", {c1} + {c2})'
                
                c3 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond})'
                c4 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond})'
                f2 = f'=IF($A$3="Selecione a IES...", "", {c3} + {c4})'
                
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            elif label == "Qtd. de Contratos com Inconsistências de Semestre Letivo":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                c1 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond})'
                c2 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond})'
                f1 = f'=IF($A$3="Selecione a IES...", "", {c1} + {c2})'
                
                c3 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond})'
                c4 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond})'
                f2 = f'=IF($A$3="Selecione a IES...", "", {c3} + {c4})'
                
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
            
            # 7. BENEFÍCIOS EXTRAS
            elif label == "Soma de Financiamento":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_VALOR_FINANC}:{COL_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond}))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_VALOR_FINANC}:{COL_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond}))'
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            elif label == "Soma de Outros Benefícios":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_VALOR_BENEF}:{COL_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond}))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_VALOR_BENEF}:{COL_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond}))'
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            # 8. Linhas vazias de segurança
            else:
                worksheet.write(row_idx, 1, '', cur_fmt_center)
                worksheet.write(row_idx, 2, '', cur_fmt_center)
                worksheet.write(row_idx, 3, '', cur_fmt_center)
            
        row_idx += 1

# ==========================================
# 7. MOTOR PRINCIPAL GGCI
# ==========================================
def gerar_relatorio_geral(docs_selecionados=None, anos_selecionados=None, sems_selecionados=None, gerar_relatorio=False):
    print(f"🚀 Iniciando GGCI - Gerando Relatório Geral...\n")
    
    # === AQUI ESTAVA O ERRO! AGORA AS VARIÁVEIS BUSCAM NO PLURAL ===
    if not docs_selecionados or "TODOS" in docs_selecionados:
        docs_selecionados = ["CONTRATOS", "FINANCIAMENTO", "BENEFICIOS", "RIAF", "HISTORICO"]
    if not anos_selecionados or "TODOS" in anos_selecionados:
        anos_selecionados = ["2025", "2026"]
    if not sems_selecionados or "TODOS" in sems_selecionados:
        sems_selecionados = ["1", "2"]
        
    check_contrato = "CONTRATOS" in docs_selecionados
    check_financ = "FINANCIAMENTO" in docs_selecionados
    check_benef = "BENEFICIOS" in docs_selecionados
    check_riaf = "RIAF" in docs_selecionados
    check_historico = "HISTORICO" in docs_selecionados
    
    pode_gerar_relatorio = (check_contrato and check_financ and check_benef and "1" in sems_selecionados and "2" in sems_selecionados)
    
    if gerar_relatorio and not pode_gerar_relatorio:
        print(f"[AVISO | RELATÓRIO | BLOQUEADO] ⚠️ A aba 'Relatório' exige: Contratos, Financiamentos, Benefícios e Semestres 1/2 simultâneos.")
    
    sems_alvo = []
    for ano in anos_selecionados:
        for periodo in sems_selecionados:
            per = "1" if "1" in str(periodo) else "2"
            sems_alvo.append(f"{ano}-{per}")
    
    df_docs = pd.DataFrame()
    df_riaf = pd.DataFrame()
    df_pag = pd.DataFrame()

    if os.path.exists(ARQ_PROCESSADOS):
        df_docs = converter_colunas_para_salvamento(pd.read_excel(ARQ_PROCESSADOS, engine='openpyxl'))
        print(f"📥 Lido: Processados -> {len(df_docs)} linhas base.")
        
    if os.path.exists(ARQ_RIAF):
        df_riaf = converter_colunas_para_salvamento(pd.read_excel(ARQ_RIAF, engine='openpyxl'))
        print(f"📥 Lido: RIAF -> {len(df_riaf)} linhas base.")

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

    # --- CRUZAMENTO COM O AGENDAR PROCESSAMENTOS ---
    if os.path.exists(ARQ_AGENDAR):
        df_agendar = converter_colunas_para_salvamento(pd.read_excel(ARQ_AGENDAR, engine='openpyxl'))
        print(f"📥 Lido: Agendamentos -> Para validação rigorosa de Corrompidos.")
        df_agendar['Semestre'] = df_agendar['Semestre'].astype(str).str.strip().str.replace('/', '-')
        
        if 'Documento Tipo' in df_agendar.columns:
            df_agendar['Documento Tipo'] = df_agendar['Documento Tipo'].apply(limpar_texto_geral).map(mapa_docs_oficiais).fillna(df_agendar['Documento Tipo'])
        
        col_data = 'Data processamento' if 'Data processamento' in df_agendar.columns else 'Data Processamento'
        if col_data not in df_agendar.columns: df_agendar[col_data] = ''
        if 'Processar' not in df_agendar.columns: df_agendar['Processar'] = ''
        if 'Processado' not in df_agendar.columns: df_agendar['Processado'] = ''
        
        df_ag_merge = df_agendar[['Inscrição', 'Semestre', 'Documento Tipo', 'Processar', 'Processado', col_data]].copy()
        df_ag_merge.rename(columns={col_data: 'Data_Processamento_Agendar'}, inplace=True)
        df_ag_merge = df_ag_merge.drop_duplicates(subset=['Inscrição', 'Semestre', 'Documento Tipo'], keep='last')
        
        if not df_docs.empty:
            df_docs = pd.merge(df_docs, df_ag_merge, on=['Inscrição', 'Semestre', 'Documento Tipo'], how='left')
        if not df_riaf.empty:
            df_riaf = pd.merge(df_riaf, df_ag_merge, on=['Inscrição', 'Semestre', 'Documento Tipo'], how='left')

    if os.path.exists(ARQ_PAGAMENTOS):
        df_pag = converter_colunas_para_salvamento(pd.read_excel(ARQ_PAGAMENTOS, engine='openpyxl'))
        print(f"📥 Lido: Pagamentos -> Para cruzamento financeiro e de Ausentes.")

    if not df_pag.empty and (check_contrato or check_financ or check_benef or check_riaf or check_historico):
        print("🔍 Identificando bolsistas sem documentação entregue...")
        
        df_ativos = df_pag[df_pag['SEMESTRE'].isin(sems_alvo)].copy()
        df_ativos = df_ativos[['SEMESTRE', 'UNI_CODIGO', 'UNI_CPF', 'UNI_NOME', 'INS_NOME', 'CUR_NOME']].drop_duplicates(subset=['UNI_CODIGO', 'SEMESTRE'], keep='last')
        
        chaves_docs_entregues = set(zip(df_docs['Inscrição'].astype(str).str.strip(), df_docs['Semestre'].astype(str).str.strip(), df_docs['Documento Tipo'].apply(limpar_texto_geral))) if not df_docs.empty else set()
        chaves_riaf_entregues = set(zip(df_riaf['Inscrição'].astype(str).str.strip(), df_riaf['Semestre'].astype(str).str.strip())) if not df_riaf.empty else set()

        novos_ausentes_docs, novos_ausentes_riaf = [], []
        
        tipos_obrigatorios_geral = []
        tipos_originais = []
        if check_contrato: 
            tipos_obrigatorios_geral.append(limpar_texto_geral(DOC_CONTRATO))
            tipos_originais.append(DOC_CONTRATO)
        if check_financ: 
            tipos_obrigatorios_geral.append(limpar_texto_geral(DOC_FINANC))
            tipos_originais.append(DOC_FINANC)
        if check_benef: 
            tipos_obrigatorios_geral.append(limpar_texto_geral(DOC_BENEF))
            tipos_originais.append(DOC_BENEF)
        if check_historico: 
            tipos_obrigatorios_geral.append(limpar_texto_geral(DOC_HISTORICO))
            tipos_originais.append(DOC_HISTORICO)

        for _, row in df_ativos.iterrows():
            insc, sem = str(row['UNI_CODIGO']).split('.')[0].strip(), str(row['SEMESTRE']).strip()
            nome_aluno, nome_faculdade, nome_curso = limpar_texto_geral(row['UNI_NOME']), limpar_texto_geral(row['INS_NOME']), limpar_texto_geral(row['CUR_NOME'])
            
            for i, tipo_limpo in enumerate(tipos_obrigatorios_geral):
                if (insc, sem, tipo_limpo) not in chaves_docs_entregues:
                    novos_ausentes_docs.append({'Status_IA': 'Ausente', 'Inscrição': row['UNI_CODIGO'], 'Bolsista': nome_aluno, 'CPF': row['UNI_CPF'], 'Semestre': row['SEMESTRE'], 'Faculdade': nome_faculdade, 'Curso': nome_curso, 'Documento Tipo': tipos_originais[i]})

            try:
                ano = int(sem.split('-')[0])
                if check_riaf and ano >= 2026 and (insc, sem) not in chaves_riaf_entregues:
                    novos_ausentes_riaf.append({'Status_IA': 'Ausente', 'Inscrição': row['UNI_CODIGO'], 'Bolsista': nome_aluno, 'CPF': row['UNI_CPF'], 'Semestre': row['SEMESTRE'], 'Faculdade': nome_faculdade, 'Curso': nome_curso, 'Documento Tipo': DOC_RIAF})
            except: pass

        if novos_ausentes_docs:
            df_docs = pd.concat([df_docs, converter_colunas_para_salvamento(pd.DataFrame(novos_ausentes_docs))], ignore_index=True)
            print(f"➕ Injetados {len(novos_ausentes_docs)} registros 'Ausentes' (Docs).")
        if novos_ausentes_riaf:
            df_riaf = pd.concat([df_riaf, converter_colunas_para_salvamento(pd.DataFrame(novos_ausentes_riaf))], ignore_index=True)
            print(f"➕ Injetados {len(novos_ausentes_riaf)} registros 'Ausentes' (Riaf).")

    if not df_docs.empty or not df_riaf.empty:
        print("🗄️ Buscando dados financeiros dos bolsistas...")
        sem_docs = df_docs['Semestre'].dropna().unique().tolist() if not df_docs.empty else []
        sem_riaf = df_riaf['Semestre'].dropna().unique().tolist() if not df_riaf.empty else []
        semestres_presentes = list(set(sem_docs + sem_riaf))
        print("🗄️ Conectando ao sistema de pagamentos...")
        df_financas = buscar_dados_financeiros_sql(semestres_presentes)
        print("✅ Dados financeiros carregados com sucesso.")
    
    def gerar_checks_documentos(df_target):
        if df_target.empty: return df_target
        
        df_target['KEY_TEMP'] = df_target['Inscrição'].astype(str) + "_" + df_target['Semestre'].astype(str)
        mapa_status = {}
        
        for doc_nome in [DOC_CONTRATO, DOC_FINANC, DOC_BENEF, DOC_RIAF, DOC_HISTORICO]:
            entregues = set(df_target[(df_target['Documento Tipo'] == doc_nome) & (~df_target['Status_IA'].isin(['Ausente', 'Ausentes']))]['KEY_TEMP'])
            mapa_status[doc_nome] = entregues
            
        def check_doc(key, doc_nome):
            return "PRESENTE" if key in mapa_status.get(doc_nome, set()) else "PENDENTE"

        def check_riaf(row):
            ano_sem = str(row['Semestre']).split('-')[0]
            if ano_sem.isdigit() and int(ano_sem) < 2026: 
                return "N/A"
            return "PRESENTE" if row['KEY_TEMP'] in mapa_status.get(DOC_RIAF, set()) else "PENDENTE"
        
        def check_historico(row):
            if str(row['Semestre']).strip() in ["2025-1", "2026-1"]:
                return "N/A"
            return "PRESENTE" if row['KEY_TEMP'] in mapa_status.get(DOC_HISTORICO, set()) else "PENDENTE"

        df_target['Check Contrato'] = df_target['KEY_TEMP'].apply(lambda k: check_doc(k, DOC_CONTRATO))
        df_target['Check Financiamento'] = df_target['KEY_TEMP'].apply(lambda k: check_doc(k, DOC_FINANC))
        df_target['Check Benefícios'] = df_target['KEY_TEMP'].apply(lambda k: check_doc(k, DOC_BENEF))
        df_target['Check RIAF'] = df_target.apply(check_riaf, axis=1)
        df_target['Check Histórico'] = df_target.apply(check_historico, axis=1)
        
        df_target.drop(columns=['KEY_TEMP'], inplace=True)
        return df_target

    if not df_docs.empty:
        print("🤖 Calculando auditorias e cruzando dados financeiros (Documentos)...")
        df_docs = mesclar_sql_e_reordenar(df_docs, df_financas, df_pag)
        df_docs = aplicar_transicoes(df_docs, df_pag)
        df_docs = calcular_auditoria_ia(df_docs)
        df_docs = gerar_checks_documentos(df_docs)
        
    if not df_riaf.empty:
        print("🤖 Calculando auditorias e cruzando dados financeiros (RIAF)...")
        df_riaf = mesclar_sql_e_reordenar(df_riaf, df_financas, df_pag)
        df_riaf = aplicar_transicoes(df_riaf, df_pag)
        df_riaf = calcular_auditoria_ia(df_riaf)
        df_riaf = gerar_checks_documentos(df_riaf)

    for df_target in [df_docs, df_riaf]:
        if not df_target.empty:
            if 'Data_Processamento_Agendar' in df_target.columns:
                df_target['Data Processamento'] = df_target['Data_Processamento_Agendar']
                df_target.drop(columns=['Data_Processamento_Agendar'], inplace=True)
            if 'Data Processamento' in df_target.columns: 
                df_target['Data Processamento'] = df_target['Data Processamento'].fillna('')
            
            colunas_remover = ['Processar', 'Processado', 'situacao', 'situacao_atual_sistema', 
                               'sit_data_atual_sistema', 'sit_tipo_atual_sistema', 'sit_obs_atual_sistema']
            df_target.drop(columns=colunas_remover, inplace=True, errors='ignore')

    if not df_docs.empty or not df_riaf.empty:
        print(f"💾 Finalizando e gerando o Relatório Geral...")
        writer = pd.ExcelWriter(ARQUIVO_GERAL_SAIDA, engine='xlsxwriter')
        
        if not df_docs.empty:
            print(f"💾 Gerando aba Documentos ({len(df_docs)} linhas)...")
            df_docs.sort_values(by=['Faculdade', 'Bolsista'], inplace=True)
            df_docs.to_excel(writer, sheet_name='Documentos', index=False)
            aplicar_formatacao_visual(writer, 'Documentos', df_docs)
            
        if not df_riaf.empty:
            print(f"💾 Gerando aba Riaf ({len(df_riaf)} linhas)...")
            df_riaf.sort_values(by=['Faculdade', 'Bolsista'], inplace=True)
            df_riaf.to_excel(writer, sheet_name='Riaf', index=False)
            aplicar_formatacao_visual(writer, 'Riaf', df_riaf)
            
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
        
        print(f"💾 Processando Resumo Quantitativo...")
        df_resumo_geral = gerar_resumo_quantitativo(df_master_resumo, tipos_resumo)
        
        if not df_resumo_geral.empty:
            df_resumo_geral.to_excel(writer, sheet_name='Resumo_Quantitativo', index=False)
            aplicar_formatacao_visual(writer, 'Resumo_Quantitativo', df_resumo_geral)
            
        if not df_docs.empty and gerar_relatorio:
            if pode_gerar_relatorio:
                print(f"💾 Gerando Abas Gerenciais (Relatório IES)...")
                for ano in anos_selecionados:
                    gerar_aba_relatorio_ies(writer, df_docs, ano)
            else:
                print(f"[AVISO | RELATÓRIO | BLOQUEADO] ⚠️ Aba 'Relatório' ignorada. Requisitos de documentos ou semestres não preenchidos.")
            
        print(f"💾 Salvando e compilando arquivo físico...")
        writer.close()
        print(f"🎉 SUPER-EXTRAÇÃO CONCLUÍDA E SALVA")
    else:
        print("❌ Falha: Nenhum dado processado de acordo com os filtros informados.")