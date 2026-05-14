/* ==========================================================================
   LÓGICA DE AUTENTICAÇÃO (LOGIN)
   Este arquivo intercepta o formulário de login (templates/login/index.html),
   valida os campos localmente e envia a requisição segura para o backend Django
   (apps/gestao_acessos/views.py -> def verificar_login).
   ========================================================================== */

document.getElementById('formLogin').addEventListener('submit', function(event) {
    // Impede que a página recarregue ao clicar no botão "Acessar"
    event.preventDefault(); 
    
    // Captura e limpa os espaços em branco dos dados inseridos no HTML
    const usuario = document.getElementById('usuario').value.trim();
    const senha = document.getElementById('senha').value.trim();

    /* --------------------------------------------------------------------------
       1. VALIDAÇÃO FRONTEND
       -------------------------------------------------------------------------- */
    if (!usuario || !senha) {
        let mensagem = "Por favor, preencha todos os campos.";
        if (!usuario) mensagem = "Ei! O campo Usuário é obrigatório.";
        else if (!senha) mensagem = "Não se esqueça da sua Senha.";

        // Exibe o balão de erro no canto da tela e interrompe o envio
        mostrarNotificacao(mensagem);
    } 
    /* --------------------------------------------------------------------------
       2. ENVIO SEGURO PARA A API DO DJANGO
       -------------------------------------------------------------------------- */
    else {
        // Captura de segurança do Token CSRF gerado pela tag {% csrf_token %} no HTML.
        // O Django bloqueia requisições POST se este token não estiver presente.
        let csrfToken = '';
        const tokenElement = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenElement) {
            csrfToken = tokenElement.value;
        } else {
            console.error("Token CSRF não encontrado na página!");
            mostrarNotificacao("Erro de segurança: Token ausente.");
            return; // Interrompe a requisição para evitar erro 403 Forbidden do Django
        }

        // Requisição AJAX para a rota mapeada no portal_ggci/urls.py
        fetch('/api/verificar-login/', {
            method: 'POST', 
            headers: { 
                'Content-Type': 'application/json',
                // A variável CSRF_TOKEN é declarada diretamente no final de templates/login/index.html
                'X-CSRFToken': CSRF_TOKEN 
            },
            body: JSON.stringify({ usuario: usuario, senha: senha })
        })
        .then(resposta => {
            // Checa se o Django não estourou um erro grave (como 500 Internal Server Error)
            if (!resposta.ok) {
                throw new Error(`HTTP error! status: ${resposta.status}`);
            }
            return resposta.json();
        })
        .then(dados => {
            // Processa o dicionário JsonResponse() enviado pelo views.py
            if (dados.sucesso === true) {
                // Redireciona o usuário para o painel principal caso a senha (Argon2) bata
                window.location.href = '/inicio/'; 
            } else {
                // Retorna a mensagem de erro formatada pelo views.py (ex: "Usuário não encontrado")
                mostrarNotificacao(dados.mensagem);
            }
        })
        .catch(erro => {
            // Cai aqui se o servidor cair, a internet do usuário falhar ou houver falha de CORS
            mostrarNotificacao("Erro de conexão com o servidor.");
            console.error('Erro de requisição:', erro);
        });
    }
});


/* ==========================================================================
   FUNÇÃO DE NOTIFICAÇÃO (TOASTS DE TELA)
   Gera caixas de mensagem dinâmicas no elemento id="toast-container" 
   (localizado no topo do body do login/index.html).
   ========================================================================== */
function mostrarNotificacao(mensagem) {
    const container = document.getElementById('toast-container');
    
    // Limpa notificações antigas para evitar empilhamento excessivo
    container.innerHTML = '';
    
    // Criação do elemento visual do Toast usando Tailwind classes
    const toast = document.createElement('div');
    toast.className = 'bg-white border-l-4 border-pink-500 shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0';
    toast.innerHTML = `
        <div class="flex-shrink-0 bg-pink-100 p-2 rounded-full">
            <svg class="w-6 h-6 text-pink-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
        </div>
        <div><p class="text-gray-800 font-semibold text-lg">${mensagem}</p></div>
    `;

    container.appendChild(toast);
    
    // Gatilho de animação de entrada (deslizando da direita para a esquerda)
    setTimeout(() => {
        toast.classList.remove('translate-x-full', 'opacity-0');
        toast.classList.add('translate-x-0', 'opacity-100');
    }, 10);

    // Destruição automática após 4 segundos
    setTimeout(() => {
        toast.classList.remove('translate-x-0', 'opacity-100');
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => toast.remove(), 500); // Remove o elemento do DOM após a animação de saída terminar
    }, 4000);
}