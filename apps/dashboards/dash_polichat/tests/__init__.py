"""
=== PACOTE: apps/dashboards/dash_polichat/tests ===
Propósito: Suíte de testes do app dash_polichat.
Autor: N/A
Dependências Principais: unittest, django.test, playwright (Chromium já instalado
                         para o extrator)

Nenhum teste aqui acessa o Poli Digital, o MySQL de produção ou a rede. Os que
precisam de banco usam `django.test.TestCase`, que roda no banco de teste e
desfaz tudo ao final; os demais são leitura de arquivo e execução de JS em
Chromium headless. Tudo roda em esteira de CI.

O que esta suíte protege, em uma frase cada:

  test_console_estilo      — classe do console não pode voltar a falhar em silêncio.
  test_console_formatador  — o log da tela não pode voltar a ser um paredão de texto.
  test_espelho_loop        — o console não pode voltar a congelar em 100%.
  test_status_loop         — o endpoint tem de continuar dizendo QUAL ciclo está ativo.
  test_cadencia_loop       — o ciclo não pode voltar a esperar por grade nem por outro ambiente.

NOTA SOBRE O PACOTE: este app usa `tests/` (pacote), e não `tests.py`. Os dois não
podem coexistir — o discovery do unittest aborta com ImportError quando encontra
ambos, que é o estado em que o dash_documentos_ia está hoje e o motivo de
`manage.py test apps.dashboards.dash_documentos_ia` falhar sem rodar nada.
"""
