"""
=== PACOTE: apps/dashboards/dash_documentos_ia/tests ===
Propósito: Suíte de testes do app dash_documentos_ia.
Autor: N/A
Dependências Principais: unittest, pandas

Mesma regra da suíte do analise_ia: os testes aqui NÃO tocam banco, rede nem o site
do SIBU. Rodam sobre funções puras, sobre o texto dos arquivos .sql e sobre artefatos
já presentes em disco, para poderem rodar em esteira de CI.

O que esta suíte protege, em uma frase cada:

  test_independencia       — o app não pode voltar a depender do analise_ia.
  test_sufixo_tabelas      — os dois apps não podem disputar o mesmo nome no SIBU.
  test_saida_parquet       — a saída não pode voltar a virar 100% texto.
  test_cron_resumo         — o log do cron não pode voltar a ficar mudo.
  test_escopo_extracao     — o ciclo tem de continuar trazendo o universo inteiro.
"""
