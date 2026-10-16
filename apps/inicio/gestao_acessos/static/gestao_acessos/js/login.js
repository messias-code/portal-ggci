/* ==========================================================================
   LÓGICA DE AUTENTICAÇÃO E INTERATIVIDADE DO FRONTEND (LOGIN)
   --------------------------------------------------------------------------
   Este script gerencia todo o fluxo do formulário de autenticação:
   1. Interceptação do envio padrão do formulário HTML.
   2. Limpeza (trimming) e validação local preliminar dos campos de entrada.
   3. Resgate e validação preventiva do Token CSRF (essencial para o Django).
   4. Comunicação assíncrona segura via AJAX (Fetch API) com o backend Django.
   5. Tratamento de respostas de sucesso/erro e manipulação de Toasts dinâmicos.
   
   Todos os comportamentos originais foram rigorosamente mantidos.
   ========================================================================== */

/**
 * Escuta e manipula o evento de submissão do formulário de login.
 * Garante que a validação de integridade frontend e a requisição Fetch 
 * aconteçam de forma coordenada e sem recarregamento da página.
 */
function initLogin() {
    const form = document.getElementById('formLogin');
    if (!form || form.dataset.loginInitialized === 'true') {
        return;
    }
    form.dataset.loginInitialized = 'true';

    form.addEventListener('submit', function(event) {
        // Intercepta e previne a ação padrão do navegador (que seria realizar um POST síncrono e recarregar a tela).
        // Isso nos permite gerenciar o ciclo de vida da requisição dinamicamente via AJAX.
        event.preventDefault(); 
        
        // Captura os valores dos campos de usuário e senha, removendo espaços em branco acidentais
        const usuarioInput = document.getElementById('usuario');
        const senhaInput = document.getElementById('senha');
        const usuario = usuarioInput ? usuarioInput.value.trim() : '';
        const senha = senhaInput ? senhaInput.value.trim() : '';

        /* --------------------------------------------------------------------------
           1. CAMADA DE VALIDAÇÃO LOCAL (FRONTEND)
           -------------------------------------------------------------------------- */
        if (!usuario || !senha) {
            let mensagem = "Por favor, preencha todos os campos.";
            if (!usuario) {
                mensagem = "Ei! O campo Usuário é obrigatório.";
            } else if (!senha) {
                mensagem = "Não se esqueça da sua Senha.";
            }

            // Renderiza o Toast na tela com a mensagem de alerta correspondente
            mostrarNotificacao(mensagem);
            return;
        }

        /* --------------------------------------------------------------------------
           2. CAMADA DE ENVIO ASSÍNCRONO SEGURO (POST)
           -------------------------------------------------------------------------- */
        let csrfToken = '';
        const tokenElement = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenElement && tokenElement.value) {
            csrfToken = tokenElement.value;
        } else if (typeof CSRF_TOKEN !== 'undefined' && CSRF_TOKEN) {
            csrfToken = CSRF_TOKEN;
        }

        if (!csrfToken) {
            console.error("Token CSRF não encontrado na página!");
            mostrarNotificacao("Erro de segurança: Token ausente.");
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        let btnTextoOriginal = '';
        if (submitBtn) {
            btnTextoOriginal = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.7';
            submitBtn.style.cursor = 'wait';
        }

        function restaurarBotao() {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.style.opacity = '';
                submitBtn.style.cursor = '';
                submitBtn.innerHTML = btnTextoOriginal;
            }
        }

        // Realiza o disparo da requisição HTTP POST assíncrona para a API do Django
        fetch('/api/verificar-login/', {
            method: 'POST', 
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken 
            },
            body: JSON.stringify({ usuario: usuario, senha: senha })
        })
        .then(resposta => {
            if (!resposta.ok) {
                throw new Error(`HTTP error! status: ${resposta.status}`);
            }
            return resposta.json();
        })
        .then(dados => {
            if (dados.sucesso === true) {
                window.location.href = '/inicio/'; 
            } else {
                restaurarBotao();
                mostrarNotificacao(dados.mensagem);
            }
        })
        .catch(erro => {
            restaurarBotao();
            mostrarNotificacao("Erro de conexão com o servidor.");
            console.error('Erro de requisição:', erro);
        });
    });
}

// Suporte para carregamento padrão, Turbo e SPA
document.addEventListener('DOMContentLoaded', initLogin);
document.addEventListener('turbo:load', initLogin);
if (document.readyState === 'interactive' || document.readyState === 'complete') {
    initLogin();
}


/* ==========================================================================
   FUNÇÃO DE NOTIFICAÇÃO (TOASTS DINÂMICOS NA TELA)
   --------------------------------------------------------------------------
   Arquitetura de renderização leve focada em performance e fluidez visual.
   Responsável por criar, animar e limpar automaticamente alertas visuais.
   ========================================================================== */
function mostrarNotificacao(mensagem) {
    // Captura o contêiner fixo na viewport onde as notificações serão injetadas
    const container = document.getElementById('toast-container');
    
    // Reseta o contêiner interno limpando mensagens antigas para evitar duplicidade ou excesso na tela
    container.innerHTML = '';
    
    // Cria dinamicamente o elemento HTML do Toast com estilização baseada em Tailwind CSS.
    // Utiliza aceleração de hardware via transformações CSS 3D/translate para animações de 60fps constantes.
    const toast = document.createElement('div');
    toast.className = 'bg-white border-l-4 border-pink-500 shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-[transform,opacity] duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] translate-x-full opacity-0 will-change-transform';
    toast.innerHTML = `
        <div class="flex-shrink-0 bg-pink-100 p-2 rounded-full">
            <svg class="w-6 h-6 text-pink-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
        </div>
        <div><p class="text-gray-800 font-semibold text-lg">${mensagem}</p></div>
    `;

    // Injeta fisicamente o nó recém-criado na árvore do DOM
    container.appendChild(toast);
    
    /**
     * Padrão Double requestAnimationFrame (rAF):
     * Garante que o navegador execute o primeiro ciclo de layout (adicionando o elemento com translate-x-full)
     * antes de remover a classe inicial e disparar a transição.
     * Sem este padrão de dois frames consecutivos, o motor de renderização do browser pode otimizar agrupando
     * (batching) a inserção e a remoção de classes de animação, pulando a transição visual do efeito de slide.
     */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.remove('translate-x-full', 'opacity-0');
            toast.classList.add('translate-x-0', 'opacity-100');
        });
    });

    /**
     * Ciclo de Vida do Alerta (Autolimpante/Autodestruição):
     * Permanece visível por 4 segundos, realiza a transição de saída para fora da tela e
     * limpa o nó correspondente da árvore do DOM para evitar vazamento de memória (memory leaks).
     */
    setTimeout(() => {
        // Dispara a animação visual de saída
        toast.classList.remove('translate-x-0', 'opacity-100');
        toast.classList.add('translate-x-full', 'opacity-0');
        
        // Remove fisicamente do DOM após o encerramento da animação de saída de 500ms
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}