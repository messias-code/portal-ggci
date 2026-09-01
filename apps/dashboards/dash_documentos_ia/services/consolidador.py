"""
Propósito: Consolidar múltiplas planilhas de resultados em arquivos únicos (.xlsx), limpando e tipando os dados.
Autor: N/A
Dependências: os, pandas, unicodedata, re
"""

import os
import pandas as pd
import unicodedata
import re
import time

# --- FUNÇÕES DE LIMPEZA ---

def converter_para_numero_real(valor):
    """
    O QUE FAZ: Converte um valor textual com sujeira em um número inteiro (Int64).
    POR QUÊ EXISTE: Arquivos gerados via scraping podem vir com decimais falsos (".0") ou pontuações.
    COMO FUNCIONA: Remove ".0" isolados e depois extrai apenas dígitos com RegEx.
    """
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
    """
    O QUE FAZ: Converte string formatada (ex: "1.234,56") para float.
    POR QUÊ EXISTE: Padronizar campos financeiros vindos do Excel/HTML.
    COMO FUNCIONA: Substitui ponto de milhar, troca vírgula por ponto decimal e converte.
    """
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
    except Exception:
        return 0.0

def limpar_texto_geral(texto):
    """
    O QUE FAZ: Padroniza textos (uppercase, sem acento, sem espaços duplos).
    """
    if pd.isna(texto): return texto
    texto = str(texto).strip().upper()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    return " ".join(texto.split())

def extrair_semestre(caminho):
    """
    O QUE FAZ: Deduz o semestre (ex: "2025-1") a partir do nome do arquivo.
    """
    nome = os.path.basename(caminho).lower()
    ano = re.search(r'202\d', caminho).group(0) if re.search(r'202\d', caminho) else "2026"
    meses_s1 = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun']
    return f"{ano}-1" if any(m in nome for m in meses_s1) else f"{ano}-2"

# --- CONFIGURAÇÃO ---

