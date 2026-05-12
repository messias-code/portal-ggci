"""
Verificador de Pagamentos Divergentes
======================================
Varre o consolidado_pagamentos.xlsx e identifica inscrições (UNI_CODIGO)
onde o valor da bolsa (LAN_VALBOLSA) variou entre os meses do mesmo semestre.

Ex: 5 meses de R$300 + 1 mês de R$350 = divergência detectada.
"""

import pandas as pd
import os

ARQ_PAGAMENTOS = os.path.join("dados_analise", "analise_pagamentos", "CONSOLIDADO", "consolidado_pagamentos.xlsx")

def main():
    if not os.path.exists(ARQ_PAGAMENTOS):
        print(f"❌ Arquivo não encontrado: {ARQ_PAGAMENTOS}")
        return

    print(f"📂 Lendo {ARQ_PAGAMENTOS}...")
    df = pd.read_excel(ARQ_PAGAMENTOS, engine='openpyxl')
    print(f"   Total de registros brutos: {len(df):,}")

    # Garante tipos corretos
    df['LAN_VALBOLSA'] = pd.to_numeric(df['LAN_VALBOLSA'], errors='coerce').fillna(0.0)
    df['UNI_CODIGO'] = pd.to_numeric(df['UNI_CODIGO'], errors='coerce').astype('Int64')
    df['SEMESTRE'] = df['SEMESTRE'].astype(str).str.strip()

    # Filtra apenas pagamentos efetivos (ignora cancelamentos)
    df_efetivos = df[df['LAN_VALBOLSA'] > 0].copy()
    print(f"   Pagamentos efetivos (LAN_VALBOLSA > 0): {len(df_efetivos):,}")

    # Agrupa por aluno + semestre e calcula estatísticas
    resumo = df_efetivos.groupby(['UNI_CODIGO', 'SEMESTRE', 'INS_NOME']).agg(
        qtd_pagtos=('LAN_VALBOLSA', 'count'),
        valor_min=('LAN_VALBOLSA', 'min'),
        valor_max=('LAN_VALBOLSA', 'max'),
        total_real=('LAN_VALBOLSA', 'sum'),
        valores=('LAN_VALBOLSA', list)
    ).reset_index()

    # Identifica divergentes: min != max (ou seja, nem todos os valores são iguais)
    divergentes = resumo[resumo['valor_min'] != resumo['valor_max']].copy()
    divergentes['diferenca'] = divergentes['valor_max'] - divergentes['valor_min']
    divergentes = divergentes.sort_values(['SEMESTRE', 'INS_NOME', 'UNI_CODIGO'])

    print(f"\n{'='*100}")
    print(f"🔍 PAGAMENTOS COM VALORES DIVERGENTES ENTRE MESES")
    print(f"{'='*100}")
    print(f"   Total de casos encontrados: {len(divergentes):,}")
    print(f"{'='*100}\n")

    if divergentes.empty:
        print("✅ Nenhuma divergência encontrada! Todos os pagamentos são consistentes.")
        return

    # Agrupa por IES para exibição organizada
    for ies_nome, grupo_ies in divergentes.groupby('INS_NOME'):
        ies_curto = ies_nome[:80] if len(ies_nome) > 80 else ies_nome
        print(f"\n📌 {ies_curto}")
        print(f"   {'─'*90}")

        for _, row in grupo_ies.iterrows():
            valores_str = ", ".join([f"R$ {v:,.2f}" for v in row['valores']])
            total_real = row['total_real']
            # Simula o cálculo antigo (qtd × último valor)
            total_antigo = row['qtd_pagtos'] * row['valores'][-1]
            diff_impacto = total_real - total_antigo

            print(f"   Inscrição: {row['UNI_CODIGO']}  |  Semestre: {row['SEMESTRE']}  |  Pagtos: {row['qtd_pagtos']}")
            print(f"   Valores: [{valores_str}]")
            print(f"   Min: R$ {row['valor_min']:,.2f}  |  Max: R$ {row['valor_max']:,.2f}  |  Δ: R$ {row['diferenca']:,.2f}")
            print(f"   Total REAL (soma): R$ {total_real:,.2f}  |  Total ANTIGO (qtd×último): R$ {total_antigo:,.2f}  |  Impacto: R$ {diff_impacto:,.2f}")
            print(f"   {'─'*90}")

    # Resumo final
    total_impacto = 0
    for _, row in divergentes.iterrows():
        total_antigo = row['qtd_pagtos'] * row['valores'][-1]
        total_impacto += (row['total_real'] - total_antigo)

    print(f"\n{'='*100}")
    print(f"📊 RESUMO GERAL")
    print(f"{'='*100}")
    print(f"   IES afetadas:          {divergentes['INS_NOME'].nunique():,}")
    print(f"   Inscrições afetadas:   {len(divergentes):,}")
    print(f"   Impacto financeiro:    R$ {total_impacto:,.2f} (diferença entre soma real e cálculo antigo)")
    print(f"{'='*100}")


if __name__ == '__main__':
    main()
