# 🧩 Manual Técnico: `consolidador.py`
### Unificador e Padronizador de Planilhas (Etapa 2 do Pipeline)

> **Para quem é este documento?** → Engenheiros de dados e desenvolvedores responsáveis por adicionar novos tipos de planilhas ao fluxo ou consertar quebras causadas por mudanças de nome de coluna no sistema de origem.
> **Posição no Pipeline:** → Esta é a **Segunda Etapa** do sistema. Ele roda imediatamente após o `extrator.py` terminar de baixar dezenas de arquivos quebrados, unindo todos eles em três grandes "Super Planilhas" padronizadas.

---

## 1. ÍNDICE
1. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
2. [🧹 Sessão 1: Funções Base de Limpeza](#-sessão-1-funções-base-de-limpeza)
3. [⚙️ Sessão 2: Dicionário de Configurações (A Mágica)](#️-sessão-2-dicionário-de-configurações-a-mágica)
4. [🛠️ Sessão 3: Loop Principal e Parsing HTML/Excel](#️-sessão-3-loop-principal-e-parsing-htmlexcel)
5. [🔄 Sessão 4: Dropping, Renomeação e Reordenação Final](#-sessão-4-dropping-renomeação-e-reordenação-final)
6. [Apêndice](#apêndice)

---

## Visão Geral da Arquitetura

O `consolidador.py` é um script altamente declarativo. Em vez de ter 50 `if/elses` espalhados pelo código para tratar cada tipo de planilha, ele usa uma matriz central de configuração (`configs`) que dita as regras de leitura e limpeza, rodando um único grande motor de consolidação universal.

```ascii
             [PASTAS DO EXTRATOR]
             ├─ dados_analise/analise_documentos_processados/ (Vários XLSX)
             ├─ dados_analise/analise_documentos_agendar/ (Vários XLSX)
             └─ dados_analise/analise_pagamentos/ (Vários XLS-HTML)
                        │
                        ↓
            [MOTOR UNIVERSAL DE CONSOLIDAÇÃO]
┌─────────────────────────────────────────────────────┐
│ 1. Lê a matriz de `configs`                         │
│ 2. os.walk() nas pastas ignorando as /CONSOLIDADO/  │
│ 3. Identifica se o arquivo é Excel real ou HTML     │
│ 4. Converte strings ("R$ 1.500,00") para Float      │
│ 5. Converte strings numéricas em Int64              │
│ 6. Injeta colunas ausentes (Ex: 'SEMESTRE')         │
│ 7. pd.concat() tudo em uma grande tabela            │
│ 8. Exclui colunas irrelevantes e reordena           │
└───────────────────────┬─────────────────────────────┘
                        │
                        ↓
                     [SAÍDAS]
┌─────────────────────────────────────────────────────┐
│ 📁 dados_analise/.../CONSOLIDADO/                   │
│  ├─ 📄 consolidado_agendar_processamentos.xlsx       │
│  ├─ 📄 consolidado_processados.xlsx                  │
│  ├─ 📄 consolidado_processados_riaf.xlsx             │
│  └─ 📄 consolidado_pagamentos.xlsx                   │
└─────────────────────────────────────────────────────┘
```

---

## 🧹 Sessão 1: Funções Base de Limpeza

### O que é e por quê existe
O Pandas nativo muitas vezes falha em ler dados legados, convertendo CPFs para notação científica e falhando em processar números monetários como `1.500,00`. Foram criadas três funções blindadas de Regex e manipulação de string para resolver isso antes de virarem tipos primitivos do Pandas.

### Como funciona
```python
def converter_para_moeda(valor):
    if pd.isna(valor) or str(valor).lower() in ['nan', 'none', '']:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).strip()
    if ',' in v:
        v = v.replace('.', '')   # Remove separador de milhar brasileiro
        v = v.replace(',', '.')  # Troca vírgula decimal por ponto americano
    v = re.sub(r'[^\d.-]', '', v) # Remove R$, espaços e letras
    try:
        return float(v)
    except:
        return 0.0
```
- **Por que `v.replace('.', '')` antes de `v.replace(',', '.')`?** O padrão contábil no Brasil é "1.500,00". O Python lê isso e surta (dois separadores flutuantes). Remove-se o ponto do milhar ("1500,00") e só depois converte-se a vírgula fracionária para o padrão americano de código ("1500.00").
- **Por que a função `converter_para_numero_real` checa `re.match(r'^\d+\.0+$', v)`?** Quando o Pandas importa um Excel mal formatado, ele frequentemente lê o CPF `12345` como a string `"12345.0"`. Esse regex detecta finais exatos de `.0` isolados e os decepa antes de limpar as pontuações extras.

### Exemplo prático
| Coluna Bruta | Função Aplicada | Resultado | Tipo Python |
| :--- | :--- | :--- | :--- |
| `1.500,99` | `converter_para_moeda` | `1500.99` | float |
| `" 12345.0 "` | `converter_para_numero_real` | `12345` | int |
| `ADMINISTRAÇÃO` | `limpar_texto_geral` | `ADMINISTRACAO` | str |

### Pseudoalgoritmo
```text
FUNÇÃO converter_para_moeda(texto)
    SE for nulo ou vazio -> Retorna 0.0
    SE já for número -> Retorna Float
    REMOVE pontos (que no Brasil são milhares)
    SUBSTITUI vírgula por ponto (para ficar no padrão Americano)
    USA REGEX para apagar Letras, Símbolos e R$
    TENTA converter para FLOAT. Se falhar, retorna 0.0
```

---

## ⚙️ Sessão 2: Dicionário de Configurações (A Mágica)

### O que é e por quê existe
Para evitar código "Spaghetti" (onde a lógica de negócio se mistura com a lógica de abrir arquivos), as regras de como consolidar cada tipo de relatório ficam declaradas em uma constante Global `configs`. Isso facilita a manutenção: se o SIBU ganhar uma coluna nova, você altera aqui no topo do arquivo sem tocar no motor `os.walk`.

### Como funciona
```python
configs = [
    {
        'tipo': 'pag',
        'pasta': 'dados_analise/analise_pagamentos',
        'saida': 'consolidado_pagamentos.xlsx',
        'ext': '.xls',
        'cols_num': ['UNI_CODIGO', 'CADUNICO', 'UNI_CPF'],
        'cols_moeda': ['VALOR_CONTRATO_APURADO', 'VALOR_PAGAMENTO'],
        'ordem_colunas': ['UNI_CODIGO', 'UNI_NOME', 'UNI_CPF', ...]
    },
    # ... outros 4 blocos de config ...
]
```
- **Por que o array `'cols_moeda'`?** Em vez de iterar linha por linha para descobrir o que é número, o Script lê esse dicionário e usa `.apply(converter_para_moeda)` apenas na lista declarada, o que é computacionalmente muito mais barato.
- **Por que declarar `ordem_colunas`?** Como estamos juntando dezenas de planilhas de meses diferentes, é possível que a ordem das colunas flutue (a TI adicionou uma coluna em Maio). Se não forçarmos uma matriz padrão no final, o `pd.concat` ficará com colunas fora de lugar. 

### Exemplo prático
O config tipo `proc_riaf` varre apenas a subpasta `['RIAF']` e aplica a limpeza avançada, enquanto o tipo `proc_geral` varre `['BENEFICIOS', 'CONTRATOS', 'FINANCIAMENTO', 'HISTORICO']`, juntando-os todos no meso `consolidado_processados.xlsx`.

### Pseudoalgoritmo
```text
(Isto não tem pseudoalgoritmo pois é apenas um mapeamento declarativo (JSON/Dict) de regras.)
```

---

## 🛠️ Sessão 3: Loop Principal e Parsing HTML/Excel

### O que é e por quê existe
O motor central itera sobre as pastas listadas no Config, descobre os arquivos e os abre. A grande peculiaridade é o tratamento do formato XLS vs HTML, pois os arquivos de faturamento do Portal Bolsa são, na verdade, exportações mal-formadas.

### Como funciona
```python
for arq in arquivos:
    if arq.endswith(cf['ext']) and not arq.startswith('~$'):
        caminho = os.path.join(raiz, arq)
        try:
            if arq.endswith('.xlsx'):
                df = pd.read_excel(caminho)
            else:
                try:
                    df = pd.read_excel(caminho, engine='xlrd')
                except:
                    dfs_html = pd.read_html(caminho)
                    if not dfs_html: continue
                    df = dfs_html[0]
                    col_referencia = cf['cols_num'][0]
                    if col_referencia in str(df.iloc[0].values):
                        df.columns = df.iloc[0]; df = df[1:]
```
- **Por que ignorar `~$`?** Quando o usuário abre um Excel para "dar uma olhadinha", o Windows cria um arquivo fantasma temporário com o prefixo `~$`. Se o script tentar ler esse arquivo invisível travado pelo sistema, ele quebra.
- **Por que o `try/except` do `engine='xlrd'` com `pd.read_html`?** O portal antigo de faturamento exporta um arquivo `.xls`. Quando o Pandas tenta ler isso nativamente, ele descobre que não é um binário Excel de verdade, e sim um arquivo HTML com tabelas disfarçado de XLS. O código falha graciosamente pro bloco de exceção e invoca o parser de tabelas HTML do Pandas para "salvar" a extração, realocando depois o título das colunas (`df.columns = df.iloc[0]`).

### Exemplo prático
Arquivo: `pagamento_2025_jan.xls`.
1. Pandas tenta ler o binário -> Erro (É HTML!).
2. `pd.read_html` lê o arquivo e cria um DataFrame gigante.
3. Linha 0 (zero) tem o texto `UNI_CODIGO, UNI_NOME...`. O script converte a Linha 0 em Header oficial e deleta a Linha 0 dos dados usando Slice `df = df[1:]`.

### Pseudoalgoritmo
```text
FUNÇÃO consolidar()
    PARA CADA configuração (bloco de regras) EM configs:
        CRIAR lista vazia de tabelas
        PARA CADA subpasta e arquivo na pasta da configuração:
            SE a pasta se chamar CONSOLIDADO -> Pula (evita recursão infinita)
            SE arquivo terminar com a extensão desejada E não for arquivo temporário:
                SE for XLSX normal:
                    Lê como Tabela
                SENÃO (Ex: XLS legado):
                    Tenta ler como Excel antigo
                    SE falhar: 
                        Lê como HTML
                        Puxa a primeira linha e transforma no Cabeçalho Oficial
                
                LIMPAR Linhas 100% vazias
                APLICAR Limpeza de Int64 nas colunas listadas no bloco de regras
                APLICAR Limpeza Monetária nas colunas listadas
                APLICAR Limpeza de Texto nas colunas listadas
                
                SE for o bloco de Pagamentos:
                    Lê o nome do arquivo, tira a data (Ex: jan-25) e cria coluna 'SEMESTRE'
                
                ADICIONA Tabela na lista de tabelas
```

---

## 🔄 Sessão 4: Dropping, Renomeação e Reordenação Final

### O que é e por quê existe
Depois de juntar dezenas de planilhas (`pd.concat`), sobram colunas técnicas oriundas da IA ou versões redundantes de controle do scriptcase que sujam a visualização final e estouram as tabelas.

### Como funciona
```python
if cf['tipo'] in ['proc_geral', 'proc_riaf']:
    cols_drop = ['Status Gemini', 'Gemini Status', 'Status Obs']
    df_final.drop(columns=cols_drop, errors='ignore', inplace=True)
    df_final.rename(columns={'Status OVG': 'Status_IA', 'Status Ovg': 'Status_IA'}, inplace=True)

if 'ordem_colunas' in cf:
    colunas_ordenadas = [c for c in cf['ordem_colunas'] if c in df_final.columns]
    colunas_extras = [c for c in df_final.columns if c not in colunas_ordenadas]
    df_final = df_final[colunas_ordenadas + colunas_extras]
```
- **Por que `errors='ignore'`?** Tenta deletar colunas. Se algumas planilhas do passado não tinham a coluna `'Status Obs'`, o Pandas daria erro (KeyError). O 'ignore' permite que ele apague se existir, ou não faça nada se já estiver ausente.
- **Por que a Reordenação usa `+ colunas_extras`?** Para evitar perda de dados (Data Loss). O array `ordem_colunas` diz as primeiras colunas que queremos ver (Status_IA, Inscrição, Bolsista). Mas se a IA extraiu uma nova variável chamada `Gemini Campo Novo` e isso ainda não foi configurado na matriz, ao invés do script descartar a coluna misteriosa, ele a apensa inteligentemente no final (`colunas_extras`).

### Exemplo prático
A planilha IA tinha `Status Ovg`, `Gemini Cpf`, `Gemini Mensalidade Sem Desconto`.
Passa pela matriz:
- `Status Ovg` vira `Status_IA` e vira a Coluna 1.
- `Gemini Cpf` é deletada.
- O Excel final é salvo já com o layout estruturado sem precisar de macros.

### Pseudoalgoritmo
```text
(Continuação de Consolidar)
        SE a lista de tabelas não estiver vazia:
            CONCATENA todas as tabelas uma embaixo da outra
            
            SE for do tipo Agendamentos:
                APAGA 30 colunas irrelevantes ("Gemini Assinatura", "Id", etc)
            SE for Processamento Geral:
                APAGA colunas duplicadas de Status e renomeia 'Status Ovg' para 'Status_IA'
            
            SE existir uma 'ordem_colunas' na Configuração:
                COPIA as colunas que estão na lista
                PEGA as colunas "perdidas" que não estavam na lista
                JUNTA (Lista Primária) + (Lista Secundária)
                REORDENA o DataFrame final
            
            SALVAR como Excel na pasta CONSOLIDADO
            APLICAR Formatação Visual Simples (Cpf, Cnpj e Dinheiro)
            SAIR
```

---

## Apêndice

### 1. Guia de Instalação e Dependências
```bash
pip install pandas lxml xlsxwriter xlrd
```
> *(Nota: `lxml` é vital aqui, pois é a engine silenciosa que o `pd.read_html` usa para conseguir ler a tabela XLS mal-formada do sistema legado).*

### 2. Tabela-resumo das principais transformações

| Ação de Tratamento | Input Original | Gatilho / Motivo | Output Resultante |
| :--- | :--- | :--- | :--- |
| Extração de Semestre Dinâmica | Nome do arquivo (ex: `pagamento_2025_jan.xls`) | Não há coluna de semestre no sistema Bolsa. | Coluna 0: `2025-1` injetada em todo o Dataframe |
| Coerção Int64 | `"150422.0"` (String do Excel) | Evitar perdas no MERGE futuro. | `150422` (Int64 validado) |
| Fallback para LXML | Um Arquivo `*.xls` | Arquivo quebra a library xlrd porque é HTML disfarçado. | Parser HTML monta um DataFrame 100% válido |

### 3. Tabela de mensagens de log

| Aviso | O que significa | Impacto |
| :--- | :--- | :--- |
| `🔄 Processando: consolidado_pagamentos.xlsx...` | Inicio de um novo bloco da constante `configs`. | Informativo. |
| `❌ Erro em contrato_2024.xlsx: ValueError` | Um arquivo específico quebrou (Ex: arquivo vazio, 0kb, corrompido fisicamente no disco). | O arquivo será pulado, mas a consolidação continua com os outros. |
| `✅ Gerado com sucesso e colunas ordenadas` | A "Super Planilha" do módulo em questão foi salva fisicamente no diretório de destino. | Sucesso. |

### 4. Fluxo de decisão ASCII da Leitura de Arquivo

```ascii
[os.walk encontra um Arquivo]
       │
       ├─ É um arquivo temporário (~$)?
       │    ├─ SIM ──> [ IGNORA ARQUIVO ]
       │    └─ NÃO ──> A Extensão é .xlsx?
       │                 ├─ SIM ──> Lê usando pd.read_excel() padrão
       │                 │
       │                 └─ NÃO (É .xls) ──> Tenta ler via xlrd
       │                                       ├─ FUNCIONOU ──> Lê Tabela e Continua
       │                                       └─ QUEBROU ──> Tenta forçar pd.read_html()
       │                                                        ├─ FALHOU ──> [ IGNORA ARQUIVO ]
       │                                                        └─ ACHOU ──> Recupera cabeçalhos da Linha 0 e Continua
```

---
*Este documento é vivo. Cada nova funcionalidade implementada no `consolidador.py` deve ganhar uma nova sessão aqui, seguindo o mesmo padrão: O que é → Por quê existe → Como funciona → Exemplo → Pseudoalgoritmo.*