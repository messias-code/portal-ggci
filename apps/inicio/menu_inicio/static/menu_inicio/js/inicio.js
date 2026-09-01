/* ==========================================================================
   SISTEMA DE NOTIFICAÇÕES (TOASTS) - PAINEL INICIAL
   Gera caixas de alerta dinâmicas no canto superior direito da tela.
   
   Onde encontrar o container no HTML: 
   Procure por <div id="toast-container"> no arquivo 'templates/inicio/index.html'.
   
   Uso: mostrarNotificacao("Sua mensagem aqui", true/false)
   - true (padrão): Exibe um card roxo/verde de sucesso.
   - false: Exibe um card vermelho de erro/alerta (ex: botão de acesso negado).
   ========================================================================== */

function mostrarNotificacao(mensagem, sucesso = true) {
    // 1. PREPARAÇÃO DO CONTAINER
    const container = document.getElementById('toast-container');
    
    // Limpa qualquer notificação anterior da tela para não empilhar vários cards
    container.innerHTML = ''; 
    
    // 2. CONFIGURAÇÃO DINÂMICA DE CORES E ÍCONES
    // Se 'sucesso' for true, aplica a paleta Roxa (padrão do portal). 
    // Se for false, aplica a paleta Vermelha de erro.
    const toast = document.createElement('div');
    const corBorda = sucesso ? 'border-purple-500' : 'border-red-500';
    const corIcone = sucesso ? 'text-purple-500' : 'text-red-500';
    const bgIcone = sucesso ? 'bg-purple-100' : 'bg-red-100';
    
    // Define o ícone do FontAwesome: Check (sucesso) ou Triângulo de Alerta (erro)
    const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';

    // 3. MONTAGEM DO HTML DO TOAST
    // Utiliza as classes do Tailwind + as variáveis de cor definidas acima
    // Inicialmente o card nasce invisível (opacity-0) e fora da tela (translate-x-full)
    toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100]`;
    toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone}">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm">${mensagem}</p></div>`;
    
    // Injeta o elemento pronto no HTML da página
    container.appendChild(toast);
    
    // 4. CONTROLE DE ANIMAÇÕES
    // Pequeno atraso de 10ms apenas para o navegador registrar o elemento antes de animar a entrada
    setTimeout(() => { 
        toast.classList.remove('translate-x-full', 'opacity-0'); 
        toast.classList.add('translate-x-0', 'opacity-100'); 
    }, 10);
    
    // Aguarda 4 segundos com a mensagem na tela, faz a animação de saída e destrói o elemento
    setTimeout(() => { 
        toast.classList.remove('translate-x-0', 'opacity-100'); 
        toast.classList.add('translate-x-full', 'opacity-0'); 
        // Destrói a div do HTML após 500ms (tempo exato da duração da animação de saída)
        setTimeout(() => toast.remove(), 500); 
    }, 4000);
}