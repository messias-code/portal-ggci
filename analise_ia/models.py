from django.db import models

class ProcessamentoAnaliseIA(models.Model):
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
    log = models.TextField(blank=True, default='') # Aqui vamos injetar os prints dos seus scripts
    arquivo_resultado = models.CharField(max_length=255, blank=True, null=True)
    configuracoes = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return f"Processamento #{self.id} - {self.get_status_display()}"