/* ==========================================================================
   SCRIPT: ALTERAÇÃO DE SENHA (FRONTEND)
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    
    function mostrarNotificacao(mensagem, sucesso = true) {
        const container = document.getElementById('toast-container');
        container.innerHTML = ''; 
        const toast = document.createElement('div');
        
        const corBorda = sucesso ? 'border-purple-500' : 'border-red-500';
        const corIcone = sucesso ? 'text-purple-500' : 'text-red-500';
        const bgIcone = sucesso ? 'bg-purple-100' : 'bg-red-100';
        const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';
        
        toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100] relative z-10`;
        toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone} relative z-10">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm relative z-10">${mensagem}</p></div>`;
        container.appendChild(toast);
        
        setTimeout(() => { toast.classList.remove('translate-x-full', 'opacity-0'); toast.classList.add('translate-x-0', 'opacity-100'); }, 10);
        
        const duracao = sucesso ? 7000 : 4000;
        
        setTimeout(() => { 
            toast.classList.remove('translate-x-0', 'opacity-100'); 
            toast.classList.add('translate-x-full', 'opacity-0'); 
            setTimeout(() => toast.remove(), 500); 
        }, duracao);
    }

    const formSenha = document.getElementById('formAlterarSenha');
    const btnSalvarSenha = document.getElementById('btnSalvarNovaSenha');
    const inputNovaSenha = document.getElementById('nova_senha');
    
    const boxDicaSenha = document.getElementById('box_dica_senha');
    const dicaSenhaText = document.getElementById('senha_dica');

    // --- Validação Inteligente e Específica ---
    inputNovaSenha.addEventListener('input', function() {
        const senha = this.value;
        dicaSenhaText.classList.remove('hidden'); // Mostra a área de feedback
        
        if (senha.length === 0) {
            boxDicaSenha.className = "bg-gray-50 rounded-xl p-4 mt-4 border border-gray-200/80 transition-colors duration-300 relative z-10";
            dicaSenhaText.className = "text-[12px] text-gray-500 font-medium pt-2 border-t border-gray-200/80";
            dicaSenhaText.innerHTML = "Comece a digitar para validar...";
            return;
        }

        // Array para guardar o que está faltando
        let faltam = [];
        if (senha.length < 8) faltam.push("atingir 8 caracteres");
        if (!/[A-Z]/.test(senha)) faltam.push("1 letra maiúscula");
        if (!/[0-9]/.test(senha)) faltam.push("1 número");
        if (!/[\W_]/.test(senha)) faltam.push("1 caractere especial");

        if (faltam.length === 0) {
            // Sucesso Total
            boxDicaSenha.className = "bg-green-50/50 rounded-xl p-4 mt-4 border border-green-300/80 transition-colors duration-300 relative z-10";
            dicaSenhaText.className = "text-[13px] text-green-700 font-bold flex items-center pt-2 border-t border-green-200/80";
            dicaSenhaText.innerHTML = '<i class="fa-solid fa-check-circle mr-2 text-lg"></i> Excelente! Senha forte e dentro dos padrões.';
        } else {
            // Faltam Requisitos
            boxDicaSenha.className = "bg-red-50/50 rounded-xl p-4 mt-4 border border-red-200/80 transition-colors duration-300 relative z-10";
            dicaSenhaText.className = "text-[13px] text-red-600 font-semibold pt-2 border-t border-red-200/80 flex flex-col";
            dicaSenhaText.innerHTML = `<span class="flex items-center mb-1"><i class="fa-solid fa-triangle-exclamation mr-2"></i> Ainda falta:</span> <span class="ml-6 text-red-500 font-medium">${faltam.join(', ')}.</span>`;
        }
    });

    // --- Submissão do Formulário ---
    btnSalvarSenha.onclick = async function(e) {
        e.preventDefault();
        
        const atual = document.getElementById('senha_atual').value;
        const nova = inputNovaSenha.value;
        const confirma = document.getElementById('confirma_senha').value;
        
        if(!atual || !nova || !confirma) { mostrarNotificacao("Preencha todos os campos do formulário.", false); return; }
        if(nova !== confirma) { mostrarNotificacao("A nova senha e a confirmação não batem.", false); return; }
        
        const regexForte = /^(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$/;
        if (!regexForte.test(nova)) { mostrarNotificacao("Resolva as pendências indicadas na caixa vermelha.", false); return; }
        
        btnSalvarSenha.disabled = true;
        btnSalvarSenha.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Processando...';
        
        try {
            const formData = new FormData(formSenha);
            const token = document.querySelector('[name=csrfmiddlewaretoken]').value;

            const response = await fetch(URL_API_ALTERAR_SENHA, { 
                method: 'POST', 
                headers: { 'X-CSRFToken': token },
                body: formData 
            });
            
            const dados = await response.json();
            
            if (dados.sucesso) { 
                formSenha.reset(); 
                mostrarNotificacao(dados.mensagem, true); 
                
                // Transforma a caixa azul de aviso na contagem regressiva
                let tempoRestante = 10;
                const boxWarning = document.getElementById('box_logout_warning');
                const textWarning = document.getElementById('logout_warning_text');

                boxWarning.className = "mt-4 bg-orange-100 border border-orange-300 text-orange-800 px-4 py-3 rounded-xl text-[14px] font-extrabold flex items-center transition-all duration-300 shadow-md";
                
                const timer = setInterval(() => {
                    tempoRestante--;
                    textWarning.innerHTML = `<i class="fa-solid fa-hourglass-half fa-spin mr-2"></i> Redirecionando para o login em ${tempoRestante}s...`;
                    
                    if (tempoRestante <= 0) {
                        clearInterval(timer);
                        window.location.href = URL_LOGOUT_ACAO;
                    }
                }, 1000);

            } else { 
                mostrarNotificacao(dados.mensagem, false); 
                btnSalvarSenha.disabled = false; 
                btnSalvarSenha.innerHTML = '<i class="fa-solid fa-floppy-disk mr-2"></i> Salvar Nova Senha'; 
            }
        } catch (erro) { 
            mostrarNotificacao("Falha de comunicação com o servidor.", false); 
            btnSalvarSenha.disabled = false; 
            btnSalvarSenha.innerHTML = '<i class="fa-solid fa-floppy-disk mr-2"></i> Salvar Nova Senha'; 
        }
    };
});