# Plano de Otimização — Análise IA (geração do relatório)

> **Estado (13/08/2026):** concluído. Geração do XLSX de **10m43s para 5m18s (-51%)**
> e do CSV de 3m30s para 2m15s, com o relatório conferido a cada passo e 82 testes
> travando o comportamento.
>
> **Não há mais alvo grande.** Do tempo restante, ~200s são xlsxwriter (`close()` e
> escrita, já no limite) e ~82s são código do projeto, cujo maior item ainda não
> investigado tem 7,5s. Continuar significa caçar 3 a 4 segundos por vez, com o mesmo
> risco de mexer em regra de negócio.
>
> As hipóteses H1 e H2 da versão de 11/08 estavam **erradas** — foram medidas e valem
> ~0% e ~3%. O que funcionou foi medir antes de mudar, e instrumentar em vez de supor:
> o maior ganho isolado (55,3s -> 17,0s) estava numa aba de 412 linhas que nenhuma
> leitura de código apontou.

---

## 1. Objetivo em uma frase

Reduzir o tempo de geração do relatório **sem alterar uma célula do
`relatorio_geral.xlsx`** e sem mudar nenhuma regra de negócio.

---

## 2. O que já foi descartado (não repetir)

| Hipótese | Veredito |
|---|---|
| Volume de dados de 2026 | **Falso.** 2026 inteiro é 0,68× o volume de 2025. |
| Mineração (`xmrig`) disputando CPU | **Fraco.** O processo travado estava em 1,2% de CPU com as threads em `futex_do_wait`. Medir sempre com a mineração no mesmo estado. |
| Regressão de performance entre 28/07 e 10/08 | **Falso — foi recuperação de dados.** O commit `5476c0b` corrigiu `check_financiamento`/`check_beneficios` (nomes errados, `NameError` engolido por `except`). Os 2–3 min de antes eram um relatório *incompleto*. |
| `constant_memory` do xlsxwriter | **Proibido.** Parecia 41% mais rápido e **zerava 22 das 23 colunas** da aba Pagamentos, silenciosamente. |
| H1 — cache de `add_format` | **Irrelevante.** Medido: ~0% do tempo. |
| H2 — `add_table` → header manual | **Quase irrelevante.** Medido: 2,4s de 87s numa aba de 64.682 × 62 (~3%). |
| Desligar Relatório Contratos / Relatório RIAF | **Não acelera nada — encerrado, ver §12.** Cronometrado isolado sobre um `df_docs` de 167.000 × 61: **0,126s** as duas abas somadas, incluindo o `close()`. É 0,03% de uma execução de 7 minutos. |
| `tmpdir` em `/dev/shm` ou `in_memory=True` no `close()` | **Nulo.** 16,07s → 16,02s / 15,83s. O `close()` é CPU (XML + zip), não I/O. |
| Baixar o `compresslevel` do zip (o xlsxwriter usa o default 6) | **Ganho pequeno com custo visível.** Numa aba de 310.338 × 22: `close()` 34,1s no nível 6, 26,3s no nível 1 (−23%) e o arquivo vai de 47,9 MB para 59,3 MB (+24%). Nível 0 corta 10,8s e infla para 244 MB — inaceitável. Extrapolando, ~25s num total de 395s. Fica na prateleira: só compensa se o tamanho do arquivo deixar de importar. **Sobra o achado principal:** mesmo sem compressão nenhuma o `close()` ainda leva 24s dos 34s — o grosso é geração de XML, irredutível dentro do xlsxwriter. |

---

## 3. Onde o tempo está, medido

Benchmark isolado com as dimensões reais das abas (`xlsxwriter` 3.2.9, pandas 3.0.2):

### Aba Contrato — 64.682 linhas × 62 colunas

| Etapa | Tempo | % |
|---|---|---|
| `df.to_excel` (pandas → xlsxwriter) | **59,4s** | **68%** |
| `writer.close()` (serializa XML + zipa) | **25,4s** | **29%** |
| `worksheet.add_table` | 2,4s | 3% |
| `set_column` + auto-fit (amostra 1000) | 0,2s | ~0% |
| `conditional_format` (7 regras/coluna) | 0,0s | 0% |
| `ignore_errors` (`A1:XFD1048576` × 9) | 0,0s | 0% |

### Aba Pagamentos — 331.117 linhas × 23 colunas

| Etapa | Tempo |
|---|---|
| `df.to_excel` | **109,9s** |
| `writer.close()` | **50,2s** |
| `add_table` | 4,6s |

**Conclusão:** ~97% do custo de escrita está em duas chamadas — `to_excel` e
`close()`. Toda a formatação visual (cores, semáforos, larguras, tabelas
nativas, supressão de avisos) custa junta menos de 3%. **Não há nada a ganhar
mexendo em formatação.**

---

## 4. A alavanca: escrever por coluna, não por célula

O `to_excel` do pandas monta um objeto Python por célula antes de repassar ao
XlsxWriter. Escrever por coluna com `worksheet.write_column` pula essa camada.

Mesma aba (64.682 × 62), conteúdo verificado célula a célula com openpyxl:

