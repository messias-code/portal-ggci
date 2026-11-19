/*
 * Propósito: Atender os cliques que antes ficavam em onclick="..." no HTML.
 *
 * POR QUE EXISTE: a Content Security Policy do portal (SECURE_CSP em settings.py)
 * bloqueia todo JavaScript escrito dentro do HTML que não tenha o nonce da página,
 * e atributos onclick não podem levar nonce. É isso que impede um texto injetado
 * via innerHTML (nome de IES, mensagem do banco...) de virar código rodando.
 *
 * COMO USAR, no lugar de onclick="minhaFuncao(1, 'x')":
 *     data-clique="minhaFuncao" data-clique-args='[1, "x"]'
 * data-clique-args é JSON (aspas duplas). Dois valores especiais:
 *     "$evento"   → o evento do clique (o antigo `event`)
 *     "$elemento" → o elemento que tem o data-clique (o antigo `this`)
 * A função precisa ser global (function declarada no topo de um script comum).
 *
 * POR QUE NA FASE DE CAPTURA: o onclick rodava no próprio elemento, antes dos
 * listeners dos pais. Ouvindo o documento na captura, a função continua rodando
 * antes deles, e um stopPropagation() lá dentro segue impedindo que os pais
 * recebam o clique, como antes.
 */
(function () {
    function resolver(valor, evento, elemento) {
        if (valor === '$evento') return evento;
        if (valor === '$elemento') return elemento;
        return valor;
    }

    // Do elemento clicado para fora, como o onclick fazia ao borbulhar: um data-clique
    // dentro de outro dispara os dois, a menos que o de dentro chame stopPropagation().
    document.addEventListener('click', function (evento) {
        let elemento = evento.target.closest ? evento.target.closest('[data-clique]') : null;
        while (elemento) {
            const funcao = window[elemento.dataset.clique];
            if (typeof funcao === 'function') {
                const args = elemento.dataset.cliqueArgs ? JSON.parse(elemento.dataset.cliqueArgs) : [];
                funcao.apply(elemento, args.map(function (a) { return resolver(a, evento, elemento); }));
            } else {
                console.error('data-clique sem função global:', elemento.dataset.clique);
            }
            if (evento.cancelBubble) break;
            elemento = elemento.parentElement ? elemento.parentElement.closest('[data-clique]') : null;
        }
    }, true);

    // Ações que antes eram trechos soltos de código no onclick.
    window.ggciOcultar = function (id) {
        document.getElementById(id).classList.add('hidden');
    };
    window.ggciLimparBusca = function (id) {
        const campo = document.getElementById(id);
        campo.value = '';
        campo.dispatchEvent(new Event('input'));
        campo.focus();
    };
})();
