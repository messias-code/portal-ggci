"""
=== ARQUIVO: apps/automacoes/recalculo_bolsas/models.py ===
Propósito: Persistência do ciclo de vida de um recálculo de bolsas.
Dependências Principais: django.db.models
"""

from django.db import models


class ProcessamentoRecalculoBolsas(models.Model):
    """
    O QUE FAZ: Registra cada execução do recálculo (status, progresso, log e artefato gerado).
    POR QUÊ EXISTE: O recálculo é assíncrono — o front consulta esta tabela via polling
                    para desenhar barra de progresso e console, sem manter conexão aberta.
    COMO FUNCIONA: Espelha o contrato já consolidado em `analise_ia` e `enquadramento_cursos`,
                   para que o JS de acompanhamento siga o mesmo formato de resposta.
    """

    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EXTRAINDO', 'Extraindo Beneficiários'),
        ('RECALCULANDO', 'Recalculando Bolsas'),
        ('AUDITANDO', 'Auditando Divergências'),
        ('CONCLUIDO', 'Concluído'),
        ('FALHA', 'Falha'),
    ]

    data_inicio = models.DateTimeField(auto_now_add=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    progresso = models.IntegerField(default=0)
    log = models.TextField(blank=True, default='')
    arquivo_resultado = models.CharField(max_length=255, blank=True, null=True)
    configuracoes = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"Recálculo #{self.id} - {self.get_status_display()}"
