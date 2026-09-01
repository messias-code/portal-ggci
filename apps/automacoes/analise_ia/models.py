"""
=== ARQUIVO: apps/automacoes/analise_ia/models.py ===
Propósito: Define as estruturas de dados (Tabelas do Banco) para o app de Análise IA.
Autor: N/A
Dependências Principais: django.db.models
"""
from django.db import models

class ProcessamentoAnaliseIA(models.Model):
    """
    O QUE FAZ: Tabela que armazena o ciclo de vida de uma execução do motor de IA.
    POR QUÊ EXISTE: Como o processamento ocorre em background (via threads/subprocessos),
    precisamos de um estado persistente no banco para que o frontend saiba o progresso,
    leia os logs em tempo real e saiba onde está o arquivo gerado.
    
    COMO FUNCIONA: 
    - `progresso`: Atualizado em tempo real pelo LogCapture (sys.stdout).
    - `log`: Acumula a saída textual para ser lida via Long Polling no Front.
    - `configuracoes`: Salva JSON com os filtros selecionados (Anos, Semestres, etc).
    """
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EXTRAINDO', 'Extraindo Dados (Playwright)'),
        ('CONSOLIDANDO', 'Consolidando Planilhas'),
        ('CRUZANDO', 'Cruzando Dados (GGCI)'),
        ('CONCLUIDO', 'Concluído'),
        ('FALHA', 'Falha'),
    ]
    
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    progresso = models.IntegerField(default=0)
    
    # // Campo crítico: Injetado dinamicamente pelos prints do script background
    log = models.TextField(blank=True, default='') 
    
    arquivo_resultado = models.CharField(max_length=255, blank=True, null=True)
    configuracoes = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return f"Processamento #{self.id} - {self.get_status_display()}"