| Caminho | Escrita | `close()` | Total |
|---|---|---|---|
| `pandas df.to_excel` (antes) | 43,98s | 18,39s | 62,37s |
| **`xlsxwriter write_column`** | **12,49s** | 18,73s | **31,23s** |
| `polars df.write_excel` | 24,96s | 26,01s | 50,98s |

`write_column` é **3,5× mais rápido na escrita** e produz o mesmo conteúdo.
O polars não compensa: economiza na escrita e devolve no `close()`.

### As duas armadilhas que o teste pegou

Trocar `to_excel` por `write_column` ingenuamente **quebra duas coisas**:

1. **`datetime`** — o pandas aplica um `num_format` de data na própria célula.
   Sem isso o Excel mostra `46037` em vez de `15/01/2026`.
2. **`inf` / `-inf`** — o pandas grava como o *texto* `'inf'`, não como célula
   vazia.

Ambas estão tratadas em `ggci.escrever_aba` e travadas por
`tests/test_escrever_aba.py`.

---

## 5. Restrições invioláveis

1. **O relatório final é idêntico.** Mesmas abas, mesma ordem, mesmos nomes,
   mesmas células, mesmos valores, mesma formatação, mesmas fórmulas, mesmas
   larguras, mesmas cores, mesmos filtros e painéis congelados.
2. **Nenhuma regra de negócio muda.**
3. **Nenhuma aba sai do XLSX.** Todas as 11 são de uso real.
4. **Escopo é só o Análise IA.**
5. **Versões travadas** — Pandas 3.0.2, Polars 1.43.0, DuckDB 1.5.4, PyArrow
   25.0.0, xlsxwriter 3.2.9, Django 6.0.5.

---

## 6. Rede de segurança

### 6.1 Baseline

`apps/automacoes/analise_ia/tests/baseline/relatorio_geral.xlsx` — cópia do
`proc_121`, o último relatório completo de 11 abas, aprovado pelo dono do
projeto ("os dados estão todos batendo"). Fora do git (74 MB, no `.gitignore`).

### 6.2 `comparar_relatorios.py`

Estendido em 12/08. Compara:

- lista e ordem das abas
- cabeçalhos e ordem das colunas
- contagem de linhas por aba
- **contagem de preenchidos por coluna** — é o que pega o caso "arquivo íntegro,
  conteúdo vazio" do `constant_memory`; coluna que zera vira REGRESSÃO
- valores célula a célula
- **fórmulas** (`data_only=False`) nas abas Relatório/Aux_IES
- **largura de coluna, painel congelado, autofilter, cor de aba, tabelas nativas**

```bash
venv/bin/python3 apps/automacoes/analise_ia/tests/comparar_relatorios.py \
    apps/automacoes/analise_ia/tests/baseline/relatorio_geral.xlsx \
    apps/automacoes/analise_ia/dados/processamento/proc_124/relatorio_geral.xlsx
```

Sai com código 1 quando encontra regressão. `--amostra N` para varredura rápida.

### 6.2.1 O baseline não vale para as abas de relatório

O `baseline/relatorio_geral.xlsx` foi gerado com **2 semestres** de contratos
selecionados na tela; os runs de 13/08 usaram **4**. Como as abas Relatório Contratos e
Relatório RIAF montam um bloco de colunas por semestre e só depois as colunas de
variação, mudar a seleção muda o layout inteiro — e o comparador acusa REGRESSÃO sem
que nenhuma linha de código tenha mudado:

```
baseline:  B D F [2025-1]  H J L [2025-2]  N P R  [VARIAÇÃO]
13/08:     B D F [2025-1]  H J L [2025-2]  N P R [2026-1]  T V X [2026-2]  Z AB AD [VARIAÇÃO]
```

Três sintomas que vêm todos daí e **não** são defeito:

- fórmulas "divergentes" nas linhas dessas duas abas;
- largura `None -> 9.86` nas colunas que o baseline nem tinha (9.14 declarado mais 0,72
  de padding que o xlsxwriter soma);
- `autofilter` mudando de `A1:BI64683` para `A1:BI64684`, que só acompanha a contagem de
  linhas.

**Como confirmar em vez de supor:** comparar as fórmulas apenas nas colunas que existem
nos dois arquivos. Em 13/08 deu 67 de 67 idênticas no Relatório RIAF. E `git log -L` na
faixa da função prova que `gerar_aba_relatorio_contratos` está intacta. Não procure a
fórmula de variação pela string exata: as referências mudam com o número de blocos.

Para as abas de dados o baseline continua válido.

### 6.3 Testes

```bash
venv/bin/python3 manage.py test apps.automacoes.analise_ia.tests
```

**35 testes, verdes em 12/08.** Os relevantes para esta refatoração:

| Arquivo | O que trava |
|---|---|
| `test_escrever_aba.py` | `escrever_aba` == `to_excel`, em 11 dtypes e nas 11 abas reais do baseline, com a formatação de verdade aplicada |
| `test_remover_caixa_alta.py` | versão rápida == versão original (a antiga fica no arquivo como oráculo) |
| `test_data_processamento.py` | o parsing das datas de cache não pode voltar para `dayfirst=True` |
| `test_contrato_saida.py` | abas, colunas e ordem contra `fixtures/contrato_saida.json`; agora lê o **baseline**, não o `proc_N` mais recente |
| `test_normalizacao.py` | funções puras de rótulo |