def get_configs(processo_id=None):
    """
    O QUE FAZ: Retorna a configuração dos mapeamentos de planilhas para consolidação.
    """
    if not processo_id:
        raise ValueError("O processo_id é obrigatório.")
    base_dir = f"apps/dashboards/dash_documentos_ia/dados/processamento/proc_{processo_id}"
    return [
        {
            'tipo': 'agendar',
            'pasta': f'{base_dir}/analise_documentos_agendar_processamentos',
            'saida': 'consolidado_agendar_processamentos.parquet',
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
            'pasta': f'{base_dir}/analise_pagamentos',
            'saida': 'consolidado_pagamentos.parquet',
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
            'tipo': 'proc_riaf',
            'pasta': f'{base_dir}/analise_documentos_processados',
            'subpastas_alvo': ['RIAF'],
            'saida': 'consolidado_processados_riaf.parquet',
            'aba': 'RIAF Processado',
            'ext': '.xlsx',
            'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Cnpj Faculdade'],
            'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
            'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Gemini Razao Social', 'Gemini Nome Faculdade', 'Gemini Beneficio Nome', 'Gemini Nome Mantenedora', 'Gemini Nome Financiamento', 'Documento Tipo'],
            'ordem_colunas': [
                'Status_IA', 'Gemini Inconsistencias', 'Perfil do Beneficiario', 'Inscrição', 'Gemini Matricula', 'Bolsista', 'Bolsistas', 'CPF', 
                'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Gemini Nome Faculdade', 
                'Curso', 'Gemini Curso', 'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
                'Gemini Matricula Sem Desconto', 'Matricula_SD_Doc', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
                'Gemini Matricula Com Desconto', 'Matricula_CD_Doc', 'Gemini Razao Social', 'Gemini Cnpj Faculdade', 
                'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies', 
                'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
                'Gemini Nome Financiamento', 'Gemini Modalidade', 'Gemini Email', 'Gemini Telefone', 
                'Gemini Tipo Bolsa', 
                'Documento Tipo', 'Coleta ID', 'Data Processamento'
            ]
        },
        {
            'tipo': 'proc_historico',
            'pasta': f'{base_dir}/analise_documentos_processados',
            'subpastas_alvo': ['HISTORICO'],
            'saida': 'consolidado_processados_historico.parquet',
            'aba': 'Processados',
            'ext': '.xlsx',
            'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Cnpj Faculdade'],
            'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
            'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Gemini Razao Social', 'Gemini Nome Faculdade', 'Gemini Beneficio Nome', 'Gemini Nome Mantenedora', 'Gemini Nome Financiamento', 'Documento Tipo'],
            'ordem_colunas': [
                'Status_IA', 'Gemini Inconsistencias', 'Perfil do Beneficiario', 'Inscrição', 'Gemini Matricula', 'Bolsista', 'Bolsistas', 'CPF', 
                'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Gemini Nome Faculdade', 
                'Curso', 'Gemini Curso', 'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
                'Gemini Matricula Sem Desconto', 'Matricula_SD_Doc', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
                'Gemini Matricula Com Desconto', 'Matricula_CD_Doc', 'Gemini Razao Social', 'Gemini Cnpj Faculdade', 
                'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies', 
                'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
                'Gemini Nome Financiamento', 'Gemini Modalidade', 'Gemini Email', 'Gemini Telefone', 
                'Gemini Tipo Bolsa', 
                'Documento Tipo', 'Coleta ID', 'Data Processamento'
            ]
        },
        {
            'tipo': 'proc_geral',
            'pasta': f'{base_dir}/analise_documentos_processados',
            'subpastas_alvo': ['BENEFICIOS', 'CONTRATOS', 'FINANCIAMENTO'],
            'saida': 'consolidado_processados.parquet',
            'aba': 'Processados',
            'ext': '.xlsx',
            'cols_num': ['Inscrição', 'CPF', 'Coleta ID', 'Gemini CPF', 'Gemini Matricula', 'Gemini Telefone', 'Gemini Cnpj Faculdade'],
            'cols_moeda': ['Mensalidade S/ Desconto', 'Mensalidade C/ Desconto', 'Gemini Mensalidade S/ Desconto', 'Gemini Mensalidade C/ Desconto', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 'Gemini Matricula Sem Desconto', 'Gemini Matricula Com Desconto'],
            'cols_txt': ['Faculdade', 'Curso', 'Bolsista', 'Bolsistas', 'Gemini Razao Social', 'Gemini Nome Faculdade', 'Gemini Beneficio Nome', 'Gemini Nome Mantenedora', 'Gemini Nome Financiamento', 'Documento Tipo'],
            'ordem_colunas': [
                'Status_IA', 'Gemini Inconsistencias', 'Perfil do Beneficiario', 'Inscrição', 'Gemini Matricula', 'Bolsista', 'Bolsistas', 'CPF', 
                'Gemini CPF', 'Semestre', 'Gemini Semestre', 'Faculdade', 'Gemini Nome Faculdade', 
                'Curso', 'Gemini Curso', 'Mensalidade S/ Desconto', 'Gemini Mensalidade S/ Desconto', 
                'Gemini Matricula Sem Desconto', 'Matricula_SD_Doc', 'Mensalidade C/ Desconto', 'Gemini Mensalidade C/ Desconto', 
                'Gemini Matricula Com Desconto', 'Matricula_CD_Doc', 'Gemini Razao Social', 'Gemini Cnpj Faculdade', 
                'Gemini Nome Mantenedora', 'Gemini Assinatura Aluno', 'Gemini Assinatura Ies', 
                'Gemini Beneficio Nome', 'Gemini Valor Beneficio', 'Gemini Valor Financiado', 
                'Gemini Nome Financiamento', 'Gemini Modalidade', 'Gemini Email', 'Gemini Telefone', 
                'Gemini Tipo Bolsa', 
                'Documento Tipo', 'Coleta ID', 'Data Processamento'
            ]
        },
        {
            # A LISTA DE COBRANÇA COMO O SITE A ENXERGA — o menu `Relatório de Contratos`,
            # baixado sem filtro de inscrição. Não é uma fonte de documento: é a única
            # forma de saber O QUE O SIBU ESTÁ COBRANDO, que nenhuma tabela do banco
            # responde. O motor cruza esta lista com a nossa para achar a cobrança sem
            # lançamento no semestre.
            #
            # `Lançamento` é a coluna que decide: ela vem do próprio site, que portanto
            # TEM o dado e cobra assim mesmo.
            'tipo': 'cobranca',
            'pasta': f'{base_dir}/cobranca_do_site',
            'saida': 'consolidado_cobranca_do_site.parquet',
            'aba': 'Cobrança do Site',
            'ext': '.xlsx',
            'semestre_do_nome_do_arquivo': True,
            'cols_num': ['Inscrição', 'CPF'],
            'cols_moeda': [],
            'cols_txt': ['Beneficiário', 'Instituição', 'Documento', 'Documento status', 'Lançamento'],
            'ordem_colunas': [
                'Inscrição', 'Semestre', 'Beneficiário', 'CPF', 'Beneficiário status',
                'Instituição', 'CNPJ', 'Documento', 'Documento status', 'Lançamento',
            ]
        }
    ]

