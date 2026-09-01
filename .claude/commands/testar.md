---
description: Roda a suíte de testes de um app específico (ou a suíte inteira) e reporta o resultado
argument-hint: "[nome do app, ex: analise_ia | dash_documentos_ia | tudo]"
---

# Rodar testes — Portal GGCI

Alvo pedido: **$ARGUMENTS**

## Como resolver o alvo

Os apps vivem em `apps/<grupo>/<app>/`, onde `<grupo>` é um de
`automacoes`, `dashboards`, `ferramentas`, `inicio`. O label do Django é
`apps.<grupo>.<app>`.

1. Se `$ARGUMENTS` estiver vazio, rode os testes dos apps tocados pelo diff
   atual (`git diff --name-only` + `git diff --cached --name-only`).
2. Se for `tudo`, rode a suíte inteira — e avise que é demorada.
3. Caso contrário, ache o grupo com
   `find apps -maxdepth 2 -type d -name "$ARGUMENTS"` e monte o label.

## Comando

```bash
source venv/bin/activate
python manage.py test <label> --parallel 4
```

## Ao reportar

- Dê o número de testes, o tempo e o veredito (`OK` / `FAILED`), sem enfeite.
- Em falha, mostre as linhas `FAIL:` / `ERROR:` e o traceback relevante.
- **Não** conclua regressão sem checar duas armadilhas conhecidas:
  - O manifesto de staticfiles está defasado (falta `css/console.css`) e
    derruba 4 testes de tela do Documentos IA — é causa conhecida, não regressão.
  - O relatório do GGCI não é determinístico: a mesma entrada diverge em
    ~800 linhas por aba. Meça o piso de ruído antes de culpar uma mudança.
