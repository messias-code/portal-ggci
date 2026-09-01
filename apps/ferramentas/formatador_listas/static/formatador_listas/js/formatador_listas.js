/* ==========================================================================
   SCRIPT: FORMATADOR DE LISTAS
   ========================================================================== */

function initFormatadorListas() {
    // Evita inicialização duplicada
    if (document.getElementById('input-list').dataset.initialized) return;
    document.getElementById('input-list').dataset.initialized = 'true';

    function mostrarNotificacao(mensagem, sucesso = true) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        const corBorda = sucesso ? 'border-pink-500' : 'border-red-500';
        const corIcone = sucesso ? 'text-pink-500' : 'text-red-500';
        const bgIcone = sucesso ? 'bg-pink-100' : 'bg-red-100';
        const iconeHtml = sucesso ? '<i class="fa-solid fa-check text-lg"></i>' : '<i class="fa-solid fa-triangle-exclamation text-lg"></i>';

        toast.className = `bg-white border-l-4 ${corBorda} shadow-2xl rounded-r-xl p-5 mb-3 flex items-center space-x-4 transform transition-all duration-500 translate-x-full opacity-0 z-[100]`;
        toast.innerHTML = `<div class="flex-shrink-0 ${bgIcone} p-2 rounded-full w-10 h-10 flex items-center justify-center ${corIcone}">${iconeHtml}</div><div><p class="text-gray-800 font-semibold text-sm">${mensagem}</p></div>`;
        container.appendChild(toast);
        
        setTimeout(() => { toast.classList.remove('translate-x-full', 'opacity-0'); toast.classList.add('translate-x-0', 'opacity-100'); }, 10);
        setTimeout(() => { toast.classList.remove('translate-x-0', 'opacity-100'); toast.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => toast.remove(), 500); }, 4000);
    }

    const inputList = document.getElementById('input-list');
    const outputList = document.getElementById('output-list');
    const badgeIn = document.getElementById('badge-in');
    const badgeOut = document.getElementById('badge-out');
    const btnLimpar = document.getElementById('btn-limpar');
    const btnProcessar = document.getElementById('btn-processar');
    const btnCopiar = document.getElementById('btn-copiar');
    const alertDup = document.getElementById('alert-duplicatas');
    const conteudoDup = document.getElementById('conteudo-duplicatas');
    const tituloDup = document.getElementById('titulo-qtd-duplicatas');
    const btnFecharAlerta = document.getElementById('btn-fechar-alerta');
    const botoesSeparador = document.querySelectorAll('.fmt-sep');

    /*  SEPARADOR DA SAÍDA.

        A vírgula continua sendo o padrão — é o `IN ('A','B')` do SQL, para o qual esta
        ferramenta nasceu. Mas a mesma lista normalizada vira parâmetro de URL, chave
        composta e nome de arquivo, e cada um desses quer outro caractere.

        Guardado numa variável, e não lido do DOM a cada uso, porque quem responde por
        ele é o botão marcado: uma segunda leitura seria uma segunda verdade.  */
    let separador = ',';

    /** A saída é refeita a partir dos itens já normalizados, guardados aqui. */
    let itensNormalizados = [];

    const escreverSaida = () => {
        outputList.value = itensNormalizados.join(separador);
    };

    botoesSeparador.forEach((botao) => {
        botao.addEventListener('click', () => {
            separador = botao.dataset.sep;
            botoesSeparador.forEach((outro) =>
                outro.classList.toggle('fmt-sep--ativo', outro === botao));
            // Refaz a saída na hora: trocar o separador não é motivo para normalizar de
            // novo — os itens são os mesmos, só a cola entre eles muda.
            if (itensNormalizados.length > 0) escreverSaida();
        });
    });

    // Conta as linhas originais
    inputList.addEventListener('input', () => {
        const items = inputList.value.split(/[\n\s,;]+/).filter(i => i.trim() !== '');
        const count = items.length;
        badgeIn.innerText = count + (count === 1 ? ' item' : ' itens');
    });

    btnFecharAlerta.addEventListener('click', () => {
        alertDup.classList.add('hidden');
    });

    btnLimpar.addEventListener('click', () => {
        inputList.value = '';
        outputList.value = '';
        itensNormalizados = [];
        badgeIn.innerText = '0 itens';
        badgeOut.innerText = '0 itens';
        alertDup.classList.add('hidden');
        inputList.focus();
    });

    btnProcessar.addEventListener('click', () => {
        const lines = inputList.value.split(/[\n\s,;]+/).map(l => l.trim()).filter(l => l !== '');
        
        if (lines.length === 0) {
            mostrarNotificacao('A lista original está vazia.', false);
            return;
        }

        const uniqueSet = new Set();
        const duplicatesSet = new Set();

        // Faz o Check
        lines.forEach(line => {
            if (uniqueSet.has(line)) {
                duplicatesSet.add(line);
            } else {
                uniqueSet.add(line);
            }
        });

        const uniqueArray = Array.from(uniqueSet);

        // Formata os dados com o separador escolhido
        itensNormalizados = uniqueArray;
        escreverSaida();
        badgeOut.innerText = uniqueArray.length + (uniqueArray.length === 1 ? ' item' : ' itens');

        // Mostra duplicadas
        if (duplicatesSet.size > 0) {
            tituloDup.innerText = `${duplicatesSet.size} ${duplicatesSet.size === 1 ? 'Item Duplicado Removido' : 'Itens Duplicados Removidos'}`;
            conteudoDup.innerHTML = Array.from(duplicatesSet).join(', ');
            alertDup.classList.remove('hidden');
        } else {
            alertDup.classList.add('hidden');
        }

        mostrarNotificacao('Dados normalizados com sucesso!');
    });

    // Copiar para a prancheta
    btnCopiar.addEventListener('click', () => {
        if (!outputList.value) return;
        
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(outputList.value).then(() => {
                mostrarNotificacao('Conteúdo copiado para a área de transferência.');
            }).catch(err => {
                mostrarNotificacao('Erro ao copiar o texto.', false);
            });
        } else {
            // Fallback para ambientes de desenvolvimento (HTTP)
            outputList.select();
            try {
                document.execCommand('copy');
                mostrarNotificacao('Conteúdo copiado para a área de transferência.');
            } catch (err) {
                mostrarNotificacao('Erro ao copiar o texto.', false);
            }
            window.getSelection().removeAllRanges();
        }
    });
}

document.addEventListener('DOMContentLoaded', initFormatadorListas);
document.addEventListener('turbo:load', initFormatadorListas);