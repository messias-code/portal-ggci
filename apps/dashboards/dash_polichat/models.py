from django.db import models

class ProcessamentoPolichat(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EXTRAINDO', 'Extraindo Dados (Polichat)'),
        ('TRATANDO', 'Tratando Dados (Pandas)'),
        ('CONCLUIDO', 'Concluído'),
        ('FALHA', 'Falha'),
    ]
    
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    usuario_solicitante = models.CharField(max_length=150, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    progresso = models.IntegerField(default=0)
    log = models.TextField(blank=True, default='')
    arquivo_resultado = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"Polichat #{self.id} - {self.get_status_display()}"
