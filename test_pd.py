import pandas as pd
import os
import json

BASE_DIR = '/home/labs/portal-ggci'
arquivo_excel = os.path.join(BASE_DIR, "dados_polichat", "analise_anual", "relatorio_chats_pronto.xlsx")

try:
    df = pd.read_excel(arquivo_excel, engine='openpyxl')
    print("Cols:", df.columns)
    # Contagens de Tipo
    if 'Tipo' in df.columns:
        total_contatos = len(df)
        contatos_receptivos = len(df[df['Tipo'].astype(str).str.lower().str.contains('receptivo', na=False)])
        contatos_ativos = len(df[df['Tipo'].astype(str).str.lower().str.contains('ativo', na=False)])
        print("Tipos:", total_contatos, contatos_receptivos, contatos_ativos)
    else:
        print("Nao achou Tipo")

    if 'Status do Atendimento' in df.columns:
        status_counts = df['Status do Atendimento'].value_counts().to_dict()
        print("Status counts:", status_counts)
    else:
        print("Nao achou status")
        
    def str_to_seconds(t_str):
        try:
            if pd.isna(t_str) or not isinstance(t_str, str): return 0
            parts = t_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return 0
        except: return 0

    if 'Tempo primeira mensagem' in df.columns:
        print("Tempos originais:")
        print(df['Tempo primeira mensagem'].head())
        tempos_segundos = df['Tempo primeira mensagem'].apply(str_to_seconds)
        tempos_validos = tempos_segundos[tempos_segundos > 0]
        print("Max tempo:", tempos_validos.max() if not tempos_validos.empty else 0)

except Exception as e:
    import traceback
    traceback.print_exc()

