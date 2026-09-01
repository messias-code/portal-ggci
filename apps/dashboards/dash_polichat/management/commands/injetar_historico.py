from django.core.management.base import BaseCommand
import os
import pandas as pd
import polars as pl
from django.conf import settings

class Command(BaseCommand):
    help = 'Injeta um CSV manual na base histórica para tapar buracos.'

    def handle(self, *args, **options):
        pasta_dados = os.path.join(settings.BASE_DIR, "apps", "dashboards", "dash_polichat", "dados")
        arquivo_historico = os.path.join(pasta_dados, "relatorio_chats_atualizado.csv")
        arquivo_injecao = os.path.join(pasta_dados, "recuperacao.csv")
        arquivo_pickle = os.path.join(pasta_dados, "cache_dataframe.pkl")
        
        if not os.path.exists(arquivo_injecao):
            self.stdout.write(self.style.ERROR(f"Arquivo não encontrado: {arquivo_injecao}"))
            return
            
        if not os.path.exists(arquivo_historico):
            self.stdout.write(self.style.ERROR("Base histórica não encontrada!"))
            return
            
        self.stdout.write("🔀 Lendo base histórica...")
        df_hist = pd.read_csv(arquivo_historico, sep=',', dtype=str, low_memory=False)
        
        self.stdout.write("📥 Lendo arquivo de recuperação...")
        df_novo = pd.read_csv(arquivo_injecao, sep=',', dtype=str, low_memory=False)
        
        self.stdout.write("🔗 Fundindo os dados...")
        df_pd = pd.concat([df_hist, df_novo], ignore_index=True)
        
        if 'Id do atendimento' in df_pd.columns:
            mask = df_pd['Id do atendimento'].notna() & (df_pd['Id do atendimento'] != '') & (df_pd['Id do atendimento'] != 'nan')
            df_valid = df_pd[mask].drop_duplicates(subset=['Id do atendimento'], keep='last')
            df_invalid = df_pd[~mask]
            df_pd = pd.concat([df_valid, df_invalid], ignore_index=True)
        else:
            df_pd = df_pd.drop_duplicates(keep='last')
            
        self.stdout.write("💾 Salvando nova base histórica consolidada...")
        df_pd.to_csv(arquivo_historico, index=False)
        
        self.stdout.write("✅ Reconstruindo o Pickle de alta performance...")
        # Chama a função de tratamento final apenas para garantir o formato do pickle
        from apps.dashboards.dash_polichat.services import polichat_extrator
        polichat_extrator.ARQUIVO_CSV_TMP = arquivo_historico  # engana a função para processar o histórico
        sucesso = polichat_extrator.analisar_e_limpar_dados(primeira_vez_dia=True)
        
        if sucesso:
            self.stdout.write(self.style.SUCCESS("🎉 SUCESSO ABSOLUTO! O buraco foi tapado e a dashboard atualizada!"))
            os.remove(arquivo_injecao)
