import os
import sys
import pandas as pd
import numpy as np
import unicodedata
import re
import datetime
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env)
load_dotenv()

# Desativa o aviso do futuro do Pandas para preenchimento de dados vazios
pd.set_option('future.no_silent_downcasting', True)

# ==========================================
# 1. CAMINHOS DE ENTRADA E SAÍDA
# ==========================================









# ==========================================
# 2. FUNÇÕES DE LIMPEZA E FORMATAÇÃO
# ==========================================
COLS_NUM = ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Cnpj Faculdade', 'UNI_CODIGO', 'UNI_CPF', 'inscricao_ano_semestre']
COLS_MOEDA = [
    'Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 
    'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 
    'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
    'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto', 
    'valor_beneficio', 'Soma Valor Beneficio', 'valor_financiamento', 'Soma Valor Financiamento', 
    'último_valor_pago_referencia', 'total bolsa paga', 
    'MSD_SOMA', 'G_MSD_SOMA', 'MCD_SOMA', 'G_MCD_SOMA', 
    '[1] OVG PAGOU (Último Referencial)',
    '[2] OVG DEVERIA PAGAR (Último Referencial)', 
    '[3] SOMA OVG PAGOU',
    '[4] SOMA OVG DEVERIA PAGAR (SISTEMA)',
    '[5] OVG DEVERIA PAGAR (IA)', 
    '[6] SOMA OVG DEVERIA PAGAR (IA)',
    '[7] PREJUÍZO DA OVG (R$)',
    '[8] SOMA PREJUÍZO DA OVG (R$)',
    '[9] ECONOMIA DA OVG (R$)',
    'VALOR_CONTRATO_APURADO', 'VALOR_PAGAMENTO', 'VALOR_PAGAMENTO2', 
    'VALOR_COMPLEMENTO', 'VALOR_CANCELAMENTO', 'LAN_VALBOLSA',
    'CD_sem_desconto', 'CD_com_desconto', 'CD_beneficios', 'CD_financiamentos'
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

def aplicar_formatacao_visual(writer, nome_aba, df, startrow=0, subtitulo_ies=""):
    workbook = writer.book
    worksheet = writer.sheets[nome_aba]
    
    # --- 1. Definição de Formatos Numéricos Base ---
    fmt_cpf = workbook.add_format({'num_format': '00000000000', 'valign': 'vcenter'})
    fmt_cnpj = workbook.add_format({'num_format': '00000000000000', 'valign': 'vcenter'}) 
    fmt_num = workbook.add_format({'num_format': '0', 'valign': 'vcenter', 'align': 'center'})
    fmt_moeda = workbook.add_format({'num_format': 'R$ #,##0.00;[Red]-R$ #,##0.00', 'valign': 'vcenter'}) 
    fmt_pct = workbook.add_format({'num_format': '0.00%', 'valign': 'vcenter', 'align': 'center'})
    fmt_padrao = workbook.add_format({'valign': 'vcenter'})
    
    if startrow > 0:
        import os
        fmt_branco = workbook.add_format({'bg_color': '#FFFFFF'})
        worksheet.set_row(0, 90)
        worksheet.merge_range('A1:D1', '', fmt_branco)
        
        caminho_imagem = os.path.join('static', 'img', 'icones', 'relatorio.png')
        if os.path.exists(caminho_imagem):
            try:
                worksheet.embed_image('A1', caminho_imagem, {'cell_format': fmt_branco})
            except Exception:
                worksheet.insert_image('A1', caminho_imagem, {'object_position': 1, 'x_offset': 5, 'y_offset': 5, 'x_scale': 0.9, 'y_scale': 0.9})
                
    if startrow >= 4:
        fmt_t1 = workbook.add_format({'bold': True, 'font_size': 12, 'valign': 'vcenter'})
        fmt_t2 = workbook.add_format({'bold': True, 'font_size': 12, 'valign': 'vcenter'})
        fmt_t3 = workbook.add_format({'bold': True, 'italic': True, 'font_size': 11, 'valign': 'vcenter'})
        
        if nome_aba == 'Enquadramento':
            worksheet.write('A2', 'BENEFICIÁRIOS CADASTRADOS NO PROGRAMA UNIVERSITÁRIO DO BEM', fmt_t1)
            worksheet.write('A3', subtitulo_ies, fmt_t2)
            worksheet.write('A4', 'CONSULTA ENQUADRAMENTO DE CURSOS -  Decreto nº 12.456/2025 / Portaria 378/2025', fmt_t3)
        elif nome_aba == 'e-MEC':
            worksheet.write('A2', subtitulo_ies, fmt_t2)
            worksheet.write('A3', 'CONSULTA ENQUADRAMENTO DE CURSOS -  Decreto nº 12.456/2025 / Portaria 378/2025', fmt_t3)
    
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
    f_verde = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'border': 1})
    f_verm  = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1})
    f_amar  = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500', 'border': 1})
    f_cinza = workbook.add_format({'bg_color': '#D9D9D9', 'font_color': '#595959', 'border': 1})

    max_row = len(df)
    max_col = len(df.columns) - 1

    # --- 4. Aplicar Tabela Oficial (Com o nosso cabeçalho forçado) ---
    col_settings = [{'header': str(col), 'header_format': fmt_header} for col in df.columns]
    worksheet.add_table(startrow, 0, startrow + max_row, max_col, {
        'columns': col_settings,
        'style': 'Table Style Light 1' # Tema base mais limpo para destacar nossas cores
    })
    
    worksheet.freeze_panes(startrow + 1, 0)
    worksheet.set_row(startrow, 35) 

    # --- 5. Ajustar Larguras das Colunas Dinamicamente (Auto-Fit Inteligente) ---
    larguras_enquadramento = [105.29, 41.86, 11.29, 12.57, 25.86, 16.43, 11.71, 11.57, 17.14, 25.86, 30, 26.57, 20.57, 16.14]
    larguras_emec = [105.29, 23.14, 25.86, 25.86, 20.0, 30.0, 35.0, 15.0, 20.0, 20.0, 25.0, 30.0, 30.0, 15.0, 15.0, 35.0, 40.0, 45.0, 30.0]

    for i, col in enumerate(df.columns):
        col_upper = str(col).upper()
        
        if '%' in col_upper: fmt_aplicar = fmt_pct
        elif 'CNPJ' in col_upper: fmt_aplicar = fmt_cnpj
        elif 'CPF' in col_upper: fmt_aplicar = fmt_cpf
        elif col in COLS_NUM or col == 'qtd_pagtos': fmt_aplicar = fmt_num
        elif col in COLS_MOEDA or 'DIF.' in col_upper or 'BOLSA PAGA' in col_upper: fmt_aplicar = fmt_moeda
        else: fmt_aplicar = fmt_padrao

        if nome_aba == 'Enquadramento' and i < len(larguras_enquadramento):
            worksheet.set_column(i, i, larguras_enquadramento[i], fmt_aplicar)
        elif nome_aba == 'e-MEC' and i < len(larguras_emec):
            worksheet.set_column(i, i, larguras_emec[i], fmt_aplicar)
        else:
            # A mágica: lê a maior string DENTRO da coluna e compara com o título
            tamanho_conteudo = df[col].map(lambda x: len(str(x)) if pd.notna(x) else 0).max() if not df.empty else 0
            largura_ideal = max(tamanho_conteudo, len(str(col))) + 3 # +3 de respiro para a seta do filtro
            
            if largura_ideal > 50: largura_ideal = 50 # Trava em 50 para colunas como "Inconsistências" não ocuparem a tela toda
            
            # Aplica a largura ideal calculada com a formatação correta
            if fmt_aplicar == fmt_pct: worksheet.set_column(i, i, max(12, largura_ideal), fmt_aplicar)
            elif fmt_aplicar == fmt_cnpj: worksheet.set_column(i, i, max(18, largura_ideal), fmt_aplicar)
            elif fmt_aplicar == fmt_cpf: worksheet.set_column(i, i, max(16, largura_ideal), fmt_aplicar)
            elif fmt_aplicar == fmt_num: worksheet.set_column(i, i, max(12, largura_ideal), fmt_aplicar)
            elif fmt_aplicar == fmt_moeda: worksheet.set_column(i, i, max(18, largura_ideal), fmt_aplicar)
            else: worksheet.set_column(i, i, largura_ideal, fmt_aplicar)

    # --- 6. Formatação Condicional (O Semáforo Padronizado) ---
    # Aplica bordas finas em toda a tabela primeiro (para que não se espalhe pelas colunas infinitas)
    fmt_borda_tabela = workbook.add_format({'border': 1})
    worksheet.conditional_format(startrow + 1, 0, startrow + max_row, max_col, {'type': 'no_blanks', 'format': fmt_borda_tabela})
    worksheet.conditional_format(startrow + 1, 0, startrow + max_row, max_col, {'type': 'blanks', 'format': fmt_borda_tabela})
    
    for i, col in enumerate(df.columns):
        
        # Validações de Lista (Menus Suspensos) para e-MEC
        if nome_aba == 'e-MEC' and max_row > 0:
            col_str = str(col).strip().upper()
            if col_str == 'ATO REGULATORIO (ULTIMO VIGENTE)':
                worksheet.data_validation(startrow + 1, i, startrow + max_row, i, {
                    'validate': 'list',
                    'source': ['Renovação de reconhecimento de curso', 'Autorização Vinculada', 'Reconhecimento de curso']
                })
            elif col_str == 'OFERTA PARA INGRESSANTES EM 2026.2 (PROBEM)?':
                worksheet.data_validation(startrow + 1, i, startrow + max_row, i, {
                    'validate': 'list',
                    'source': ['Sim', 'Não', 'Exclusivo para veteranos']
                })
            elif col_str == 'GRAU':
                worksheet.data_validation(startrow + 1, i, startrow + max_row, i, {
                    'validate': 'list',
                    'source': ['Bacharelado', 'Licenciatura', 'Tecnólogo']
                })

        # Status da IA e Auditoria
        if col == 'Status_IA':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Válido"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Inválido"', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Ausente"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'Falso', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Documento não processado"', 'format': f_cinza})

        # Diagnóstico Financeiro Final
        elif col == 'Diagnóstico Financeiro Final':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"Pagamento correto"', 'format': f_verde})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a mais"', 'format': f_verm})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '==', 'value': '"OVG pagou a menos"', 'format': f_amar})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não localizado', 'format': f_cinza})
            worksheet.conditional_format(1, i, max_row, i, {'type': 'text', 'criteria': 'containing', 'value': 'não realizado', 'format': f_cinza})

        # Alertas de OVG DEVERIA PAGAR (Pinta de vermelho o bloco se for menor que 0)
        elif col in ['[2] OVG DEVERIA PAGAR (Último Referencial)', '[5] OVG DEVERIA PAGAR (IA)']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '<', 'value': 0, 'format': f_verm})

        # Alerta para Diferenças de Mensalidade (Qualquer divergência acende o bloco vermelho)
        elif col in ['Dif. s/Desc.', 'Total Dif. s/Desc.', 'Dif. c/Desc.', 'Total Dif. c/Desc.']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '!=', 'value': 0, 'format': f_verm})
        
        # Alerta Financeiro Vermelho (Prejuízos gritam em vermelho se for maior que 0)
        elif col in ['[7] PREJUÍZO DA OVG (R$)', '[8] SOMA PREJUÍZO DA OVG (R$)']:
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verm})
            
        # NOVA COLUNA: Economia da OVG (Grita em VERDE se for maior que 0)
        elif col == '[9] ECONOMIA DA OVG (R$)':
            worksheet.conditional_format(1, i, max_row, i, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': f_verde})
            
    # --- 7. Ocultar Linhas de Grade de Fundo ---
    worksheet.hide_gridlines(2)
        
# ==========================================
# 3. EXTRAÇÃO FINANCEIRA VIA SQL
# ==========================================
def buscar_dados_financeiros_sql(semestres_presentes):
    if not semestres_presentes: return pd.DataFrame()
    
    DB_HOST = os.getenv('SIBU_BANCO_DADOS_HOST')
    DB_USER = os.getenv('SIBU_BANCO_DADOS_USER')
    DB_PASS = os.getenv('SIBU_BANCO_DADOS_PASS')
    DB_NAME = os.getenv('SIBU_BANCO_DADOS_NAME')
    
    sems_banco = [str(x).strip().replace('-', '/') for x in semestres_presentes]
    sems_formatados = ",".join([f"'{x}'" for x in sems_banco])
    
    query = f"""
        SELECT 
            v.uni_codigo, v.semestre, v.tipo_bolsa_final, v.qtd_pagtos, v.valor_ultima_bolsa_paga AS último_valor_pago_referencia,
            v.valor_mensalidade_sem_desconto, v.valor_mensalidade_com_desconto,
            v.situacao, v.situacao_atual_sistema, v.sit_data_atual_sistema, v.sit_obs_atual_sistema,
            v.valor_beneficio, v.qual_beneficio, v.valor_financiamento, v.qual_financiamento,
            v.data_create AS data_coleta,
            v.inscricao_ano_semestre, v.uni_deficiencia, v.uni_sexo, v.tipo_bolsista_renovacao, v.tipo_veterano_ingresso,
            b.uni_nome, b.uni_cpf, b.ins_nome, b.cur_nome
        FROM sibu.PY_ggci_analise_IA_completa v
        LEFT JOIN sibu.bolsistas b ON v.uni_codigo = b.uni_codigo
        WHERE v.semestre IN ({sems_formatados})
    """
    
    try:
        engine = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}/{DB_NAME}',
            connect_args={'connect_timeout': 30, 'read_timeout': 300} 
        )
        print("🗄️ Conectando ao banco de dados...")
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
                
            cols_absolutas = ['situacao_atual_sistema', 'sit_data_atual_sistema', 'sit_obs_atual_sistema', 'inscricao_ano_semestre', 'uni_deficiencia', 'uni_sexo', 'tipo_bolsista_renovacao', 'tipo_veterano_ingresso']
            for col in cols_absolutas:
                if col in df_merged.columns:
                    df_merged[col] = df_merged[col].replace(['', None, 'nan', 'NaN'], np.nan)
                    df_merged[col] = df_merged.groupby('uni_codigo')[col].transform(lambda x: x.ffill().bfill())
                
            valores_para_zerar = {
                'qtd_pagtos': 0, 'último_valor_pago_referencia': 0.0,
                'valor_mensalidade_sem_desconto': 0.0, 'valor_mensalidade_com_desconto': 0.0,
                'situacao': '', 'situacao_atual_sistema': '',
                'sit_data_atual_sistema': '', 'sit_obs_atual_sistema': '',
                'valor_beneficio': 0.0, 'valor_financiamento': 0.0,
                'qual_beneficio': 'Sem outros benefícios', 'qual_financiamento': 'Sem financiamento',
                'data_coleta': '',
                'inscricao_ano_semestre': '', 'uni_deficiencia': '', 'uni_sexo': '', 'tipo_bolsista_renovacao': '', 'tipo_veterano_ingresso': ''
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
            df_sql['valor_mensalidade_sem_desconto'] = pd.to_numeric(df_sql['valor_mensalidade_sem_desconto'], errors='coerce').fillna(0.0)
            df_sql['valor_mensalidade_com_desconto'] = pd.to_numeric(df_sql['valor_mensalidade_com_desconto'], errors='coerce').fillna(0.0)
            
            # Formatação numérica nativa
            df_sql['valor_beneficio'] = pd.to_numeric(df_sql['valor_beneficio'], errors='coerce').fillna(0.0)
            df_sql['valor_financiamento'] = pd.to_numeric(df_sql['valor_financiamento'], errors='coerce').fillna(0.0)
            
            df_sql = df_sql.drop_duplicates(subset=['uni_codigo', 'semestre'], keep='last')
            print("[OK] Dados carregados com sucesso.")
            
        return df_sql
    except Exception as e:
        print(f"\n   ⚠️ ERRO CRÍTICO: Não foi possível conectar ao banco de dados SQL.")
        print(f"   Detalhes do erro: {e}")
        print("   Abortando a execução do GGCI pois os dados do banco são indispensáveis para o relatório.")
        sys.exit(1)
        
def buscar_dados_pagamentos_mes_a_mes_sql(semestres_presentes):
    """ Extrai o histórico financeiro mês a mês da View Descompactada. """
    if not semestres_presentes: return pd.DataFrame()
    
    DB_HOST = os.getenv('SIBU_BANCO_DADOS_HOST')
    DB_USER = os.getenv('SIBU_BANCO_DADOS_USER')
    DB_PASS = os.getenv('SIBU_BANCO_DADOS_PASS')
    DB_NAME = os.getenv('SIBU_BANCO_DADOS_NAME')
    
    sems_banco = [str(x).strip().replace('-', '/') for x in semestres_presentes]
    sems_formatados = ",".join([f"'{x}'" for x in sems_banco])
    
    query = f"""
        SELECT 
            uni_codigo, lan_anomes, semestre, valr_bolsa,
            CD_sem_desconto, CD_com_desconto, CD_beneficios, CD_financiamentos, data_coleta
        FROM sibu.PY_ggci_analise_IA_descompactada
        WHERE semestre IN ({sems_formatados})
    """
    
    try:
        engine = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}/{DB_NAME}',
            connect_args={'connect_timeout': 30, 'read_timeout': 300} 
        )
        pass
        df_sql_mes = pd.read_sql(query, engine)
        
        if not df_sql_mes.empty:
            df_sql_mes['uni_codigo'] = pd.to_numeric(df_sql_mes['uni_codigo'], errors='coerce').astype('Int64')
            # Padroniza "2025/1" para "2025-1" igual ao Excel
            df_sql_mes['semestre'] = df_sql_mes['semestre'].astype(str).str.replace('/', '-').str.strip()
            
        return df_sql_mes
    except Exception as e:
        print(f"\n   ⚠️ ERRO: Não foi possível puxar a view descompactada. Detalhes: {e}")
        return pd.DataFrame()

