"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/scraping.py ===
Propósito: Atualização BRUTA dos envios de documentos, lidos direto do site (ScriptCase).
Dependências: playwright (via o extrator do Documentos IA), pandas, polars.

POR QUÊ EXISTE: o banco SIBU que a atualização normal lê é D-1 — o que a IES anexou hoje
só apareceria amanhã. A bruta baixa do site, na hora, a lista de documentos enviados.

COMO FUNCIONA:
  - Usa o mesmo robô do Documentos IA (`extrair_documento_scriptcase`) no menu "Análise
    Contratos Processados", que lista todo documento enviado, processado ou não, com
    Inscrição, Semestre e Coleta ID. Em modo bruto: sem filtro de inscrições, o semestre
    inteiro de cada documento.
  - Só o semestre atual e o anterior: os mais antigos já estão completos no banco, e cada
    download do semestre inteiro leva minutos no site.
  - Grava um Parquet só (`caminho_documentos_site`), que a consulta soma aos envios do
    banco. Falhou tudo → o Parquet anterior fica.
"""

import concurrent.futures
import datetime
import os
import shutil

import pandas as pd
import polars as pl

from .extrator import PASTA_APP, caminho_documentos_site

# Categoria do robô do Documentos IA → `documentos.id` do SIBU.
DOC_ID_DA_CATEGORIA = {'CONTRATOS': 39, 'RIAF': 42, 'HISTORICO': 9, 'BENEFICIOS': 41, 'FINANCIAMENTO': 40}

MENU = "Análise Contratos Processados"

# Downloads ao mesmo tempo. O robô já segura a geração no site a 3 por vez (`export_lock`).
PARALELO = 3


def semestres_recentes(hoje=None):
    """O semestre atual e o anterior, no formato do site ('2026-2', '2026-1')."""
    hoje = hoje or datetime.date.today()
    atual = (hoje.year, 1 if hoje.month <= 6 else 2)
    anterior = (atual[0], 1) if atual[1] == 2 else (atual[0] - 1, 2)
    return [f"{a}-{s}" for a, s in (anterior, atual)]


def _ler_planilha(caminho, categoria, semestre):
    """
    As linhas de envio de uma planilha baixada, no formato do Parquet de documentos.
    O menu não traz a data do envio: `data_create` fica nulo (a tela mostra "—").
    """
    df = pd.read_excel(caminho)
    if 'Inscrição' not in df.columns and len(df) and 'Inscrição' in [str(v) for v in df.iloc[0].values]:
        df.columns = df.iloc[0]
        df = df[1:]
    numero = lambda col: (pd.to_numeric(df[col], errors='coerce') if col in df.columns
                          else pd.Series([None] * len(df), dtype='float64'))
    processado_em = (pd.to_datetime(df['Data Processamento'], dayfirst=True, errors='coerce')
                     if 'Data Processamento' in df.columns else pd.Series([pd.NaT] * len(df)))
    saida = pd.DataFrame({
        'uni_codigo': numero('Inscrição').to_numpy(),
        'coleta_dados_id': numero('Coleta ID').to_numpy(),
        'data_processamento': processado_em.to_numpy(),
    })
    return (pl.from_pandas(saida, nan_to_null=True)
            .select(
                pl.lit(None, dtype=pl.Int64).alias('id'),
                pl.col('uni_codigo').cast(pl.Int64),
                pl.lit(DOC_ID_DA_CATEGORIA[categoria], dtype=pl.Int64).alias('documentos_id'),
                pl.lit(semestre, dtype=pl.String).alias('semestre'),
                pl.lit(None, dtype=pl.Int64).alias('status'),
                pl.col('coleta_dados_id').cast(pl.Int64),
                pl.lit(None, dtype=pl.Datetime('us')).alias('data_create'),
                # O menu não tem a coluna `processado`; a data do processamento diz o mesmo.
                pl.when(pl.col('data_processamento').is_not_null()).then(pl.lit('S'))
                  .otherwise(pl.lit(None, dtype=pl.String)).alias('processado'),
                pl.col('data_processamento').cast(pl.Datetime('us')),
            )
            .filter(pl.col('uni_codigo').is_not_null()))


def atualizar_documentos_site(processo_id, ja_feitas=0, total_etapas=None):
    """
    O QUE FAZ: Baixa do site os envios de cada documento nos semestres recentes e grava
      o Parquet dos envios do site.
    PARÂMETROS: `ja_feitas`/`total_etapas` continuam a contagem do `[ETL_PROGRESSO]` de
      onde a extração do banco parou, para a barra andar numa escala só.
    RETORNO: lista das tarefas que falharam (vazia = tudo certo).
    """
    # Import tardio: o robô traz o Playwright, que a atualização normal não precisa.
    from apps.dashboards.dash_documentos_ia.services.extrator import (
        CONFIG_DOCUMENTOS, extrair_documento_scriptcase)

    pasta = os.path.join(PASTA_APP, "dados", "site", f"proc_{processo_id}")
    shutil.rmtree(pasta, ignore_errors=True)
    tarefa = {"nome_menu": MENU, "pasta_raiz": pasta}
    semestres = semestres_recentes()
    trabalhos = [(doc, sem) for doc in CONFIG_DOCUMENTOS for sem in semestres]
    total = total_etapas or len(trabalhos)
    bruta = [{"documento": doc["categoria"], "semestres": []} for doc in CONFIG_DOCUMENTOS]

    print(f"[SITE       | INFO          | SCRIPTCASE ] 🔁 Atualização bruta: {len(trabalhos)} downloads "
          f"({', '.join(semestres)}).")
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALELO) as executor:
        futuros = [executor.submit(extrair_documento_scriptcase, tarefa, doc, sem, atualizacao_bruta=bruta)
                   for doc, sem in trabalhos]
        for feitas, futuro in enumerate(concurrent.futures.as_completed(futuros), start=ja_feitas + 1):
            try:
                futuro.result()
            except Exception as erro:
                print(f"[SITE       | ERRO          | SCRIPTCASE ] ❌ {erro}")
            print(f"[ETL_PROGRESSO] {feitas}/{total}")

    # O robô não devolve se baixou: quem diz é o arquivo em disco. "Sem registros" também
    # não gera arquivo, então ausência só é falha quando NENHUM chegou.
    partes, falhas = [], []
    for doc, sem in trabalhos:
        caminho = os.path.join(pasta, doc["categoria"], sem[:4], f"{doc['prefixo']}_{sem}.xlsx")
        if not os.path.exists(caminho):
            falhas.append(f"{doc['categoria']} {sem}")
            continue
        try:
            partes.append(_ler_planilha(caminho, doc["categoria"], sem))
        except Exception as erro:
            falhas.append(f"{doc['categoria']} {sem}")
            print(f"[SITE       | ERRO          | PLANILHA   ] ❌ {doc['categoria']} {sem}: {erro}")

    if falhas:
        print(f"[SITE       | AVISO         | SCRIPTCASE ] ⚠️ Sem planilha (falha ou semestre vazio): {', '.join(falhas)}")
    if partes:
        df = pl.concat(partes, how="vertical").unique(
            subset=['uni_codigo', 'documentos_id', 'semestre', 'coleta_dados_id'], keep='first')
        destino = caminho_documentos_site()
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        df.write_parquet(f"{destino}.tmp")
        os.replace(f"{destino}.tmp", destino)
        print(f"[SITE       | INFO          | DISCO LOCAL] ✅ {df.height:,} envios lidos do site.".replace(",", "."))
    shutil.rmtree(pasta, ignore_errors=True)
    return falhas if not partes else []
