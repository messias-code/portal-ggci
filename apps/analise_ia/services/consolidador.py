import os
import pandas as pd
import unicodedata
import re

# --- FUNÇÕES DE LIMPEZA ---

def converter_para_numero_real(valor):
    """Remove pontuações e converte para número inteiro."""
    if pd.isna(valor) or str(valor).lower() in ['nan', 'none', '']:
        return pd.NA
    v = str(valor).strip()
    if re.match(r'^\d+\.0+$', v):
        v = v.split('.')[0]
    apenas_numeros = re.sub(r'\D', '', v)
    if not apenas_numeros:
        return pd.NA
    return int(apenas_numeros)

def converter_para_moeda(valor):
    """Lida com valores financeiros garantindo os decimais corretos."""
    if pd.isna(valor) or str(valor).lower() in ['nan', 'none', '']:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).strip()
    if ',' in v:
        v = v.replace('.', '')   
        v = v.replace(',', '.')  
    v = re.sub(r'[^\d.-]', '', v)
    try:
        return float(v)
    except:
        return 0.0

def limpar_texto_geral(texto):
    """Uppercase, sem acentos e remove espaços nas pontas e duplos no meio."""
    if pd.isna(texto): return texto
    texto = str(texto).strip().upper()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    return " ".join(texto.split())

def extrair_semestre(caminho):
    nome = os.path.basename(caminho).lower()
    ano = re.search(r'202\d', caminho).group(0) if re.search(r'202\d', caminho) else "2026"
    meses_s1 = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun']
    return f"{ano}-1" if any(m in nome for m in meses_s1) else f"{ano}-2"

# --- CONFIGURAÇÃO ---

configs = [
    {
        'tipo': 'agendar',
        'pasta': 'dados/dados_analise_ia/analise_documentos_agendar_processamentos',
        'saida': 'consolidado_agendar_processamentos.xlsx',
        'aba': 'Agendar Proc.',
        'ext': '.xlsx',
        'cols_num': ['Inscrição', 'CPF'],
        'cols_moeda': [], 
        'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Documento Tipo'],
        'ordem_colunas': [
            'Inscrição', 'Bolsistas', 'Bolsista', 'CPF', 'Curso', 'Faculdade', 
            'Data Create', 'Semestre', 'Processar', 'Processado', 
            'Data processamento', 'Documento Tipo'
        ]
    },
    {
        'tipo': 'pag',
        'pasta': 'dados/dados_analise_ia/analise_pagamentos',
        'saida': 'consolidado_pagamentos.xlsx',
        'aba': 'Pagamentos',
        'ext': '.xls',
        'cols_num': ['UNI_CODIGO', 'UNI_MATRICULA', 'CADUNICO', 'UNI_CPF'],
        'cols_moeda': ['VALOR_CONTRATO_APURADO', 'VALOR_PAGAMENTO', 'VALOR_PAGAMENTO2', 'VALOR_COMPLEMENTO', 'VALOR_CANCELAMENTO', 'LAN_VALBOLSA'],
        'cols_txt': ['INS_NOME', 'UNI_NOME', 'CUR_NOME'],
        'ordem_colunas': [
            'UNI_CODIGO', 'UNI_NOME', 'UNI_CPF', 'UNI_DEFICIENCIA', 'UNI_MATRICULA', 
            'DATA_NASCIMENTO', 'CADUNICO', 'DATA_INGRESSO', 'CID_NOME', 'INS_NOME', 
            'CUR_NOME', 'VALOR_CONTRATO_APURADO', 'VALOR_PAGAMENTO', 'VALOR_PAGAMENTO2', 
            'VALOR_COMPLEMENTO', 'VALOR_CANCELAMENTO', 'LAN_VALBOLSA', 'TIPO_BOLSA', 
            'FAIXA', 'TIPO_PAGTO', 'TIPO_BOLSISTA', 'DATA_LANCAMENTO', 'SEMESTRE'
        ]
    },
    {
        'tipo': 'proc_geral',
        'pasta': 'dados/dados_analise_ia/analise_documentos_processados',
        'subpastas_alvo': ['BENEFICIOS', 'CONTRATOS', 'FINANCIAMENTO'],
        'saida': 'consolidado_processados.xlsx',
        'aba': 'Processados',
        'ext': '.xlsx',
        'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF'],
        'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
        'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Documento Tipo'],
        'ordem_colunas': [
            'Status_IA', 'Gemini Inconsistencias', 'Inscrição', 'Bolsista', 'Bolsistas', 'CPF', 
            'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Curso', 
            'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
            'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
            'Documento Tipo', 'Data Processamento', 'Coleta ID'
        ]
    },
    {
        'tipo': 'proc_riaf',
        'pasta': 'dados/dados_analise_ia/analise_documentos_processados',
        'subpastas_alvo': ['RIAF'],
        'saida': 'consolidado_processados_riaf.xlsx',
        'aba': 'RIAF Processado',
        'ext': '.xlsx',
        'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Cnpj Faculdade'],
        'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
        'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Gemini Razao Social', 'Gemini Nome Faculdade', 'Gemini Beneficio Nome', 'Gemini Nome Mantenedora', 'Gemini Nome Financiamento', 'Documento Tipo'],
        'ordem_colunas': [
            'Status_IA', 'Gemini Inconsistencias', 'Inscrição', 'Gemini Matricula', 'Bolsista', 'Bolsistas', 'CPF', 
            'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Gemini Nome Faculdade', 
            'Curso', 'Gemini Curso', 'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
            'Gemini Matricula Sem Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
            'Gemini Matricula Com Desconto', 'Gemini Razao Social', 'Gemini Cnpj Faculdade', 
            'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies', 
            'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
            'Gemini Nome Financiamento', 'Gemini Modalidade', 'Gemini Email', 'Gemini Telefone', 
            'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Tipo Bolsa', 
            'Documento Tipo', 'Coleta ID', 'Data Processamento'
        ]
    },
    {
        'tipo': 'proc_geral',
        'pasta': 'dados/dados_analise_ia/analise_documentos_processados',
        'subpastas_alvo': ['BENEFICIOS', 'CONTRATOS', 'FINANCIAMENTO', 'HISTORICO'], # <-- Adicionado aqui
        'saida': 'consolidado_processados.xlsx',
        'aba': 'Processados',
        'ext': '.xlsx',
        'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF'],
        'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
        'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Documento Tipo'],
        'ordem_colunas': [
            'Status_IA', 'Gemini Inconsistencias', 'Inscrição', 'Bolsista', 'Bolsistas', 'CPF', 
            'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Curso', 
            'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
            'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
            'Documento Tipo', 'Data Processamento', 'Coleta ID'
        ]
    }
]