### 6.4 `comparar_csv_xlsx.py`

Confere o ZIP de CSV contra as abas do XLSX: conjunto de arquivos, colunas e sua
ordem, contagem de linhas, ordem das linhas e valores. Compara número como
número — comparar `650` com `650.0` ou `3353.22` com `3353.2200000000003` como
texto acusa dezenas de milhares de células que estão corretas.

```bash
venv/bin/python3 apps/automacoes/analise_ia/tests/comparar_csv_xlsx.py \
    <proc>/relatorio_geral.xlsx <proc>/relatorio_geral.zip
```

---

## 7. O que foi aplicado em 12/08

### 7.1 `escrever_aba` no lugar de `to_excel` (§4)

Nova função de módulo em `ggci.py`. Cria a worksheet, registra em
`writer.sheets` (para `aplicar_formatacao_visual` continuar achando a aba pelo
nome) e escreve por coluna, normalizando os tipos do pandas do mesmo jeito que o
pandas normalizava. Substituiu as 9 chamadas de `to_excel` das abas de dados.

As abas com fórmula (`gerar_aba_relatorio_contratos` / `_riaf`) **não** foram
tocadas: são pequenas e o ganho seria nulo contra o risco de mexer em fórmula.

**Ganho projetado:** ~285s → ~80s de escrita. Falta confirmar end-to-end.

### 7.2 `remover_caixa_alta_df` por valores distintos

A função aplicava `.apply()` célula a célula e depois 6 passes de
`str.replace` regex — 8 varreduras por coluna de texto, sobre 166.849 linhas,
3 a 4 vezes por execução.

As colunas de texto do relatório são altamente repetitivas (nome de IES, status,
curso, diagnóstico). A versão nova transforma só os valores **distintos** e
remapeia com `map()`, e usa um regex alternado único no lugar dos 6 passes.

**Medido:** 28,9s → 8,6s (3,4×), `.equals()` == `True`, mesmo com uma coluna de
166 mil valores únicos no teste. Movida para o nível de módulo para ficar
testável.

### 7.3 Curto-circuito das flags de aba

`df_pag_filt` (enriquecimento de ~331 mil linhas de pagamento) e
`df_resumo_geral` eram calculados **incondicionalmente** — o código dizia
`# (só cálculos por enquanto)` — mesmo com as abas desmarcadas. São dados-folha:
`df_pag_filt` só alimenta Pagamentos e Médias, `df_resumo_geral` só alimenta
Envios & Pendências. Os relatórios Contratos/RIAF não os consomem e já ficam
bloqueados quando `gerar_quantitativo` é `False`.

Agora `gerar_pagamentos=False` e `gerar_quantitativo=False` pulam o cálculo de
verdade. **Era isso que fazia "desmarcar a aba" não economizar nada.**

### 7.4 CSV fiel ao XLSX

O ramo CSV tinha divergido do XLSX em 5 pontos: mantinha a coluna
`tipo_documento`, ordenava sem o semestre e sem normalizar caixa, não aplicava
`remover_caixa_alta_df` em Pagamentos, não ordenava Pagamentos, ignorava as
flags `gerar_pagamentos` / `gerar_quantitativo` e não gerava Médias.

A preparação das abas virou uma função única (`montar_abas_de_dados`) que devolve
`[(nome_aba, DataFrame)]` na ordem oficial. Os dois formatos consomem a mesma
lista — o CSV só troca o escritor. Os arquivos do ZIP passam a ter o nome da aba
(`Contrato.csv`, `Envios & Pendências.csv`, `Médias.csv`) em vez do nome longo do
documento truncado em 31 caracteres.

Fora do CSV ficam apenas as 4 abas com fórmula (Relatório Contratos,
Aux_IES_Contratos, Relatório RIAF, Aux_IES_RIAF), que não têm equivalente.

### 7.5 Writer do Excel não é mais aberto no modo CSV

O `pd.ExcelWriter` era criado antes de saber o formato e, no modo CSV, nunca
fechado — deixava um `relatorio_geral.xlsx` corrompido no disco e o handle
pendurado. Confirmado no `proc_122`: `BadZipFile: File is not a zip file`.

### 7.6 `montar_abas_de_dados` é gerador, não lista

**Regressão introduzida por esta refatoração e corrigida depois do proc_126 morrer
por OOM.** A primeira versão devolvia uma lista, deixando vivos ao mesmo tempo o
`df_docs` inteiro (~167 mil × 62), uma cópia por tipo de documento repetindo essas
mesmas linhas, o RIAF e as ~310 mil de Pagamentos. O código original preparava e
escrevia uma aba por vez.

Com `yield`, cada aba é preparada, escrita e liberada antes da seguinte. Efeito
colateral desejável: os prints `GERANDO` voltam a intercalar com a escrita.

