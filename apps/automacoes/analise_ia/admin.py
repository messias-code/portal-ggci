"""
=== ARQUIVO: apps/automacoes/analise_ia/admin.py ===
Propósito: Configuração da interface administrativa do Django para o app analise_ia.
Autor: N/A
Dependências Principais: django.contrib.admin
"""
from django.contrib import admin
from .models import ProcessamentoAnaliseIA

# ---------------------------------------------------------
# O QUE FAZ: Registra o modelo ProcessamentoAnaliseIA no Admin.
# POR QUÊ EXISTE: Permite que administradores gerenciem (CRUD) os processos 
# manuais caso ocorra alguma falha grave no banco.
# ---------------------------------------------------------
@admin.register(ProcessamentoAnaliseIA)
class ProcessamentoAnaliseIAAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'progresso', 'data_inicio', 'data_fim')
    list_filter = ('status',)
    readonly_fields = ('data_inicio',)
