"""
=== ARQUIVO: apps/sugestoes/controle_acesso/services/extrator.py ===
Propósito: Traz do banco SIBU, em Parquet local, tudo o que a ficha do Controle de Acesso mostra.
Dependências: sqlalchemy, mysql-connector, pandas, polars, python-dotenv.

MESMA METODOLOGIA DO DOCUMENTOS IA (`dash_documentos_ia/services/extrator.py`):
cada `.sql` de `sql/<assunto>/` vira uma tabela `sibu.PY_ggci_<assunto>_temp_d1_controle_acesso`,
que é lida para Parquet e
apagada em seguida — CREATE → SELECT → DROP. O banco não guarda nada deste app.

O QUE MUDA EM RELAÇÃO A ELE:
  - Não há ScriptCase: tudo o que a ficha precisa (inclusive os documentos que a IES
    enviou, em `documentos_faculdades`) está no banco. Sem navegador, sem disputa de
    sessão com os outros motores.
  - A leitura é EM BLOCOS. O histórico de pagamentos tem ~3,9 milhões de linhas; lido de
    uma vez pelo pandas, ele ocupa a memória do servidor inteiro por alguns segundos.
"""

import concurrent.futures
import datetime
import os
import time
from urllib.parse import quote_plus

from dotenv import load_dotenv

# override=True: o motor nasce de um Popen do worker do Django, e sem isso uma senha
# trocada no .env só valeria depois de reiniciar o servidor (mesmo motivo do Documentos IA).
load_dotenv(override=True)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
PASTA_APP = os.path.join(PROJECT_ROOT, "apps", "sugestoes", "controle_acesso")
PASTA_SQL = os.path.join(PASTA_APP, "sql")
PASTA_PARQUETS = os.path.join(PASTA_APP, "dados", "tabelas_sql")

# O sufixo do app vai no nome do .sql, no CREATE TABLE e no Parquet: sem ele, dois apps
# rodando a mesma família de queries derrubariam a tabela um do outro. O sufixo do
# ambiente fica no FIM, e é por isso que `nome_base = nome.replace(env_suffix, "")` funciona.
SUFIXO_APP = "_controle_acesso"
ENV_SUFFIX = "_dev" if "dev" in os.path.basename(PROJECT_ROOT).lower() else "_prod"

# Chave lógica → nome-base da tabela/arquivo (sem o sufixo do ambiente). Mesmo padrão do
# Documentos IA: `PY_ggci_<assunto>_temp_d1<sufixo do app>`, com o .sql em `sql/<assunto>/`
# (a chave é o nome da subpasta).
TABELAS = {
    "beneficiarios": f"PY_ggci_beneficiarios_temp_d1{SUFIXO_APP}",
    "situacoes": f"PY_ggci_situacoes_temp_d1{SUFIXO_APP}",
    "coletas": f"PY_ggci_coletas_temp_d1{SUFIXO_APP}",
    "pagamentos": f"PY_ggci_pagamentos_temp_d1{SUFIXO_APP}",
    "documentos": f"PY_ggci_documentos_temp_d1{SUFIXO_APP}",
}

# Quantas tabelas materializar ao mesmo tempo no SIBU — o mesmo teto do Documentos IA.
ETL_PARALELO = 4

# Linhas por bloco na leitura. 200 mil mantém o pico de memória baixo sem multiplicar
# demais as idas ao banco.
LINHAS_POR_BLOCO = 200_000


def caminho_parquet(chave):
    """Onde fica o Parquet de uma tabela lógica neste ambiente."""
    return os.path.join(PASTA_PARQUETS, f"{TABELAS[chave]}{ENV_SUFFIX}.parquet")


def caminho_documentos_site():
    """Envios de documentos lidos do site na atualização bruta (ver `scraping.py`)."""
    return os.path.join(PASTA_APP, "dados", "site", f"PY_ggci_documentos_site{SUFIXO_APP}{ENV_SUFFIX}.parquet")


def _engine():
    from sqlalchemy import create_engine

    # `pool_pre_ping`: uma conexão que morreu num timeout não pode ser devolvida pelo pool
    # para a tabela seguinte (caso de 10/09/2026 no Documentos IA).
    return create_engine(
        f"mysql+mysqlconnector://{os.getenv('SIBU_BANCO_DADOS_USER')}:"
        f"{quote_plus(os.getenv('SIBU_BANCO_DADOS_PASS'))}@{os.getenv('SIBU_BANCO_DADOS_HOST')}/"
        f"{os.getenv('SIBU_BANCO_DADOS_NAME')}",
        connect_args={"connect_timeout": 30, "read_timeout": 600},
        pool_pre_ping=True,
    )