def mesclar_sql_e_reordenar(df, df_sql, df_pag=None, df_mes_a_mes=None):
    if df.empty: return df
    
    if not df_sql.empty:
        df['Inscrição'] = pd.to_numeric(df['Inscrição'], errors='coerce').astype('Int64')
        df['Semestre'] = df['Semestre'].astype(str).str.strip().str.replace('/', '-')
        
        df_sql['uni_codigo'] = pd.to_numeric(df_sql['uni_codigo'], errors='coerce').astype('Int64')
        df_sql['semestre'] = df_sql['semestre'].astype(str).str.strip().str.replace('/', '-')

        df = pd.merge(df, df_sql, left_on=['Inscrição', 'Semestre'], right_on=['uni_codigo', 'semestre'], how='left')
        df.drop(columns=['uni_codigo', 'semestre'], errors='ignore', inplace=True)
        
    for col in ['tipo_bolsa_final', 'qtd_pagtos', 'último_valor_pago_referencia']:
        if col not in df.columns: df[col] = "SEM DADOS" if col == 'tipo_bolsa_final' else 0

    df['tipo_bolsa_final'] = df.groupby('Inscrição')['tipo_bolsa_final'].transform(lambda x: x.ffill().bfill()).fillna("SEM DADOS")
    df['qtd_pagtos'] = pd.to_numeric(df['qtd_pagtos'], errors='coerce').fillna(0).astype(int)
    df['último_valor_pago_referencia'] = pd.to_numeric(df['último_valor_pago_referencia'], errors='coerce').fillna(0.0)
    
    # --- RECALCULAR pagamentos a partir do consolidado ---
    if df_pag is not None and not df_pag.empty and 'LAN_VALBOLSA' in df_pag.columns:
        print("📊 Recalculando cruzamentos...")
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
            df_mm.sort_values(by=['uni_codigo', 'semestre', 'lan_anomes'], inplace=True)
            df_mm['row_idx'] = df_mm.groupby(['uni_codigo', 'semestre']).cumcount()
            
            # Mesclando os dados da Coleta do mês para dentro do pagamento
            df_pag_calc = pd.merge(
                df_pag_calc, 
                df_mm[['uni_codigo', 'semestre', 'row_idx', 'CD_com_desconto', 'CD_beneficios', 'CD_financiamentos']],
                left_on=['UNI_CODIGO', 'SEMESTRE', 'row_idx'],
                right_on=['uni_codigo', 'semestre', 'row_idx'],
                how='left'
            )
            
            df_pag_calc['CD_com_desconto'] = pd.to_numeric(df_pag_calc['CD_com_desconto'], errors='coerce').fillna(0.0)
            df_pag_calc['CD_beneficios'] = pd.to_numeric(df_pag_calc['CD_beneficios'], errors='coerce').fillna(0.0)
            df_pag_calc['CD_financiamentos'] = pd.to_numeric(df_pag_calc['CD_financiamentos'], errors='coerce').fillna(0.0)
            
            # CÁLCULO MÊS A MÊS DO TETO DO SISTEMA
            curso_str = df_pag_calc['CUR_NOME'].astype(str).str.strip().str.upper()
            is_med_odonto = curso_str.isin(['MEDICINA', 'ODONTOLOGIA'])
            # Correção: .str.upper() para aplicar na Series inteira
            bolsa_str = df_pag_calc['TIPO_BOLSA'].astype(str).str.strip().str.upper()
            
            sys_mcd_50 = df_pag_calc['CD_com_desconto'] * 0.5
            sys_calc_parcial = np.where(is_med_odonto, np.minimum(sys_mcd_50, 2900.0), np.minimum(sys_mcd_50, 650.0))
            sys_calc_integral = np.where(is_med_odonto, np.minimum(df_pag_calc['CD_com_desconto'], 5800.0), np.minimum(df_pag_calc['CD_com_desconto'], 1500.0))
            sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
            sys_base_calculo = df_pag_calc['CD_com_desconto']
            
            sys_excedeu = (sys_bolsa_base + df_pag_calc['CD_beneficios']) > sys_base_calculo
            sys_bolsa_final_mes = np.where(sys_excedeu, sys_base_calculo - df_pag_calc['CD_beneficios'], sys_bolsa_base)
            
            lan_valor_complemento = pd.to_numeric(df_pag_calc.get('lan_valor_complemento', 0), errors='coerce').fillna(0.0)
            lan_valor_cancelamento = pd.to_numeric(df_pag_calc.get('lan_valor_cancelamento', 0), errors='coerce').fillna(0.0)
            sys_bolsa_final_mes_limit = np.maximum(sys_bolsa_final_mes, 0.0)
            sys_bolsa_final_mes_adjusted = sys_bolsa_final_mes_limit + lan_valor_complemento - lan_valor_cancelamento
            
            df_pag_calc['deveria_pagar_sistema_mes'] = np.where(df_pag_calc['LAN_VALBOLSA'].fillna(0) > 0, np.maximum(sys_bolsa_final_mes_adjusted, 0.0), 0.0)
        else:
            df_pag_calc['deveria_pagar_sistema_mes'] = 0.0

        # Agrupa pegando TOTAL de pagamentos e a SOMA DO SISTEMA CALCULADA
        df_pag_resumo = df_pag_calc.groupby(['UNI_CODIGO', 'SEMESTRE']).agg(
            qtd_pagtos_total=('LAN_VALBOLSA', 'count'),
            qtd_pagtos_retroativos=('LAN_VALBOLSA', lambda x: (x == 0).sum()),
            total_bolsa_real=('LAN_VALBOLSA', 'sum'),
            soma_sistema=('deveria_pagar_sistema_mes', 'sum'),
            soma_cd_beneficios=('CD_beneficios', 'sum'),
            soma_cd_financiamentos=('CD_financiamentos', 'sum')
        ).reset_index()

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
        
        mask_tem_pag = df['qtd_pagtos_total'].notna()
        df.loc[mask_tem_pag, 'qtd_pagtos'] = df.loc[mask_tem_pag, 'qtd_pagtos_total'].astype(int)
        df.loc[mask_tem_pag, 'último_valor_pago_referencia'] = df.loc[mask_tem_pag, 'valor_calculo_real']
        df['qtd_pagtos_retroativos'] = pd.to_numeric(df.get('qtd_pagtos_retroativos', 0), errors='coerce').fillna(0).astype(int)

        # --- NOVO PERFIL DO BENEFICIARIO ---
        if 'data_ingresso' in df.columns:
            dt_ingresso = pd.to_datetime(df['data_ingresso'], dayfirst=True, errors='coerce')
            sem_ingresso = dt_ingresso.dt.year.astype(str) + '-' + np.where(dt_ingresso.dt.month <= 6, '1', '2')
            semestre_str = df['Semestre'].astype(str).str.strip()
            df['Perfil do Beneficiario'] = np.where(pd.isna(sem_ingresso), "Não Informado", 
                                            np.where(semestre_str > sem_ingresso, "Veterano", "Ingressante"))
        else:
            df['Perfil do Beneficiario'] = "Não Informado"

        
        df['total bolsa paga'] = df['qtd_pagtos'] * df['último_valor_pago_referencia']  
        df.loc[mask_tem_pag, 'total bolsa paga'] = df.loc[mask_tem_pag, 'total_bolsa_real']
        
        # INJETANDO A SOMA DO SISTEMA (Mês a Mês calculado)
        df['soma_deveria_sistema'] = 0.0
        df.loc[mask_tem_pag, 'soma_deveria_sistema'] = df.loc[mask_tem_pag, 'soma_sistema']
        df['tem_pagamento_historico'] = mask_tem_pag
        
        df['Soma Valor Beneficio'] = 0.0
        if 'soma_cd_beneficios' in df.columns:
            df.loc[mask_tem_pag, 'Soma Valor Beneficio'] = df.loc[mask_tem_pag, 'soma_cd_beneficios']
            
        df['Soma Valor Financiamento'] = 0.0
        if 'soma_cd_financiamentos' in df.columns:
            df.loc[mask_tem_pag, 'Soma Valor Financiamento'] = df.loc[mask_tem_pag, 'soma_cd_financiamentos']

        df.drop(columns=['UNI_CODIGO', 'SEMESTRE', 'qtd_pagtos_total', 'valor_calculo_real', 'total_bolsa_real', 'soma_sistema', 'tipo_bolsa_pag', 'soma_cd_beneficios', 'soma_cd_financiamentos'], errors='ignore', inplace=True)
    
    else:
        df['total bolsa paga'] = df['qtd_pagtos'] * df['último_valor_pago_referencia']
        df['qtd_pagtos_retroativos'] = 0
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
            
        if 'valor_mensalidade_sem_desconto' in df.columns:
            df.loc[mask_ausente, 'Mensalidade S/ Desconto'] = df.loc[mask_ausente, 'valor_mensalidade_sem_desconto']
            df.loc[mask_ausente, 'Gemini Mensalidade S/ Desconto'] = 0.0
            df.drop(columns=['valor_mensalidade_sem_desconto'], inplace=True)

        if 'valor_mensalidade_com_desconto' in df.columns:
            df.loc[mask_ausente, 'Mensalidade C/ Desconto'] = df.loc[mask_ausente, 'valor_mensalidade_com_desconto']
            df.loc[mask_ausente, 'Gemini Mensalidade C/ Desconto'] = 0.0
            df.drop(columns=['valor_mensalidade_com_desconto'], inplace=True)
            
    
    if 'sit_motivos' in df.columns: df['sit_motivos'] = df['sit_motivos'].fillna("-")
    if 'sit_obs' in df.columns: df['sit_obs'] = df['sit_obs'].fillna("-")
    
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
        val_ultima = pd.to_numeric(row.get('último_valor_pago_referencia', 0), errors='coerce')
        if pd.isna(val_ultima): val_ultima = 0.0
        
        # Se a IA listou como Ausente, mas migrou de IES e o pgto é retroativo/zero -> Falso Ausente!
        if ia_st in ['Ausente', 'Ausentes']:
            if has_insc_post and val_ultima == 0.0:
                return 'Falso Ausente'
        
        # --- REGRA DO CORROMPIDO ---
        processar = get_primeiro_valido(row, ['Processar', 'Processar_y', 'Processar_x']).upper()
        processado = get_primeiro_valido(row, ['Processado', 'Processado_y', 'Processado_x']).upper()
        d_proc = get_primeiro_valido(row, ['Data Processamento', 'Data Processamento_y', 'Data Processamento_x'])
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
    
    d_proc_series = df.get('Data Processamento', pd.Series(['']*len(df), index=df.index))
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
    
    # Calculate effective months paid multiplier (to account for retroactives in total bolsa paga)
    paga_mensal = pd.to_numeric(df.get('último_valor_pago_referencia', 0), errors='coerce').fillna(0.0)
    total_pago = pd.to_numeric(df.get('total bolsa paga', 0), errors='coerce').fillna(0.0)
    qtd_pagtos_float = qtd.astype(float)
    
    # Where paga_mensal > 0, effective multiplier = total_pago / paga_mensal. Otherwise, fallback to qtd_pagtos
    multiplier = np.where(paga_mensal > 0, total_pago / paga_mensal, qtd_pagtos_float)
    
    tot_dif_s = dif_s * multiplier
    tot_dif_c = dif_c * multiplier

    df['MSD_SOMA'] = msd_sys * multiplier
    df['G_MSD_SOMA'] = msd_ia * multiplier
    df['MCD_SOMA'] = mcd_sys * multiplier
    df['G_MCD_SOMA'] = mcd_ia * multiplier

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
    paga = pd.to_numeric(df.get('último_valor_pago_referencia', 0), errors='coerce').fillna(0.0)
    
    df['[1] OVG PAGOU (Último Referencial)'] = paga
    df['[3] SOMA OVG PAGOU'] = df.get('total bolsa paga', 0.0)

    is_med_odonto = curso_str.isin(['MEDICINA', 'ODONTOLOGIA'])
    is_contrato = df['Documento Tipo'] == 'CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA'
    
    # [2] Referência do Sistema
    sys_mcd_50 = mcd_sys * 0.5
    sys_calc_parcial = np.where(is_med_odonto, np.minimum(sys_mcd_50, 2900.0), np.minimum(sys_mcd_50, 650.0))
    sys_calc_integral = np.where(is_med_odonto, np.minimum(mcd_sys, 5800.0), np.minimum(mcd_sys, 1500.0))
    sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
    
    sys_excedeu = (sys_bolsa_base + beneficios) > mcd_sys
    sys_bolsa_final = np.where(sys_excedeu, mcd_sys - beneficios, sys_bolsa_base)
    sys_bolsa_final = np.maximum(sys_bolsa_final, 0.0)

    df['[2] OVG DEVERIA PAGAR (Último Referencial)'] = np.where(is_contrato & (~mask_ignorar_math), sys_bolsa_final, 0.0)

    df['[4] SOMA OVG DEVERIA PAGAR (SISTEMA)'] = df.get('soma_deveria_sistema', 0.0)
    if 'tem_pagamento_historico' in df.columns:
        mask_sem_pag = (~df['tem_pagamento_historico']) & (df['qtd_pagtos'].fillna(0).astype(float) > 0)
        df.loc[mask_sem_pag, '[4] SOMA OVG DEVERIA PAGAR (SISTEMA)'] = df.loc[mask_sem_pag, 'qtd_pagtos'].fillna(0).astype(float) * df.loc[mask_sem_pag, '[2] OVG DEVERIA PAGAR (Último Referencial)']

    # [5] e [6] Referência da IA
    g_mcd_50 = mcd_ia * 0.5
    g_calc_parcial = np.where(is_med_odonto, np.minimum(g_mcd_50, 2900.0), np.minimum(g_mcd_50, 650.0))
    g_calc_integral = np.where(is_med_odonto, np.minimum(mcd_ia, 5800.0), np.minimum(mcd_ia, 1500.0))
    g_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [g_calc_parcial, g_calc_integral], default=0.0)
    
    g_excedeu = (g_bolsa_base + beneficios) > mcd_ia
    g_bolsa_final = np.where(g_excedeu, mcd_ia - beneficios, g_bolsa_base)
    g_bolsa_final = np.maximum(g_bolsa_final, 0.0)

    df['[5] OVG DEVERIA PAGAR (IA)'] = np.where(is_contrato & (~mask_ignorar_math), g_bolsa_final, 0.0)

    qtd_pag_calc = df['qtd_pagtos'].fillna(0).astype(float)
    qtd_retro = df.get('qtd_pagtos_retroativos', pd.Series(0, index=df.index)).fillna(0).astype(float)
    mult_soma_ia = np.maximum(qtd_pag_calc - qtd_retro, 0.0)

    df['[6] SOMA OVG DEVERIA PAGAR (IA)'] = df['[5] OVG DEVERIA PAGAR (IA)'] * mult_soma_ia
    
    if 'Soma Valor Financiamento' not in df.columns:
        df['Soma Valor Financiamento'] = pd.to_numeric(df.get('valor_financiamento', 0), errors='coerce').fillna(0.0) * mult_soma_ia
    else:
        df['Soma Valor Financiamento'] = pd.to_numeric(df['Soma Valor Financiamento'], errors='coerce').fillna(0.0)
        mask_sf = (df['Soma Valor Financiamento'] == 0)
        df.loc[mask_sf, 'Soma Valor Financiamento'] = pd.to_numeric(df.get('valor_financiamento', 0), errors='coerce').fillna(0.0)[mask_sf] * mult_soma_ia[mask_sf]

    if 'Soma Valor Beneficio' not in df.columns:
        df['Soma Valor Beneficio'] = pd.to_numeric(df.get('valor_beneficio', 0), errors='coerce').fillna(0.0) * mult_soma_ia
    else:
        df['Soma Valor Beneficio'] = pd.to_numeric(df['Soma Valor Beneficio'], errors='coerce').fillna(0.0)
        mask_sb = (df['Soma Valor Beneficio'] == 0)
        df.loc[mask_sb, 'Soma Valor Beneficio'] = pd.to_numeric(df.get('valor_beneficio', 0), errors='coerce').fillna(0.0)[mask_sb] * mult_soma_ia[mask_sb]

    if 'qual_beneficio' in df.columns and 'valor_beneficio' in df.columns:
        mask_benef_zero = (pd.to_numeric(df['valor_beneficio'], errors='coerce').fillna(0.0) == 0) & (df['Soma Valor Beneficio'] == 0) & (df['qual_beneficio'] != 'Sem outros benefícios')
        df.loc[mask_benef_zero, 'qual_beneficio'] = 'Sem outros benefícios'

    if 'qual_financiamento' in df.columns and 'valor_financiamento' in df.columns:
        mask_fin_zero = (pd.to_numeric(df['valor_financiamento'], errors='coerce').fillna(0.0) == 0) & (df['Soma Valor Financiamento'] == 0) & (df['qual_financiamento'] != 'Sem financiamento')
        df.loc[mask_fin_zero, 'qual_financiamento'] = 'Sem financiamento'

    # Prejuízo e Economia (IA) [7], [8] e [9]
    cond_falha_leitura = (mcd_ia == 0)
    prejuizo_ovg = np.maximum(paga - g_bolsa_final, 0.0)
    economia_ovg = np.maximum(g_bolsa_final - paga, 0.0)

    df['[7] PREJUÍZO DA OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), prejuizo_ovg, 0.0)
    df['[8] SOMA PREJUÍZO DA OVG (R$)'] = df['[7] PREJUÍZO DA OVG (R$)'] * multiplier
    df['[9] ECONOMIA DA OVG (R$)'] = np.where(is_contrato & (~mask_ignorar_math) & (~cond_falha_leitura), economia_ovg, 0.0)

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
    
    def resolver_status_ia(row):
        ia_status_original = str(row.get('Status_IA', '')).strip()
        ia_status_upper = ia_status_original.upper()
        
        if ia_status_original == "Falso Ausente": return "Falso Ausente"
        if not ia_status_original or "NÃO PROCESSADO" in ia_status_upper: return "Documento não processado"
        if "AUSENTE" in ia_status_upper or "X" == ia_status_upper or "CORROMPIDO" in ia_status_upper: return "Ausente"
            
        ia_resultado = "Válido" if ia_status_upper.startswith("V") else "Inválido"
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
        return ia_resultado
        
    df['Status_IA'] = df.apply(resolver_status_ia, axis=1)

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

    # Limpa a variável temporária para não vazar no Excel
    df.drop(columns=['soma_deveria_sistema', 'tipo_bolsista_renovacao', 'tipo_veterano_ingresso'], errors='ignore', inplace=True)

    df.rename(columns={'sit_motivos': 'Situação do Motivo', 'sit_obs': 'Observação da Situação'}, inplace=True)

    ordem_desejada = [
        'Status_IA', 'Status_Vínculo', 
        'Situação do Motivo', 'Observação da Situação',
        'Mudou IES?', 'IES Anterior', 'IES Posterior', 'Mudou Bolsa?', 'Bolsa Anterior', 'Bolsa Posterior', 
        'Semestre', 'Gemini Semestre', 'Inscrição', 'Inscrição Anterior', 'Inscrição Posterior', 
        'Bolsista', 'CPF', 'Gemini CPF', 'Gemini Inconsistencias', 'Faculdade', 'Curso', 
        'tipo_bolsa_final', 'qtd_pagtos', 'qtd_pagtos_retroativos', 'último_valor_pago_referencia', 'total bolsa paga', 
        
        'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Dif. s/Desc.', '% Dif. s/Desc.', 'Total Dif. s/Desc.', 'MSD_SOMA', 'G_MSD_SOMA', 'MSD_DOC', 
        
        'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Dif. c/Desc.', '% Dif. c/Desc.', 'Total Dif. c/Desc.', 'MCD_SOMA', 'G_MCD_SOMA', 'MCD_DOC', 
        
        # --- O BLOCO FINANCEIRO NA ORDEM EXATA ---
        '[1] OVG PAGOU (Último Referencial)',
        '[2] OVG DEVERIA PAGAR (Último Referencial)', 
        '[3] SOMA OVG PAGOU',
        '[4] SOMA OVG DEVERIA PAGAR (SISTEMA)',
        '[5] OVG DEVERIA PAGAR (IA)', 
        '[6] SOMA OVG DEVERIA PAGAR (IA)',
        '[7] PREJUÍZO DA OVG (R$)',
        '[8] SOMA PREJUÍZO DA OVG (R$)',
        '[9] ECONOMIA DA OVG (R$)',
        'Diagnóstico Financeiro Final',
        
        'valor_beneficio', 'Soma Valor Beneficio', 'qual_beneficio', 'valor_financiamento', 'Soma Valor Financiamento', 'qual_financiamento', 'data_coleta',
        'Documento Tipo', 'Check Contrato', 'Check Financiamento', 'Check Benefícios', 'Check RIAF', 'Check Histórico', 
        'Processar', 'Processado', 'Data Processamento', 'Coleta ID',
        'inscricao_ano', 'uni_deficiencia', 'uni_sexo'
    ]
    
    cols_ordenadas = [col for col in ordem_desejada if col in df.columns]
    colunas_sujas = ['situacao', 'situacao_atual_sistema', 'sit_data_atual_sistema', 'sit_obs_atual_sistema']
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
    
    for (ies, semestre), group_raw in df_target.groupby(['Faculdade', 'Semestre']):
        
        # 1. Ignorar "Falso Ausente" de todo o resumo
        group_raw = group_raw[group_raw['Status_IA'].astype(str).str.strip() != 'Falso Ausente'].copy()
        
        if group_raw.empty:
            continue
            
        # 2. Remover duplicadas estrategicamente: priorizamos a data_coleta mais recente
        if 'data_coleta' in group_raw.columns:
            group_raw['temp_data'] = pd.to_datetime(group_raw['data_coleta'], format='%d/%m/%Y', errors='coerce')
            group_raw.sort_values(by=['temp_data'], ascending=False, inplace=True, na_position='last')
            group_raw.drop(columns=['temp_data'], inplace=True)
            
        group_raw.drop_duplicates(subset=['CPF', 'Documento Tipo'], keep='first', inplace=True)
        
        cpfs_validos = group_raw['CPF'].dropna().unique()
        tot_benef = len(cpfs_validos)
        
        status_por_cpf = group_raw.groupby('CPF', sort=False)['Status_Vínculo'].first()
        ativos = (status_por_cpf == 'ATIVO').sum()
        desligados = (status_por_cpf == 'DESLIGADO').sum()
        
        group = group_raw
        
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
            
            # --- MATEMÁTICA CONSISTENTE (Evita somar mais que o Total de Beneficiários) ---
            status_ia_benef = group_doc['Status_IA'].astype(str).str.lower().str.strip()
            
            # 1. Quantos foram processados e não processados (únicos por CPF)
            proc_count = status_ia_benef.isin(['inválido', 'válido', 'falso inválido', 'falso válido', 'invalido', 'valido', 'falso invalido', 'falso valido']).sum()
            nao_proc_count = (status_ia_benef == 'documento não processado').sum()
            
            enviados = proc_count + nao_proc_count
            
            # 2. As pendências reais são os alunos da base esperada que não enviaram documento
            pendentes_contados = status_ia_benef.isin(['ausente', 'ausentes', 'corrompido']).sum()
            pendentes_reais = max(pendentes_contados, tot_benef - enviados)
            
            base_real = max(tot_benef, enviados + pendentes_reais)
            
            row[f'Env. {doc_k}'] = enviados
            row[f'Pend. {doc_k}'] = pendentes_reais
            row[f'% {doc_k}'] = enviados / base_real if base_real > 0 else 0.0
            
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
def gerar_aba_relatorio_consolidado(writer, df_docs):
    if df_docs.empty or 'Faculdade' not in df_docs.columns:
        return

    workbook = writer.book
    worksheet = workbook.add_worksheet('Relatório Consolidado')
    
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
    COL_QTD_PAGTOS = get_col('qtd_pagtos') or 'W'
    
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
    COL_BOLSA_CALC = get_col('[6] SOMA OVG DEVERIA PAGAR (IA)') or 'AQ'
    
    # Tipo de Bolsa e CPF
    COL_TIPO_BOLSA = get_col('tipo_bolsa_final') or 'V'
    COL_CPF = get_col('CPF') or 'Q'
    
    # Benefícios Extras
    COL_VALOR_FINANC = get_col('valor_financiamento') or 'AZ'
    COL_SOMA_VALOR_FINANC = get_col('Soma Valor Financiamento') or 'AZ'
    COL_VALOR_BENEF = get_col('valor_beneficio') or 'AX'
    COL_SOMA_VALOR_BENEF = get_col('Soma Valor Beneficio') or 'AX'
    
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
    worksheet.set_column('B:E', 20)
    worksheet.set_row(0, 90) 
    worksheet.set_row(1, 25) 
    worksheet.set_row(2, 25) 

    # --- 3. Inserir Imagem ---
    worksheet.merge_range('A1:E1', '', fmt_branco)
    
    caminho_imagem = os.path.join('static', 'img', 'icones', 'relatorio.png')
    if os.path.exists(caminho_imagem):
        try:
            worksheet.embed_image('A1', caminho_imagem, {'cell_format': fmt_branco})
        except Exception:
            worksheet.insert_image('A1', caminho_imagem, {'object_position': 1, 'x_offset': 5, 'y_offset': 5, 'x_scale': 0.9, 'y_scale': 0.9})

    # --- 4. Menu Suspenso e Títulos ---
    ies_list = sorted(df_docs['Faculdade'].dropna().unique().tolist())
    
    aux_sheet = workbook.add_worksheet('Aux_IES_Consolidado')
    aux_sheet.hide()
    for i, ies in enumerate(ies_list):
        aux_sheet.write(i, 0, ies)
        
    worksheet.merge_range('A2:E2', 'Relatório Informativo sobre Instituição de Ensino Superior', fmt_titulo)
    
    primeira_ies = ies_list[0] if ies_list else "Selecione a IES..."
    worksheet.merge_range('A3:E3', primeira_ies, fmt_input)
    
    if ies_list:
        worksheet.data_validation('A3', {
            'validate': 'list',
            'source': f'=Aux_IES_Consolidado!$A$1:$A${len(ies_list)}',
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
        ("Quantidade de Parciais", False, 1),
        ("Quantidade de Integrais", False, 1),
        ("Valor Total de Bolsas Pagas", False, 1),
        ("Valor Médio das Bolsas Parciais", False, 1),
        ("Valor Médio das Bolsas Integrais", False, 1),
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
            worksheet.write(row_idx, 1, '2025-1', cur_fmt_header)
            worksheet.write(row_idx, 2, '2025-2', cur_fmt_header)
            worksheet.write(row_idx, 3, '2026-1', cur_fmt_header)
            worksheet.write(row_idx, 4, 'Variação', cur_fmt_header)
        else:
            excel_row = row_idx + 1 # Linha real no Excel
            worksheet.write(row_idx, 0, label, cur_fmt_cell)
            
            # FÓRMULA DE VARIAÇÃO À PROVA DE FALHAS E DIVISÃO POR ZERO
            form_var = f'=IF($A$3="Selecione a IES...", "", IFERROR(IF(AND(C{excel_row}=0,D{excel_row}=0),0,IF(C{excel_row}=0,1,(D{excel_row}-C{excel_row})/C{excel_row})),""))'

            # 1. Quantidade de Beneficiários
            if label == "Quantidade de Beneficiários":
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUM(B{excel_row+1}:B{excel_row+2}))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUM(C{excel_row+1}:C{excel_row+2}))'
                form_3 = f'=IF($A$3="Selecione a IES...", "", SUM(D{excel_row+1}:D{excel_row+2}))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_3, cur_fmt_center)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
                
            # 2. Valor Total de Bolsas Pagas
            elif label == "Valor Total de Bolsas Pagas":
                row_valor_total_bolsas = excel_row  # Salva para referência dinâmica
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"))'
                form_3 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_3, cur_fmt_money)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

            # 3. Valor Médio das Bolsas (Parciais e Integrais)
            elif label in ["Valor Médio das Bolsas Parciais", "Valor Médio das Bolsas Integrais"]:
                tipo_valor = "PARCIAL" if label == "Valor Médio das Bolsas Parciais" else "INTEGRAL"
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                # Soma dos pagamentos para o tipo de bolsa
                def _sum_tipo(per):
                    return f'SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, per, {doc_cond})'
                
                # Soma da quantidade de meses pagos (qtd_pagtos) para o tipo de bolsa
                def _sum_qtd_meses(per):
                    return f'SUMIFS(Documentos!{COL_QTD_PAGTOS}:{COL_QTD_PAGTOS}, Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, per, {doc_cond})'

                # Cálculo: Soma Dinheiro / Soma Meses (Já resulta na média mensal)
                form_1 = f'=IF($A$3="Selecione a IES...", "", IFERROR({_sum_tipo("2025-1")}/{_sum_qtd_meses("2025-1")}, 0))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", IFERROR({_sum_tipo("2025-2")}/{_sum_qtd_meses("2025-2")}, 0))'
                form_3 = f'=IF($A$3="Selecione a IES...", "", IFERROR({_sum_tipo("2026-1")}/{_sum_qtd_meses("2026-1")}, 0))'
                
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_3, cur_fmt_money)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

            # 3b. Quantidade de Parciais / Integrais (por CPF único, apenas Ausente/Válido/Inválido)
            elif label in ["Quantidade de Parciais", "Quantidade de Integrais"]:
                tipo_valor = "PARCIAL" if label == "Quantidade de Parciais" else "INTEGRAL"
                doc_cond_bolsa = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                # COUNTIFS por status (Ausente + Válido + Inválido) para ignorar Falso Ausente
                def _count_tipo(per, st):
                    return f'COUNTIFS(Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, per, {doc_cond_bolsa}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{st}")'
                form_1 = f'=IF($A$3="Selecione a IES...", "", {_count_tipo("2025-1", "Ausente")} + {_count_tipo("2025-1", "Válido")} + {_count_tipo("2025-1", "Inválido")})'
                form_2 = f'=IF($A$3="Selecione a IES...", "", {_count_tipo("2025-2", "Ausente")} + {_count_tipo("2025-2", "Válido")} + {_count_tipo("2025-2", "Inválido")})'
                form_3 = f'=IF($A$3="Selecione a IES...", "", {_count_tipo("2026-1", "Ausente")} + {_count_tipo("2026-1", "Válido")} + {_count_tipo("2026-1", "Inválido")})'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_3, cur_fmt_center)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

            # 4. Casos diretos mapeados no Resumo_Quantitativo
            elif label in mapa_colunas:
                l_col = mapa_colunas[label]
                form_1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Resumo_Quantitativo!{l_col}:{l_col}, Resumo_Quantitativo!A:A, $A$3, Resumo_Quantitativo!B:B, "2025-1"))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Resumo_Quantitativo!{l_col}:{l_col}, Resumo_Quantitativo!A:A, $A$3, Resumo_Quantitativo!B:B, "2025-2"))'
                form_3 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Resumo_Quantitativo!{l_col}:{l_col}, Resumo_Quantitativo!A:A, $A$3, Resumo_Quantitativo!B:B, "2026-1"))'
                worksheet.write_formula(row_idx, 1, form_1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, form_2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, form_3, cur_fmt_center)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
                
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
                    return " + ".join([f'SUMIFS(Documentos!{c_sum}:{c_sum}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, per, {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{s}")' for s in st])

                def _c(c_crit, val, per, st=None):
                    if st is None:
                        st = ["Ausente", "Válido", "Inválido"]
                    return " + ".join([f'COUNTIFS(Documentos!{c_crit}:{c_crit}, "{val}", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, per, {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "{s}")' for s in st])

                if label == "Soma na Coleta de Dados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-1")})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-2")})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2026-1")})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Soma na Coleta de Dados de Contratos Não Enviados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-1", ["Ausente"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-2", ["Ausente"])})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2026-1", ["Ausente"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Soma na Coleta de Dados de Contratos Enviados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-1", ["Válido", "Inválido"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2025-2", ["Válido", "Inválido"])})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_s(col_coleta, "2026-1", ["Válido", "Inválido"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Soma no Contrato":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_s(col_contrato, "2025-1", ["Válido", "Inválido"])})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_s(col_contrato, "2025-2", ["Válido", "Inválido"])})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_s(col_contrato, "2026-1", ["Válido", "Inválido"])})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Diferença entre Contrato e Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", B{excel_row-1}-B{excel_row-2})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", C{excel_row-1}-C{excel_row-2})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", D{excel_row-1}-D{excel_row-2})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Porcentagem de Diferença entre Coleta de Dados (enviados) e Contrato":
                    f1 = f'=IF($A$3="Selecione a IES...", "", IFERROR((B{excel_row-2}-B{excel_row-3})/B{excel_row-3}, 0))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", IFERROR((C{excel_row-2}-C{excel_row-3})/C{excel_row-3}, 0))'
                    f3 = f'=IF($A$3="Selecione a IES...", "", IFERROR((D{excel_row-2}-D{excel_row-3})/D{excel_row-3}, 0))'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Porcentagem do Total Pago acima do Valor do Contrato":
                    # Referência dinâmica à linha do "Valor Total de Bolsas Pagas"
                    ref_bolsas = row_valor_total_bolsas or 9
                    f1 = f'=IF($A$3="Selecione a IES...", "", IFERROR(1-(B{excel_row-1}/B{ref_bolsas}), 0))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", IFERROR(1-(C{excel_row-1}/C{ref_bolsas}), 0))'
                    f3 = f'=IF($A$3="Selecione a IES...", "", IFERROR(1-(D{excel_row-1}/D{ref_bolsas}), 0))'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_pct)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Soma Valor de Bolsas Calculadas conforme o Contrato":
                    # Aceitamos tudo, menos "Falso Ausente"
                    f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_BOLSA_CALC}:{COL_BOLSA_CALC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_BOLSA_CALC}:{COL_BOLSA_CALC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                    f3 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_BOLSA_CALC}:{COL_BOLSA_CALC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valores de Acordo com a Coleta de Dados":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Coleta de dados conforme documento", "2025-1")})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Coleta de dados conforme documento", "2025-2")})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Coleta de dados conforme documento", "2026-1")})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Não Localizado":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor não localizado no documento", "2025-1")})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor não localizado no documento", "2025-2")})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor não localizado no documento", "2026-1")})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Maior que a Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Maior", "2025-1")})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Maior", "2025-2")})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Maior", "2026-1")})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

                elif label == "Qtd. de Contratos com Valor Menor que a Coleta":
                    f1 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Menor", "2025-1")})'
                    f2 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Menor", "2025-2")})'
                    f3 = f'=IF($A$3="Selecione a IES...", "", {_c(col_doc, "Valor no documento é Menor", "2026-1")})'
                    worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                    worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                    worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                    worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)

            # 6. INCONSISTÊNCIAS (Coringas '*')
            elif label == "Qtd. de Contratos com Inconsistências de CPF":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                c1 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond})'
                c2 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond})'
                f1 = f'=IF($A$3="Selecione a IES...", "", {c1} + {c2})'
                
                c3 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond})'
                c4 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond})'
                f2 = f'=IF($A$3="Selecione a IES...", "", {c3} + {c4})'
                c5 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond})'
                c6 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*CPF não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond})'
                f3 = f'=IF($A$3="Selecione a IES...", "", {c5} + {c6})'
                
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
                
            elif label == "Qtd. de Contratos com Inconsistências de Semestre Letivo":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                c1 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond})'
                c2 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond})'
                f1 = f'=IF($A$3="Selecione a IES...", "", {c1} + {c2})'
                
                c3 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond})'
                c4 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond})'
                f2 = f'=IF($A$3="Selecione a IES...", "", {c3} + {c4})'
                c5 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo não localizado no contrato*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond})'
                c6 = f'COUNTIFS(Documentos!{COL_INCONSIST}:{COL_INCONSIST}, "*Semestre letivo do contrato diverge do sistema*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond})'
                f3 = f'=IF($A$3="Selecione a IES...", "", {c5} + {c6})'
                
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_center)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_center)
                worksheet.write_formula(row_idx, 3, f3, cur_fmt_center)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
            
            # 7. BENEFÍCIOS EXTRAS
            elif label == "Soma de Financiamento":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_FINANC}:{COL_SOMA_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_FINANC}:{COL_SOMA_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f3 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_FINANC}:{COL_SOMA_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
                
            elif label == "Soma de Outros Benefícios":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_BENEF}:{COL_SOMA_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_BENEF}:{COL_SOMA_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2025-2", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f3 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_BENEF}:{COL_SOMA_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "2026-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, f3, cur_fmt_money)
                worksheet.write_formula(row_idx, 4, form_var, cur_fmt_pct)
                
            # 8. Linhas vazias de segurança
            else:
                worksheet.write(row_idx, 1, '', cur_fmt_center)
                worksheet.write(row_idx, 2, '', cur_fmt_center)
                worksheet.write(row_idx, 3, '', cur_fmt_center)
                worksheet.write(row_idx, 4, '', cur_fmt_center)
            
        row_idx += 1



