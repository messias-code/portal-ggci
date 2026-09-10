/* ==========================================================================
   DOCUMENTOS IA — AS DUAS ABAS
   ==========================================================================
   O QUE ESTE ARQUIVO É: o dono da troca entre "Envios & Pendências" e
   "Análise IA", e a memória de onde a pessoa estava.

   AS DUAS ABAS SÃO A MESMA TELA. Mesma URL, mesma base, mesma extração. Antes
   eram duas rotas (`/` e `/relatorio-ies/`) e dois `<a href>`, e isso custava
   caro em três lugares:

     1. Trocar de aba recarregava a página inteira — e uma atualização em curso
        morria no caminho, porque a guarda de `pagehide` em
        `dash_documentos_ia.js` não avisava: ela mandava PARAR o processo.
     2. Voltar para a aba de trabalho exigia refazer o caminho a cada entrada,
        porque o menu de Dashboards aponta sempre para a primeira.
     3. Havia dois templates com o mesmo cabeçalho, a mesma barra e a mesma
        casca, que envelheciam separados.

   Agora é uma tela só com dois painéis, e trocar de aba não vai ao servidor.

   POR QUE NO `<head>` E SÍNCRONO: quem decide qual painel aparece é o atributo
   `data-docia-aba` no `<html>`, lido pelo CSS (ver `dash_documentos_ia.css`).
   Escrito aqui, antes da primeira pintura, a aba certa já nasce visível. No fim
   do corpo, quem trabalha na Análise IA veria a aba de Envios montar inteira
   para só então sumir.

   `localStorage` pode estourar (janela anônima, cookies bloqueados, dados do
   site limpos). Tudo aqui é `try/catch` e, sem ele, a tela simplesmente volta a
   se comportar como antes — abre na primeira aba.
   ========================================================================== */

(function () {
    'use strict';

    var CHAVE_ABA = 'docia:aba';
    var CHAVE_MODO = 'docia:modo:';
    var ABAS = ['envios', 'analise'];

    var guardar = function (chave, valor) {
        try {
            window.localStorage.setItem(chave, valor);
        } catch (erro) {
            /* sem armazenamento: a tela funciona, só não lembra */
        }
    };

    var ler = function (chave) {
        try {
            return window.localStorage.getItem(chave);
        } catch (erro) {
            return null;
        }
    };

    var valida = function (nome) {
        return ABAS.indexOf(nome) >= 0 ? nome : null;
    };

    /* ----------------------------------------------------------------------
       A ABA, ANTES DA PRIMEIRA PINTURA
       ---------------------------------------------------------------------- */

    var abaInicial = valida(ler(CHAVE_ABA)) || 'envios';
    document.documentElement.setAttribute('data-docia-aba', abaInicial);

    /* ----------------------------------------------------------------------
       O MODO DE VISUALIZAÇÃO, por aba
       ----------------------------------------------------------------------
       Guardado POR ABA: "beneficiarios" só existe em Envios & Pendências e
       "performance" só na Análise IA. Numa chave só, a lembrança de uma aba
       chegaria na outra como um valor que ela não conhece.  */

    window.dociaAbaAtiva = function () {
        return document.documentElement.getAttribute('data-docia-aba') || 'envios';
    };

    window.dociaLembrarModo = function (valor) {
        if (valor) guardar(CHAVE_MODO + window.dociaAbaAtiva(), valor);
    };

    /**
     * O modo lembrado desta aba, ou `padrao` se não houver.
     * `permitidos` é a lista de valores que a tela aceita — sem ela, um valor
     * velho (de uma versão em que o modo se chamava outra coisa) marcaria um
     * rádio que não existe mais e a tela abriria com nenhum modo aceso.
     */
    window.dociaModoLembrado = function (padrao, permitidos) {
        var valor = ler(CHAVE_MODO + window.dociaAbaAtiva());
        if (!valor) return padrao;
        if (permitidos && permitidos.indexOf(valor) < 0) return padrao;
        return valor;
    };

    /* ----------------------------------------------------------------------
       A TROCA DE ABA
       ----------------------------------------------------------------------
       O CSS já mostra e esconde os painéis a partir de `data-docia-aba`; o que
       sobra aqui é acender a pastilha certa e AVISAR.

       O aviso (`docia:aba`) é o que desacopla os dois módulos: nem
       `dash_documentos_ia.js` nem `analise_ia.js` precisam saber que o outro
       existe. Cada um ouve, e faz duas coisas na sua vez — busca o que ficou
       pendente enquanto estava escondido e remede os gráficos, que enquanto
       invisíveis não tinham largura nenhuma para medir.  */

    var ligar = function () {
        var pastilhas = Array.prototype.slice.call(
            document.querySelectorAll('.docia-aba[data-aba]'));
        if (!pastilhas.length) return;

        var mostrar = function (nome, porClique) {
            nome = valida(nome) || 'envios';
            var anterior = window.dociaAbaAtiva();
            if (porClique && nome === anterior) return;

            document.documentElement.setAttribute('data-docia-aba', nome);
            guardar(CHAVE_ABA, nome);

            pastilhas.forEach(function (pastilha) {
                var ativa = pastilha.getAttribute('data-aba') === nome;
                pastilha.classList.toggle('docia-aba--ativa', ativa);
                pastilha.setAttribute('aria-selected', ativa ? 'true' : 'false');
            });

            document.dispatchEvent(new CustomEvent('docia:aba', {
                detail: { aba: nome, anterior: anterior }
            }));
        };

        pastilhas.forEach(function (pastilha) {
            pastilha.addEventListener('click', function () {
                mostrar(pastilha.getAttribute('data-aba'), true);
            });
        });

        /*  A primeira passada NÃO é um clique: ela alinha a pastilha acesa com o
            atributo que o `<head>` já escreveu, e avisa os dois módulos de qual
            aba está no ar — é desse aviso que a Análise IA descobre que precisa
            medir os gráficos, quando é ela quem abre a tela.  */
        mostrar(window.dociaAbaAtiva(), false);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ligar);
    } else {
        ligar();
    }
})();