### 7.7 `base_dir` era sobrescrito no meio da função

Bug **pré-existente**, exposto pelo modo CSV. Dentro do bloco de pendentes,
`base_dir = .../dados/tabelas_sql` reatribuía a variável que aponta para a pasta
do processamento. Como o caminho do ZIP é montado depois desse ponto, todo ZIP de
CSV ia para `tabelas_sql/relatorio_geral.zip` e era **sobrescrito pelo run
seguinte**. O XLSX escapava porque o caminho dele é montado antes. Variável
renomeada para `dir_tabelas_sql`.

### 7.8 Timings do motor acumulam em vez de sobrescrever

`_registrar_timing` fazia `block_timers[bloco] = duracao`. Como `"GERANDO | DOCS"`
dispara uma vez por aba e `"GERANDO | RIAF"` dispara duas (aba Riaf e Relatório
RIAF IES), cada rótulo guardava só o último trecho. As métricas `⏱ GGCI_*` nunca
foram confiáveis para a fase de escrita — **use os timestamps do log**.

### 7.9 Coluna numérica normalizada por máscara — achado do py-spy (13/08)

O perfil do proc_129 mostrou **22s de uma única execução** dentro de `escrever_aba`,
em duas linhas: `np.isnan(v)` e `np.isinf(v)`, uma chamada por célula. Numa aba de 310
mil linhas são milhões de chamadas em Python para responder algo que o NumPy resolve na
coluna inteira de uma vez.

Passou a testar o dtype e sair por máscara. Medido sobre um DataFrame com as dimensões
da aba Pagamentos: **14,05s → 1,72s (8,2×)**, resultado idêntico coluna a coluna.

O teste é por `isinstance(s.dtype, np.dtype)` e `s.dtype.kind`, não por
`is_float_dtype`: os tipos anuláveis do pandas (`Float64`, `Int64`) também respondem
como float mas guardam `pd.NA` e estourariam num `to_numpy(dtype=float)`. Eles seguem
pelo laço, como antes.

---

### 7.10 O resumo quantitativo — o achado da instrumentação

Os `⏱` do motor mostravam `GGCI_EXCEL_INIT: 72,4s` sem dizer de quê. Instrumentado, o
proc_132 respondeu: **`resumo quantitativo: 55,28s`** — a aba "Envios & Pendências", que
tem **412 linhas**. Doze por cento do pipeline para 0,1% do conteúdo. Nenhuma leitura de
código tinha apontado para lá.

O laço percorre ~420 grupos (105 IES x 4 semestres) e repetia em cada um o que não
depende do grupo: `to_datetime` da mesma coluna 420 vezes, `astype(str).str.lower()` do
Status_IA mais de 2.000 vezes, `to_numeric` dos valores 800 vezes, `padronizar_ies` e
`buscar_mantenedora` 420 vezes para 105 IES distintas, e **duas cópias de um DataFrame
de 62 colunas por iteração**.

Resultado no pipeline real: **55,28s -> 16,99s (3,3x)**, e o total caiu de 6m44s para
5m56s.

**A armadilha:** o primeiro protótipo ordenava a Series solta em vez do DataFrame. Era
igualmente rápido e o benchmark passou — mas `sort_values` não é estável, e com datas
empatadas as duas versões podem manter linhas diferentes no `drop_duplicates(keep=
'first')`, trocando o `Status_Vínculo` do aluno sem erro nenhum. A conversão saiu do
laço; a ordenação continua sendo a mesma chamada sobre o mesmo DataFrame.
`test_resumo_quantitativo.py` tem um caso com todas as datas iguais de propósito.

**Como a validação foi feita** (vale como método): comparar `proc_133` contra `proc_132`
em vez do baseline — mesmo dia, mesma seleção de semestres, única diferença de código é
a otimização. Deu 52 células divergentes, todas em `Ativos`/`Desligados` e com a soma
preservada. Confirmado como dado: 50 registros mudaram `status_vinculo` na aba Contrato
entre os dois runs, e essa aba não passa pelo resumo. O que fecha o argumento é que
nenhuma coluna `Env.`/`Pend.`/`Proc.` mudou — se o desempate tivesse mudado, o
`Status_IA` da linha mantida mudaria junto e essas contagens iriam junto.

**A evidência que dispensa as outras:** o `situacao_motivo` acompanha a direção da
mudança. Das 50 inscrições, 25 foram Ativo -> Desligado com motivos de saída (Desistência
da Bolsa, Não Renovou Benefício, Trancamento, Ganhou Bolsa Integral, Descumprimento do
Banco de Oportunidades) e 25 foram Desligado -> Ativo com motivos de volta (Renovação
CPD, Inclusão, Correção de Desligamento Automático). Nenhum motivo aparece no lado
errado. Um desempate acidental de ordenação não produz coerência semântica entre o
motivo e a direção — produziria motivos misturados. O dono do projeto confirmou que essa
transição é comportamento normal, dependendo da situação e dos pagamentos.

**Guarde o método:** quando uma otimização mexer em contagem e a saída divergir, procure
uma coluna correlata que não deveria mudar junto por acaso. Ela separa "meu código errou"
de "o dado mudou" mais rápido do que qualquer outra checagem.