def consolidar():
    for cf in configs:
        pasta_base = cf['pasta']
        pasta_dest = os.path.join(pasta_base, 'CONSOLIDADO')
        os.makedirs(pasta_dest, exist_ok=True)
        
        lista_df = []
        print(f"🔄 Processando: {cf['saida']} em {pasta_base}")

        for raiz, dirs, arquivos in os.walk(pasta_base):
            if 'CONSOLIDADO' in raiz: continue
            
            if 'subpastas_alvo' in cf:
                if not any(alvo in raiz for alvo in cf['subpastas_alvo']):
                    continue

            for arq in arquivos:
                if arq.endswith(cf['ext']) and not arq.startswith('~$'):
                    caminho = os.path.join(raiz, arq)
                    try:
                        if arq.endswith('.xlsx'):
                            df = pd.read_excel(caminho)
                        else:
                            try:
                                df = pd.read_excel(caminho, engine='xlrd')
                            except:
                                dfs_html = pd.read_html(caminho)
                                if not dfs_html: continue
                                df = dfs_html[0]
                                col_referencia = cf['cols_num'][0]
                                if col_referencia in str(df.iloc[0].values):
                                    df.columns = df.iloc[0]; df = df[1:]
                        
                        if df is not None:
                            df = df.dropna(how='all', axis=0)
                            
                            # OTIMIZAÇÃO: Limpeza de Texto Vetorizada
                            for col in cf['cols_txt']:
                                if col in df.columns:
                                    # Maiúsculas e remove espaços duplos
                                    df[col] = df[col].astype(str).str.upper().str.strip()
                                    # Normaliza acentuação usando encoding vetorizado indireto (ou regex de substituição leve)
                                    df[col] = df[col].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
                                    df[col] = df[col].str.replace(r'\s+', ' ', regex=True)

                            # OTIMIZAÇÃO: Limpeza de Moedas (Corrigido para não corromper floats lidos do Excel)
                            for col in cf['cols_moeda']:
                                if col in df.columns:
                                    df[col] = df[col].apply(converter_para_moeda)

                            # OTIMIZAÇÃO: Limpeza Numérica Vetorizada
                            for col in cf['cols_num']:
                                if col in df.columns:
                                    s = df[col].astype(str).str.strip().str.lower()
                                    s = s.replace({'nan': '', 'none': '', '<na>': ''})
                                    s = s.str.replace(r'\.0+$', '', regex=True)  # Remove ".0" isolados
                                    s = s.str.replace(r'\D', '', regex=True)     # Remove tudo que não for dígito
                                    df[col] = pd.to_numeric(s, errors='coerce').astype('Int64')

                            if cf['tipo'] == 'pag':
                                df.insert(0, 'SEMESTRE', extrair_semestre(caminho))

                            lista_df.append(df)
                    except Exception as e:
                        print(f"❌ Erro em {arq}: {e}")

        if lista_df:
            df_final = pd.concat(lista_df, ignore_index=True)
            
            # --- LIMPEZA DE COLUNAS DE STATUS/IDs ---
            if cf['tipo'] == 'agendar':
                col_rem = ['Id', 'ID', 'id', 'Status Gemini', 'Status Ovg', 'Gemini Cpf', 'Gemini Mensalidade Com Desconto', 
                           'Gemini Mensalidade Sem Desconto', 'Gemini Semestre', 'Gemini Inconsistencias', 
                           'Gemini Status', 'Gemini Curso', 'Gemini Matricula', 'Gemini Matricula Sem Desconto', 
                           'Gemini Matricula Com Desconto', 'Gemini Razao Social', 'Gemini Nome Faculdade', 
                           'Gemini Cnpj Faculdade', 'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 
                           'Gemini Assinatura Ies', 'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 
                           'Gemini Valor Financiado', 'Gemini Nome Financiamento', 'Gemini Modalidade', 
                           'Gemini Email', 'Gemini Telefone', 'Gemini Periodo', 'Gemini Quantidade Periodos', 'Gemini Tipo Bolsa']
                df_final.drop(columns=col_rem, errors='ignore', inplace=True)
                
            elif cf['tipo'] in ['proc_geral', 'proc_riaf']:
                cols_drop = ['Status Gemini', 'Gemini Status', 'Status Obs']
                df_final.drop(columns=cols_drop, errors='ignore', inplace=True)
                df_final.rename(columns={'Status OVG': 'Status_IA', 'Status Ovg': 'Status_IA'}, inplace=True)

            # --- APLICA A NOVA ORDEM DE COLUNAS ---
            if 'ordem_colunas' in cf:
                # Pega as colunas na ordem desejada que existem no dataframe
                colunas_ordenadas = [c for c in cf['ordem_colunas'] if c in df_final.columns]
                # Pega qualquer coluna extra que tenha sobrado e adiciona no final (para não perder dados)
                colunas_extras = [c for c in df_final.columns if c not in colunas_ordenadas]
                df_final = df_final[colunas_ordenadas + colunas_extras]

            caminho_final = os.path.join(pasta_dest, cf['saida'])
            writer = pd.ExcelWriter(caminho_final, engine='xlsxwriter')
            df_final.to_excel(writer, sheet_name=cf['aba'], index=False)
            
            workbook = writer.book
            worksheet = writer.sheets[cf['aba']]
            
            fmt_cpf = workbook.add_format({'num_format': '00000000000'})
            fmt_cnpj = workbook.add_format({'num_format': '00000000000000'}) 
            fmt_num = workbook.add_format({'num_format': '0'})
            fmt_moeda = workbook.add_format({'num_format': '#,##0.00'}) 
            
            for i, col in enumerate(df_final.columns):
                largura = max(len(str(col)), 12) + 2
                col_upper = str(col).upper()
                
                if 'CNPJ' in col_upper:
                    worksheet.set_column(i, i, 18, fmt_cnpj)
                elif 'CPF' in col_upper:
                    worksheet.set_column(i, i, 16, fmt_cpf)
                elif col in cf['cols_num']:
                    worksheet.set_column(i, i, 16, fmt_num)
                elif col in cf.get('cols_moeda', []):
                    worksheet.set_column(i, i, 18, fmt_moeda) 
                else:
                    worksheet.set_column(i, i, largura)
            
            writer.close()
            print(f"✅ Gerado com sucesso e colunas ordenadas: {caminho_final}")