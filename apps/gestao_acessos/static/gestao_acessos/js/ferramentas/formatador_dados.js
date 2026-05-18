/* ==========================================================================
   SCRIPT: FORMATADOR DE DADOS
   Lógica de normalização de texto: capitalização, acentos, duplicatas e
   remoção de caracteres, replicando o comportamento do antigo app Dash.
   ========================================================================== */

document.addEventListener('turbo:load', () => {

    // -------------------------------------------------------------------------
    // NOTIFICAÇÕES (Toast)
    // -------------------------------------------------------------------------
    function mostrarNotificacao(mensagem, sucesso = true) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        const corBorda = sucesso ? 'border-pink-500' : 'border-red-500';
        const corIcone = sucesso ? 'text-pink-500' : 'text-red-500';
        const bgIcone  = sucesso ? 'bg-pink-100'   : 'bg-red-100';
        const iconeHtml = sucesso
            ? '<i class="fa-solid fa-check text-lg"></i>'
            : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';

        toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100]`;
        toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone}">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm">${mensagem}</p></div>`;
        container.appendChild(toast);

        setTimeout(() => { toast.classList.remove('translate-x-full', 'opacity-0'); toast.classList.add('translate-x-0', 'opacity-100'); }, 10);
        setTimeout(() => { toast.classList.remove('translate-x-0', 'opacity-100'); toast.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => toast.remove(), 500); }, 4000);
    }

    // -------------------------------------------------------------------------
    // ESTADO DAS OPÇÕES
    // -------------------------------------------------------------------------
    let opcoes = {
        case: 'none',       // none | upper | lower | title
        accent: 'keep',     // keep | remove
        duplicates: 'all',  // all | unique
    };

    // Helpers de grupo de botões toggle
    function setupToggleGroup(groupId, stateKey) {
        const btns = document.querySelectorAll(`#${groupId} .btn-option`);
        btns.forEach(btn => {
            btn.addEventListener('click', () => {
                btns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                opcoes[stateKey] = btn.dataset.val;
            });
        });
    }

    // Grupos simples (fora de #group-case)
    function setupTwoToggle(btn1Id, btn2Id, stateKey, val1, val2) {
        const b1 = document.getElementById(btn1Id);
        const b2 = document.getElementById(btn2Id);
        b1.addEventListener('click', () => { b1.classList.add('active'); b2.classList.remove('active'); opcoes[stateKey] = val1; });
        b2.addEventListener('click', () => { b2.classList.add('active'); b1.classList.remove('active'); opcoes[stateKey] = val2; });
    }

    setupToggleGroup('group-case', 'case');
    setupTwoToggle('opt-acc-keep',    'opt-acc-remove',  'accent',     'keep',   'remove');
    setupTwoToggle('opt-dup-all',     'opt-dup-unique',  'duplicates', 'all',    'unique');

    // -------------------------------------------------------------------------
    // REFERÊNCIAS DO DOM
    // -------------------------------------------------------------------------
    const inputDados     = document.getElementById('input-dados');
    const outputDados    = document.getElementById('output-dados');
    const badgeIn        = document.getElementById('badge-in');
    const badgeOut       = document.getElementById('badge-out');
    const badgeInCount   = document.getElementById('badge-in-count');
    const btnLimpar      = document.getElementById('btn-limpar');
    const btnProcessar   = document.getElementById('btn-processar');
    const btnCopiar      = document.getElementById('btn-copiar');
    const alertDup       = document.getElementById('alert-duplicatas');
    const conteudoDup    = document.getElementById('conteudo-duplicatas');
    const tituloDup      = document.getElementById('titulo-qtd-duplicatas');
    const btnFecharAlerta = document.getElementById('btn-fechar-alerta');
    const inputRmChars   = document.getElementById('input-rm-chars');

    // -------------------------------------------------------------------------
    // CONTAGEM AO DIGITAR
    // -------------------------------------------------------------------------
    inputDados.addEventListener('input', () => {
        const count = inputDados.value.split('\n').filter(l => l.trim() !== '').length;
        badgeIn.innerText = count + (count === 1 ? ' item' : ' itens');
    });

    // -------------------------------------------------------------------------
    // FECHAR ALERTA
    // -------------------------------------------------------------------------
    btnFecharAlerta.addEventListener('click', () => alertDup.classList.add('hidden'));

    // -------------------------------------------------------------------------
    // LIMPAR
    // -------------------------------------------------------------------------
    btnLimpar.addEventListener('click', () => {
        inputDados.value  = '';
        outputDados.value = '';
        badgeIn.innerText  = '0 itens';
        badgeOut.innerText = '0 itens';
        badgeInCount.classList.add('hidden');
        alertDup.classList.add('hidden');
        inputDados.focus();
    });

    // -------------------------------------------------------------------------
    // FUNÇÕES AUXILIARES DE NORMALIZAÇÃO
    // -------------------------------------------------------------------------
    function removerAcentos(texto) {
        return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    function aplicarCapitalizacao(texto, modo) {
        switch (modo) {
            case 'upper': return texto.toUpperCase();
            case 'lower': return texto.toLowerCase();
            case 'title': return texto.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
            default:      return texto;
        }
    }

    // -------------------------------------------------------------------------
    // PROCESSAR
    // -------------------------------------------------------------------------
    btnProcessar.addEventListener('click', () => {
        const raw = inputDados.value;
        const linhasOriginais = raw.split('\n').map(l => l.trim()).filter(l => l !== '');

        if (linhasOriginais.length === 0) {
            mostrarNotificacao('A área de dados está vazia!', false);
            return;
        }

        // Montar regex de remoção de caracteres
        let regexRm = null;
        const rmCharsRaw = inputRmChars.value;
        if (rmCharsRaw) {
            // Remove espaços do campo (usuário pode ter digitado "- . /")
            const semEspacos = rmCharsRaw.replace(/\s/g, '');
            if (semEspacos) {
                try {
                    // Escapa cada caractere individualmente para a classe regex
                    const escaped = semEspacos.split('').map(c => c.replace(/[-[\]{}()*+?.,\\^$|#]/g, '\\$&')).join('');
                    regexRm = new RegExp(`[${escaped}]`, 'g');
                } catch (e) {
                    mostrarNotificacao('Caracteres especiais inválidos no campo de remoção.', false);
                    return;
                }
            }
        }

        // Processar cada linha
        const processadas = linhasOriginais.map(item => {
            if (regexRm) item = item.replace(regexRm, '');
            if (opcoes.accent === 'remove') item = removerAcentos(item);
            item = aplicarCapitalizacao(item, opcoes.case);
            // Colapsa múltiplos espaços internos
            item = item.replace(/\s+/g, ' ').trim();
            return item;
        }).filter(i => i !== '');

        // Controle de duplicatas
        const duplicatasSet = new Set();
        const uniqueSet     = new Set();
        const seenSet       = new Set();

        processadas.forEach(item => {
            if (seenSet.has(item)) {
                duplicatasSet.add(item);
            } else {
                seenSet.add(item);
            }
        });

        const final = opcoes.duplicates === 'unique'
            ? processadas.filter((item, idx, arr) => arr.indexOf(item) === idx)
            : processadas;

        outputDados.value  = final.join('\n');
        badgeOut.innerText = final.length + (final.length === 1 ? ' item' : ' itens');

        // Badge da entrada
        badgeInCount.innerText = linhasOriginais.length + ' entrada';
        badgeInCount.classList.remove('hidden');

        // Alerta de duplicatas
        if (duplicatasSet.size > 0 && opcoes.duplicates === 'unique') {
            const qtd = duplicatasSet.size;
            tituloDup.innerText     = `${qtd} ${qtd === 1 ? 'Item Duplicado Removido' : 'Itens Duplicados Removidos'}`;
            conteudoDup.innerHTML   = Array.from(duplicatasSet).join(', ');
            alertDup.classList.remove('hidden');
        } else {
            alertDup.classList.add('hidden');
        }

        mostrarNotificacao('Dados normalizados com sucesso!');
    });

    // -------------------------------------------------------------------------
    // COPIAR
    // -------------------------------------------------------------------------
    btnCopiar.addEventListener('click', () => {
        if (!outputDados.value) return;
        navigator.clipboard.writeText(outputDados.value)
            .then(() => mostrarNotificacao('Conteúdo copiado para a área de transferência.'))
            .catch(() => mostrarNotificacao('Erro ao copiar o texto.', false));
    });
});
