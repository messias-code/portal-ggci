/**
 * ============================================================================
 * PORTAL GGCI — MOTOR DE TEMAS (GLOBAL)
 * ============================================================================
 * Responsável por decidir, persistir e aplicar o modo de exibição do portal.
 *
 * ARQUITETURA
 *   O modo ativo é escrito no atributo `data-tema` do elemento <html>, e todo o
 *   visual decorre dele via CSS (ver `static/css/tema.css`). Este script nunca
 *   manipula estilos diretamente — ele apenas mantém esse atributo correto.
 *
 * POR QUE ESTE ARQUIVO PRECISA SER CARREGADO DE FORMA SÍNCRONA NO <head>
 *   Sem `defer` e sem `async`, o navegador executa o script antes de pintar o
 *   primeiro pixel. É o que impede o "flash" do tema padrão aparecer por uma
 *   fração de segundo antes de trocar para o tema salvo pelo usuário.
 *
 * PERSISTÊNCIA E ALCANCE GLOBAL
 *   A escolha vai para o `localStorage`, que é compartilhado por toda a origem
 *   (mesmo domínio). Logo, o modo selecionado na tela de login vale para
 *   qualquer outra página do portal que carregue este script — inclusive depois
 *   do login, em outra sessão ou em outra aba.
 *
 * CONVIVÊNCIA COM O TURBO
 *   O Hotwired Turbo substitui o <body> a cada navegação, mas preserva o <html>.
 *   Duas decisões tornam o componente imune a isso:
 *     1. O clique é capturado por delegação em `document`, e não por um listener
 *        preso ao botão — o listener sobrevive à troca de <body>.
 *     2. O estado visual do seletor é derivado do CSS, então nada precisa ser
 *        re-renderizado à mão após a navegação.
 * ============================================================================
 */

