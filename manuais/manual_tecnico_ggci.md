# ⚙️ Manual Técnico: `ggci.py`
### Motor Principal de Processamento, Consolidação e Relatórios do Portal GGCI

> **Para quem é este documento?** → Desenvolvedores e engenheiros de dados que precisam entender, auditar, manter ou recriar do zero a lógica de consolidação e auditoria financeira de documentos de bolsistas (Contratos, Benefícios, RIAF).
> **Posição no Pipeline:** → Este é o script final (Etapa de Consolidação). Ele atua *após* a extração web (`extrator.py`) e *após* o processamento de visão computacional/LLM (`executar_motor_ia.py`), cruzando o que a IA extraiu com o banco de dados oficial (SQL) para encontrar inconsistências financeiras.

---

## 1. ÍNDICE
1. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
2. [🧹 Sessão 1: Limpeza e Tipagem de Dados](#-sessão-1-limpeza-e-tipagem-de-dados)
3. [🎨 Sessão 2: Formatação Visual Dinâmica (Excel)](#-sessão-2-formatação-visual-dinâmica-excel)
4. [🗄️ Sessão 3: Extração Financeira via SQL](#-sessão-3-extração-financeira-via-sql)
5. [🔄 Sessão 4: Mesclagem SQL e Reordenação](#-sessão-4-mesclagem-sql-e-reordenação)
6. [🚶 Sessão 5: Transições de Vínculo e Regras de Negócio](#-sessão-5-transições-de-vínculo-e-regras-de-negócio)
7. [🤖 Sessão 6: Auditoria da IA e Diagnóstico Financeiro](#-sessão-6-auditoria-da-ia-e-diagnóstico-financeiro)
8. [📊 Sessão 7: Gerador de Resumo Quantitativo](#-sessão-7-gerador-de-resumo-quantitativo)
9. [📈 Sessão 8: Gerador da Aba de Relatório IES](#-sessão-8-gerador-da-aba-de-relatório-ies)
10. [⚙️ Sessão 9: Orquestrador Principal do GGCI](#️-sessão-9-motor-principal-ggci)
11. [Apêndice](#apêndice)

---

## Visão Geral da Arquitetura

O `ggci.py` atua como um ETL complexo de cruzamento de fontes heterogêneas:

```ascii
                      [ENTRADAS]
┌─────────────────────────────────────────────────────┐
│ 1. Planilhas IA (.xlsx)                             │
│    ├─ consolidado_processados.xlsx (Contratos/etc)  │
│    └─ consolidado_processados_riaf.xlsx             │
│                                                     │
│ 2. Faturamento (Planilha)                           │
│    └─ consolidado_pagamentos.xlsx                   │
│                                                     │
│ 3. Banco de Dados SQL (MySQL)                       │
│    └─ Tabela sibu.PY_ggci_analise_IA                │
└───────────────────────┬─────────────────────────────┘
                        │
                        ↓
            [TRANSFORMAÇÕES (ggci.py)]
┌─────────────────────────────────────────────────────┐
│ a) Limpeza e tipagem rigorosa (Int64 / float)       │
│ b) Identificação de Falsos Ausentes                 │
│ c) Cruzamento de dados SQL (Left Join por Aluno/Sem)│
│ d) Identificação de transições (Mudou de curso/IES) │
│ e) Cálculo de divergências de Mensalidade           │
│ f) Geração de Resumo Quantitativo                   │
└───────────────────────┬─────────────────────────────┘
                        │
                        ↓
                       [SAÍDA]
┌─────────────────────────────────────────────────────┐
│ 📁 dados/dados_analise_ia/                           │
│  └─ 📄 relatorio_geral.xlsx                          │
│     ├─ Aba: Documentos (Lista 1x1 colorida)          │
│     ├─ Aba: Riaf (Lista 1x1 colorida)                │
│     ├─ Aba: Resumo_Quantitativo (Estatísticas)       │
│     └─ Aba: Relatório 2025 (Dashboard dinâmico)      │
└─────────────────────────────────────────────────────┘
```

---

## 🧹 Sessão 1: Limpeza e Tipagem de Dados

### O que é e por quê existe
Antes de cruzar chaves (CPFs, IDs de inscrição) e realizar operações matemáticas (diferença de mensalidades), é preciso uniformizar os dados. A decisão de design crucial aqui foi o uso do tipo numérico `Int64` do Pandas para IDs e CPFs em vez do clássico `int64`. 
**Por que Int64 e não int64 ou object (string)?** O Pandas padrão converte automaticamente um `int64` para `float64` quando encontra um valor vazio (`NaN`), o que transformaria um CPF de `12345678900` para `1.23456789e+10`. O `Int64` (com "I" maiúsculo) suporta valores nulos sem alterar a tipagem raiz, evitando perdas de informação em chaves primárias.

### Como funciona
```python
def converter_colunas_para_salvamento(df):
    for col in COLS_NUM: # Lista de colunas como CPF, Inscrição, etc.
        if col in df.columns:
            # errors='coerce': Transforma strings impossíveis (ex: 'Não informado') em nulo (NaN)
            # .astype('Int64'): Força tipo inteiro anulável
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    for col in COLS_MOEDA:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
    return df
```
- **Parâmetro não trivial:** `errors='coerce'` em `pd.to_numeric`. Se a IA leu "Cem reais" em vez de "100", o sistema tenta converter e falha. Em vez de crashar a aplicação (`raise`), o `coerce` converte para `<NA>` ou `NaN`, permitindo que as máscaras seguintes classifiquem a leitura como corrompida.

### Exemplo prático
| Coluna (Antes) | Tipo (Antes) | Valor (Depois) | Tipo (Depois) |
| :--- | :--- | :--- | :--- |
| `Gemini CPF` | object | `06543212345` | Int64 |
| `Inscrição` | object | `<NA>` | Int64 |
| `Mensalidade` | string | `1500.5` | float64 |
| `Mensalidade` | string | `NaN` | float64 |

### Pseudoalgoritmo
```text
FUNÇÃO converter_colunas_para_salvamento(df)
    PARA CADA coluna EM COLUNAS_DE_NUMEROS_INTEIROS:
        SE coluna EXISTIR em df:
            CONVERTA valores para NÚMERO (force erros para NULO)
            TRANSFORME tipo para INTEIRO_COM_NULOS (Int64)
    PARA CADA coluna EM COLUNAS_DE_DINHEIRO:
        SE coluna EXISTIR em df:
            CONVERTA valores para NÚMERO (force erros para NULO)
            TRANSFORME tipo para FLOAT (float64)
    RETORNAR df
```

---

## 🎨 Sessão 2: Formatação Visual Dinâmica (Excel)

### O que é e por quê existe
O script não salva apenas um CSV sujo. Ele entrega um relatório pronto para diretoria, pintado com formatações de tabela oficiais (`xlsxwriter`). A decisão de design foi usar **Auto-Fit inteligente das colunas** e **Mapeamento de Cores** ao invés de deixar isso pro usuário do Excel.

### Como funciona
```python
# A mágica: lê a maior string DENTRO da coluna e compara com o título
tamanho_conteudo = df[col].astype(str).map(len).max() if not df.empty else 0
largura_ideal = max(tamanho_conteudo, len(col_str)) + 3 

if largura_ideal > 50: largura_ideal = 50 

col_upper = col_str.upper()

if col_str.startswith('%'):
    worksheet.set_column(i, i, max(12, largura_ideal), fmt_pct)
elif 'CNPJ' in col_upper:
    worksheet.set_column(i, i, max(18, largura_ideal), fmt_cnpj)
```
- **Por que Auto-Fit limitando a 50?** Se uma IA extrair um texto com 500 caracteres, a coluna no Excel vai "engolir" a tela inteira, destruindo a leitura da tabela. O limite a 50 garante legibilidade sem truncar a formatação real do dado.
- **Por que `.astype(str).map(len).max()`?** Esta é a maneira vetorizada e mais eficiente do Pandas para descobrir a maior string de uma Série, superando um loop for convencional.

### Exemplo prático
Transformação visual das planilhas:
- Valores monetários ganham máscara `R$ #,##0.00`.
- Se a coluna for `Status_IA` e o valor for `Válido`, o fundo fica verde (`#C6EFCE`).
- `Corrompido` ou `< 0` ganha fundo vermelho alerta.

### Pseudoalgoritmo
```text
FUNÇÃO aplicar_formatacao_visual(planilha, dados)
    CRIAR formatos (moedas, cpf, verde, vermelho, azul)
    TRANSFORMAR área de dados em Tabela Formatada Nativa do Excel
    TRAVAR a primeira linha do Excel (Freeze Panes)
    PARA CADA coluna EM dados:
        Calcular LARGURA = tamanho_da_maior_palavra(coluna)
        SE LARGURA > 50 ENTÃO LARGURA = 50
        SE nome_da_coluna tem 'CNPJ' -> Aplicar largura e máscara 00.000.000/0001-00
        SE nome_da_coluna tem 'R$' -> Aplicar largura e máscara Moeda
    APLICAR Semáforos (se celula == "Inválido" -> Pinta Vermelho)
```

---

## 🗄️ Sessão 3: Extração Financeira via SQL

### O que é e por quê existe
O relatório depende de saber "quanto a faculdade informou que cobraria" cruzado com "quanto o governo efetivamente pagou". Estes dados moram em uma base de dados legado (SIBU). 
A decisão foi baixar apenas os alunos e semestres relevantes usando clausula `IN`, e aplicar lógicas de preenchimento (`ffill`) para o tipo de bolsa (pois algumas inscrições antigas perdem essa classificação).

### Como funciona
```python
df_sql = pd.read_sql(query, engine)
# ... tratamento ...
df_sql = df_sql.drop_duplicates(subset=['uni_codigo', 'semestre'], keep='last')

# ... num merge depois para reconstruir histórico ...
df_merged['tipo_bolsa_final'] = df_merged.groupby('uni_codigo')['tipo_bolsa_final'].transform(lambda x: x.ffill().bfill())
```
- **Por que `keep='last'`?** O SIBU pode conter registros duplicados do mesmo aluno no mesmo semestre se houve reprocessamentos manuais. Confia-se que a inserção cronologicamente mais recente (`last`) contém a realidade consolidada do sistema.
- **Por que `ffill().bfill()`?** Forward-Fill (ffill) propaga o último tipo de bolsa válido conhecido (ex: "INTEGRAL") para semestres futuros nulos. Se o aluno entrou no sistema sem registro inicial e preencheu depois, o Backward-Fill (bfill) volta no tempo para cobrir os buracos. É a forma mais robusta de sanar lacunas de dados longitudinais.

### Exemplo prático
| uni_codigo | semestre | tipo_bolsa (SQL) | ffill().bfill() aplicado |
| :--- | :--- | :--- | :--- |
| 102 | 2025-1 | NaN | INTEGRAL (via bfill) |
| 102 | 2025-2 | INTEGRAL | INTEGRAL |
| 102 | 2026-1 | NaN | INTEGRAL (via ffill) |

### Pseudoalgoritmo
```text
FUNÇÃO buscar_dados_financeiros_sql(semestres_presentes)
    SE não tem semestres RETORNA tabela vazia
    FORMATAR semestres para SQL ('2025/1')
    CONECTAR ao MySQL 
    EXECUTAR SELECT cruzando alunos e mensalidades WHERE semestre IN (semestres)
    REMOVER DUPLICATAS garantindo que ficamos com a última atualização (keep='last')
    PARA CADA aluno:
        PREENCHA vazios no tipo_bolsa copiando o valor do semestre passado ou futuro
    FORMATAR todas as colunas numéricas (coerção para 0.0)
    RETORNAR tabela sql
```

---

## 🔄 Sessão 4: Mesclagem SQL e Reordenação

### O que é e por quê existe
Une o dataframe gerado localmente (IA) com os dados financeiros recém-baixados (SQL). Trata conflitos diretos entre as fontes.

### Como funciona
```python
df = pd.merge(df, df_sql, left_on=['Inscrição', 'Semestre'], right_on=['uni_codigo', 'semestre'], how='left')
df.drop(columns=['uni_codigo', 'semestre'], errors='ignore', inplace=True)
```
- **Por que `how='left'`?** O dataframe principal (`df`) da IA é a "verdade". Queremos trazer os dados financeiros SQL APENAS para os alunos e semestres que estamos avaliando na máquina. Se houverem dados no banco de alunos não processados, eles são descartados.
- **Por que `errors='ignore'`?** Tenta apagar a coluna suja (`uni_codigo`), e se ela não existir no dataframe, não paralisa a rotina.

### Exemplo prático
Se um documento estava marcado como `Ausente`, os valores do SIBU substituem a leitura zerada da IA na coluna oficial para visualização, ajudando a gestão a saber quanto aquele aluno faltante custa para o Estado.

### Pseudoalgoritmo
```text
FUNÇÃO mesclar_sql_e_reordenar(dados_ia, dados_sql)
    CRUZAR (LEFT JOIN) dados_ia e dados_sql usando CHAVES [Inscrição, Semestre]
    APAGAR colunas de apoio SQL
    SE status do aluno é AUSENTE:
        PREENCHER "Mensalidade do Sistema" com o valor do SQL
        ZERAR "Mensalidade da IA" (pois o doc não existe)
    REORDENAR colunas de apresentação
    RETORNAR dados mesclados
```

---

## 🚶 Sessão 5: Transições de Vínculo e Regras de Negócio

### O que é e por quê existe
O sistema precisa alertar se o aluno mudou de faculdade ou se a inscrição dele foi cancelada para abrir uma nova. Essa lógica detecta migrações cruzando o histórico de pagamentos.

### Como funciona
```python
pag_trans['PREV_ID'] = pag_trans.groupby('UNI_CPF')['K_ID'].shift(1)
pag_trans['NEXT_ID'] = pag_trans.groupby('UNI_CPF')['K_ID'].shift(-1)
map_next_id = pag_trans.set_index('K_ID')['NEXT_ID'].to_dict()

# Mapeando (Lookup) super rápido em vez de merges custosos
df['Inscrição Posterior'] = pd.to_numeric(k_id_series.map(map_next_id), errors='coerce')
```
- **A lógica do `.shift(1)` e `.shift(-1)`:** Após ordenar pelo CPF e Semestre, "empurrar" as linhas em +1 e -1 cria instantaneamente visibilidade temporal. Você descobre exatamente qual foi a inscrição *passada* e qual foi a inscrição *futura* na vida daquele CPF.
- **Por que usar dicionários (`.to_dict`) com `.map`?** Em vez de fazer múltiplos JOINs do Pandas (que custam memória), converte-se a relação `ID_ATUAL -> ID_FUTURO` num dicionário Python em memória. O lookup é executado em `O(1)`, acelerando radicalmente a etapa.

### Exemplo prático
CPF de João foi ordenado (2025-1 IES Alfa, 2025-2 IES Beta).
| CPF | Semestre | IES | Shift(1) IES Anterior |
| :--- | :--- | :--- | :--- |
| João | 2025-1 | Alfa | NaN |
| João | 2025-2 | Beta | Alfa |
Resultado: "Mudou IES?" = "SIM".

### Pseudoalgoritmo
```text
FUNÇÃO aplicar_transicoes(df, pagamentos)
    ORDENAR pagamentos por CPF e SEMESTRE
    AGRUPAR por CPF e DESLOCAR as inscrições em -1 (futuro) e +1 (passado)
    CRIAR mapas de Dicionário (ID -> ID Futuro), (ID -> IES Futura)
    PARA CADA linha da tabela principal:
        DESCOBRIR via dicionário sua "Inscrição Posterior"
        SE existir uma "Inscrição Posterior":
            MUDAR Vínculo para "DESLIGADO" (Foi substituído)
    RETORNAR df
```

---

## 🤖 Sessão 6: Auditoria da IA e Diagnóstico Financeiro

### O que é e por quê existe
O coração contábil do GGCI. Verifica se a leitura que a IA fez das mensalidades nos PDFs condiz com as regras matemáticas governamentais (Limites de bolsas) comparando-as com o histórico bancário real do aluno.

### Como funciona
```python
# OTIMIZAÇÃO SÊNIOR: Fast-Loop substituindo df.apply
for idx, row_dict in enumerate(df.to_dict(orient='records')):
    # Avaliação de quebra da consistência (Corrompido, Falso Ausente)
...

sys_bolsa_base = np.select([bolsa_str == 'PARCIAL', bolsa_str == 'INTEGRAL'], [sys_calc_parcial, sys_calc_integral], default=0.0)
sys_excedeu = (sys_bolsa_base + beneficios) > mcd_sys
```
- **Por que `df.to_dict(orient='records')`?** A iteração usando `df.apply(lambda row: ..., axis=1)` no Pandas em matrizes grandes é terrível (sobrecarga de Series instantiation para cada linha). Transformar em dicionários Python nativos faz o loop rodar até 50 vezes mais rápido.
- **Decisões Nativas (`np.select` e `np.where`):** Para as contas matemáticas como as regras de bolsa Parcial ou Integral (que pagam tetos diferentes se for Medicina), usamos Numpy (`np.where`), que roda em C e aplica a conta a milhares de linhas instantaneamente de maneira vetorizada.

### Exemplo prático
Regras implícitas contidas no código:
- **Teto Geral Parcial:** Paga 50% até no máximo R$ 650.
- **Teto Medicina/Odonto Parcial:** Paga 50% até no máximo R$ 2.900.
- Se o teto somado a benefícios extrair estourar a mensalidade integral do aluno, bloqueia o pagamento residual (`sys_excedeu`).

### Pseudoalgoritmo
```text
FUNÇÃO calcular_auditoria_ia(df)
    ITERAR LINHAS PARA AVALIAÇÃO DE IA:
        SE documento lido tinha 0.0 em tudo MAS era Contrato -> Corrompido
        SE IA marcou como Ausente MAS aluno teve boleto pago recentemente -> Falso Ausente
        
    CALCULAR CUSTOS (Vetorizado):
        PARA CADA Aluno:
            Teto_Sistema = Calcula (Mensalidade_Sistema * Fator_Bolsa) respeitando o TETO DO CURSO
            Teto_IA = Calcula (Mensalidade_IA * Fator_Bolsa) respeitando o TETO DO CURSO
            
            Prejuízo = OVG_Pagou_Mês - Teto_IA (O que pagamos a mais do que o Doc manda)
            Lucro_Indevido = (OVG_Pagou_Mês + Beneficios) - Mensalidade_IA
            Economia = Teto_IA - OVG_Pagou_Mês
            
    CLASSIFICAR Diagnóstico Final:
        SE Prejuízo > 0 -> "OVG pagou a mais"
        SE Prejuízo < 0 -> "OVG pagou a menos"
        SE Prejuízo == 0 -> "Pagamento correto"
```

---

## 📊 Sessão 7: Gerador de Resumo Quantitativo

### O que é e por quê existe
Comprime a lista de milhares de alunos e documentos numa tabela condensada indicando adesão por Faculdade/Semestre (entregaram X% dos Contratos).

### Como funciona
```python
is_riaf_na = (doc_name == DOC_RIAF and str(semestre).split('-')[0].isdigit() and int(str(semestre).split('-')[0]) < 2026)
is_hist_na = (doc_name == DOC_HISTORICO and str(semestre).strip() in ["2025-1", "2026-1"])

if is_riaf_na or is_hist_na:
    row[f'Env. {doc_k}'] = "N/A"
```
- **Regra Implícita de Domínio:** O documento "RIAF" não existia no projeto antes de 2026. Documentos Históricos não entram na conta dos semestres específicos de 25/1 e 26/1. Assim evita-se penalizar o percentual de conformidade de uma IES no passado por um tipo de documento recém-criado.

### Exemplo prático
| IES | Semestre | Total Beneficiários | Env. RIAF | Pend. RIAF |
| :--- | :--- | :--- | :--- | :--- |
| UFG | 2025-1 | 1500 | N/A | N/A |
| UFG | 2026-1 | 1600 | 1550 | 50 |

### Pseudoalgoritmo
```text
FUNÇÃO gerar_resumo_quantitativo(df_alvo, tipos_de_doc)
    PARA CADA (Faculdade, Semestre):
        Contar total_de_alunos
        PARA CADA tipo_documento (Ex: RIAF, CONTRATO):
            SE for RIAF e Ano < 2026 -> Atribuir 'N/A' e pular
            Ausentes = Contar alunos com Status_IA == 'Ausente'
            Enviados = Total - Ausentes
            Adicionar ao Resumo
    RETORNAR Tabela Consolidada Resumo
```

---

## 📈 Sessão 8: Gerador da Aba de Relatório IES (Layout e Fórmulas)

### O que é e por quê existe
Em vez de depender do PowerBI, este gerador monta via código Python (`xlsxwriter`) um **Dashboard Dinâmico dentro do Excel**. O usuário seleciona a Faculdade na célula "A3" e o relatório recalcula somas e prejuízos via dezenas de fórmulas conectadas dinamicamente às outras abas invisíveis.

### Como funciona
```python
col_msd_sys = get_col('MSD_SOMA')
form_1 = f'=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!{col_total_bolsa}:{col_total_bolsa}, Documentos!{col_faculdade}:{col_faculdade}, $A$3, Documentos!{col_semestre}:{col_semestre}, "{ano}-1", {doc_cond}))'
worksheet.write_formula(row_idx, 1, form_1, cur_fmt_money)
```
- **Por que injetar fórmulas SUMIFS cruas via Python?** Desta forma, a planilha final pode ser enviada por email e será auto-sustentável sem macros VBA perigosas. A função `get_col` localiza as colunas de origem por Nome na aba base (como "BD"), adaptando a fórmula caso o Python embaralhe as posições no futuro.

### Exemplo prático
A célula B15 terá literalmente a string de fórmula:
`=IF($A$3="Selecione a IES...", "", SUMIFS(Documentos!Y:Y, Documentos!T:T, $A$3, Documentos!K:K, "2025-1", ...))`
Isso calcula o total de bolsas pagas pela instituição selecionada na aba.

**Regras Lógicas Críticas Injetadas nas Fórmulas:**
- **Inversão Semântica (Coleta - Contrato):** A variação de R$ não é calculada como `Contrato - Coleta`, mas sim o inverso (`Coleta - Contrato`). Isso garante inteligência visual: se a IES inflou a base cobrando a mais, a equação gera um número POSITIVO (excesso). Se cobrou a menos, gera um NEGATIVO (queda). 
- **Filtro Cego para Falsos Ausentes:** O sumário principal exige explicitamente apenas `["Válido", "Inválido"]`. Se uma linha for marcada como "Falso Ausente", o Excel a destrói da somatória geral, impedindo a IES de inflar o indicador com registros indevidos.

### Pseudoalgoritmo
```text
FUNÇÃO gerar_aba_relatorio_ies(planilha, dados_documentos, ano)
    CRIAR aba de relatório e Esconder as grades de visualização do Excel
    CRIAR aba oculta e despejar nomes das Faculdades sem duplicatas
    VINCULAR a célula A3 a um Dropdown (Validação de Dados) dessa aba oculta
    DESCOBRIR as Letras de Coluna (A, B, Z, AA) das métricas alvo na tabela bruta
    PARA CADA Métrica da Estrutura (Ex: Total de Beneficiários):
        Escrever Título
        Montar Fórmula do Semestre 1 apontando para a célula A3
        Montar Fórmula do Semestre 2 apontando para a célula A3
        Montar Fórmula de % Variação = (Sem2 - Sem1)/Sem1
        Inserir na Planilha
```

---

## ⚙️ Sessão 9: Motor Principal GGCI

### O que é e por quê existe
O Orquestrador geral (`gerar_relatorio_geral`). Responsável por instanciar os caminhos do projeto, invocar as uniões e checagens lógicas e produzir os logs operacionais. 

### Como funciona
- Verifica via IF se os documentos selecionados dão quórum mínimo para gerar o relatório final (exige Contratos, Financiamentos e Semestres completos).
- Realiza injeção massiva de alunos ("Falsos Ausentes"): Se o pagamentos.xlsx indica que a universidade X recebeu 10 bolsas do aluno A, mas a extração IA não localizou NENHUM documento PDF entregue na pasta do aluno, o motor automaticamente constrói as linhas dele avisando a ausência e somando esse desfalque.

### Exemplo prático
Pipeline de chamadas real:
1. `converter_colunas...` (Limpa)
2. Injetar Ausentes (Lógica)
3. `buscar_dados_financeiros_sql` (Traz mensalidades reais)
4. `mesclar_sql_e_reordenar` (Left Join)
5. `aplicar_transicoes` (Mudanças Vínculos)
6. `calcular_auditoria_ia` (As Regras e Descontos)
7. `gerar_checks_documentos` (Cruzamento check/Xis)
8. Excel Writer -> Output

### Pseudoalgoritmo
```text
FUNÇÃO gerar_relatorio_geral(filtros_tela)
    ABRIR planilhas da IA de Documentos e RIAF
    ABRIR planilhas de Agendamentos e Pagamentos
    
    FILTRAR apenas pelos Semestres da Interface do Usuário
    
    # Injeção de Ausentes
    PARA CADA aluno ativo no Faturamento:
        SE Aluno NÃO ENTREGOU Contrato -> Criar linha no DF marcando 'Ausente'
        SE Aluno NÃO ENTREGOU RIAF (em >2026) -> Criar linha no DF marcando 'Ausente'
        
    BAIXAR SQL usando os Semestres Encontrados
    
    CRUZAR (Merge SQL com Documentos)
    APLICAR Transições (Morte de inscrição / Nova IES)
    CALCULAR Regras Matemáticas da IA
    GERAR Colunas de Checkbox de Presença (Check RIAF, Check Benefício)
    
    GERAR Resumo Quantitativo
    CRIAR Relatório Excel Final e Chamar Formatação Visuais
    SALVAR dados/dados_analise_ia/relatorio_geral.xlsx
```

---

## Apêndice

### 1. Guia de Instalação e Dependências
Para suportar toda a lógica de engine conectada, vetorização pesada e exportação com layouts em Excel:
```bash
pip install pandas numpy sqlalchemy mysql-connector-python xlsxwriter openpyxl
```

### 2. Tabela-Resumo de Transformações (Pipeline de Dados)

| Transformação Principal | Input Necessário | Output / Efeito |
| :--- | :--- | :--- |
| Injeção de Falsos Ausentes | CPF no `consolidado_pagamentos.xlsx` sem registro lido pela IA | + Nova linha 'Ausente' no df final |
| Cruzamento SIBU SQL | `Inscrição` + `Semestre` | Preenchimento real de mensalidade no df |
| Transições de Migração | Shift cronológico dos Contratos do CPF | Tag 'DESLIGADO', IES Anterior, Bolsa Posterior |
| Diagnóstico Final de Auditoria | Contrato PDF + IA + SQL SIBU | Economia, Prejuízo, Lucro Indevido (Em Reais) |

### 3. Fluxo de Decisão ASCII (Vínculo e Atividade)

```ascii
[Aluno Listado]
       │
       ├─ Tem [Inscrição Posterior] no BD?
       │     ├─ SIM ──> Marcar Status_Vínculo como 'DESLIGADO'
       │     └─ NÃO ──> Tem registro no Semestre Máximo/Atual?
       │                  ├─ NÃO ──> Marcar Status_Vínculo como 'DESLIGADO'
       │                  └─ SIM ──> Marcar Status_Vínculo como 'ATIVO'
```

### 4. Tabela de Logs Estruturados de Negócio

| Mensagem | Origem/Gatilho |
| :--- | :--- |
| `⚠️ A aba 'Relatório' exige: Contratos, Financiamentos...` | O usuário pediu para Gerar o Dashboard IES, mas desmarcou extrair Contratos ou isolou apenas 1 semestre. O painel requer ambos os semestres para variação percentual. |
| `🚨 ERRO CRÍTICO: Não foi possível conectar ao SQL` | Falha de VPN ou de credenciais da porta MySQL SIBU. Aborta tudo, pois sem SQL o relatório financeiro é 100% nulo. |
| `➕ Injetados {X} registros 'Ausentes'` | O código encontrou X bolsistas com faturamento recente que sequer criaram a subpasta no Drive web. |
| `⚡ Aplicando auditoria lógica otimizada (Fast-Loop)` | Marca o início da bateria mais pesada do script (Conversão DataFrame > Dicionário). |

### 5. Exclusões por Tipo (Aba RIAF vs Documentos)

- **Aba Documentos:** Contém a triagem massiva de `Contratos`, `Benefícios Extras`, `Financiamentos` e `Históricos`. Recebem o cálculo completo da Matemática Financeira (OVG Deveria Pagar, Saldo Restante, etc).
- **Aba RIAF:** Possui aba *exclusiva* porque este documento consolida a vida acadêmica. Como não tem efeito financeiro imediato atrelado a mensalidade bruta na lógica deste motor (pois a mensalidade fica ancorada ao Contrato), ele é monitorado à parte apenas por aderência (Ausente, Válido, etc) para métricas qualitativas das IES. 

---
*Este documento é vivo. Cada nova funcionalidade implementada no `ggci.py` deve ganhar uma nova sessão aqui, seguindo o mesmo padrão: O que é → Por quê existe → Como funciona → Exemplo → Pseudoalgoritmo.*