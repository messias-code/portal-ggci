import os
import sys

# Simulating the path calculation in polichat_extrator.py
file_path = "/home/labs/portal-ggci/apps/dash_polichat/services/polichat_extrator.py"
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(file_path))))
download_path = os.path.join(base_dir, "dados", "dados_polichat", "analise_anual")

print(f"File Path: {file_path}")
print(f"BASE_DIR: {base_dir}")
print(f"DOWNLOAD_PATH: {download_path}")
print(f"Exists: {os.path.exists(download_path)}")
