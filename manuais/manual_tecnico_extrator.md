# 🕷️ Manual Técnico: `extrator.py`
### Robô de Web Scraping e Download em Lote (Etapa 1 do Pipeline)

> **Para quem é este documento?** → Desenvolvedores que precisam manter a extração automatizada, lidar com mudanças de layout no SIBU/Portal Bolsa ou ajustar as regras de semestres/documentos baixados.
> **Posição no Pipeline:** → Esta é a **Primeira Etapa** do sistema. Ele "pilota" navegadores invisíveis para baixar centenas de relatórios `.xls` e `.xlsx` direto dos sistemas legado do governo antes que o consolidador ou a IA possam agir.

---

## 1. ÍNDICE
1. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
2. [🧹 Sessão 1: Setup e Limpeza de Diretórios](#-sessão-1-setup-e-limpeza-de-diretórios)
3. [🤖 Sessão 2: Worker - Documentos (Scriptcase)](#-sessão-2-worker---documentos-scriptcase)
4. [💰 Sessão 3: Worker - Pagamentos (Portal Bolsa)](#-sessão-3-worker---pagamentos-portal-bolsa)
5. [🚄 Sessão 4: Macro-Orquestradores (Paralelismo)](#-sessão-4-macro-orquestradores-paralelismo)
6. [🧠 Sessão 5: Orquestrador Global e Regras de Negócio](#-sessão-5-orquestrador-global-e-regras-de-negócio)
7. [Apêndice](#apêndice)

---

## Visão Geral da Arquitetura

O `extrator.py` atua como um coordenador de Múltiplos Trabalhadores (Workers) simultâneos via Threads. Ele domina o **Playwright** para simular cliques humanos e baixar arquivos.

```ascii
                      [FILTROS DO USUÁRIO]
                      (Docs, Anos, Semestres)
                                │
                                ↓
                      [ORQUESTRADOR GLOBAL]
                      Gera fila de tarefas bloqueando
                      combinações inválidas (ex: RIAF < 2026)
                                │
             ┌──────────────────┼──────────────────┐
             ↓                  ↓                  ↓
    [THREAD POOL 1]    [THREAD POOL 2]    [THREAD POOL 3]
    Baixar Documentos  Baixar Agendamentos Baixar Faturamento
    (Scriptcase SIBU)  (Scriptcase SIBU)   (Portal Bolsa)
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ↓
                      [SAÍDAS EM DISCO]
┌─────────────────────────────────────────────────────────────┐
│ 📁 dados/dados_analise_ia/                                            │
│  ├─ analise_documentos_processados/ (Centenas de .xlsx)      │
│  ├─ analise_documentos_agendar_processamentos/ (.xlsx)       │
│  └─ analise_pagamentos/ (Dezenas de .xls mensais)            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧹 Sessão 1: Setup e Limpeza de Diretórios

### O que é e por quê existe
Antes de iniciar qualquer download, o sistema precisa de uma "lousa em branco". Se não apagarmos a pasta raiz de análise anterior, o sistema pode misturar planilhas da semana passada com as de hoje, gerando dados duplicados. A decisão de design foi usar `shutil.rmtree` para destruir a árvore inteira e recriar.

### Como funciona
```python
def limpar_pasta_raiz(pasta):
    if os.path.exists(pasta):
        shutil.rmtree(pasta) # Apaga a pasta inteira e tudo dentro
    os.makedirs(pasta, exist_ok=True) # Recria vazia
```
- **Por que `shutil.rmtree` e não `os.remove` em loop?** `rmtree` deleta pastas não vazias numa única chamada atômica ao sistema operacional, sendo imensamente mais limpo e rápido que iterar recursivamente em Python para deletar arquivo por arquivo.

### Exemplo prático
Ao iniciar, o diretório `dados/dados_analise_ia/analise_pagamentos` que tinha 24 relatórios antigos (2024 e 2025) é completamente fulminado e uma nova pasta vazia com o mesmo nome é criada.

### Pseudoalgoritmo
```text
FUNÇÃO limpar_pasta_raiz(caminho)
    SE o caminho existir:
        APAGAR ARVORE DE DIRETORIOS COMPLETA (arquivos e subpastas)
    CRIAR pasta novamente garantindo que está vazia
```

---

## 🤖 Sessão 2: Worker - Documentos (Scriptcase)

### O que é e por quê existe
O portal interno `10.237.1.11/pbu/entrar/` foi feito em Scriptcase (PHP). Isso significa pesadelo para automação: navegação baseada em Iframes, requisições escondidas e menus dinâmicos. A decisão arquitetural foi usar **Playwright em vez de Selenium ou BeautifulSoup**. O Playwright lida melhor com Iframes aninhados e downloads em segundo plano de forma nativa e paralela (via contexts).

### Como funciona
```python
frame = page.frame_locator(f"iframe[name='{nome_iframe}']")
frame.locator("#SC_semestre").wait_for(state="visible", timeout=15000)

try:
    frame.locator("#SC_semestre").select_option(valor_semestre, timeout=3000)
except:
    print(f"⚠️  {tag} Semestre não disponível no sistema.")
    return

# ... Interação para download
with page.expect_download(timeout=60000) as download_info:
    btn_baixar.click()
download = download_info.value
download.save_as(caminho_final)
```
- **Por que `.frame_locator`?** Scriptcase gera conteúdo "dentro" da página real. Ferramentas comuns de XPath não acham os botões porque eles estão em outro escopo DOM. O `frame_locator` transpassa essa barreira.
- **Por que `expect_download`?** Evita o problema clássico de automação onde o robô clica para baixar, não sabe onde o navegador salvou o arquivo temporário, e encerra o processo abortando o download no meio. Essa cláusula "prende" o robô até o arquivo pingar completo em disco.

### Exemplo prático
- Parâmetro recebido: `semestre_str = "2025-1"`
- Tradução Scriptcase: Valor injetado no campo HTML via `.select_option` é `"2025-1##@@2025-1"` (peculiaridade do sistema PHP legado).
- Se o semestre não foi lançado no sistema pela TI, o código pega a Exceção do Timeout (3s), avisa no log, e finaliza a thread sem dar erro crítico no robô principal.

### Pseudoalgoritmo
```text
FUNÇÃO extrair_documento_scriptcase(tarefa, configuracao, semestre)
    CRIAR pastas de destino necessárias
    TENTAR ATÉ 3 VEZES:
        ABRIR navegador invisível Chromium
        NAVEGAR para o login, preencher credenciais e logar
        ENCONTRAR o menu no dropdown e clicar
        ENTRAR NO IFRAME gerado pelo Scriptcase
        SELETOR: Mudar dropdown para o Semestre desejado
        SE semestre não existir: Aborta educadamente
        CLICAR em buscar
        SE aviso de "Sem registros" aparecer: Aborta educadamente
        CLICAR em Exportar Excel
        AGUARDAR o botão de download piscar verde
        INICIAR modo de escuta de download e clicar em Baixar
        SALVAR na pasta com o nome formatado (ex: contratos_2025-1.xlsx)
        SAIR com Sucesso
```

---

## 💰 Sessão 3: Worker - Pagamentos (Portal Bolsa)

### O que é e por quê existe
Enquanto documentos são baixados por semestre (2 relatórios/ano), o Portal de Faturamento exige o download **Mês a Mês** no formato CSV disfarçado de XLS. Ele acessa uma rota diferente (`/bolsa/`) e possui travas de negócio temporais: não adianta tentar baixar o faturamento de Dezembro em Janeiro do mesmo ano.

### Como funciona
```python
if ano_int > ano_atual:
    print(f"⚠️  {tag} Ano futuro. Pulando.")
    return
    
limite_mes = 12
if ano_int == ano_atual:
    limite_mes = mes_atual - 1
    if limite_mes == 0:
        print(f"⚠️  {tag} Janeiro ainda não fechou. Pulando.")
        return
```
- **Por que `limite_mes = mes_atual - 1`?** Se estamos em Agosto, a OVG/IES ainda estão trabalhando o mês corrente. O sistema financeiro só disponibiliza relatórios fechados do mês anterior. Portanto o teto de busca será Julho (Mês 7).

```python
page.locator("#formato").select_option("CSV") 

for mes in range(1, limite_mes + 1):
    mes_str = f"{mes:02d}"
    page.locator("#mes").select_option(mes_str)
```
- **Por que escolhemos "CSV" mas salvamos como ".xls"?** Comportamento "contraintuitivo". O sistema antigo exporta um CSV separado por ponto e vírgula, mas se você não o obrigar a exportar nesse padrão cru (CSV), o "Excel" nativo dele vem corrompido em tags HTML quebradas. Salvamos localmente com `.xls` para o `consolidador.py` ler nativamente na próxima etapa do pipeline.

### Exemplo prático
Execução em Julho de 2025 (Mês 07). 
Teto: Mês 06 (Junho).
O script vai rodar um loop de 1 a 6 e realizar **6 downloads sequenciais na mesma sessão de navegador**:
- `pagamento_2025_jan.xls`
- ...
- `pagamento_2025_jun.xls`

### Pseudoalgoritmo
```text
FUNÇÃO extrair_ano_pagamento(ano)
    VERIFICAR regras temporais (Bloquear anos futuros, limitar ao mês anterior)
    TENTAR ATÉ 3 VEZES:
        ABRIR navegador invisível Chromium
        NAVEGAR para o login e logar
        Mergulhar nas arvores do menu até a tela de Lançamentos
        SELECIONAR Ano Alvo
        MARCAR tipo Exportação para CSV 
        PARA CADA Mês (de Janeiro até limite_mes):
            SELECIONAR Mês no form
            CLICAR em buscar
            INICIAR escuta de download e clicar em Baixar
            SALVAR arquivo (pagamento_2025_jan.xls)
        SAIR com Sucesso
```

---

## 🚄 Sessão 4: Macro-Orquestradores (Paralelismo)

### O que é e por quê existe
Baixar arquivos em UI (User Interface) é um processo bloqueante (Network e DOM Paint). Baixar 30 arquivos seguidos em uma aba levaria de 10 a 20 minutos. A decisão arquitetural foi usar **Programação Concorrente com `ThreadPoolExecutor`**, criando múltiplos navegadores que operam ao mesmo tempo. O Playwright gerencia os isolamentos (`contexts`) lindamente.

### Como funciona
```python
def macro_processar_menu_documentos(tarefa, pre_calculados):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(extrair_documento_scriptcase, tarefa, doc, sem) for doc, sem in pre_calculados]
        for f in concurrent.futures.as_completed(futures):
            try: f.result()
            except Exception as e: print(f"⚠️ Erro interno na extração: {e}")
```
- **Por que `max_workers=3`?** Três threads batendo ao mesmo tempo num banco de dados / IIS legado é o limite ótimo empírico. Se passarmos para 10, o servidor interno (10.237.1.11) possivelmente travaria bloqueando as conexões por gargalo HTTP (Timeouts/504).
- **Por que `as_completed(futures)`?** Em vez de esperar em ordem alfabética (A termina, B termina, C termina), o `as_completed` libera as threads assim que elas terminam, pegando o próximo serviço da fila instantaneamente (ex: O ano de 2025 terminou de baixar antes de 2024? Ele já injeta 2026 na máquina aberta).

### Exemplo prático
Em vez de baixar:
1. Contratos 25-1 -> Contratos 25-2 -> Contratos 26-1 ...
O robô baixa simultaneamente:
[Navegador 1: Contrato 25-1] | [Navegador 2: Contrato 25-2] | [Navegador 3: Contrato 26-1]
Isso divide o tempo total de operação por 3.

### Pseudoalgoritmo
```text
FUNÇÃO macro_processar_menu_documentos(tarefas)
    INICIAR Gerenciador de Threads com máximo de 3 Trabalhadores
    JOGAR TODAS as tarefas (tipo x semestre) na piscina de Execução
    PARA CADA tarefa que terminar:
        Traz o resultado (ou erro) para a tela
```

---

## 🧠 Sessão 5: Orquestrador Global e Regras de Negócio

### O que é e por quê existe
Antes de ativar os Trabalhadores e esmagar a rede da empresa, o Script atua como um Fiscal Lógico (`executar()`), que lê as solicitações do usuário, gera a matriz de `Docs x Anos x Semestres` e bloqueia as rotas que ele sabe por regra de negócio que são furadas, evitando que o Playwright abra um navegador inteiro para descobrir que algo não existia.

### Como funciona
```python
# Regra para HISTÓRICO (Pula os semestres que você sabe que não tem registro)
if doc["categoria"] == "HISTORICO" and sem in ["2025-1", "2026-1"]:
    continue

if doc["categoria"] == "RIAF" and ano_int < 2026:
    continue
if ano_int > ano_atual:
    continue
if ano_int == ano_atual and str(per) == "2" and mes_atual < 7:
    continue
```
- **A Regra de Ouro (RIAF):** O RIAF não existia em 2025. Se o script tentasse buscar isso no front-end, perderia preciosos 15-20 segundos na fila esperando o sistema avisar "Sem registros". O filtro "chumba" o bloqueio matematicamente antes da criação da Thread.
- **Teto do 2º Semestre:** `mes_atual < 7`. Você não pode buscar a rematrícula do 2º Semestre (Julho a Dezembro) num mês que seja anterior a Julho (07).

```python
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as macro_executor:
    t_analise = macro_executor.submit(macro_processar_menu_documentos, TAREFAS_MENUS[0], docs_para_baixar)
    t_agendar = macro_executor.submit(macro_processar_menu_documentos, TAREFAS_MENUS[1], docs_para_baixar)
    t_pag = macro_executor.submit(macro_processar_pagamentos, list(anos_reais_pagamentos))
    concurrent.futures.wait([t_analise, t_agendar, t_pag])
```
- **O Macro-Paralelismo:** Aqui a magia é elevada ao quadrado. Ele aciona os 3 MACRO-orquestradores ao mesmo tempo. Enquanto 3 abas baixam Contratos, 3 abas baixam Agendamentos e 2 abas baixam Faturamento. Totalizando quase 8 instâncias de navegador simultâneas controladas pelo Python. A função `.wait` congela o terminal principal até que tudo, de todos os lados, seja concluído.

### Exemplo prático
Usuário pede: TODOS documentos, anos 2025 e 2026, TODOS os períodos.
O script limpa os arrays, aplica as regras (corta RIAF 25, Histórico 25-1, etc), envia a lista refinada para as Pools. No final, imprime "🎉 Extração concluída: 54 Arquivos baixados estruturados em 2m e 15s".

### Pseudoalgoritmo
```text
FUNÇÃO executar(filtros)
    LIMPAR DIRETÓRIOS FISICOS
    CONVERTER filtros "TODOS" em listas reais
    CRIAR lista de tarefas_a_baixar_documentos vazia
    CRIAR lista de anos_a_baixar_pagamentos vazia
    
    PARA CADA Documento:
        PARA CADA Ano e Periodo cruzado:
            SE esbarrar na Regra do RIAF (<2026): Ignora
            SE esbarrar na Regra do Histórico (sem. impar): Ignora
            SE Semestre do Futuro inatingível: Ignora
            
            ADICIONAR na lista de documentos
            ADICIONAR Ano na lista de pagamentos
            
    INICIAR Macro-Gerenciador de Threads
        Ativar Pool 1 (Contratos/Benefícios)
        Ativar Pool 2 (Agendamentos)
        Ativar Pool 3 (Financeiro)
    ESPERAR TUDO TERMINAR
    
    Contar arquivos físicos nas pastas e Avisar Sucesso/Tempo
```

---

## Apêndice

### 1. Guia de Instalação e Dependências
Para suportar toda a automação de navegadores:
```bash
pip install playwright
playwright install chromium
```

### 2. Tabela-resumo das principais transformações

| Input UI | Origem Extração | Transformação/Restrição | Output (Disco) |
| :--- | :--- | :--- | :--- |
| Contrato 25-1 | 10.237.1.11/pbu | Tag: `2025-1##@@2025-1` | `contratos_2025-1.xlsx` |
| RIAF 25-2 | 10.237.1.11/pbu | Tag: `2025-2` | **BLOQUEADO (Regra de Ano)** |
| Faturamento 2025 | 10.237.1.11/bolsa | Teto: Mês Corrente - 1 | `pagamento_2025_jan.xls` (múltiplos) |

### 3. Fluxo de decisão em árvore ASCII (Filtro Global)

```ascii
[Avaliação do Semestre]
       │
       ├─ É documento RIAF?
       │    ├─ SIM ──> O Ano é menor que 2026?
       │    │            ├─ SIM ──> [ BLOQUEAR ]
       │    │            └─ NÃO ──> [ CONTINUAR ]
       │    └─ NÃO ──> É Histórico Escolar?
       │                 ├─ SIM ──> É Semestre Ímpar (X-1)?
       │                 │            ├─ SIM ──> [ BLOQUEAR ]
       │                 │            └─ NÃO ──> [ CONTINUAR ]
       │                 └─ NÃO ──> [ CONTINUAR ]
       │
       └─ O Mês já permite buscar o 2º Semestre?
            ├─ Mês Atual < Julho E Semestre == '2'
            │    ├─ SIM ──> [ BLOQUEAR ]
            │    └─ NÃO ──> [ ADICIONA À FILA DE DOWNLOAD ]
```

### 4. Tabela de mensagens de log

| Código Visual | Significado | Exemplo Real |
| :--- | :--- | :--- |
| ⚠️  | **Aviso Suave / Skips Lógicos** | `[ REGRA | RIAF ] ⚠️ Ignorado: RIAF só existe a partir de 2026.` |
| ✅ | **Sucesso Confirmado** | `✅ [PAGAMENTOS ] Download concluído (6 meses)` |
| ❌ | **Erro não obstrutivo / Isolado** | `❌ [ANÁLISE ] Falha final após 3x: Timeout Error` |
| 🚨 | **Erro Crítico de Infra** | `🚨 [PAGAMENTOS ] Erro crítico na API Playwright` |

---
*Este documento é vivo. Cada nova funcionalidade implementada no `extrator.py` deve ganhar uma nova sessão aqui, seguindo o mesmo padrão: O que é → Por quê existe → Como funciona → Exemplo → Pseudoalgoritmo.*