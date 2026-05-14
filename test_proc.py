import os
import sys

# Setup paths
sys.path.append('/home/labs/portal-ggci')
from apps.dash_polichat.services import polichat_extrator

# Ensure the temp CSV exists (copy the main one to temp)
csv_main = "/home/labs/portal-ggci/dados/dados_polichat/analise_anual/relatorio_chats_atualizado.csv"
csv_temp = "/home/labs/portal-ggci/dados/dados_polichat/analise_anual/relatorio_chats_temp.csv"

import shutil
if os.path.exists(csv_main):
    shutil.copy2(csv_main, csv_temp)
    print(f"Copiado {csv_main} para {csv_temp}")
else:
    print("CSV principal não encontrado!")
    sys.exit(1)

# Run processing
print("Iniciando analisar_e_limpar_dados()...")
success = polichat_extrator.analisar_e_limpar_dados()
print(f"Sucesso: {success}")

# Check files
path_base = "/home/labs/portal-ggci/dados/dados_polichat/analise_anual/"
for f in ["relatorio_chats_atualizado.csv", "relatorio_chats_pronto.xlsx", "cache_dataframe.pkl"]:
    p = os.path.join(path_base, f)
    print(f"Arquivo {f}: {'EXISTE' if os.path.exists(p) else 'NÃO EXISTE'}")
