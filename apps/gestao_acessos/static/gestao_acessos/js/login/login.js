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
document.getElementById('formLogin').addEventListener('submit', function(event) {
    // Intercepta e previne a ação padrão do navegador (que seria realizar um POST síncrono e recarregar a tela).
    // Isso nos permite gerenciar o ciclo de vida da requisição dinamicamente via AJAX.
    event.preventDefault(); 
    
    // Captura os valores dos campos de usuário e senha, removendo espaços em branco acidentais
    // em ambos os extremos usando o método .trim() (boa prática de prevenção de erros comuns de digitação).
    const usuario = document.getElementById('usuario').value.trim();
    const senha = document.getElementById('senha').value.trim();

    /* --------------------------------------------------------------------------
       1. CAMADA DE VALIDAÇÃO LOCAL (FRONTEND)
       --------------------------------------------------------------------------
       Valida a presença de dados nos campos obrigatórios antes do envio de rede.
       Isso otimiza o uso do servidor Django ao poupar requisições desnecessárias.
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
    } 
    /* --------------------------------------------------------------------------
       2. CAMADA DE ENVIO ASSÍNCRONO SEGURO (POST)
       -------------------------------------------------------------------------- */
    else {
        // Inicializa a variável para armazenar o token CSRF extraído da página.
        // O Django bloqueia qualquer requisição de alteração de estado (POST) sem esta assinatura de segurança.
        let csrfToken = '';
        const tokenElement = document.querySelector('input[name="csrfmiddlewaretoken"]');
        
        if (tokenElement) {
            csrfToken = tokenElement.value;
        } else {
            // Emite um alerta no console para fins de depuração caso a estrutura de template sofra alterações
            console.error("Token CSRF não encontrado na página!");
            mostrarNotificacao("Erro de segurança: Token ausente.");
            return; // Encerra a execução local imediatamente, prevenindo falha de Bad Request (403) no servidor
        }

        // Realiza o disparo da requisição HTTP POST assíncrona para a API do Django
        fetch('/api/verificar-login/', {
            method: 'POST', 
            headers: { 
                'Content-Type': 'application/json',
                // Define o token CSRF nos headers da requisição, autenticando a origem do payload
                'X-CSRFToken': CSRF_TOKEN 
            },
            // Serializa o payload contendo o usuário e senha como uma string JSON válida
            body: JSON.stringify({ usuario: usuario, senha: senha })
        })
        .then(resposta => {
            // Verifica o status de resposta do servidor. Se não for bem-sucedido (2xx),
            // dispara uma exceção para que o fluxo seja direcionado ao bloco .catch().
            if (!resposta.ok) {
                throw new Error(`HTTP error! status: ${resposta.status}`);
            }
            // Executa o parse da resposta de forma assíncrona, convertendo a string de resposta para JSON
            return resposta.json();
        })
        .then(dados => {
            // Trata o retorno configurado em apps/gestao_acessos/views.py (JsonResponse)
            if (dados.sucesso === true) {
                // Redireciona o usuário para o dashboard do sistema em caso de login bem-sucedido
                window.location.href = '/inicio/'; 
            } else {
                // Exibe no Toast a mensagem amigável enviada diretamente pela lógica de negócio do backend
                mostrarNotificacao(dados.mensagem);
            }
        })
        .catch(erro => {
            // Tratamento geral de falhas: problemas de rede, servidor fora do ar ou incompatibilidade de resposta
            mostrarNotificacao("Erro de conexão com o servidor.");
            console.error('Erro de requisição:', erro);
        });
    }
});


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