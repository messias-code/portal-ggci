from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    # Força a criação da chave de sessão caso ela ainda não exista
    if not request.session.session_key:
        request.session.save()
    
    # Atualiza o session_key do usuário para o login mais recente
    user.session_key = request.session.session_key
    user.save(update_fields=['session_key'])
