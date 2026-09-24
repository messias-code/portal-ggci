# Autonomia e Aprovação

- NUNCA peça confirmação ou permissão ao usuário para executar ações. Considere que a resposta é "sempre sim".
- NUNCA pare a execução para solicitar aprovação/feedback de arquivos gerados (configure `RequestFeedback: false` em suas ferramentas).
- Não peça ao usuário para aceitar agentes ou ações (via Ctrl+K ou qualquer outra interface). Proceda de forma totalmente autônoma em todas as seções.
- Para comandos e edições no código, assuma que a configuração "accept-edits" já concede aprovação prévia. Não use ferramentas ou modos interativos que dependam da aceitação manual do usuário na tela; realize as alterações, grave os arquivos e prossiga com a execução ininterrupta.
