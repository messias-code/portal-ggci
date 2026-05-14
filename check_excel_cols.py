import pandas as pd
import os

path = "/home/labs/portal-ggci/dados/dados_polichat/analise_anual/relatorio_chats_pronto.xlsx"
if os.path.exists(path):
    df = pd.read_excel(path, engine='openpyxl')
    print(f"Colunas: {df.columns.tolist()}")
else:
    print("Arquivo não encontrado")