def consolidar(processo_id=None):
    """
    O QUE FAZ: Percorre as pastas configuradas, une as planilhas parciais, limpa os dados e exporta um Excel unificado.
    POR QUÊ EXISTE: Preparar a base de dados em um formato que o Motor GGCI possa ler sem se preocupar com I/O de dezenas de arquivos pequenos.
    COMO FUNCIONA:
      1. Usa os.walk() para achar as planilhas geradas.
      2. Concatena os DataFrames.
      3. Executa tratamentos (conversões, uppercase) de forma vetorizada (para otimizar O(N)).
      4. Gera o Excel utilizando XlsxWriter para formatar larguras e tipos.
    """
    t_inicio_global = time.time()
    configs = get_configs(processo_id)
    for cf in configs:
        pasta_base = cf['pasta']
        pasta_dest = os.path.join(pasta_base, 'CONSOLIDADO')
        os.makedirs(pasta_dest, exist_ok=True)
        t_inicio = time.time()
        lista_df = []
        tipo_fmt = cf['tipo'].upper()[:6].ljust(6)

        for raiz, dirs, arquivos in os.walk(pasta_base):
            if 'CONSOLIDADO' in raiz: continue
            
            if 'subpastas_alvo' in cf:
                if not any(alvo in raiz for alvo in cf['subpastas_alvo']):
                    continue

            for arq in arquivos:
                if arq.endswith(cf['ext']) and not arq.startswith('~$'):
                    caminho = os.path.join(raiz, arq)
                    try:
                        # Fallback de HTML table para arquivos com extensão .xls enganosa
                        if arq.endswith('.xlsx'):
                            df = pd.read_excel(caminho)
                        else:
                            try:
                                df = pd.read_excel(caminho, engine='xlrd')
                            except Exception:
                                dfs_html = pd.read_html(caminho)
                                if not dfs_html: continue
                                df = dfs_html[0]
                                col_referencia = cf['cols_num'][0]
                                if col_referencia in str(df.iloc[0].values):
                                    df.columns = df.iloc[0]; df = df[1:]
                        
                        if df is not None:
                            df = df.dropna(how='all', axis=0)

                            # O RELATÓRIO DE COBRANÇA NÃO TRAZ O SEMESTRE em coluna nenhuma —
                            # ele é um parâmetro da tela, não um dado da linha. O extrator o
                            # grava no nome do arquivo (`{prefixo}_{semestre}.xlsx`), e é de
                            # lá que ele vem. Sem isso as planilhas dos vários semestres
                            # empilhariam indistinguíveis, e a cobrança de 2025-2 se
                            # misturaria com a de 2026-1.
                            if cf.get('semestre_do_nome_do_arquivo'):
                                achado = re.search(r'(\d{4}-[12])', arq)
                                if not achado:
                                    print(f"[CONSOLIDAR | AVISO         | {tipo_fmt}] "
                                          f"{arq}: sem semestre no nome, ignorado.")
                                    continue
                                df['Semestre'] = achado.group(1)
                            
                            # OTIMIZAÇÃO: Limpeza de Texto Vetorizada
                            for col in cf['cols_txt']:
                                if col in df.columns:
                                    df[col] = df[col].fillna("").astype(str).str.upper().str.strip()
                                    df[col] = df[col].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
                                    df[col] = df[col].str.replace(r'\s+', ' ', regex=True)

                            # OTIMIZAÇÃO: Limpeza de Moedas
                            for col in cf['cols_moeda']:
                                if col in df.columns:
                                    df[col] = df[col].apply(converter_para_moeda)

                            # OTIMIZAÇÃO: Limpeza Numérica Vetorizada
                            for col in cf['cols_num']:
                                if col in df.columns:
                                    s = df[col].fillna("").astype(str).str.strip().str.lower()
                                    s = s.replace({'nan': '', 'none': '', '<na>': ''}).astype(str)
                                    s = s.str.replace(r'\.0+$', '', regex=True)
                                    s = s.str.replace(r'\D', '', regex=True)
                                    s_num = pd.to_numeric(s, errors='coerce')
                                    s_num = s_num.where((s_num >= -9223372036854775800) & (s_num <= 9223372036854775800))
                                    df[col] = s_num.astype('Int64')

                            if cf['tipo'] == 'pag':
                                df.insert(0, 'SEMESTRE', extrair_semestre(caminho))

                            lista_df.append(df)
                    except Exception as e:
                        print(f"[CONSOLIDAR | ERRO          | {tipo_fmt}] {arq}: {e}")

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
                           'Gemini Email', 'Gemini Telefone', 'Gemini Tipo Bolsa']
                df_final.drop(columns=col_rem, errors='ignore', inplace=True)
                
            elif cf['tipo'] in ['proc_geral', 'proc_riaf', 'proc_historico']:
                # `proc_historico` ficava de fora desta lista, e o efeito era silencioso:
                # sem o rename, o consolidado do histórico nunca tinha `Status_IA`, então
                # as 21 mil linhas trazidas do ScriptCase entravam no motor sem status
                # nenhum. O histórico dependia inteiramente do espelho D-1 do banco — o
                # oposto do que a extração existe para fazer.
                cols_drop = ['Gemini Status', 'Status Obs', 'Status OVG', 'Status Ovg']
                df_final.drop(columns=cols_drop, errors='ignore', inplace=True)
                df_final.rename(columns={
                    'Status Gemini': 'Status_IA'
                }, inplace=True)

            # --- APLICA A NOVA ORDEM DE COLUNAS ---
            if 'ordem_colunas' in cf:
                colunas_ordenadas = [c for c in cf['ordem_colunas'] if c in df_final.columns]
                colunas_extras = [c for c in df_final.columns if c not in colunas_ordenadas]
                df_final = df_final[colunas_ordenadas + colunas_extras]

            caminho_final = os.path.join(pasta_dest, cf['saida'])
            df_final.to_parquet(caminho_final, engine='pyarrow', index=False)
            t_total = time.time() - t_inicio
            print(f"[CONSOLIDAR | PLANILHA      | {tipo_fmt}] {cf['saida']} salvo em {t_total:.2f}s")

    t_total_global = time.time() - t_inicio_global
    minutos = int(t_total_global // 60)
    segundos = int(t_total_global % 60)
    print(f"🎉 Consolidação concluída: Planilhas consolidadas e limpas em {minutos}m e {segundos}s.")