# ==========================================
# 7. MOTOR PRINCIPAL GGCI
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
    COL_QTD_PAGTOS = get_col('qtd_pagtos') or 'W'
    
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
    COL_BOLSA_CALC = get_col('[6] SOMA OVG DEVERIA PAGAR (IA)') or 'AQ'
    
    # Tipo de Bolsa e CPF
    COL_TIPO_BOLSA = get_col('tipo_bolsa_final') or 'V'
    COL_CPF = get_col('CPF') or 'Q'
    
    # Benefícios Extras
    COL_VALOR_FINANC = get_col('valor_financiamento') or 'AZ'
    COL_SOMA_VALOR_FINANC = get_col('Soma Valor Financiamento') or 'AZ'
    COL_VALOR_BENEF = get_col('valor_beneficio') or 'AX'
    COL_SOMA_VALOR_BENEF = get_col('Soma Valor Beneficio') or 'AX'
    
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
    
    caminho_imagem = os.path.join('static', 'img', 'icones', 'relatorio.png')
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
        ("Quantidade de Parciais", False, 1),
        ("Quantidade de Integrais", False, 1),
        ("Valor Total de Bolsas Pagas", False, 1),
        ("Valor Médio das Bolsas Parciais", False, 1),
        ("Valor Médio das Bolsas Integrais", False, 1),
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

            # 3. Valor Médio das Bolsas (Parciais e Integrais)
            elif label in ["Valor Médio das Bolsas Parciais", "Valor Médio das Bolsas Integrais"]:
                tipo_valor = "PARCIAL" if label == "Valor Médio das Bolsas Parciais" else "INTEGRAL"
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                
                # Soma dos pagamentos para o tipo de bolsa
                def _sum_tipo(per):
                    return f'SUMIFS(Documentos!{COL_TOTAL_BOLSA}:{COL_TOTAL_BOLSA}, Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-{per}", {doc_cond})'
                
                # Soma da quantidade de meses pagos (qtd_pagtos) para o tipo de bolsa
                def _sum_qtd_meses(per):
                    return f'SUMIFS(Documentos!{COL_QTD_PAGTOS}:{COL_QTD_PAGTOS}, Documentos!{COL_TIPO_BOLSA}:{COL_TIPO_BOLSA}, "*{tipo_valor}*", Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-{per}", {doc_cond})'

                # Cálculo: Soma Dinheiro / Soma Meses (Já resulta na média mensal)
                form_1 = f'=IF($A$3="Selecione a IES...", "", IFERROR({_sum_tipo(1)}/{_sum_qtd_meses(1)}, 0))'
                form_2 = f'=IF($A$3="Selecione a IES...", "", IFERROR({_sum_tipo(2)}/{_sum_qtd_meses(2)}, 0))'
                
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
                    # Aceitamos tudo, menos "Falso Ausente"
                    f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_BOLSA_CALC}:{COL_BOLSA_CALC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                    f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_BOLSA_CALC}:{COL_BOLSA_CALC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
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
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_FINANC}:{COL_SOMA_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_FINANC}:{COL_SOMA_VALOR_FINANC}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                worksheet.write_formula(row_idx, 1, f1, cur_fmt_money)
                worksheet.write_formula(row_idx, 2, f2, cur_fmt_money)
                worksheet.write_formula(row_idx, 3, form_var, cur_fmt_pct)
                
            elif label == "Soma de Outros Benefícios":
                doc_cond = f'Documentos!{COL_DOC_TIPO}:{COL_DOC_TIPO}, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS EDUCACIONAIS OU COMPROVANTE DE MATRÍCULA"'
                f1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_BENEF}:{COL_SOMA_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-1", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
                f2 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{COL_SOMA_VALOR_BENEF}:{COL_SOMA_VALOR_BENEF}, Documentos!{COL_FACULDADE}:{COL_FACULDADE}, $A$3, Documentos!{COL_SEMESTRE}:{COL_SEMESTRE}, "{ano}-2", {doc_cond}, Documentos!{COL_STATUS_IA}:{COL_STATUS_IA}, "<>Falso Ausente"))'
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

