# Inconsistências CONTRATOS 2026-1 — Frases Fora do Catálogo

> **Fonte:** Gráfico da aba Análise IA · Contratos · 2026-1  
> **Base:** [Preencher] documentos lidos · [Preencher] ocorrências  
> **Data:** 05/10/2026

---

## Frases que a IA escreveu ERRADO vs o que DEVERIA ser

| # | O que a IA escreveu (ERRADO) | Qtd | O que deveria ser (CATÁLOGO) | Problema |
|---|---|---:|---|---|
| 1 | `Valor da mensalidade com desconto diverge da coleta` | ? | `Valor da mensalidade com desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 2 | `Valor da mensalidade sem desconto diverge da coleta` | ? | `Valor da mensalidade sem desconto é MENOR que a coleta` ou `...é MAIOR que a coleta` | Usou "diverge" genérico em vez de indicar a direção |
| 3 | `Valor da mensalidade com desconto é maior que o sistema` | ? | `Valor da mensalidade com desconto é MAIOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 4 | `Valor da mensalidade com desconto é menor que o sistema` | ? | `Valor da mensalidade com desconto é MENOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 5 | `Valor da mensalidade sem desconto é maior que o sistema` | ? | `Valor da mensalidade sem desconto é MAIOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 6 | `Valor da mensalidade sem desconto é menor que o sistema` | ? | `Valor da mensalidade sem desconto é MENOR que a coleta` | Usou "sistema" em vez de "coleta" |
| 7 | `CPF diverge do sistema` | ? | `CPF diverge da coleta` | Usou "sistema" em vez de "coleta" |
| 8 | `Semestre diverge do sistema` | ? | `Semestre diverge da coleta` | Usou "sistema" em vez de "coleta" |

---

## Frases que a IA escreveu CORRETAMENTE (já no catálogo)

| # | Frase (conforme catálogo) | Nível |
|---|---|---|
| 1 | `CPF diverge da coleta` | crítico |
| 2 | `Semestre diverge da coleta` | alto |
| 3 | `Valor da mensalidade sem desconto é MENOR que a coleta` | médio |
| 4 | `Valor da mensalidade sem desconto é MAIOR que a coleta` | médio |
| 5 | `Valor da mensalidade com desconto é MENOR que a coleta` | baixo |
| 6 | `Valor da mensalidade com desconto é MAIOR que a coleta` | baixo |
| 7 | `CPF não localizado` | crítico |
| 8 | `Semestre não localizado` | alto |
| 9 | `Valor da mensalidade sem desconto não localizado` | médio |
| 10 | `Valor da mensalidade com desconto não localizado` | baixo |
| 11 | `Tipo de Documento inválido` | crítico |

---

## Frases do catálogo que NUNCA apareceram (0 ocorrências)

| # | Frase do catálogo | Nível | Observação |
|---|---|---|---|
| 1 | `Valor da mensalidade com desconto é MENOR que a coleta` | baixo | Reformulação recente do prompt |
| 2 | `Valor da mensalidade com desconto é MAIOR que a coleta` | baixo | Reformulação recente do prompt |
| 3 | `Valor da mensalidade sem desconto é MENOR que a coleta` | médio | Reformulação recente do prompt |
| 4 | `Valor da mensalidade sem desconto é MAIOR que a coleta` | médio | Reformulação recente do prompt |

---

## Resumo

| Categoria | Frases |
|---|---:|
| ✅ Corretas (no catálogo) | 11 |
| ❌ Erradas (fora do catálogo) | 8 |
| 🔇 Do catálogo sem ocorrência | 4 |