(function () {
    'use strict';

    /** Chave única no localStorage. O prefixo evita colisão com outros sistemas. */
    var CHAVE = 'ggci:tema';

    /** Modos aceitos. Qualquer valor fora desta lista é tratado como inválido. */
    var TEMAS = ['claro', 'eleitoral'];

    /** Modo usado quando não há preferência salva ou o valor salvo é inválido. */
    var PADRAO = 'claro';

    /**
     * Lê a preferência persistida.
     *
     * O acesso ao localStorage é protegido porque navegadores em modo privado ou
     * com cookies de terceiros bloqueados lançam exceção só de tocar no objeto.
     * Nesse cenário o portal continua funcionando, apenas sem lembrar a escolha.
     *
     * @returns {string} um dos valores de TEMAS.
     */
    function lerPreferencia() {
        try {
            var salvo = window.localStorage.getItem(CHAVE);
            return TEMAS.indexOf(salvo) !== -1 ? salvo : PADRAO;
        } catch (erro) {
            return PADRAO;
        }
    }

    /**
     * Persiste a preferência. Falha silenciosamente pelos mesmos motivos acima:
     * não conseguir salvar não pode quebrar a troca de tema em si.
     *
     * @param {string} tema modo a ser gravado.
     */
    function salvarPreferencia(tema) {
        try {
            window.localStorage.setItem(CHAVE, tema);
        } catch (erro) {
            /* Sem persistência disponível: o tema vale só para esta página. */
        }
    }

    /**
     * Aplica o modo ao documento e avisa o restante da aplicação.
     *
     * O evento `ggci:tema` existe para que componentes que não conseguem ser
     * resolvidos por CSS (um gráfico em canvas, por exemplo) possam reagir à
     * troca sem precisar vigiar o DOM.
     *
     * @param {string} tema modo a ser aplicado.
     */
    function aplicar(tema) {
        document.documentElement.setAttribute('data-tema', tema);
        sincronizarAcessibilidade(tema);

        document.dispatchEvent(new CustomEvent('ggci:tema', {
            detail: { tema: tema }
        }));
    }

    /**
     * Atualiza o rótulo acessível dos botões de alternância.
     *
     * O ícone é resolvido inteiramente por CSS, mas leitores de tela não leem
     * CSS: sem um rótulo textual, o botão seria anunciado como um controle
     * anônimo. O texto descreve a AÇÃO do clique, não o estado atual — é o que
     * torna o controle compreensível sem enxergar o ícone.
     *
     * Roda em modo defensivo porque, na primeira execução (ainda dentro do
     * <head>), o botão nem existe no DOM.
     *
     * @param {string} tema modo atualmente ativo.
     */
    function sincronizarAcessibilidade(tema) {
        var escuroAtivo = tema === 'eleitoral';
        var rotulo = escuroAtivo
            ? 'Ativar modo padrão'
            : 'Ativar modo eleitoral';

        var botoes = document.querySelectorAll('[data-tema-toggle]');

        for (var i = 0; i < botoes.length; i++) {
            botoes[i].setAttribute('aria-label', rotulo);
            botoes[i].setAttribute('title', rotulo);
            /* `aria-pressed` comunica o estado ligado/desligado do modo escuro,
               complementando o rótulo, que fala da ação. */
            botoes[i].setAttribute('aria-pressed', escuroAtivo ? 'true' : 'false');
        }

        /* Suporte a telas que ainda usem o seletor de duas posições. */
        var opcoes = document.querySelectorAll('[data-tema-alvo]');

        for (var j = 0; j < opcoes.length; j++) {
            opcoes[j].setAttribute(
                'aria-checked',
                opcoes[j].getAttribute('data-tema-alvo') === tema ? 'true' : 'false'
            );
        }
    }

    /**
     * Troca para um modo específico, validando a entrada.
     * Exposto publicamente para uso em outras telas (menus, atalhos, etc).
     *
     * @param {string} tema modo desejado.
     */
    function definir(tema) {
        if (TEMAS.indexOf(tema) === -1) {
            return;
        }

        salvarPreferencia(tema);
        aplicar(tema);
    }

    /**
     * Alterna entre os dois modos disponíveis.
     *
     * @returns {string} o modo que passou a vigorar.
     */
    function alternar() {
        var proximo = lerPreferencia() === 'eleitoral' ? 'claro' : 'eleitoral';
        definir(proximo);
        return proximo;
    }

    /* ------------------------------------------------------------------------
       APLICAÇÃO IMEDIATA
       Executa ainda durante o parse do <head>, antes da primeira pintura.
       ------------------------------------------------------------------------ */
    aplicar(lerPreferencia());

    /**
     * Encontra o controle de tema que originou um evento.
     *
     * O `closest` só existe em Element — um evento sem foco em elemento algum
     * chega com `target` valendo o próprio `document`, e a checagem de tipo
     * evita um TypeError silencioso no console.
     *
     * @param {Event} evento evento capturado por delegação.
     * @returns {Element|null} o controle acionado, ou null.
     */
    function controleDoEvento(evento) {
        var alvo = evento.target;

        if (!alvo || typeof alvo.closest !== 'function') {
            return null;
        }

        return alvo.closest('[data-tema-toggle], [data-tema-alvo]');
    }

    /* ------------------------------------------------------------------------
       DELEGAÇÃO DE EVENTOS
       Um único listener em `document` atende a todos os controles de tema da
       página — presentes agora ou inseridos depois por Turbo/AJAX.

       Dois contratos são aceitos:
         [data-tema-toggle]         → alterna entre os modos (botão sol/lua)
         [data-tema-alvo="<modo>"]  → vai direto para um modo específico
       ------------------------------------------------------------------------ */
    document.addEventListener('click', function (evento) {
        var controle = controleDoEvento(evento);

        if (!controle) {
            return;
        }

        evento.preventDefault();

        if (controle.hasAttribute('data-tema-alvo')) {
            definir(controle.getAttribute('data-tema-alvo'));
            return;
        }

        alternar();
    });

    /* Ressincroniza o ARIA quando o DOM fica pronto e a cada navegação do Turbo,
       momentos em que o seletor pode ter acabado de entrar na página. */
    document.addEventListener('DOMContentLoaded', function () {
        sincronizarAcessibilidade(lerPreferencia());
    });

    document.addEventListener('turbo:load', function () {
        sincronizarAcessibilidade(lerPreferencia());
    });

    /* Propaga a troca feita em outra aba do portal, mantendo tudo coerente. */
    window.addEventListener('storage', function (evento) {
        if (evento.key === CHAVE) {
            aplicar(lerPreferencia());
        }
    });

    /* API pública para as demais telas do portal. */
    window.TemaGGCI = {
        obter: lerPreferencia,
        definir: definir,
        alternar: alternar,
        TEMAS: TEMAS
    };
})();
