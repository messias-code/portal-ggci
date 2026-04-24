from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

class UsuarioManager(BaseUserManager):
    def create_user(self, usuario, password=None, **extra_fields):
        if not usuario:
            raise ValueError('O nome de usuário é obrigatório')
        user = self.model(usuario=usuario, **extra_fields)
        # O Django já sabe que tem que usar Argon2 por causa do settings.py!
        user.set_password(password) 
        user.save(using=self._db)
        return user

    def create_superuser(self, usuario, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('perfil', 'administrador')
        return self.create_user(usuario, password, **extra_fields)

class Usuario(AbstractBaseUser):
    PERFIS = [
        ('administrador', 'Administrador'),
        ('comum', 'Comum'),
        ('consulta', 'Consulta'), # <-- ADICIONE ESTA LINHA AQUI!
    ]
    
    nome = models.CharField(max_length=100)
    usuario = models.CharField(max_length=100, unique=True)
    perfil = models.CharField(max_length=20, choices=PERFIS, default='comum')
    
    # Suas permissões customizadas
    p_ferramentas = models.BooleanField(default=False)
    p_formatador_listas = models.BooleanField(default=False) 
    p_formatador_dados = models.BooleanField(default=False)  
    
    p_automacoes = models.BooleanField(default=False)
    p_analise_ia = models.BooleanField(default=False)
    
    p_documentacoes = models.BooleanField(default=False)

    # Controles internos do Django
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = 'usuario' 
    REQUIRED_FIELDS = ['nome']

    class Meta:
        db_table = 'usuarios' 

    def __str__(self):
        return self.usuario

    # Requisitos do Django para acessar o painel administrativo
    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser