import pandas as pd
import os

path = "/home/labs/portal-ggci/dados/dados_polichat/analise_anual/cache_dataframe.pkl"
if os.path.exists(path):
    df = pd.read_pickle(path)
    print(f"Colunas (repr): {[repr(c) for c in df.columns]}")
else:
    print("Arquivo não encontrado")