### 7.11 O `apply(axis=1)` das datas de processamento

`get_d_proc` escolhia a primeira das quatro colunas de data com valor útil e era um
`apply(axis=1)` — o pior padrão do pandas, que monta um objeto Series por linha antes de
chamar a função. Rodava duas vezes sobre as ~167 mil linhas x 62 colunas.

Sendo um coalesce, virou máscara: cada coluna é avaliada de uma vez e só preenche onde
ainda não há resposta, na mesma ordem de prioridade.

| medição | antes | depois |
|---|---:|---:|
| isolado, 167.000 x 62 | 7,80s | 1,28s (6x) |
| `docs auditoria_ia` (pipeline) | 27,18s | **14,93s** |
| `riaf auditoria_ia` (pipeline) | 9,36s | **6,47s** |

**Por que exigia validação extra:** o texto devolvido vira a data que decide se o cache
local sobrepõe o banco (`mask_newer`). Errar não daria erro — restauraria valores de IA
que não deviam voltar. Conferido comparando proc_135 contra proc_133 nas colunas
`gemini_*`, `status_ia` e `processado`: **zero divergências em 160 mil registros**.

### 7.12 `mesclar_sql_e_reordenar` — o `transform(lambda)`

`transform(lambda x: x.ffill().bfill())` sobre `tipo_bolsa_final`: o lambda roda uma vez
por grupo, em Python, e são ~25 mil inscrições no df_docs e ~15 mil no df_riaf. As
rotinas nativas `groupby.ffill()` e `groupby.bfill()` fazem a coluna inteira de uma vez.
Junto foram os `.apply()` de Faculdade (105 valores em 167 mil linhas), Bolsista e
Documento Tipo (5 valores), via `texto_por_distintos`.

| | proc_135 | proc_136 |
|---|---:|---:|
| `docs mesclar_sql` | 18,06s | **7,66s** |
| `riaf mesclar_sql` | 10,06s | **3,46s** |
| geração | 5m46s | **5m18s** |

**A sutileza que o teste pegou:** a primeira versão de `texto_por_distintos` preservava
`None`. O `.apply()` do pandas normaliza `None` para `NaN` ao reconstruir a Series —
preservar o `None` parecia mais correto e faria a coluna divergir da anterior. A saída
passou a ser montada do zero.

**Validação de `tipo_bolsa_final`** (decide integral x parcial em todo o cálculo
financeiro): 311 registros divergiram entre os dois runs, e a prova de que não é o
código é **estrutural, não estatística** — nenhuma das 311 envolve valor nulo, e
ffill/bfill só toca célula nula. Some-se que não aparece `Sem Dados` em nenhum dos dois
runs (o `fillna` final denunciaria preenchimento falho), que as mudanças são
bidirecionais (145 x 166) e que em 286 delas o valor devido mudou na proporção exata
(604,53 -> 1209,06; 735 -> 367,50).

**Guarde o argumento:** quando a coluna suspeita for preenchida por ffill/bfill, olhe se
as divergências envolvem nulo. Se nenhuma envolve, o preenchimento está descartado sem
precisar de mais nada.

### Onde o tempo está agora (proc_136)

| fase | tempo | situação |
|---|---:|---|
| `close()` + escrita das abas | ~200s | xlsxwriter — no limite |
| `resumo quantitativo` | 17,1s | já 3,3x |
| `docs auditoria_ia` | 14,1s | já 1,8x |
| `title case final` | 8,4s | já 3,4x |
| `docs mesclar_sql` | 7,7s | já 2,4x |
| `pend cruzar e filtrar` | 7,5s | não investigado |
| `pend montar ausentes docs` | 6,1s | laço Python, não investigado |
| `riaf auditoria_ia` | 6,0s | já otimizado |
| `docs checks` | 4,4s | não investigado |
| `riaf mesclar_sql` | 3,5s | já 2,9x |
| `pend montar ausentes riaf` | 2,6s | laço Python |
| `docs transicoes` | 2,6s | pequeno |

Todo o código do projeto soma ~82s contra ~200s de xlsxwriter. **Não há mais nenhum
alvo grande** — o maior item não investigado tem 7,5s.

### ~~Onde o tempo está agora (proc_135)~~ (histórico)

| fase | tempo | situação |
|---|---:|---|
| `GGCI_SAVE` (`close()` do xlsxwriter) | ~120s | irredutível, é geração de XML |
| escrita das abas | ~84s | já 3,2x via `write_column` |
| `docs mesclar_sql` + `riaf mesclar_sql` | 28,1s | **não investigado** |
| `resumo quantitativo` | 17,4s | já 3,3x |
| `docs auditoria_ia` + `riaf auditoria_ia` | 21,4s | já 1,8x |
| `title case final` | 8,5s | já 3,4x |
| `docs checks` + `docs transicoes` | 7,8s | pequeno demais para valer |

O maior alvo restante que é código nosso são as duas chamadas de
`mesclar_sql_e_reordenar`, somando 28,1s.

### 7.13 O CSV herdou os ganhos — conferido em 13/08