def gerar_relatorio_geral(docs_selecionados=None, anos_selecionados=None, sems_selecionados=None, gerar_relatorio=False, processo_id=None):
    if not processo_id: raise ValueError("O processo_id é obrigatório.")
    base_dir = f"apps/automacoes/enquadramento_cursos/dados/proc_{processo_id}"
    ARQ_PROCESSADOS = os.path.join(base_dir, "analise_documentos_processados", "CONSOLIDADO", "consolidado_processados.xlsx")
    ARQ_RIAF = os.path.join(base_dir, "analise_documentos_processados", "CONSOLIDADO", "consolidado_processados_riaf.xlsx")
    ARQ_PAGAMENTOS = os.path.join(base_dir, "analise_pagamentos", "CONSOLIDADO", "consolidado_pagamentos.xlsx")
    ARQUIVO_GERAL_SAIDA = os.path.join(base_dir, "enquadramento_geral.zip")
    # Não exibir mais a msg inicial aqui, já exibimos em outro local ou fica oculto
    
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
    
    tem_multiplos_periodos = len(anos_selecionados) > 1 or len(sems_selecionados) > 1
    pode_gerar_relatorio = (check_contrato and check_financ and check_benef and tem_multiplos_periodos)
    
    if gerar_relatorio and not pode_gerar_relatorio:
        print(f"⚠️ [RELATÓRIO | BLOQUEADO] A aba 'Relatório' exige: Contratos, Financiamentos, Benefícios e pelo menos dois períodos para comparação (ex: dois anos ou dois semestres).")
    
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

    # --- DEDUPLICAÇÃO GLOBAL (Garante que alunos com múltiplos uploads não dupliquem linhas) ---
    def deduplicar_dataset(df_temp):
        if df_temp.empty: return df_temp
        if 'data_coleta' in df_temp.columns:
            df_temp['temp_data'] = pd.to_datetime(df_temp['data_coleta'], format='%d/%m/%Y', errors='coerce')
            df_temp.sort_values(by=['temp_data'], ascending=False, inplace=True, na_position='last')
            df_temp.drop(columns=['temp_data'], inplace=True)
            
        if all(c in df_temp.columns for c in ['Inscrição', 'Semestre', 'Documento Tipo']):
            df_temp.drop_duplicates(subset=['Inscrição', 'Semestre', 'Documento Tipo'], keep='first', inplace=True)
        return df_temp

    df_docs = deduplicar_dataset(df_docs)
    df_riaf = deduplicar_dataset(df_riaf)

    if os.path.exists(ARQ_PAGAMENTOS):
        df_pag = converter_colunas_para_salvamento(pd.read_excel(ARQ_PAGAMENTOS, engine='openpyxl'))
        print(f"📥 Lido: Pagamentos -> Para cruzamento de Ausentes.")

    if not df_pag.empty and (check_contrato or check_financ or check_benef or check_riaf or check_historico):
        print("↳ Identificando bolsistas...")

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
            print(f"↳ +{len(novos_ausentes_docs)} bolsistas pendentes (Docs)")
        if novos_ausentes_riaf:
            df_riaf = pd.concat([df_riaf, converter_colunas_para_salvamento(pd.DataFrame(novos_ausentes_riaf))], ignore_index=True)
            print(f"↳ +{len(novos_ausentes_riaf)} bolsistas pendentes (Riaf)")

    if not df_docs.empty or not df_riaf.empty:
        print("↳ Buscando dados dos bolsistas...")
        sem_docs = df_docs['Semestre'].dropna().unique().tolist() if not df_docs.empty else []
        sem_riaf = df_riaf['Semestre'].dropna().unique().tolist() if not df_riaf.empty else []
        semestres_presentes = list(set(sem_docs + sem_riaf))
        print("↳ Conectando ao sistema...")
        df_financas = buscar_dados_financeiros_sql(semestres_presentes)
        df_mes_a_mes = buscar_dados_pagamentos_mes_a_mes_sql(semestres_presentes)
        print("Dados carregados com sucesso.")
    
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
        print("🤖 Calculando e cruzando dados...")
        df_docs = mesclar_sql_e_reordenar(df_docs, df_financas, df_pag, df_mes_a_mes)
        df_docs = aplicar_transicoes(df_docs, df_pag)
        df_docs = gerar_checks_documentos(df_docs)
        
    if not df_riaf.empty:
        print("🤖 Calculando e cruzando dados...")
        df_riaf = mesclar_sql_e_reordenar(df_riaf, df_financas, df_pag, df_mes_a_mes)
        df_riaf = aplicar_transicoes(df_riaf, df_pag)
        df_riaf = gerar_checks_documentos(df_riaf)

    for df_target in [df_docs, df_riaf]:
        if not df_target.empty:

            if 'Data Processamento' in df_target.columns: 
                df_target['Data Processamento'] = df_target['Data Processamento'].fillna('')
            
            colunas_remover = ['Processar', 'Processado', 'situacao', 'situacao_atual_sistema', 
                               'sit_data_atual_sistema', 'sit_obs_atual_sistema', 'soma_cd_sem_desconto', 'soma_cd_com_desconto']
            df_target.drop(columns=colunas_remover, inplace=True, errors='ignore')

    if not df_docs.empty or not df_riaf.empty:
        import zipfile
        import io
        import re
        
        print(f"💾 Finalizando e gerando o pacote ZIP...")
        os.makedirs(os.path.dirname(ARQUIVO_GERAL_SAIDA), exist_ok=True)
        
        if not df_docs.empty:
            print(f"📦 Agrupando planilhas por Faculdade e Semestre ({len(df_docs)} linhas)...")
            
            # --- Renomear e selecionar colunas desejadas conforme solicitado ---
            colunas_map = {
                'Faculdade': 'Faculdade',
                'Bolsista': 'Beneficiario',
                'CPF': 'CPF',
                'Inscrição': 'Inscrição',
                'Curso': 'Curso',
                'tipo_bolsa_final': 'Tipo da Bolsa',
                'tipo_veterano_ingresso': 'Bolsista',
                'Status_Vínculo': 'Vínculo',
                'Semestre': 'Semestre'
            }
            
            # Manter apenas as colunas que estão no mapa e renomeá-las
            cols_to_keep = [k for k in colunas_map.keys() if k in df_docs.columns]
            df_docs = df_docs[cols_to_keep].rename(columns=colunas_map)
            
            # Adicionar novas colunas vazias
            novas_colunas = ['Período Atual', 'Código Curso no e-MEC', 'Semestre de ingresso na IES', 
                             'Modalidade no ingresso', 'Modalidade atual', 'Observações']
            for col in novas_colunas:
                df_docs[col] = ''
                
            # Garantir a ordem final (o Semestre entra aqui para o agrupamento e será dropado depois)
            ordem_final = [
                'Semestre', 'Faculdade', 'Beneficiario', 'CPF', 'Inscrição', 'Curso', 'Tipo da Bolsa', 'Bolsista',
                'Vínculo', 'Período Atual', 'Código Curso no e-MEC', 'Semestre de ingresso na IES', 
                'Modalidade no ingresso', 'Modalidade atual', 'Observações'
            ]
            
            ordem_final = [col for col in ordem_final if col in df_docs.columns]
            df_docs = df_docs[ordem_final]
            
            df_docs.sort_values(by=['Faculdade', 'Beneficiario'], inplace=True, ignore_index=True)
            # Cria chave única e limpa para evitar que variações do mesmo nome gerem arquivos duplicados
            def sanitizar_nome(texto):
                f = str(texto).upper()
                import unicodedata
                import re
                f = unicodedata.normalize('NFKD', f).encode('ASCII', 'ignore').decode('utf-8')
                return re.sub(r'[^A-Z0-9]+', '_', f).strip('_')
                
            df_docs['Faculdade_Agrupamento'] = df_docs['Faculdade'].apply(sanitizar_nome)
            
            with zipfile.ZipFile(ARQUIVO_GERAL_SAIDA, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for (fac_chave, semestre), group in df_docs.groupby(['Faculdade_Agrupamento', 'Semestre']):
                    semestre_limpo = str(semestre).replace('-', '_')
                    
                    # Salva no ZIP apenas com a pasta da Faculdade e nomeia o arquivo com IES e Semestre
                    caminho_planilha = f"Separadas/{fac_chave}/{fac_chave}_{semestre_limpo}.xlsx"
                    
                    # Remove colunas de agrupamento da planilha exportada
                    group_export = group.drop(columns=['Semestre', 'Faculdade_Agrupamento'], errors='ignore')
                    
                    ies_nome = group_export['Faculdade'].iloc[0] if not group_export.empty else fac_chave
                    subtitulo_ies_str = f"{ies_nome} {str(semestre).strip()}"
                    
                    # Gera o Excel em memória
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        group_export.to_excel(writer, sheet_name='Enquadramento', index=False, startrow=5)
                        aplicar_formatacao_visual(writer, 'Enquadramento', group_export, startrow=5, subtitulo_ies=subtitulo_ies_str)
                        
                        # --- NOVA ABA (e-MEC) ---
                        df_temp = group_export[['Curso']].dropna().copy()
                        df_temp['curso_norm'] = df_temp['Curso'].astype(str).str.strip().str.upper()
                        cursos_unicos = df_temp.drop_duplicates(subset=['curso_norm'])['Curso'].tolist()
                        
                        df_nova_aba = pd.DataFrame({
                            'INSTITUICAO': [ies_nome] * len(cursos_unicos),
                            'CODIGO E-MEC DA IES': [''] * len(cursos_unicos),
                            'IGC (INDICE GERAL DE CURSO)': [''] * len(cursos_unicos),
                            'NOME DO CURSO': cursos_unicos,
                            'CODIGO E-MEC DO CURSO': [''] * len(cursos_unicos),
                            'SITUACAO DO CURSO NO E-MEC': [''] * len(cursos_unicos),
                            'CPC (CONCEITO PRELIMINAR DE CURSO)': [''] * len(cursos_unicos),
                            'GRAU': [''] * len(cursos_unicos),
                            'DURACAO (SEMESTRES)': [''] * len(cursos_unicos),
                            'MODALIDADE (E-MEC)': [''] * len(cursos_unicos),
                            'CARGA HORARIA TOTAL (H)': [''] * len(cursos_unicos),
                            'CARGA HORARIA PRESENCIAL (H)': [''] * len(cursos_unicos),
                            'CARGA HORARIA EAD (H)': [''] * len(cursos_unicos),
                            '% PRESENCIAL': [''] * len(cursos_unicos),
                            '% EAD': [''] * len(cursos_unicos),
                            'ATO REGULATORIO (ULTIMO VIGENTE)': [''] * len(cursos_unicos),
                            'TIPO DE DOCUMENTO / Nº DO DOCUMENTO': [''] * len(cursos_unicos),
                            'OFERTA PARA INGRESSANTES EM 2026.2 (PROBEM)?': [''] * len(cursos_unicos),
                            'OBSERVACOES': [''] * len(cursos_unicos)
                        })
                        
                        df_nova_aba.to_excel(writer, sheet_name='e-MEC', index=False, startrow=4)
                        aplicar_formatacao_visual(writer, 'e-MEC', df_nova_aba, startrow=4, subtitulo_ies=subtitulo_ies_str)
                    
                    # Salva no ZIP
                    zipf.writestr(caminho_planilha, excel_buffer.getvalue())

                print("📦 Gerando consolidados por semestre (Consolidado)...")
                for semestre, group in df_docs.groupby('Semestre'):
                    caminho_consolidado = f"Consolidado/consolidado_{semestre}.xlsx"
                    
                    # Remove colunas de agrupamento da planilha exportada
                    group_export = group.drop(columns=['Semestre', 'Faculdade_Agrupamento'], errors='ignore')
                    
                    subtitulo_str = f"Consolidado Todas IES {str(semestre).strip()}"
                    
                    # Gera o Excel em memória
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        group_export.to_excel(writer, sheet_name='Enquadramento', index=False, startrow=5)
                        aplicar_formatacao_visual(writer, 'Enquadramento', group_export, startrow=5, subtitulo_ies=subtitulo_str)
                        
                        # --- NOVA ABA (e-MEC) CONSOLIDADA ---
                        df_cursos = group_export[['Faculdade', 'Curso']].dropna().copy()
                        df_cursos['fac_norm'] = df_cursos['Faculdade'].astype(str).str.strip().str.upper()
                        df_cursos['curso_norm'] = df_cursos['Curso'].astype(str).str.strip().str.upper()
                        df_cursos = df_cursos.drop_duplicates(subset=['fac_norm', 'curso_norm']).drop(columns=['fac_norm', 'curso_norm'])
                        
                        df_nova_aba = pd.DataFrame({
                            'INSTITUICAO': df_cursos['Faculdade'],
                            'CODIGO E-MEC DA IES': [''] * len(df_cursos),
                            'IGC (INDICE GERAL DE CURSO)': [''] * len(df_cursos),
                            'NOME DO CURSO': df_cursos['Curso'],
                            'CODIGO E-MEC DO CURSO': [''] * len(df_cursos),
                            'SITUACAO DO CURSO NO E-MEC': [''] * len(df_cursos),
                            'CPC (CONCEITO PRELIMINAR DE CURSO)': [''] * len(df_cursos),
                            'GRAU': [''] * len(df_cursos),
                            'DURACAO (SEMESTRES)': [''] * len(df_cursos),
                            'MODALIDADE (E-MEC)': [''] * len(df_cursos),
                            'CARGA HORARIA TOTAL (H)': [''] * len(df_cursos),
                            'CARGA HORARIA PRESENCIAL (H)': [''] * len(df_cursos),
                            'CARGA HORARIA EAD (H)': [''] * len(df_cursos),
                            '% PRESENCIAL': [''] * len(df_cursos),
                            '% EAD': [''] * len(df_cursos),
                            'ATO REGULATORIO (ULTIMO VIGENTE)': [''] * len(df_cursos),
                            'TIPO DE DOCUMENTO / Nº DO DOCUMENTO': [''] * len(df_cursos),
                            'OFERTA PARA INGRESSANTES EM 2026.2 (PROBEM)?': [''] * len(df_cursos),
                            'OBSERVACOES': [''] * len(df_cursos)
                        })
                        
                        df_nova_aba.to_excel(writer, sheet_name='e-MEC', index=False, startrow=4)
                        aplicar_formatacao_visual(writer, 'e-MEC', df_nova_aba, startrow=4, subtitulo_ies=subtitulo_str)
                    
                    # Salva no ZIP
                    zipf.writestr(caminho_consolidado, excel_buffer.getvalue())

                print("📦 Gerando acompanhamento por semestre (Acompanhamento)...")
                for semestre, group in df_docs.groupby('Semestre'):
                    caminho_acompanhamento = f"Acompanhamento/cursos_por_ies_{semestre}.xlsx"
                    
                    # Remove colunas de agrupamento da planilha exportada
                    group_export = group.drop(columns=['Semestre', 'Faculdade_Agrupamento'], errors='ignore')
                    
                    # Extrai apenas valores únicos de Faculdade e Curso
                    df_acompanhamento = group_export[['Faculdade', 'Curso']].dropna().drop_duplicates()
                    
                    # Recria todas as outras colunas vazias para manter a formatação exata
                    for col in group_export.columns:
                        if col not in ['Faculdade', 'Curso']:
                            df_acompanhamento[col] = ''
                            
                    # Restaura a ordem exata das colunas
                    df_acompanhamento = df_acompanhamento[group_export.columns]
                    
                    subtitulo_str = f"Acompanhamento Cursos {str(semestre).strip()}"
                    
                    # Gera o Excel em memória
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        df_acompanhamento.to_excel(writer, sheet_name='Enquadramento', index=False, startrow=5)
                        aplicar_formatacao_visual(writer, 'Enquadramento', df_acompanhamento, startrow=5, subtitulo_ies=subtitulo_str)
                        
                        # --- NOVA ABA (e-MEC) ACOMPANHAMENTO ---
                        df_cursos = df_acompanhamento[['Faculdade', 'Curso']].dropna().copy()
                        df_cursos['fac_norm'] = df_cursos['Faculdade'].astype(str).str.strip().str.upper()
                        df_cursos['curso_norm'] = df_cursos['Curso'].astype(str).str.strip().str.upper()
                        df_cursos = df_cursos.drop_duplicates(subset=['fac_norm', 'curso_norm']).drop(columns=['fac_norm', 'curso_norm'])
                        
                        df_nova_aba = pd.DataFrame({
                            'INSTITUICAO': df_cursos['Faculdade'],
                            'CODIGO E-MEC DA IES': [''] * len(df_cursos),
                            'IGC (INDICE GERAL DE CURSO)': [''] * len(df_cursos),
                            'NOME DO CURSO': df_cursos['Curso'],
                            'CODIGO E-MEC DO CURSO': [''] * len(df_cursos),
                            'SITUACAO DO CURSO NO E-MEC': [''] * len(df_cursos),
                            'CPC (CONCEITO PRELIMINAR DE CURSO)': [''] * len(df_cursos),
                            'GRAU': [''] * len(df_cursos),
                            'DURACAO (SEMESTRES)': [''] * len(df_cursos),
                            'MODALIDADE (E-MEC)': [''] * len(df_cursos),
                            'CARGA HORARIA TOTAL (H)': [''] * len(df_cursos),
                            'CARGA HORARIA PRESENCIAL (H)': [''] * len(df_cursos),
                            'CARGA HORARIA EAD (H)': [''] * len(df_cursos),
                            '% PRESENCIAL': [''] * len(df_cursos),
                            '% EAD': [''] * len(df_cursos),
                            'ATO REGULATORIO (ULTIMO VIGENTE)': [''] * len(df_cursos),
                            'TIPO DE DOCUMENTO / Nº DO DOCUMENTO': [''] * len(df_cursos),
                            'OFERTA PARA INGRESSANTES EM 2026.2 (PROBEM)?': [''] * len(df_cursos),
                            'OBSERVACOES': [''] * len(df_cursos)
                        })
                        
                        df_nova_aba.to_excel(writer, sheet_name='e-MEC', index=False, startrow=4)
                        aplicar_formatacao_visual(writer, 'e-MEC', df_nova_aba, startrow=4, subtitulo_ies=subtitulo_str)
                    
                    # Salva no ZIP
                    zipf.writestr(caminho_acompanhamento, excel_buffer.getvalue())
            
        print("↳ Salvando arquivo físico...")
        print("✔ CONCLUÍDO")
        print("|")
        print("Relatório Geral gerado com sucesso!")
    else:
        print("❌ Falha: Nenhum dado processado de acordo com os filtros informados.")