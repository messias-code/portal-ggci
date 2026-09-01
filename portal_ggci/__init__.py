"""
==========================================================================
INICIALIZADOR DE PACOTE PYTHON (__init__.py)
==========================================================================
Apesar de estar totalmente vazio, este arquivo desempenha um papel 
estrutural fundamental e NÃO DEVE SER APAGADO.

No ecossistema da linguagem Python, a presença de um arquivo '__init__.py' 
(mesmo sem nenhuma linha de código dentro) avisa ao interpretador que a 
pasta onde ele se encontra deve ser tratada como um "Pacote" (Package).

⚠️ O QUE ISSO SIGNIFICA NA PRÁTICA?
É graças a este arquivo silencioso que conseguimos "conectar" as partes 
do nosso projeto e importar arquivos de uma pasta para outra. 

Por exemplo, ele é o responsável por permitir que:
- O 'manage.py' consiga ler o 'portal_ggci/settings.py'
- O 'portal_ggci/urls.py' consiga puxar o 'apps/gestao_acessos/views.py'

Se este arquivo for deletado, o Python deixará de reconhecer a pasta 
como parte do código, os imports vão quebrar, e o servidor do Portal GGCI 
cairá imediatamente com um erro de 'ModuleNotFoundError'.
"""