O CSV compartilha a fase de dados inteira com o XLSX e só diverge na escrita, então
herdou tudo que foi feito no resumo quantitativo, no coalesce das datas e no
`mesclar_sql`. Nunca havia sido medido depois disso: **3m30s -> 2m15s**.

Conferido com `comparar_csv_xlsx.py` contra o XLSX do proc_136:

- conjunto de abas idêntico (7);
- colunas iguais e na mesma ordem em todas;
- contagem e ordem das linhas iguais em todas;
- **Pagamentos idêntica**, 5.000 linhas x 22 colunas sem uma divergência;
- Envios & Pendências: 60 células de 14.832 divergentes, **todas** em `Ativos` e
  `Desligados` (30 + 30) e **nenhuma** em `Env.`, `Pend.`, `%` ou `Proc.` — ou seja,
  nenhuma nas colunas que o resumo calcula. `Ativos`/`Desligados` seguem o
  `status_vinculo`, que muda entre execuções por regra de negócio (confirmado
  manualmente pelo dono do projeto).

**Comparação completa, 19,3 milhões de células** (todas as linhas e colunas das 7 abas):

| aba | células divergentes | fora das colunas voláteis |
|---|---:|---:|
| Envios & Pendências | 60 de 14.832 | **0** |
| Contrato | 2.019 de 3.945.663 | **0** |
| Riaf | 1.879 de 2.323.008 | **0** |
| Benefício | 530 de 1.579.046 | **0** |
| Financiamento | 263 de 720.654 | **0** |
| Histórico | 1.990 de 3.932.182 | **0** |
| Pagamentos | **0 de 6.827.414** | **0** |

**O formato não introduz divergência nenhuma.** Somando as cinco abas de documentos, a
diferença CSV x XLSX é **6.681** células — contra **6.703** do piso medido entre dois
runs do MESMO formato (§7.14). São o mesmo número: tudo que diverge é a volatilidade do
dado, que apareceria igual comparando dois XLSX. Pagamentos dá exatamente zero porque vem
do parquet fiel do SQL e não passa pelas colunas que oscilam.

### 7.14 O piso de ruído, finalmente medido (proc_137 x proc_138)

Dois runs de CSV com **código idêntico**, mesma configuração, mesmo dia. Fecha duas
contas que ficaram abertas a sessão inteira.

**Tempo — varia menos de 1%:**

| | proc_137 | proc_138 |
|---|---:|---:|
| soma das fases `PERFIL` | 82,73s | 82,00s |
| total | 2m54s | 2m55s |

A estimativa de "uns 8%" que circulou nesta análise **estava errada** e foi repetida
sem medição. Os ganhos por fase reportados aqui são todos reais e bem acima do ruído.
Ressalva: isso mede o CSV; a escrita do XLSX (`close()`, ~120s) envolve muito mais
memória e I/O e não foi medida.

**Dado — varia 0,0536% das células:** 6.703 de 12,5 milhões. Por aba, linhas afetadas:
Histórico 1.139, Contrato 903, Riaf 704, Benefício 372, Financiamento 157. As colunas
são sempre as mesmas: `perfil`, `tipo_bolsa_final`, `mudou_bolsa`, `bolsa_anterior`,
`periodo_atual`, `soma_ovg_devia_pagar_sis`.

**O que isso prova retroativamente:** `tipo_bolsa_final` muda em **326** registros do
Contrato entre dois runs de código idêntico. Quando o `transform(lambda)` virou groupby
nativo (§7.12), mudaram **311** — menos que o piso. Junto com o argumento estrutural
(nenhuma divergência envolvia nulo), a otimização está descartada como causa por dois
caminhos independentes.

**Fica registrado como método:** antes de culpar uma mudança por divergência de
conteúdo, rode o mesmo código duas vezes. Custa um run e evita perseguir bug
inexistente.

---

## 8. Como medir sem estragar a medição

**Nunca rodar o comparador em paralelo com uma geração.** Foi o que matou o
`proc_126`: a passada de formatação usava `openpyxl` com `read_only=False`, que
materializa o workbook inteiro — **6,38 GB de pico** medidos para o relatório de
74 MB. Numa máquina de 14 GB com 8,4 GB já em uso, o OOM killer levou o processo
do relatório, sem traceback.

Corrigido: `carregar_visual` agora lê o XML direto do zip com parser incremental,
**0,07 GB de pico** (91× menos). Ainda assim, medir tempo com outra carga pesada
ao lado invalida o número.

Cuidado com `pgrep -f "executar_motor_ia"` em script de monitoramento: o padrão
casa com o próprio comando do monitor e o processo parece vivo para sempre.

## 9. Fase 3 — o que falta

1. Rodar o pipeline completo em XLSX **com a máquina livre** e comparar contra o
   baseline:

   ```bash
   ggci_ia --run
   venv/bin/python3 apps/automacoes/analise_ia/tests/comparar_relatorios.py \
       apps/automacoes/analise_ia/tests/baseline/relatorio_geral.xlsx \
       apps/automacoes/analise_ia/dados/processamento/proc_<N>/relatorio_geral.xlsx
   ```

   **Aceite:** zero linhas sob "REGRESSÃO". Diferença de linha/valor pode ser
   dado novo — julgar pelos exemplos e pelo ranking de colunas.

