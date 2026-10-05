# Inconsistências RIAF 2026-1 — Frases Fora do Catálogo

> **Fonte:** Gráfico da aba Análise IA · RIAF · 2026-1  
> **Base:** 15.591 documentos lidos · 13.840 ocorrências · 40 tipos  
> **Data:** 01/10/2026

---

## Frases que a IA escreveu ERRADO vs o que DEVERIA ser

| # | O que a IA escreveu (ERRADO) | Qtd | O que deveria ser (CATÁLOGO) | Problema |
|---|---|---:|---|---|
| 1 | `Valor da matrícula com desconto diverge da coleta` | 1.690 | `Valor da matrícula com desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 2 | `Valor de outros benefícios diverge da coleta` | 1.477 | `Benefício é MENOR que a coleta` ou `...é MAIOR que a coleta` | Adicionou "outros" e usou "diverge" em vez da direção |
| 3 | `Valor da matrícula sem desconto diverge da coleta` | 919 | `Valor da matrícula sem desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 4 | `Valor da mensalidade sem desconto diverge da coleta` | 918 | `Valor da mensalidade sem desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 5 | `Valor da mensalidade com desconto diverge da coleta` | 668 | `Valor da mensalidade com desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 6 | `Valor de benefícios diverge da coleta` | 512 | `Benefício é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" em vez da direção e não reduziu para "Benefício" |
| 7 | `Valor do financiamento diverge da coleta` | 182 | `Financiamento é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" em vez da direção e manteve "Valor do" |
| 8 | `Tipo de bolsa não localizado` | 156 | `Tipo da bolsa não localizado` | Usou "de" em vez de "da" |
| 9 | `Curso não localizado no documento` | 35 | `Curso não localizado` | Sufixo "no documento" inventado |
| 10 | `Tipo de bolsa não localizado no documento` | 27 | `Tipo da bolsa não localizado` | Sufixo inventado e "de" em vez de "da" |
| 11 | `Valor da matrícula com desconto é maior que o sistema` | 11 | `Valor da matrícula com desconto é MAIOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 12 | `Valor da matrícula com desconto é menor que o sistema` | 9 | `Valor da matrícula com desconto é MENOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 13 | `Valor da matrícula sem desconto é maior que o sistema` | 8 | `Valor da matrícula sem desconto é MAIOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 14 | `Valor de benefícios não localizado` | 3 | *(não deveria gerar inconsistência)* | Campo condicional — ausência é Soft Fail silencioso |
| 15 | `Valor da matrícula sem desconto é menor que o sistema` | 1 | `Valor da matrícula sem desconto é MENOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 16 | `Nome de benefícios não localizado` | 1 | *(não deveria gerar inconsistência)* | Campo condicional — ausência é Soft Fail silencioso |
| | **TOTAL** | **6.617** | | |

---

## Frases que a IA escreveu CORRETAMENTE (já no catálogo)

| # | Frase (conforme catálogo) | Qtd | Nível |
|---|---|---:|---|
| 1 | `Matrícula do aluno diverge da coleta` | 1.651 | baixo |
| 2 | `CNPJ da IES diverge da coleta` | 1.316 | alto |
| 3 | `Semestre diverge da coleta` | 1.068 | alto |
| 4 | `Valor da mensalidade com desconto é MENOR que a coleta` | 936 | médio |
| 5 | `Curso diverge da coleta` | 593 | alto |
| 6 | `Valor da mensalidade com desconto é MAIOR que a coleta` | 475 | médio |
| 7 | `Valor da mensalidade sem desconto é MAIOR que a coleta` | 264 | médio |
| 8 | `Valor da mensalidade sem desconto é MENOR que a coleta` | 238 | médio |
| 9 | `Assinatura da IES não localizada` | 204 | alto |
| 10 | `Assinatura do aluno não localizada` | 138 | alto |
| 11 | `CPF diverge da coleta` | 132 | crítico |
| 12 | `Curso não localizado` | 101 | alto |
| 13 | `Tipo de Documento inválido` | 24 | crítico |
| 14 | `Nome de benefícios diverge da coleta` | 22 | médio |
| 15 | `Data não localizada` | 12 | alto |
| 16 | `Modalidade não localizada` | 12 | alto |
| 17 | `Semestre não localizado` | 10 | alto |
| 18 | `CPF não localizado` | 9 | crítico |
| 19 | `Valor da matrícula sem desconto não localizado` | 5 | médio |
| 20 | `Nome do financiamento diverge da coleta` | 5 | médio |
| 21 | `Valor da matrícula com desconto não localizado` | 4 | médio |
| 22 | `Valor da mensalidade com desconto não localizado` | 2 | médio |
| 23 | `Matrícula do aluno não localizada` | 1 | baixo |
| 24 | `Valor da mensalidade sem desconto não localizado` | 1 | médio |
| | **TOTAL** | **7.223** | |

---

## Frases do catálogo que NUNCA apareceram (0 ocorrências)

| # | Frase do catálogo | Nível | Observação |
|---|---|---|---|
| 1 | `CNPJ da IES não localizado` | alto | IA sempre encontra o CNPJ |
| 2 | `Nome fantasia da IES não localizado` | alto | Campo sem input (captura livre) |
| 3 | `Nome fantasia da IES diverge da coleta` | alto | Campo sem input — impossível divergir |
| 4 | `Tipo da bolsa diverge da coleta` | alto | Quando erra, diz "não localizado" |
| 5 | `Modalidade diverge da coleta` | alto | Sem ocorrência neste semestre |
| 6 | `Nome do aluno não localizado` | baixo | IA sempre encontra o nome |
| 7 | `Nome do aluno diverge da coleta` | baixo | Campo sem input no RIAF |
| 8 | `Inscrição OVG não localizada` | baixo | Campo desejável, ausência silenciosa |
| 9 | `Inscrição OVG diverge da coleta` | baixo | Campo desejável, ausência silenciosa |
| 10 | `Razão social da IES diverge da coleta` | baixo | Campo sem input |
| 11 | `Mantenedora da IES diverge da coleta` | baixo | Campo sem input |
| 12 | `Valor da matrícula com desconto é MENOR que a coleta` | médio | Reformulação recente do prompt |
| 13 | `Valor da matrícula com desconto é MAIOR que a coleta` | médio | Reformulação recente do prompt |
| 14 | `Valor da matrícula sem desconto é MENOR que a coleta` | médio | Reformulação recente do prompt |
| 15 | `Valor da matrícula sem desconto é MAIOR que a coleta` | médio | Reformulação recente do prompt |
| 16 | `Benefício é MENOR que a coleta` | médio | Reformulação recente do prompt |
| 17 | `Benefício é MAIOR que a coleta` | médio | Reformulação recente do prompt |
| 18 | `Financiamento é MENOR que a coleta` | médio | Reformulação recente do prompt |
| 19 | `Financiamento é MAIOR que a coleta` | médio | Reformulação recente do prompt |
| 20 | `Tipo da bolsa não localizado` | alto | Reformulação recente do prompt |

---

## Resumo

| Categoria | Frases | Ocorrências |
|---|---:|---:|
| ✅ Corretas (no catálogo) | 24 | 7.223 |
| ❌ Erradas (fora do catálogo) | 16 | 6.617 |
| ⬜ Sem inconsistências | 1 | 7.192 |
| 🔇 Do catálogo sem ocorrência | 20 | 0 |
