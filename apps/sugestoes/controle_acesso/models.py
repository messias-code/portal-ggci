from django.db import models


class ProcessamentoControleAcesso(models.Model):
    """
    Uma execução do botão "Atualizar" do Controle de Acesso: a view cria o registro e o
    comando `executar_controle_acesso` grava nele o log e o progresso que a tela acompanha.
    Mesmo formato do `ProcessamentoDocIA`, sem o escopo configurável — aqui toda
    atualização traz o universo inteiro.
    """
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EXTRAINDO', 'Extraindo Dados (SIBU)'),
        ('CONCLUIDO', 'Concluído'),
        ('FALHA', 'Falha'),
    ]

    data_inicio = models.DateTimeField(auto_now_add=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    usuario_solicitante = models.CharField(max_length=150, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    progresso = models.IntegerField(default=0)
    log = models.TextField(blank=True, default='')

    def __str__(self):
        return f"ControleAcesso #{self.id} - {self.get_status_display()}"