2. **Fechar o `cnpj_ies`** (ver §11). É o único bloqueio para commitar.

3. Rodar em CSV **com o JS atualizado no browser** (`Ctrl+Shift+R`) e conferir com
   `comparar_csv_xlsx.py`.

4. Se o `close()` (~122s) virar a maior fatia restante, a única saída conhecida é
   trocar a biblioteca de escrita — decisão que viola a restrição de versões
   travadas e precisa ser discutida antes.

---

## 10. O `dayfirst` — investigado, é correção de bug

A mudança não commitada `dayfirst=True` → `dayfirst=False` (`ggci.py`, blocos de
`Data_Processamento_Cache` e `Data_Processamento_Atual`) **corrige um bug**. Não
é regressão. Deve ser mantida e commitada.

**Por quê:** `get_d_proc` devolve `str(row[c]).strip()`, e `data_processamento`
chega do banco como `Datetime` nativo (confirmado nos parquets: 5 dos 9 espelhos
usam `Datetime(time_unit='us')`; os outros 4 são `String` mas estão vazios). O
`str()` de um `Timestamp` sai em **ISO, ano primeiro**: `'2026-02-09 18:13:36'`.

Com `dayfirst=True`, o pandas lê essa string como **9 de setembro** e emite
`UserWarning: Parsing dates in %Y-%m-%d %H:%M:%S format when dayfirst=True was
specified`. Toda data cujo dia fosse ≤ 12 saía com mês e dia trocados —
aproximadamente 12 dos 31 dias possíveis.

**Consequência do bug:** essas datas alimentam
`mask_newer = data_cache_col > data_atual_col` (§`atualizar_e_aplicar_cache_local`),
que decide se o cache local do Gemini sobrepõe o dado do banco. Com as datas
embaralhadas, a decisão de reprocessar era errada em parte dos registros. O erro
era silencioso: nunca gerava `NaT`, então nada estourava.

**Travado por:** `tests/test_data_processamento.py`, que documenta o bug, valida
o parse correto e falha se algum espelho passar a entregar data em `dd/mm/aaaa`
(caso em que `dayfirst=False` viraria o problema). Os dois pontos no código
levaram comentário explicando por que não se deve "corrigir" de volta.

O baseline do `proc_121` foi gerado com `dayfirst=False`, então segue válido como
referência.

---

## 11. O `cnpj_ies` — encerrado em 13/08, é dado

Na aba **Riaf**, a coluna `cnpj_ies` saiu de **100% vazia** no baseline (proc_121)
para **100% preenchida**. O `comparar_relatorios.py` marca isso como REGRESSÃO pela
regra "coluna que muda em todos os registros quase nunca é dado novo" — a regra é boa,
mas aqui deu falso positivo. Quatro evidências independentes fecham o caso:

1. **Nenhum commit toca a cadeia.** `git log -S"cnpj"` e `-S"ins_cnpj"` sobre o
   `ggci.py` voltam vazios. O caminho `b.ins_cnpj` (SQL) → `'Ins. CNPJ'` → `ins_cnpj`
   → `cnpj_ies` está intacto.
2. **A origem passou a trazer o dado.** O parquet de beneficiários tem `ins_cnpj` em
   95.310 de 95.310 registros. O baseline foi gerado antes disso.
3. **`test_escrever_aba` roda sobre a aba Riaf do baseline**, onde a coluna é 100%
   `None`, e devolve células idênticas ao `to_excel`. A função não inventa valor.
4. **O CSV também traz 31.392 de 31.392 preenchidos** — e o CSV sai por `to_csv`, sem
   passar pelo `escrever_aba`. Dois caminhos de escrita independentes concordam, então
   a diferença está no dado, não na escrita.

**Lição para a próxima vez:** quando o comparador acusar uma coluna que mudou em 100%
dos registros, gerar os dois formatos e conferir se ambos concordam separa "mudou a
escrita" de "mudou o dado" sem precisar de um run com o código antigo.

---

## 12. Por que desligar os relatórios não acelera — encerrado em 13/08

A dúvida era legítima: se eu peço menos abas, deveria demorar menos. A resposta é que
essas abas nunca custaram tempo.

### 12.1 As abas de relatório são fórmula, não dado

`gerar_aba_relatorio_contratos` e `gerar_aba_relatorio_riaf` tocam o DataFrame em três
lugares e só: `list(df.columns)`, um `dropna().unique()` da coluna `faculdade` e uma
lista de colunas existentes. Elas **não percorrem as linhas** — escrevem fórmulas do
Excel que o próprio Excel resolve na abertura. O custo é proporcional ao número de IES
(~105) e de semestres (4), não ao volume.

Peso das abas dentro do `relatorio_geral.xlsx` (XML descomprimido, baseline com tudo):

