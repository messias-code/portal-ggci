# Configuração do Claude Code — Portal GGCI

## Estrutura

```
CLAUDE.md              índice na raiz (só imports) — carregado automaticamente
.claude/
├── regras/            as regras de verdade, uma por assunto
├── commands/          prompts reutilizáveis, viram slash commands
└── settings.local.json   permissões desta máquina (ignorado pelo git)
```

## Como adicionar uma regra

1. Crie o `.md` em `.claude/regras/`.
2. Acrescente a linha `@.claude/regras/nome-do-arquivo.md` no `CLAUDE.md` da raiz.

Sem o import, o arquivo **não é lido**.

## Como adicionar um prompt

Cada `.md` dentro de `.claude/commands/` se torna um slash command com o nome do
arquivo: `revisar-view.md` → `/revisar-view`. Subpastas viram namespace:
`django/migrar.md` → `/django:migrar`.

Template:

```markdown
---
description: Uma linha explicando o que o comando faz (aparece no menu)
argument-hint: [nome-do-app]
---

Analise o app Django `$1` e faça X, Y e Z.

Contexto adicional: @portal_ggci/settings.py
```

Recursos disponíveis dentro de um comando:

| Recurso | Uso |
|---|---|
| Argumentos | `$ARGUMENTS` (tudo), `$1`, `$2` (posicionais) |
| Ler arquivo | `@caminho/do/arquivo.py` |
| Rodar bash antes do prompt | crases com `!` no início, ex: `` !`git diff --stat` `` |
| Restringir ferramentas | frontmatter `allowed-tools:` |

## O que é versionado

`regras/comunicacao.md`, `regras/git.md` e `commands/` vão para o git — servem em
qualquer worktree. Já `CLAUDE.md`, `regras/seguranca-e-acessos.md` e
`settings.local.json` ficam fora, porque são locais ou contêm referência a credenciais.