def dono_do_lock_morto(caminho_lock):
    """
    O QUE FAZ: Diz se o processo que criou o lock já não existe.
    POR QUÊ EXISTE: o Parar mata o motor por SIGTERM e o `finally` que apaga o lock não
      roda; sem esta checagem a execução seguinte esperaria o lock órfão envelhecer.
    """
    try:
        with open(caminho_lock) as f_lock:
            pid = int(f_lock.readline().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f_stat:
            return f_stat.read().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


def _tipos_do_mysql(conn, nome_tabela):
    """
    Coluna → tipo polars, a partir do tipo declarado no MySQL.

    POR QUÊ EXISTE: o pandas adivinha o tipo de cada bloco pelo conteúdo. Uma coluna inteira
    com nulos sai `float` num bloco e `object` em outro, e a concatenação promovia a coluna
    inteira a TEXTO ("49700.0") — era o caso de `valor_matricula_sem_desconto`. Tipando pelo
    banco, todos os blocos chegam iguais e o Parquet sai com o tipo certo.
    """
    import polars as pl
    from sqlalchemy import text

    inteiros = {"tinyint", "smallint", "mediumint", "int", "bigint", "year"}
    decimais = {"decimal", "float", "double"}
    tipos = {}
    for coluna, tipo in conn.execute(text(
            "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = 'sibu' AND TABLE_NAME = :t"), {"t": nome_tabela}):
        if tipo in inteiros:
            tipos[coluna] = pl.Int64
        elif tipo in decimais:
            tipos[coluna] = pl.Float64
        elif tipo == "date":
            tipos[coluna] = pl.Date
        elif tipo in ("datetime", "timestamp"):
            tipos[coluna] = pl.Datetime("us")
        else:
            tipos[coluna] = pl.String
    return tipos


def _tipar_bloco(bloco, tipos):
    """Converte um bloco do pandas para polars já com os tipos do MySQL."""
    import pandas as pd
    import polars as pl

    for coluna, tipo in tipos.items():
        if coluna not in bloco.columns:
            continue
        if tipo in (pl.Int64, pl.Float64):
            bloco[coluna] = pd.to_numeric(bloco[coluna], errors="coerce")
        elif tipo == pl.Date or isinstance(tipo, pl.Datetime):
            # Datas inválidas do SIBU ('0000-00-00') viram nulo em vez de derrubar o bloco.
            bloco[coluna] = pd.to_datetime(bloco[coluna], errors="coerce")
        else:
            bloco[coluna] = bloco[coluna].astype("string")
    df = pl.from_pandas(bloco)
    return df.with_columns([pl.col(c).cast(t) for c, t in tipos.items() if c in df.columns])


def _ler_em_blocos(conn, nome_tabela):
    """
    Lê `sibu.<nome_tabela>` em blocos e devolve um único DataFrame polars tipado.

    A PAGINAÇÃO É FEITA PELO BANCO. O `chunksize` do pandas sozinho não economiza nada com o
    mysql-connector: o driver traz o resultado INTEIRO antes de o pandas fatiar, e o
    `stream_results` do SQLAlchemy é ignorado nesse dialeto. Medido em 16/10/2026: 3,9 GB de
    pico com os 3,9 milhões de pagamentos, nas duas formas. Aqui a tabela temporária ganha
    uma chave numerada e cada bloco é um intervalo dessa chave — só ele chega à memória.
    """
    import pandas as pd
    import polars as pl
    from sqlalchemy import text

    tipos = _tipos_do_mysql(conn, nome_tabela)
    conn.execute(text(f"ALTER TABLE sibu.{nome_tabela} "
                      "ADD COLUMN _linha BIGINT AUTO_INCREMENT PRIMARY KEY FIRST"))
    blocos, ultima = [], 0
    while True:
        bloco = pd.read_sql(
            text(f"SELECT * FROM sibu.{nome_tabela} WHERE _linha > :ultima "
                 f"ORDER BY _linha LIMIT {LINHAS_POR_BLOCO}"),
            conn, params={"ultima": ultima},
        )
        if bloco.empty:
            break
        ultima = int(bloco["_linha"].iloc[-1])
        blocos.append(_tipar_bloco(bloco.drop(columns="_linha"), tipos))
        if len(bloco) < LINHAS_POR_BLOCO:
            break
    if not blocos:
        return pl.DataFrame(schema=tipos)
    # Concatenação ESTRITA: com os blocos tipados pelo banco, qualquer divergência de tipo
    # é defeito e precisa aparecer, não ser resolvida virando texto.
    return pl.concat(blocos, how="vertical")


def atualizar_parquets(forcar=False, total_etapas=None):
    """
    O QUE FAZ: Materializa cada tabela `PY_ggci_*_controle_acesso` no SIBU, grava em Parquet e a apaga.
    COMO FUNCIONA:
      1. Varre resíduos de execuções que morreram no meio (só pelos nomes DESTE app).
      2. Para cada tabela: pula se o Parquet já é de hoje (o banco é D-1, então reconsultar
         no mesmo dia devolveria os mesmos dados); senão pega o lock, roda
         DROP → CREATE (o .sql) → SELECT em blocos → DROP no `finally` e grava o Parquet
         de forma atômica (.tmp + os.replace), para a tela nunca ler um arquivo pela metade.
      3. Emite `[ETL_PROGRESSO] n/total` a cada tabela, que move a barra da tela.
    PARÂMETROS: `forcar` (atualização bruta) ignora o Parquet de hoje e consulta de novo;
      `total_etapas` é o total do `[ETL_PROGRESSO]` quando há etapas depois desta.
    RETORNO: lista com as tabelas que falharam (vazia = tudo certo).
    """
    from sqlalchemy import text

    os.makedirs(PASTA_PARQUETS, exist_ok=True)
    engine = _engine()
    nomes = [f"{base}{ENV_SUFFIX}" for base in TABELAS.values()]

    # VARREDURA DE RESÍDUOS — só os nomes exatos do nosso mapa, nunca um LIKE no prefixo,
    # que apanharia a tabela de outro app no meio do SELECT dele.
    try:
        with engine.connect() as conn:
            marcadores = ", ".join(f":n{i}" for i in range(len(nomes)))
            residuos = [linha[0] for linha in conn.execute(
                text("SELECT TABLE_NAME FROM information_schema.TABLES "
                     f"WHERE TABLE_SCHEMA = 'sibu' AND TABLE_NAME IN ({marcadores})"),
                {f"n{i}": nome for i, nome in enumerate(nomes)},
            )]
            for nome in residuos:
                conn.execute(text(f"DROP TABLE IF EXISTS sibu.{nome}"))
            if residuos:
                conn.commit()
                print(f"[EXTRATOR   | INFO          | BD SIBU    ] Resíduos removidos: {', '.join(residuos)}")
    except Exception as erro:
        # Resíduo é desperdício de espaço, não dado errado: não impede a extração.
        print(f"[EXTRATOR   | AVISO         | BD SIBU    ] ⚠️ Varredura de resíduos falhou: {erro}")

    falhas = []

    def materializar(chave):
        base = TABELAS[chave]
        nome_tabela = f"{base}{ENV_SUFFIX}"
        destino = caminho_parquet(chave)
        caminho_lock = os.path.join(PASTA_PARQUETS, f".lock_{nome_tabela}")

        while True:
            if os.path.exists(destino) and not forcar:
                quando = datetime.datetime.fromtimestamp(os.path.getmtime(destino))
                if quando.date() == datetime.date.today():
                    print(f"[EXTRATOR   | INFO          | CACHE LOCAL] {chave}: Parquet de hoje "
                          f"({quando:%H:%M:%S}) já em disco. Pulando.")
                    return
            if not os.path.exists(caminho_lock):
                break
            if time.time() - os.path.getmtime(caminho_lock) > 600 or dono_do_lock_morto(caminho_lock):
                try:
                    os.remove(caminho_lock)
                except OSError:
                    pass
                continue
            print(f"[EXTRATOR   | INFO          | FILE LOCK  ] Aguardando outro processo extrair {chave}...")
            time.sleep(5)

        with open(caminho_lock, "w") as f_lock:
            f_lock.write(f"{os.getpid()}\n{time.time()}")

        inicio = time.time()
        print(f"[EXTRATOR   | INFO          | BD SIBU    ] Montando {chave}...")
        try:
            with open(os.path.join(PASTA_SQL, chave, f"{base}.sql"), encoding="utf-8") as f_sql:
                sql = f_sql.read().replace(base, nome_tabela)

            with engine.connect() as conn:
                # Datas '0000-00-00' existem no SIBU e o strict mode recusaria copiá-las.
                conn.execute(text("SET SESSION sql_mode = ''"))
                conn.execute(text(f"DROP TABLE IF EXISTS sibu.{nome_tabela}"))
                # O DROP final fica no `finally`: se o CREATE ou o SELECT falharem, a tabela
                # não pode ficar esquecida no SIBU.
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    df = _ler_em_blocos(conn, nome_tabela)
                finally:
                    conn.execute(text(f"DROP TABLE IF EXISTS sibu.{nome_tabela}"))
                    conn.commit()

            temporario = f"{destino}.tmp"
            df.write_parquet(temporario)
            os.replace(temporario, destino)
            print(f"[EXTRATOR   | INFO          | DISCO LOCAL] ✅ {chave}: {df.height:,} linhas "
                  f"em {time.time() - inicio:.0f}s".replace(",", "."))
        except Exception as erro:
            falhas.append(chave)
            print(f"[EXTRATOR   | ERRO          | BD SIBU    ] ❌ {chave}: {erro}")
        finally:
            try:
                os.remove(caminho_lock)
            except OSError:
                pass

    total = len(TABELAS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=ETL_PARALELO) as executor:
        futuros = [executor.submit(materializar, chave) for chave in TABELAS]
        for feitas, futuro in enumerate(concurrent.futures.as_completed(futuros), start=1):
            try:
                futuro.result()
            except Exception as erro:
                print(f"[EXTRATOR   | ERRO          | ETL        ] ❌ Erro não tratado: {erro}")
            print(f"[ETL_PROGRESSO] {feitas}/{total_etapas or total}")

    return falhas