| aba | linhas | XML | % |
|---|---:|---:|---:|
| Relatório Contratos | 65 | 0,10 MB | 0,013% |
| Aux_IES_Contratos | 109 | 0,01 MB | 0,001% |
| Relatório RIAF | 69 | 0,02 MB | 0,003% |
| Aux_IES_RIAF | 105 | 0,01 MB | 0,001% |
| **as 4 somadas** | **348** | **0,13 MB** | **0,018%** |
| Pagamentos | 310.338 | 272,0 MB | 36,2% |
| Contrato | 64.683 | 155,8 MB | 20,7% |
| Histórico | 64.462 | 149,7 MB | 19,9% |
| Riaf | 31.392 | 86,6 MB | 11,5% |
| Benefício | 25.893 | 60,0 MB | 8,0% |
| Financiamento | 11.815 | 27,0 MB | 3,6% |
| Envios & Pendências | 413 | 0,5 MB | 0,1% |

Medição direta, com as duas funções isoladas do pipeline sobre um `df_docs` de
167.000 × 61 e um `df_riaf` de 31.392 × 63:

```
gerar_aba_relatorio_contratos :   0.059s
gerar_aba_relatorio_riaf      :   0.031s
close() só com essas 2 abas   :   0.036s
CUSTO TOTAL DOS RELATÓRIOS    :   0.126s
```

**0,126s.** Desligá-los devolve 0,03% de uma execução de 7 minutos — abaixo do ruído.

### 12.2 Os três tempos de 13/08, lado a lado

Os três runs processaram exatamente o mesmo volume (88.919 ausentes injetados,
Contrato 64.683, Riaf 31.392, Histórico 64.462), então são comparáveis:

O tempo que vale é o **total** (o "Concluído em" da tela), não só o da geração:

| run | formato | abas escritas | conteúdo | total | geração |
|---|---|---|---|---|---|
| proc_124 | XLSX completo | 11 | 751,7 MB de XML | **7m25s** | 6m35s |
| proc_125 | CSV incompleto | 5 | 116,6 MB de texto | **3m05s** | 2m02s |
| proc_127 | XLSX sem relatórios | 7 | 735,2 MB de XML | **8m01s** | 7m08s |
| proc_129 | XLSX completo | 11 | 751,7 MB de XML | **8m19s** | 7m24s |
| proc_130 | CSV completo | 7 | 166,5 MB de texto | **4m12s** | 3m30s |
| proc_131 | XLSX completo, já com a máscara (§7.9) | 11 | 751,7 MB de XML | **7m22s** | **6m42s** |
| proc_132 | XLSX completo, com a instrumentação | 11 | 751,7 MB de XML | **7m25s** | 6m44s |
| proc_133 | XLSX completo, já com o resumo de §7.10 | 11 | 751,7 MB de XML | **6m39s** | **5m56s** |
| proc_135 | XLSX completo, já com o coalesce de §7.11 | 11 | 751,7 MB de XML | **6m28s** | **5m46s** |
| proc_136 | XLSX completo, já com §7.12 | 11 | 751,7 MB de XML | **6m01s** | **5m18s** |
| proc_137 | CSV completo, mesmo código do 136 | 7 | 166,5 MB de texto | **2m54s** | **2m15s** |

Duas leituras importantes:

- **O CSV daquele run não é comparável.** O ZIP tem 5 arquivos: Contrato, Riaf,
  Benefício, Financiamento e Histórico. Não tem Pagamentos (a maior aba de todas), nem
  Envios & Pendências, nem Médias. A causa **não** foi a configuração da tela: o
  `analise_ia.js` forçava `gerar_quantitativo = false` e `gerar_pagamentos = false`
  sempre que o formato era CSV, e o curto-circuito de §7.3 passou a obedecer essas flags
  de verdade. Ou seja, aquele run escreveu **um sexto** do conteúdo. As duas linhas foram
  removidas do JS (§7.4); o próximo CSV vem completo e será mais lento que 3m05s.
- **A diferença de 7m25s para 8m01s não são os relatórios** — eles valem 0,126s. São 8%
  de variação num pipeline que faz consultas a banco remoto, dentro do ruído já
  documentado. Para fechar esse número seria preciso repetir o mesmo run duas vezes
  seguidas, o que não vale o custo de 16 minutos de máquina.

### 12.3 A regra que sai daqui

O tempo do XLSX é proporcional ao **número de células escritas**, e 99,98% delas estão
nas seis abas analíticas. Desmarcar aba de relatório é escolha de conteúdo, não de
performance. Quem quiser velocidade desmarca **Pagamentos** (36% do arquivo sozinha).

---

## 13. Comandos de referência

```bash
# pipeline completo (aliases do dono do projeto)
init_analise_ia --verbose && extracao_ia --run && consolidacao_ia --run && ggci_ia --run

# só a geração do relatório
venv/bin/python3 manage.py executar_motor_ia <processo_id>

# testes
venv/bin/python3 manage.py test apps.automacoes.analise_ia.tests

# comparar contra o baseline
venv/bin/python3 apps/automacoes/analise_ia/tests/comparar_relatorios.py <base> <novo>

# perfilar processo em andamento
py-spy dump --pid $(pgrep -f executar_motor_ia)
```
