from django.db import models

class ProcessamentoDocIA(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EXTRAINDO', 'Extraindo Dados (Portal)'),
        ('TRATANDO', 'Aplicando Regras (GGCI)'),
        ('CONCLUIDO', 'Concluído'),
        ('FALHA', 'Falha'),
    ]
    
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    usuario_solicitante = models.CharField(max_length=150, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    progresso = models.IntegerField(default=0)
    log = models.TextField(blank=True, default='')

    # O que a tela pediu para esta execução: documentos, semestres por documento,
    # inscrições específicas e pares em atualização bruta. Vazio significa o escopo
    # completo, que é como a atualização sempre funcionou — ver `executar_doc_ia`.
    #
    # Fica no registro, e não em argumentos de linha de comando, porque o comando roda
    # desacoplado do request: guardado aqui, o histórico também responde "com que
    # configuração esta execução rodou", que é a primeira pergunta quando um número sai
    # diferente do esperado.
    configuracoes = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"DocIA #{self.id} - {self.get_status_display()}"
