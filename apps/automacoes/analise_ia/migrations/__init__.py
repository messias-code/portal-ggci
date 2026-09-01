"""
=== ARQUIVO: apps/automacoes/analise_ia/migrations/__init__.py ===
Propósito: Inicializador do pacote de migrações do Django.
Autor: N/A

O QUE FAZ: Sinaliza ao interpretador Python e ao ORM do Django que o 
diretório `migrations` é um módulo válido.
POR QUÊ EXISTE: O Django exige este arquivo (ainda que vazio ou com docstring) 
para conseguir rastrear e registrar os arquivos (ex: `0001_initial.py`) no banco.
COMO FUNCIONA: Ao executar `makemigrations`, o Django escaneia a pasta apenas 
se o `__init__.py` estiver presente.
"""
