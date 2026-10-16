# Prompts da IA (`prompts/`)

- **É PROIBIDO renomear variáveis em qualquer prompt** (`prompts/*/prompt.yaml`). Os nomes ficam exatamente como estão hoje; vale a partir de 15/10/2026.
  - Chaves do JSON de saída (`saida_json`, ex.: `tipo_da_bolsa`, `cpf_aluno`).
  - Chaves de `dados_esperados` e os placeholders entre parênteses que o sistema substitui (ex.: `(tipo_bolsa)`, `(uni_cpf)`, `(ins_cnpj)`).
  - Nomes de campos citados nas regras e nos exemplos (`exemplos_saida`).
  - Exemplo do que NÃO fazer: trocar `tipo_bolsa` por `tipo_da_bolsa` (ou o contrário).
- O sistema lê esses nomes para gravar e comparar os dados: um nome trocado faz o campo sumir em silêncio.
- Pode mudar o texto das regras, exemplos e frases do catálogo. Variável nova só se o usuário pedir; renomear, nunca.
