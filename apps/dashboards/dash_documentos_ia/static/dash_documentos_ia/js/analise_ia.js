/* ==========================================================================
   ANÁLISE IA — a segunda aba do Documentos IA
   ==========================================================================
   POR QUE UM ARQUIVO SÓ SEU, e não mais um bloco dentro de
   `dash_documentos_ia.js`: aquele arquivo monta a tela de Envios & Pendências
   inteira (KPIs, cinco roscas, Detalhamento, exportação, console). Aqui a
   pergunta é outra — como a IA está se comportando — e o único pedaço dele que
   serve às duas telas é o filtro de instituições, que já vive fora da função de
   inicialização e continua sendo carregado por esta página.

   AS CLASSES DOS CONTROLES SÃO AS MESMAS DE LÁ (`filter-semestre`,
   `filter-documento-ies`, `filter-vinculo`, ...). Isso é deliberado: quem pinta
   a caixinha marcada é o CSS, e os seletores dele partem dessas classes. O que
   impede os dois arquivos de disputarem os mesmos controles é a saída antecipada
   no começo de `initDashDocumentosIA` — ver o comentário lá.
   ========================================================================== */

(() => {
    'use strict';

    const URL_TABELA = '/dashboards/documentos-ia/api/tabela-ia/';
    const URL_RESUMO = '/dashboards/documentos-ia/api/resumo-ia/';
    const URL_EXPORTAR = '/dashboards/documentos-ia/api/exportar-ia/';

    /* ======================================================================
       AS CORES SÃO AS DA OVG — as mesmas do quantitativo em Envios & Pendências
       ======================================================================
       Cópia deliberada de `PALETA` em `dash_documentos_ia.js`, e não uma paleta
       própria: as duas abas são a mesma tela para quem usa, e duas famílias de
       cor lado a lado fariam a pessoa procurar um significado na diferença que
       não existe. É a cor da marca, e ela manda.

       O QUE O VALIDADOR DIZ DELA (o do skill de dataviz, contra #FFFFFF no claro
       e a superfície do eleitoral no escuro):

         PASSA no que decide se dá para distinguir as barras — separação sob
         daltonismo ΔE 11,0 a 12,9 e piso de visão normal 16,1 a 21,2, ambos
         acima do mínimo.

         RESSALVA em três pontos, todos herdados da paleta da marca e já no ar
         nas cinco roscas da outra aba: o roxo #6B007B é mais escuro que a banda
         de referência (L 0,38 contra 0,43), o cinza #A3A3A3 não tem croma
         nenhum — de propósito, ele é a ausência — e o rosa claro fica abaixo de
         3:1 de contraste. A ressalva de contraste se resolve com o número
         escrito em cima de cada barra, que existe justamente por isso.

       A ORDEM É FIXA e nunca gira: cada categoria tem o seu degrau, e um filtro
       que mude a quantidade de barras não pode repintar as que sobraram.  */
    const PALETA_OVG = {
        claro:     ['#EB8DC8', '#D6008F', '#6B007B', '#BF616A', '#A3A3A3', '#D62828', '#888888', '#444444'],
        eleitoral: ['#99F0D0', '#3EA9B2', '#6B71B2', '#BF616A', '#A3A3A3', '#F94144', '#888888', '#444444'],
    };

    /*  Mensalidade: os três primeiros e o CINZA — pulando o quarto degrau de
        propósito. "Não localizado" é a IA não ter achado o valor, que é ausência
        de leitura, não um quarto assunto; o cinza é o degrau que a paleta da OVG
        reserva para isso, e é o mesmo papel que ele faz nas roscas da outra aba.  */
    const CORES_MENSALIDADE = (tema) => [
        PALETA_OVG[tema][0], PALETA_OVG[tema][1], PALETA_OVG[tema][2], PALETA_OVG[tema][4],
    ];

    /*  UMA PALAVRA POR BALDE, e não a frase inteira da coluna do documento.

        O nome cru ("Coleta de Dados conforme Documento", 34 caracteres) obrigava a
        faixa dos nomes a 205px — mais da metade de um card de mensalidade, e o que
        sobrava para as barras era menos que o texto ao lado delas. A frase também
        não acrescenta nada: as quatro são variações de "o valor do documento contra
        o do sistema", e o que as distingue são as quatro palavras daqui.

        O TEXTO INTEIRO CONTINUA A UM PALMO: é o que a tabela logo abaixo e a
        planilha trazem na coluna `msd_doc`/`mcd_doc`, onde ele é o dado, e não um
        rótulo.  */
    const ROTULO_MENSALIDADE = {
        'Bateu': 'Conforme',
        'Maior': 'Maior',
        'Menor': 'Menor',
        'Não localizado': 'Não loc.',
    };

    const temaAtual = () =>
        document.documentElement.getAttribute('data-tema') === 'eleitoral' ? 'eleitoral' : 'claro';

    /*  Os quatro recortes de PESSOA, no formato que a view espera: o nome do
        parâmetro na query string e a classe das caixas que o alimentam. A view
        lê exatamente estes nomes (ver `FILTROS_DE_PESSOA` em `views.py`) —
        errar um deles é o filtro rodar só na aparência, que é o pior jeito de
        errar, porque o número não muda e ninguém desconfia do controle.  */
    const FILTROS_DE_PESSOA = [
        ['vinculo', 'filter-vinculo'],
        ['perfil', 'filter-perfil'],
        ['mudou_ies', 'filter-mudou-ies'],
        ['mudou_bolsa', 'filter-mudou-bolsa'],
    ];

    const iniciar = () => {
        const vistaPerformance = document.getElementById('ia-vista-performance');
        const vistaRelatorios = document.getElementById('ia-vista-relatorios');

        // Não é esta tela. O arquivo é carregado só por ela, mas o Turbo pode
        // reaproveitar o documento entre navegações.
        if (!vistaPerformance) return;

        /*  DOMContentLoaded E turbo:load disparam os dois na primeira carga. Com o
            DOM ainda sendo o mesmo, a segunda passada duplicaria todos os ouvintes
            e cada clique valeria por dois pedidos. Numa navegação de verdade a
            marca não existe, porque o elemento é outro.  */
        if (vistaPerformance.dataset.ligado === '1') return;
        vistaPerformance.dataset.ligado = '1';

        /* ==================================================================
           OS FILTROS DESTA ABA SÃO SÓ DELA
           ==================================================================
           As duas abas vivem no MESMO documento e a barra lateral carrega os
           dois conjuntos de controles, um escondido de cada vez. As classes são
           as mesmas nos dois (`filter-semestre`, `filter-documento-ies`, ...),
           e têm de ser: o CSS que pinta a caixinha marcada parte delas — ver
           `.filter-documento-ies:checked + .docia-grade-doc__caixa`.

           Por isso NADA aqui procura a partir do `document`: uma busca global
           acharia também as caixas da aba vizinha, e um clique em Semestre aqui
           marcaria o Semestre de lá. O recorte de cada aba é dela, e é a raiz
           que garante isso.
           ================================================================== */
        const raizFiltros = document.getElementById('filtros-analise') || document;
        const nosFiltros = (seletor) => raizFiltros.querySelectorAll(seletor);

        /* ==================================================================
           A BARRA DE FILTROS NÃO É REGISTRADA AQUI
           ==================================================================
           A barra é UMA só, do lado de fora das duas abas, e quem a abre e
           fecha é `dash_documentos_ia.js` — que roda sempre, porque a aba de
           Envios & Pendências está sempre no documento, mesmo escondida.

           ESTE ARQUIVO JÁ TEVE O SEU PRÓPRIO OUVINTE, de quando as abas eram
           duas páginas separadas e o de lá não chegava até aqui. Com as duas no
           mesmo documento, os dois passaram a disparar no mesmo clique: cada um
           LÊ o estado atual e o inverte, então o segundo desfazia o primeiro e
           a barra não abria mais. Um botão, um ouvinte.

           `esteEstaVisivel` é o que sobrou da necessidade: o ApexCharts mede a
           caixa no momento em que desenha, e enquanto esta aba está escondida a
           caixa tem largura zero.
           ================================================================== */
        const esteEstaVisivel = () => vistaPerformance.offsetParent !== null;

        /*  As instituições escolhidas NESTA aba. Vem de `dash_documentos_ia.js`,
            que é o dono do modal e guarda uma lista para cada aba.  */
        const iesDaAba = () => (typeof window.dociaIESAtivas === 'function'
            ? window.dociaIESAtivas('analise') : []);

        const el = {
            cabecalho: document.getElementById('ia-tabela-cabecalho'),
            corpo: document.getElementById('ia-tabela-corpo'),
            contagem: document.getElementById('ia-tabela-contagem'),
            titulo: document.getElementById('ia-tabela-titulo'),
            rolagem: document.getElementById('ia-tabela-rolagem'),
        };

        const radiosModo = nosFiltros('.filter-modo');
        const caixasSemestre = nosFiltros('.filter-semestre');
        const caixasDocumento = nosFiltros('.filter-documento-ies');

        const marcados = (caixas) => Array.from(caixas)
            .filter((caixa) => caixa.checked)
            .map((caixa) => caixa.value);

        const formatarNumero = (valor) => (Number(valor) || 0).toLocaleString('pt-BR');

        /*  R$ 74.080.081,86 -> "R$ 74,1 mi". Só para o rótulo em cima da coluna, que
            não tem largura para o valor inteiro; o balão e a linha de base mostram o
            número exato. Abaixo de um milhão sai em milhares, e abaixo de mil, cru —
            arredondar R$ 340 para "R$ 0,0 mi" apagaria o dado.  */
        const formatarMilhoes = (valor) => {
            const numero = Number(valor) || 0;
            const absoluto = Math.abs(numero);
            if (absoluto >= 1e6) return 'R$ ' + (numero / 1e6).toFixed(1).replace('.', ',') + ' mi';
            if (absoluto >= 1e3) return 'R$ ' + (numero / 1e3).toFixed(0) + ' mil';
            return 'R$ ' + numero.toFixed(0);
        };

        /*  Moeda COM sinal explícito no positivo: sem o "+", um valor positivo ao lado
            de um negativo lê como se fossem a mesma coisa em tamanhos diferentes.  */
        const formatarMoeda = (valor) => {
            const numero = Number(valor) || 0;
            const texto = Math.abs(numero).toLocaleString('pt-BR', {
                style: 'currency', currency: 'BRL',
            });
            if (numero < 0) return '−' + texto;
            return numero > 0 ? '+' + texto : texto;
        };

        /*  AS FRASES ESCOLHIDAS VIVEM AQUI, e não no DOM como as outras seções.

            A lista é redesenhada a cada resposta (ela muda com o documento e os
            contadores mudam com o recorte), e ler o estado das caixas depois de
            redesenhá-las seria ler o que acabou de ser criado — a escolha se
            perderia a cada clique. Guardada fora do DOM, ela sobrevive ao
            redesenho e é reaplicada nas caixas novas.

            O que NÃO sobrevive é trocar de documento: as frases do RIAF não
            existem no contrato, e carregá-las adiante deixaria um recorte
            impossível valendo em silêncio.  */
        let inconsistenciasEscolhidas = new Set();

        /*  O recorte clicado na legenda da rosca: os vereditos escolhidos, em união
            entre si — clicar "Válido" e "Inválido" mostra os dois.  */
        const recorteVereditos = new Set();

        /*  O nome de um documento sai da caixa que o oferece, e não de uma lista aqui:
            uma segunda lista envelheceria calada no dia em que o rótulo da barra
            mudasse, e o título passaria a chamar a tabela de outra coisa.  */
        const nomeDoDocumento = (chave) => {
            const caixa = Array.from(caixasDocumento).find((c) => c.value === chave);
            const texto = caixa && caixa.parentElement
                && caixa.parentElement.querySelector('.docia-grade-doc__texto');
            return (texto ? texto.textContent : chave).toUpperCase();
        };

        /* ==================================================================
           A CONSULTA
           ==================================================================
           Ausência de parâmetro significa "tudo" do lado do servidor, que é o
           estado inicial desta barra: nada marcado é o recorte inteiro, e não
           um recorte vazio.
           ================================================================== */

        const parametros = () => {
            const busca = new URLSearchParams();

            const semestres = marcados(caixasSemestre);
            if (semestres.length) busca.append('semestres', semestres.join(','));

            /*  UM documento, no singular: a rota serve UMA aba, com todas as
                colunas dela. `exclusividadeDocumento` garante que sempre há
                exatamente um marcado, e o CONTRATO de reserva aqui cobre só o
                instante entre o HTML e o primeiro clique.  */
            busca.append('documento', marcados(caixasDocumento)[0] || 'CONTRATO');

            if (recorteVereditos.size) busca.append('vereditos', Array.from(recorteVereditos).join('||'));

            const campoBusca = document.getElementById('ia-tabela-busca');
            const termo = (campoBusca && campoBusca.value || '').trim();
            if (termo) busca.append('busca', termo);

            const card = document.getElementById('ia-card-tabela');
            if (card && card.classList.contains('docia-detalhamento--expandido')) {
                busca.append('expandido', '1');
            }

            /*  `||` e não vírgula: a frase É separada por vírgula dentro da coluna
                — é assim que a IA cola várias numa string só.  */
            if (inconsistenciasEscolhidas.size) {
                busca.append('inconsistencias', Array.from(inconsistenciasEscolhidas).join('||'));
            }

            FILTROS_DE_PESSOA.forEach(([parametro, classe]) => {
                const escolhidos = marcados(nosFiltros('.' + classe));
                if (escolhidos.length) busca.append(parametro, escolhidos.join(','));
            });

            /*  `||` e não vírgula: nome de faculdade tem vírgula, e a view separa
                esta lista por `||` justamente por isso.

                A LISTA É POR ABA. O modal de instituições é um só — é uma telinha
                passageira, não precisa de duas cópias —, mas a seção que ele grava
                é a da aba aberta: mexer nas instituições aqui não pode mexer nas de
                Envios & Pendências. Quem guarda as duas listas é
                `dash_documentos_ia.js`, e `dociaIESAtivas` devolve a desta.  */
            const ies = iesDaAba();
            if (ies.length) busca.append('ies', ies.join('||'));

            return busca;
        };

        /* ==================================================================
           OS CONTADORES DA BARRA
           ==================================================================
           A barra passa a maior parte do tempo fechada, e o cabeçalho é a única
           coisa dela que se lê de relance ao abrir. Sem o número, descobrir que
           sobrou um recorte de ontem exige rolar seção por seção conferindo.
           ================================================================== */

        const contador = (id, quantos) => {
            const alvo = document.getElementById(id);
            if (!alvo) return quantos;
            alvo.innerText = quantos;
            alvo.style.display = quantos ? '' : 'none';
            return quantos;
        };

        const atualizarContadores = () => {
            let total = 0;
            total += contador('contador-semestres-ia', marcados(caixasSemestre).length);
            total += contador('contador-situacao-ia',
                marcados(nosFiltros('.filter-vinculo')).length
                + marcados(nosFiltros('.filter-perfil')).length);
            total += contador('contador-mudancas-ia',
                marcados(nosFiltros('.filter-mudou-ies')).length
                + marcados(nosFiltros('.filter-mudou-bolsa')).length);
            total += contador('contador-inconsistencias', inconsistenciasEscolhidas.size);
            total += contador('contador-ies-ia', iesDaAba().length);
            contador('contador-filtros', total);
        };

        /* ==================================================================
           A TABELA
           ==================================================================
           O cabeçalho vem da resposta, e não fixado aqui: a lista de colunas é
           fixa do lado do servidor (`COLUNAS_TABELA`), e repetir os 31 nomes
           neste arquivo criaria uma segunda verdade que envelhece calada.
           ================================================================== */

        const escaparHtml = (valor) => String(valor)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

        /** Rótulo legível a partir do nome cru da coluna: `status_doc` -> `Status Doc`. */
        const rotuloColuna = (nome) => String(nome)
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (letra) => letra.toUpperCase());

        /*  Número inteiro sai sem casas; fracionário, com duas — e SEM símbolo de
            moeda, porque a resposta não diz quais colunas são dinheiro e adivinhar
            pelo nome erraria em `qtd_token` e `periodo_atual`.  */
        const celula = (valor) => {
            if (valor === null || valor === undefined || valor === '') return '-';
            if (typeof valor === 'number') {
                return Number.isInteger(valor)
                    ? valor.toLocaleString('pt-BR')
                    : valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            return String(valor);
        };

        const marcarContagem = (texto, carregando) => {
            if (!el.contagem) return;
            el.contagem.innerHTML = texto;
            el.contagem.classList.remove('hidden');
            el.contagem.classList.toggle('docia-contagem--carregando', !!carregando);
        };

        const avisoNaTabela = (texto, cor) => {
            const colunas = el.cabecalho ? Math.max(el.cabecalho.children.length, 1) : 1;
            el.corpo.innerHTML = `<tr><td colspan="${colunas}" class="px-4 py-8 text-center ${cor}">${texto}</td></tr>`;
        };

        /*  As colunas que ganham botão de copiar. São os dois identificadores pelos
            quais alguém leva a lista para fora da tela — a pergunta seguinte a esta
            tabela é quase sempre "me dá essas inscrições".  */
        const COLUNAS_COPIAVEIS = ['inscricao', 'cpf'];

        /*  AS FLAGS. `Status IA` era texto cinza no meio de 62 colunas de texto cinza —
            e é a coluna pela qual se varre esta tabela. Achar "Falso Válido" numa lista
            de 200 linhas exigia ler linha a linha.

            O TEXTO NÃO MUDA: a flag é um `<span>` em volta do MESMO valor que a view
            mandou, então continua sendo o que se copia e o que a busca encontra.

            O slug sai do próprio valor, sem acento e sem pontuação — `Falso Válido` vira
            `falso-valido`. Assim a folha de estilo lista os valores que conhece e
            QUALQUER valor novo que o motor passe a mandar cai sozinho na flag neutra,
            em vez de aparecer sem moldura ou, pior, com a cor de outro estado.  */
        //  SÓ `status_ia`. A folha de estilo conhece os oito valores dela; `msd_doc` e
        //  `mcd_doc` cairiam na flag neutra, e três pílulas cinzas de texto longo numa
        //  tabela de 63 colunas viram ruído em vez de sinal.
        const COLUNAS_COM_FLAG = new Set(['status ia']);

        const slugDaFlag = (texto) => texto
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .toLowerCase().trim()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '');

        /*  Capitulares de verdade: `text-transform: capitalize` só levanta a primeira
            letra de cada palavra e NÃO baixa o resto — sobre `VÁLIDO`, que é como a view
            manda, ele devolve `VÁLIDO`. Encadear duas transformações não existe em CSS.  */
        const rotuloDaFlag = (texto) => texto.toLocaleLowerCase('pt-BR')
            .replace(/(^|\s)(\p{L})/gu, (_, antes, letra) => antes + letra.toLocaleUpperCase('pt-BR'));

        const pintar = (colunas, linhas) => {
            el.cabecalho.innerHTML = colunas.map((nome, i) => {
                const miolo = escaparHtml(rotuloColuna(nome));
                const abre = '<th class="px-4 py-3 text-[11px] font-extrabold text-gray-600'
                    + ' uppercase tracking-wider border-b border-gray-200 bg-gray-50/50">';
                if (COLUNAS_COPIAVEIS.indexOf(String(nome).toLowerCase()) < 0) {
                    return abre + miolo + '</th>';
                }
                return abre + '<div class="flex items-center gap-2">' + miolo
                    + '<button type="button" class="docia-btn-copiar-coluna text-gray-400'
                    + ' hover:text-pink-600 transition-colors bg-white rounded shadow-sm'
                    + ' border border-gray-200 px-1.5 py-0.5" data-coluna="' + escaparHtml(nome)
                    + '" aria-label="Copiar a coluna inteira">'
                    + '<i class="fa-regular fa-copy"></i></button></div></th>';
            }).join('');

            if (!linhas.length) {
                avisoNaTabela('Nenhum dado encontrado', 'text-gray-400');
                return;
            }

            //  Quais colunas viram flag, resolvido UMA vez por pintura e não uma vez
            //  por célula: são até 500 linhas × 76 colunas.
            const comFlag = colunas.map(
                (nome) => COLUNAS_COM_FLAG.has(String(nome).toLowerCase().replace(/_/g, ' ')));

            el.corpo.innerHTML = linhas.map((linha) =>
                '<tr class="docia-tr transition-colors group cursor-default">'
                + linha.map((valor, i) => {
                    const texto = celula(valor);
                    const miolo = (comFlag[i] && texto !== '-')
                        ? '<span class="docia-flag docia-flag--' + slugDaFlag(texto) + '">'
                          + escaparHtml(rotuloDaFlag(texto)) + '</span>'
                        : escaparHtml(texto);
                    return '<td class="px-4 py-2.5 border-b border-gray-100 text-[13px]'
                        + ' text-gray-700 group-hover:text-gray-900 transition-colors'
                        + (i === 0 ? ' font-medium' : '') + '">' + miolo + '</td>';
                }).join('')
                + '</tr>').join('');
        };

        /* ==================================================================
           OS GRÁFICOS
           ==================================================================
           Colunas em pé nos três. A pergunta é "quantos", que é magnitude — e as
           grandezas dentro de um mesmo card chegam a 1 para 467 (52 Falso
           Inválido contra 24.276 Válido, no contrato). Numa rosca as duas
           fatias que esta tela existe para vigiar seriam fios de cabelo.

           O NOME DE CADA COLUNA VAI EM DUAS LINHAS (ver `ROTULO_MENSALIDADE`): é
           o que permite manter o texto reto embaixo de uma coluna estreita, em vez
           de deixar o Apex girá-lo em 45°.
           ================================================================== */

        const graficos = {};

        const tinta = (nome, reserva) => {
            const valor = getComputedStyle(document.documentElement)
                .getPropertyValue(nome).trim();
            return valor || reserva;
        };

        const tintaMedia = () => (temaAtual() === 'eleitoral'
            ? tinta('--tema-texto-medio', '#C8D1DD') : '#4B5563');

        const tintaForte = () => (temaAtual() === 'eleitoral'
            ? tinta('--tema-texto-forte', '#F2F5F9') : '#111827');

        /*  A calha é quase invisível de propósito: ela é o FUNDO da medida, não um
            dado. Forte demais, viraria uma segunda série; ausente, o vazio volta a ser
            só vazio. No tema escuro ela clareia em vez de escurecer, porque ali o que
            recua é o que se aproxima do fundo.  */
        const corDaCalha = () => (temaAtual() === 'eleitoral'
            ? 'rgba(255, 255, 255, 0.055)' : 'rgba(107, 0, 123, 0.045)');

        const superficie = () => (temaAtual() === 'eleitoral'
            ? tinta('--tema-superficie', '#38414F') : '#FFFFFF');

        /*  O BALÃO É O MESMO DA OUTRA ABA — cópia de `balao` em
            `dash_documentos_ia.js`, inclusive nas correções que ele carrega: fundo a
            0,96 de opacidade (a 0,85 a fatia passava por trás do número, que é
            justamente o que se veio ler), UMA sombra curta em vez de duas somadas, e
            borda na cor da marca a 14% em vez do cinza neutro, que nos cantos
            arredondados aparecia como quatro pontinhos sujos.  */
        const balao = (conteudo) => {
            const escuro = temaAtual() === 'eleitoral';
            const fundo = escuro
                ? tinta('--tema-superficie-2', '#424C5B') : 'rgba(255, 255, 255, 0.96)';
            const borda = escuro ? 'rgba(255,255,255,0.16)' : 'rgba(107,0,123,0.14)';
            return '<div style="background:' + fundo + ';border:1px solid ' + borda + ';'
                + 'border-radius:12px;padding:9px 13px;font-family:Poppins,sans-serif;'
                + 'box-shadow:0 1px 2px rgba(17,24,39,0.08), 0 6px 16px -6px rgba(17,24,39,0.22);">'
                + conteudo + '</div>';
        };

        /*  O conteúdo do balão: bolinha da cor, nome, número e percentual — a mesma
            informação e a mesma ordem da legenda, para o hover confirmar o que já
            está escrito em vez de dizer outra coisa.  */
        const conteudoDoBalao = (cor, nome, valor, total, formato) => {
            const pct = total > 0 ? (valor / total) * 100 : 0;
            const escrito = formato === 'moeda'
                ? formatarMoeda(valor).replace('+', '') : formatarNumero(valor);
            return '<div style="display:flex;align-items:center;gap:8px;font-size:11px;'
                + 'font-weight:600;color:' + tintaMedia() + ';">'
                + '<span style="width:9px;height:9px;border-radius:999px;flex-shrink:0;'
                + 'background:' + cor + ';"></span>'
                + '<span>' + escaparHtml(nome) + '</span>'
                + '<span style="font-weight:800;color:' + tintaForte() + ';">'
                + escrito + '</span>'
                + '<span style="opacity:0.7;">' + pct.toFixed(1).replace('.', ',') + '%</span>'
                + '</div>';
        };

        /**
         * O QUE FAZ: as opções comuns às três colunas.
         * O QUE NÃO TEM: grade, eixo de valores e legenda. O número está escrito em
         *   cima de cada coluna e a categoria embaixo dela — uma grade atrás disso é
         *   ruído sobre um dado que já se lê direto, e o eixo de valores repetiria o
         *   que o rótulo já diz, com menos precisão. Legenda também não: é UMA série,
         *   e o nome de cada coluna está debaixo dela.
         */
        const opcoesDeBarra = (categorias, valores, cores, maximo, altura, formato) => {
            /*  ALTURA MÍNIMA PARA BARRAS: Barras com valores pequenos (ex: 1 ou 3 perto de 160)
                sumiam e viravam um risco no chão. Isso garante que qualquer valor > 0 tenha
                pelo menos 4% da altura máxima para a barra ser visível e acomodar o número.  */
            const alturaMinima = maximo * 0.04;
            const valoresVisuais = valores.map(v => (v > 0 && v < alturaMinima) ? alturaMinima : v);

            return {
                chart: {
                    type: 'bar',
                    height: altura,
                    fontFamily: 'Poppins, sans-serif',
                    toolbar: { show: false },
                    animations: { enabled: false },
                    background: 'transparent',
                    /*  O Apex reserva 15px acima do gráfico por conta própria, para um
                        título que aqui não existe — o título é o `<h3>` do card.  */
                    parentHeightOffset: 0,
                },
                series: [{ name: 'Linhas', data: valoresVisuais }],
                xaxis: {
                    categories: categorias,
                    labels: {
                        style: { colors: tintaMedia(), fontSize: '10px', fontWeight: 600 },
                        /*  `rotate: 0` com `rotateAlways: false` é o que IMPEDE o giro
                            automático: o Apex inclina o rótulo sozinho quando acha que
                            não cabe, e um eixo de cinco rótulos inclinados é ilegível.
                            Quem faz caber é a quebra em duas linhas.  */
                        rotate: 0,
                        rotateAlways: false,
                        trim: false,
                        hideOverlappingLabels: false,
                    },
                    axisBorder: { show: false },
                    axisTicks: { show: false },
                    crosshairs: { show: false },
                    tooltip: { enabled: false },
                },
                yaxis: {
                    /*  TETO EXPLÍCITO, com folga de 18%. Sem ele a maior coluna encosta no
                        topo do gráfico e não sobra onde escrever o número — ele cai DENTRO
                        da barra, em tinta de texto sobre fundo saturado. A folga é o lugar
                        do rótulo.  */
                    max: maximo,
                    min: 0,
                    labels: { show: false },
                    axisBorder: { show: false },
                    axisTicks: { show: false },
                },
                /*  A GRADE NÃO APARECE, mas o `padding` dela é o que reserva o ar em cima
                    (para o número) e embaixo (para o nome em três linhas).  */
                grid: {
                    show: false,
                    padding: {
                        left: -15, right: -15, top: -12,
                        bottom: formato === 'moeda' ? 12 : 8,
                        //  Três linhas de rótulo nas medidas de mensalidade; uma só no de
                        //  repasse, onde a categoria é um algarismo.
                        //
                        //  ERA 32, E ISSO SOBRAVA: o Apex já mede sozinho a altura das
                        //  três linhas do rótulo e reserva a faixa do eixo; o `padding`
                        //  daqui vem POR CIMA dela. Medido na bancada, o desenho parava
                        //  56,8px acima da borda do card — um vão morto que não mudava com
                        //  a altura da janela, e que era justamente o "espaçamento embaixo"
                        //  que sobrava depois do F11. Com 8 são 32,8px, dos quais 16 são o
                        //  `py-4` do card, e ainda sobram ~17px abaixo da última linha do
                        //  rótulo: nada fica cortado, e as colunas ganham os 24px.
                    },
                },
                plotOptions: {
                    bar: {
                        horizontal: false,
                        /*  RAIO DE 8, o mesmo vocabulário do anel ao lado (que usa 10 nas
                            pontas). Com 4 as colunas ficavam com o topo quase reto e a
                            faixa inteira lia como um gráfico de outro lugar.  */
                        borderRadius: 8,
                        /*  Só o topo do dado é arredondado; a base fica cravada na linha
                            de origem. Arredondar os dois lados descola a coluna do zero e
                            faz o olho ler um começo que não existe.  */
                        borderRadiusApplication: 'end',
                        /*  COLUNA MAIS LARGA.  */
                        columnWidth: '70%',
                        distributed: Array.isArray(cores) && cores.length > 1,
                        dataLabels: { position: 'top' },
                    },
                },
                colors: cores,
                /*  NÚMERO EM TODA COLUNA, e não seletivo: são quatro ou cinco, o número é
                    a resposta da pergunta ("quantos") e não há eixo de valores para
                    consultar. É também o alívio que o validador de paleta exige do rosa
                    claro e do cinza, que ficam abaixo de 3:1 de contraste.  */
                dataLabels: {
                    enabled: true,
                    offsetY: -18,
                    /*  Em reais o número inteiro não cabe em cima de uma coluna estreita
                        (R$ 74.080.081,86 são 17 caracteres), então o gráfico de repasse
                        escreve em milhões — e o balão, ao passar o mouse, mostra o valor
                        exato. O rótulo dá a ordem de grandeza; o balão dá o número.  */
                    /*  EM REAIS O RÓTULO É SELETIVO: sete colunas estreitas não comportam
                        "R$ 235 mil" cada uma, e o resultado era uma faixa de texto colado.
                        Escreve só nas colunas que respondem a pergunta — as que passam de
                        5% do maior valor —, e o balão dá o número exato de qualquer uma.
                        Nas colunas de contagem todas levam rótulo: são quatro, e o número
                        É a resposta.  */
                    formatter: (valorVis, opcoes) => {
                        const valorReal = valores[opcoes.dataPointIndex];
                        if (formato !== 'moeda') return formatarNumero(valorReal);
                        const maior = Math.max.apply(null, valores);
                        if (maior > 0 && valorReal < maior * 0.05) return '';
                        return formatarMilhoes(valorReal);
                    },
                    style: { fontSize: '11px', fontWeight: 700, colors: [tintaMedia()] },
                    background: { enabled: false },
                    dropShadow: { enabled: false },
                },
                legend: { show: false },
                /*  BALÃO PRÓPRIO, o mesmo da outra aba. O do Apex vem com cabeçalho de
                    categoria, moldura cinza e o nome da série ("Linhas"), que aqui não diz
                    nada — a série é uma só e a categoria já está escrita embaixo da coluna.  */
                tooltip: {
                    intersect: false,
                    shared: true,
                    marker: { show: false },
                    custom: ({ seriesIndex, dataPointIndex, w }) => {
                        const valorReal = valores[dataPointIndex];
                        const soma = valores.reduce((a, b) => a + b, 0);
                        const nome = [].concat(w.globals.labels[dataPointIndex]).join(' ');
                        const cor = w.globals.colors[dataPointIndex] || w.globals.colors[0];
                        return balao(conteudoDoBalao(cor, nome, valorReal, soma, formato));
                    },
                },
                states: {
                    hover: { filter: { type: 'lighten', value: 0.16 } },
                    active: { filter: { type: 'none' } },
                },
            };
        };

        /*  O NÚMERO ESCRITO NA PONTA DA BARRA. Vive fora do gráfico porque quem
            desenha o rótulo e quem reserva o lugar dele no eixo precisam da MESMA
            string — duas cópias divergiriam no dia em que o percentual deixasse de
            sair, e a conta passaria a guardar espaço para um texto que não existe.  */
        const rotuloDoValor = (valor, totalParaPct) => {
            let escrito = formatarNumero(valor);
            if (totalParaPct && totalParaPct > 0) {
                const pct = (valor / totalParaPct) * 100;
                escrito += ' (' + pct.toFixed(1).replace('.', ',') + '%)';
            }
            return escrito;
        };

        /*  A LARGURA DO TEXTO MEDIDA, e não estimada por contagem de caracteres: os
            rótulos de valor misturam dígitos, parênteses, vírgula e espaço, e a média
            por caractere erra justamente no caso extremo, que é o único que importa
            aqui. A régua é um canvas solto, fora do documento — `measureText` não
            provoca layout e o mesmo contexto serve todas as chamadas.  */
        const reguaDeTexto = document.createElement('canvas').getContext('2d');
        const larguraDoTexto = (texto, fonte) => {
            reguaDeTexto.font = fonte;
            return reguaDeTexto.measureText(texto).width;
        };

        /*  O RÓTULO NASCE ACIMA DA BARRA, uns 6px. O Apex ancora o texto do eixo Y pela
            linha de base, e o que sobra é esta diferença constante, medida na bancada.
            Sem ela o nome encosta no da barra de cima e a lista perde o pareamento
            entre nome e barra, que é tudo o que ela tem.  */
        const RECUO_DO_NOME = 6;

        /*  A FAIXA DOS NOMES SAI DOS NOMES, e não de um número escolhido a dedo.

            Os quatro baldes de mensalidade são palavras curtas (ver
            `ROTULO_MENSALIDADE`) e o card deles é o mais estreito da faixa: cada pixel
            reservado aqui é um pixel a menos de barra. Enquanto o rótulo era a frase
            inteira da coluna do documento, a faixa custava 205px fixos — mais da
            metade do card. Medindo o maior nome, ela custa o que ele ocupa.

            A folga é o ar entre o fim do nome e o começo da barra.  */
        const FOLGA_DO_NOME = 12;
        const larguraDaFaixa = (categorias) => FOLGA_DO_NOME + Math.ceil(Math.max(
            ...categorias.map((t) => larguraDoTexto(t, '600 10px Poppins, sans-serif'))));

        /*  O AR ENTRE A PONTA DA BARRA E O NÚMERO: os 10px do `dataLabels.offsetX`
            mais 2px de arredondamento — o Apex corta o rótulo na borda da área de
            plotagem, e chegar exatamente nela é chegar em cima dela.  */
        const FOLGA_DO_VALOR = 12;

        /*  AS MARGENS DOS DOIS LADOS do gráfico deitado, que o Apex desconta da área
            de plotagem. Entram na conta abaixo pelo mesmo motivo que a faixa dos
            nomes: o que sobra para as barras é o card MENOS todas elas.

            Eram 24 à direita e ZERO à esquerda, e o nome ainda levava um `offsetX` de
            -8 para fora — o texto começava 4px ANTES da área útil do card, encostado
            na moldura, enquanto sobravam 45px vazios do outro lado. Os dois números
            agora são próximos de propósito: é o que centra o bloco inteiro (nome,
            barra e número) na largura do card.

            À DIREITA BASTAM 10. Quem garante que o número cabe não é esta margem, é o
            `fatorDeitado` logo abaixo, que reserva a largura do texto mais 12px antes
            de escolher o teto do eixo. Os 24 de antes eram folga sobre folga, e era
            dela que vinha o vão da direita.  */
        const AR_DA_ESQUERDA = 24;
        const AR_DA_DIREITA = 10;

        /*  O VÃO ENTRE O NOME E A BARRA. O Apex encosta um no outro: a faixa que ele
            reserva para o eixo tem a largura do texto mais longo, e o texto, alinhado
            à esquerda, termina exatamente onde a barra começa — "Conforme" ficava
            grudado na barra "Conforme".

            Sai pelo `offsetX` negativo do rótulo, que anda com o texto e não com a
            área: o afastamento da moldura do card continua sendo o `AR_DA_ESQUERDA`,
            e é dele que estes 8px são descontados.  */
        const VAO_ATE_A_BARRA = 8;

        /*  QUANTO O TETO DO EIXO PASSA DA MAIOR BARRA, deitado.

            O rótulo do valor mora depois da ponta da barra, então o vazio à direita
            do eixo é o lugar dele: a barra mais longa pode ir até onde o texto mais
            largo da série ainda caiba atrás. Como a faixa das barras muda com a
            largura do card, a conta é feita a cada desenho, sobre a caixa medida.

            O TETO SAI DA `base`, NÃO DA MAIOR BARRA — é o que mantém os dois gráficos
            de mensalidade na mesma régua, já que ambos recebem a mesma base. Quando a
            base é maior que a maior barra, a barra simplesmente termina antes da
            sobra, e o rótulo ganha ainda mais ar.

            O piso de 30% é para o card estreito demais para o texto: ali nada cabe
            direito, e uma barra curta ainda diz mais que uma barra invisível.  */
        const fatorDeitado = (alvo, valores, faixa, totalParaPct) => {
            const faixaDasBarras = (alvo.clientWidth || 0)
                - faixa - AR_DA_ESQUERDA - AR_DA_DIREITA;
            if (faixaDasBarras <= 0) return 1.35;

            const texto = Math.max(...valores.map((valor) => larguraDoTexto(
                rotuloDoValor(valor, totalParaPct), '700 11px Poppins, sans-serif')));
            const sobra = Math.max(faixaDasBarras - texto - FOLGA_DO_VALOR,
                                   faixaDasBarras * 0.3);
            return faixaDasBarras / sobra;
        };

        /*  DEITADO, o eixo das CATEGORIAS é o Y e o dos VALORES é o X — e é aí que este
            gráfico estava quebrado: `max`/`min` estavam no eixo Y (numérico sobre um eixo
            de categorias) e o `labels: { show: false }` apagava justamente o nome de cada
            barra, enquanto o eixo X aparecia com a régua de 0 a 20.000 que o desenho não
            usa. As categorias entram SEMPRE por `xaxis.categories`, mesmo deitado — quem
            decide onde elas são desenhadas é o `horizontal: true`.  */
        /*  METADE DA SOBRA QUE O APEX GUARDA NO ALTO. Ver a nota do `grid.padding`
            logo abaixo: é constante, não acompanha a altura do card, e por isso é uma
            constante aqui e não uma conta.  */
        const AR_QUE_O_APEX_GUARDA = 8;

        const opcoesDeBarraHorizontal = (categorias, valores, cores, maximo, altura, faixa, formato, totalParaPct) => {
            const alturaMinima = maximo * 0.04;
            const valoresVisuais = valores.map(v => (v > 0 && v < alturaMinima) ? alturaMinima : v);

            return {
                chart: {
                    type: 'bar',
                    height: altura,
                    fontFamily: 'Poppins, sans-serif',
                    toolbar: { show: false },
                    animations: { enabled: false },
                    background: 'transparent',
                    parentHeightOffset: 0,
                },
                series: [{ name: 'Linhas', data: valoresVisuais }],
                xaxis: {
                    categories: categorias,
                    /*  O EIXO DOS VALORES. O teto com folga é o que reserva o lugar do
                        número escrito na ponta da barra — sem ele a maior encosta na
                        borda e o rótulo cai fora do desenho.  */
                    max: maximo,
                    min: 0,
                    //  A régua não aparece: o número está escrito em cada barra.
                    labels: { show: false },
                    axisBorder: { show: false },
                    axisTicks: { show: false },
                    crosshairs: { show: false },
                    tooltip: { enabled: false },
                },
                yaxis: {
                    //  O EIXO DAS CATEGORIAS: é aqui que o nome de cada barra é desenhado.
                    labels: {
                        show: true,
                        //  Alinhados à ESQUERDA, um sob o outro: são frases de tamanhos
                        //  diferentes, e alinhá-las à direita faria cada uma começar num
                        //  lugar — a lista deixaria de ter uma margem para ler.
                        align: 'left',
                        maxWidth: faixa,
                        offsetX: -VAO_ATE_A_BARRA,
                        offsetY: RECUO_DO_NOME,
                        style: { colors: tintaMedia(), fontSize: '10px', fontWeight: 600 },
                    },
                    axisBorder: { show: false },
                    axisTicks: { show: false },
                },
                grid: {
                    show: false,
                    /*  À DIREITA o ar do número na ponta da barra; à esquerda o que
                        separa o nome da moldura do card (ver `AR_DA_ESQUERDA`).

                        EM CIMA E EMBAIXO O MESMO TANTO DE PADDING, repartido de um
                        jeito torto de propósito. O Apex reserva no alto do desenho um
                        espaço fixo que era do título e da barra de ferramentas — 23px
                        medidos, contra 7px embaixo — e não devolve esse espaço quando
                        os dois estão desligados. As quatro barras ficavam com 25px de
                        vão em cima e 10px embaixo, sempre os mesmos ~15px de
                        diferença, em card de 76px ou de 272px.

                        Somando, `top` e `bottom` continuam valendo os -16 de antes,
                        então a altura da área de plotagem não muda; o que muda é onde
                        ela começa. Os 8px saem do alto e entram embaixo, que é metade
                        da diferença medida — é o que centra as barras na caixa.  */
                    padding: {
                        left: AR_DA_ESQUERDA,
                        right: AR_DA_DIREITA,
                        top: -8 - AR_QUE_O_APEX_GUARDA,
                        bottom: -8 + AR_QUE_O_APEX_GUARDA,
                    },
                },
                plotOptions: {
                    bar: {
                        horizontal: true,
                        borderRadius: 6,
                        borderRadiusApplication: 'end',
                        barHeight: '70%',
                        distributed: Array.isArray(cores) && cores.length > 1,
                        dataLabels: { position: 'top' },
                    },
                },
                colors: cores,
                dataLabels: {
                    enabled: true,
                    offsetX: 10,
                    offsetY: 2,
                    textAnchor: 'start',
                    formatter: (valorVis, opcoes) =>
                        rotuloDoValor(valores[opcoes.dataPointIndex], totalParaPct),
                    style: { fontSize: '11px', fontWeight: 700, colors: [tintaMedia()] },
                    background: { enabled: false },
                    dropShadow: { enabled: false },
                },
                legend: { show: false },
                tooltip: {
                    intersect: false,
                    shared: true,
                    marker: { show: false },
                    custom: ({ seriesIndex, dataPointIndex, w }) => {
                        const valorReal = valores[dataPointIndex];
                        const soma = totalParaPct || valores.reduce((a, b) => a + b, 0);
                        /*  As linhas de espaço que centram o rótulo no eixo também entram
                            aqui — no balão a frase é UMA, e sem colar os brancos ela sairia
                            com buracos no meio.  */
                        const nome = [].concat(w.globals.labels[dataPointIndex])
                            .join(' ').replace(/\s+/g, ' ').trim();
                        const cor = w.globals.colors[dataPointIndex] || w.globals.colors[0];
                        return balao(conteudoDoBalao(cor, nome, valorReal, soma, formato));
                    },
                },
                states: {
                    hover: { filter: { type: 'lighten', value: 0.16 } },
                    active: { filter: { type: 'none' } },
                },
            };
        };

        /** Troca o gráfico por uma explicação — ver `.docia-grafico-vazio` no CSS. */
        const mostrarVazio = (id, icone, texto) => {
            const alvo = document.getElementById(id);
            if (!alvo) return;
            if (graficos[id]) { graficos[id].destroy(); delete graficos[id]; }
            alvo.innerHTML = '<div class="docia-grafico-vazio">'
                + '<i class="fa-solid ' + icone + ' docia-grafico-vazio__icone"></i>'
                + '<span class="docia-grafico-vazio__texto">' + escaparHtml(texto) + '</span>'
                + '</div>';
        };

        /*  A ALTURA VAI EM PIXELS, MEDIDA — e não `height: '100%'`.

            `100%` NÃO É A CAIXA DO GRÁFICO: no ApexCharts (v7.1.0, o que o CDN serve
            hoje), `setSVGDimensions` resolve altura em porcentagem sobre
            `getDimensions(this.el.parentNode)` — o CARD inteiro, do qual a nossa caixa
            é só uma fatia. Medido na bancada: card de 393px devolvia svg de 371px numa
            caixa de 180px, e o anel era desenhado 191px para fora, por cima da legenda.
            Com `overflow: visible` no canvas (que o balão precisa para vazar), nada o
            segurava. E como o Apex só grava o `min-height` inline no caminho em PIXEL,
            no caminho da porcentagem a caixa nem sequer crescia junto: o desenho
            simplesmente transbordava.

            ZERAR O `min-height` ANTES DE MEDIR, pelo mesmo motivo de `ajustarAlturasIA`:
            o valor que o Apex deixou inline no render anterior é o piso da caixa, e
            medir sem zerar é medir o passado — a caixa cresceria e nunca encolheria.

            O piso existe para o caso oposto: num card muito baixo o flex espreme a caixa
            a quase zero, e um gráfico de 3px não é gráfico.  */
        const alturaDe = (alvo) => {
            alvo.style.minHeight = '0px';
            return Math.max(alvo.clientHeight || 0, 90);
        };

        /*  QUANTO DA CAIXA O DESENHO OCUPA — 100% em quase todos, menos no anel das
            inconsistências.

            Lá a caixa é alta: a lista ao lado pede a altura inteira do card, e o anel,
            que divide a mesma linha com ela, herdava essa altura e virava um disco de
            quase 280px de diâmetro — o dobro do anel do veredito, para um card que não
            é o dobro de importante. Desenhado em três quartos da caixa ele volta ao
            tamanho de gráfico e o resto vira respiro em volta.

            É a ALTURA passada ao Apex que muda, e não uma escala aplicada depois: o
            número do meio ("13.276") e a legenda do centro têm corpo calculado a
            partir dela, então encolhem junto e continuam cabendo no furo. E como a
            caixa é `flex ... items-center justify-center`, o desenho menor fica
            centrado nela sozinho, sem margem escrita em lugar nenhum.

            E O ANEL TAMBÉM CABE DEITADO. Só a altura não basta: o anel é REDONDO, e
            quando a barra de filtros abre é a LARGURA da caixa que vira o lado curto —
            a de inconsistências cai de 251px para 182px, porque ela é uma fração do
            card e o card encolheu 216px. Medido na bancada, com a barra aberta o anel
            ficava 203px de diâmetro numa caixa de 182px: 10px vazando de cada lado,
            por cima da lista, e não só durante a animação — ficava assim.

            A CULPA É DO `customScale`, e ele é de propósito (ver `plotOptions.pie`).
            O Apex desenha o diâmetro em `ESCALA_DO_ANEL × menor lado da grade`, e com
            escala acima de 1 o desenho é maior do que o lado que o limita: quando quem
            limita é a largura, o excesso vaza para fora da caixa por definição. Então
            a largura entra na conta ANTES, virando um teto de altura — é a altura que
            o Apex aceita, e é dela que ele deduz o resto.

            OS DOIS NÚMEROS SÃO MEDIDOS, não deduzidos da documentação: `1,12` é
            diâmetro ÷ lado curto da grade nos dois casos acima, e `23` é o que o Apex
            guarda no alto do desenho (o mesmo espaço morto de `AR_QUE_O_APEX_GUARDA`,
            aqui inteiro em vez de metade). `0,92` é o respiro que sobra dos lados,
            para o anel não encostar na linha que separa o desenho da lista.  */
        const FRACAO_DO_DESENHO = { 'ia-gr-veredito': 0.90 };
        const alturaDoDesenho = (id, altura, largura) => {
            const fracao = FRACAO_DO_DESENHO[id];
            return fracao ? Math.round(altura * fracao) : altura;
        };

        /* ==================================================================
           A ROSCA — OS SEIS BALDES, IGUAIS AOS DE ENVIOS & PENDÊNCIAS
           ==================================================================
           As fatias são as MESMAS SEIS da outra aba, produzidas pela MESMA função
           no servidor (`_balde_do_documento`) e pintadas com a MESMA paleta. É
           isso que faz "Inadimplentes Proc." valer 311 aqui e 311 lá — inclusive
           os dois desempates que separam cobrança sem lastro de documento lido.

           OS CINCO VEREDITOS DA IA NÃO VIRAM FATIA — viram LINHAS da legenda,
           recuadas sob "Processados", que é o balde de que eles são feitos.

           POR QUÊ: dez fatias exigiriam dez cores distinguíveis entre si DUAS A
           DUAS (numa rosca qualquer fatia se compara com qualquer outra, não só
           com a vizinha). Medido no validador, a família da marca colapsa aí —
           ΔE 1,0 sob daltonismo e 4,1 na visão normal, contra pisos de 8 e 15.
           Fora da marca fecha, mas com quatro marrons no meio dos rosas. Na
           legenda o nome e o número separam sem depender de cor nenhuma, e o
           clique recorta a tabela do mesmo jeito.
           ================================================================== */

        /*  `id` VEM DE FORA porque a tela tem DUAS roscas — veredito e
            inconsistências. Fixo, as duas nasciam com o mesmo `chart.id`, e o Apex
            guarda as instâncias por id: a segunda passava a responder pelos eventos
            da primeira.  */
        const opcoesDeRosca = (id, nomes, valores, cores, altura, valoresCru, rotuloDoCentro) => ({
            chart: {
                type: 'donut',
                id: id,
                height: altura,
                fontFamily: 'Poppins, sans-serif',
                toolbar: { show: false },
                animations: {
                    enabled: true, easing: 'easeout', speed: 1200,
                    dynamicAnimation: { speed: 500 },
                    animateGradually: { enabled: true, delay: 150 },
                },
                background: 'transparent',
                parentHeightOffset: 0,
                /*  A barra de filtros anima `padding-left` do container pai. Sem isto o
                    Apex redesenharia a cada quadro; quem avisa do tamanho novo é o
                    ResizeObserver logo abaixo.  */
                redrawOnParentResize: false,
                /*  SEM SOMBRA NO ANEL: `dropShadow` do ApexCharts é aplicado POR FATIA,
                    e num anel as fatias se tocam — a sombra de cada uma cai em cima da
                    vizinha e nasce uma mancha cinza na emenda.  */
                dropShadow: { enabled: false },
            },
            grid: {
                padding: id === 'ia-gr-inconsistencias' ? { left: 15, right: 15, top: 15, bottom: 15 } : { left: -12, right: -12, top: 0, bottom: 0 },
            },
            series: valores,
            labels: nomes,
            colors: cores,
            plotOptions: {
                pie: {
                    expandOnClick: false,
                    customScale: id === 'ia-gr-inconsistencias' ? 1.0 : 1.1,
                    //  As pontas das fatias são ARREDONDADAS, como no quantitativo da
                    //  outra aba. Sem isto o anel fica com emendas em esquadro.
                    borderRadius: 10,
                    donut: {
                        //  Anel fino, o mesmo 82% de lá.
                        size: '82%',
                        labels: {
                            show: true,
                            name: {
                                show: true, fontSize: id === 'ia-gr-inconsistencias' ? '10px' : '12px', fontWeight: 600,
                                color: tintaMedia(), offsetY: id === 'ia-gr-inconsistencias' ? 12 : 20,
                            },
                            /*  O NÚMERO GRANDE ACOMPANHA A ALTURA do card, em vez dos
                                28px fixos da outra aba. Lá a legenda tem seis linhas;
                                aqui tem dez, e o gráfico fica proporcionalmente mais
                                baixo — em 28px o total transbordava o furo do anel e
                                encostava nas fatias dos dois lados.  */
                            value: {
                                show: true,
                                fontSize: Math.max(17, Math.round(altura * 0.135 * (id === 'ia-gr-inconsistencias' ? 0.72 : 1))) + 'px',
                                fontWeight: 800,
                                color: tintaForte(), offsetY: id === 'ia-gr-inconsistencias' ? -10 : -18,
                                formatter: (valor) => formatarNumero(valor),
                            },
                            /*  `total` é o par NÚMERO + RÓTULO, e o `fontSize` daqui é
                                só o do RÓTULO — o número segue o de `value`. Estava em
                                28px e 800, o que desenhava "Documentos" do tamanho do
                                total e transbordava o furo.  */
                            total: {
                                show: true, showAlways: true, label: rotuloDoCentro,
                                fontSize: '12px', fontWeight: 600, color: tintaMedia(),
                                formatter: (w) => formatarNumero(
                                    valoresCru.reduce((a, b) => a + b, 0)),
                            },
                        },
                    },
                },
            },
            /*  ESPAÇAMENTO VAZADO, e não pintado. Era `colors: [superficie()]`, que
                desenha a cor da superfície em volta de cada fatia — e o card tem
                gradiente, então o anel ganhava um contorno BRANCO por dentro e por
                fora, que não é separação, é sujeira. Transparente, o que aparece na
                emenda é o próprio fundo do card, exatamente como na outra aba.  */
            stroke: { show: true, width: 4, colors: ['transparent'] },
            fill: { type: 'solid' },
            dataLabels: { enabled: false },
            legend: { show: false },
            states: {
                hover: { filter: { type: 'lighten', value: 0.16 } },
                active: { filter: { type: 'none' } },
            },
            tooltip: {
                custom: ({ seriesIndex, w }) => {
                    const total = valoresCru.reduce((a, b) => a + b, 0);
                    return balao(conteudoDoBalao(w.globals.colors[seriesIndex],
                                                 w.globals.labels[seriesIndex],
                                                 valoresCru[seriesIndex], total));
                },
            },
        });

        /*  A MARCA DO RECORTE — quem está dentro, quem ficou de fora — escrita
            sozinha, sem passar pelos números.

            É o que deixa o CLIQUE responder na hora: a resposta do servidor leva
            ~200 ms para voltar, e até ela chegar a lista ficava exatamente como
            estava, sem sinal nenhum de que o clique foi ouvido. Marcar antes de
            pedir é a mesma verdade que vai chegar — o recorte já mudou aqui, é ele
            que está sendo consultado — e ainda serve à repintura, que reaproveita
            esta função em vez de repetir as duas linhas de classe.  */
        const marcarRecorteNaLegenda = (caixa, recorteSet) => {
            const haRecorte = recorteSet.size > 0;
            Array.from(caixa.children).forEach((linha) => {
                const ativo = recorteSet.has(linha.dataset.chave);
                linha.classList.toggle('docia-legenda__item--ativo', ativo);
                linha.classList.toggle('docia-legenda__item--fora', haRecorte && !ativo);
            });
        };

        /*  A LEGENDA USA AS CLASSES DA CASA (`docia-legenda__*`), e não classes
            próprias: assim ela herda de uma vez o quadradinho de 10px com o brilho
            interno, o realce do item ativo, o risco no que ficou de fora e os dois
            temas — sem uma segunda folha de estilo para envelhecer em paralelo.

            É BOTÃO, não texto: clicar recorta a tabela pela fatia, que é o gesto
            que a outra aba já ensina. Com qualquer fatia escolhida, as demais ficam
            riscadas — escolher uma é, ao mesmo tempo, deixar as outras de fora, e
            elas passam a dizer isso de si mesmas.

            A LISTA SÓ É REESCRITA QUANDO OS NOMES MUDAM. Antes cada resposta do
            servidor jogava um `innerHTML` novo na caixa, e um `innerHTML` não é uma
            atualização: é destruir treze botões e criar treze outros. O que se via a
            cada clique era a lista piscar e se re-empilhar, o `:hover` largar o item
            que estava sob o cursor e o foco do teclado voltar para o começo da página.
            Nos casos que interessam — clicar numa fatia, trocar de semestre, trocar de
            tema — os nomes são exatamente os mesmos de antes: o que muda é número,
            percentual, cor e marca, e isso se escreve por cima do que já está lá.  */
        const pintarLegendaRosca = (idCaixa, nomes, valores, cores, chaves = null, recorteSet = null) => {
            const caixa = document.getElementById(idCaixa);
            if (!caixa) return;

            const total = valores.reduce((soma, valor) => soma + valor, 0);
            const chaveDe = (i) => (chaves ? chaves[i] : nomes[i]);

            const linhas = Array.from(caixa.children);
            const mesmaLista = linhas.length === nomes.length
                && nomes.every((nome, i) => linhas[i].dataset.nome === nome);

            if (!mesmaLista) {
                caixa.innerHTML = nomes.map((nome, i) => {
                    /*  SEM `recorteSet` A LINHA NÃO É BOTÃO — e também não se veste de
                        um: o `--estatico` tira o cursor de mão e o realce do hover, que
                        prometeriam um clique que não existe.  */
                    const btnData = recorteSet ? ' data-chave="' + escaparHtml(chaveDe(i)) + '"' : '';
                    const tag = recorteSet ? 'button type="button"' : 'div';
                    const tagClose = recorteSet ? 'button' : 'div';
                    const estatico = recorteSet ? '' : ' docia-legenda__item--estatico';

                    return '<' + tag + ' class="docia-legenda__item' + estatico + '"'
                        + ' data-nome="' + escaparHtml(nome) + '"' + btnData + '>'
                        + '<span class="docia-legenda__ponto"></span>'
                        /*  O NOME INTEIRO NO `title`: as frases da IA passam de 60
                            caracteres e a coluna as apara com reticências.  */
                        + '<span class="docia-legenda__nome" title="' + escaparHtml(nome) + '">'
                        + escaparHtml(nome) + '</span>'
                        + '<span class="docia-legenda__valor"></span>'
                        + '<span class="docia-legenda__pct"></span>'
                        + '</' + tagClose + '>';
                }).join('');
            }

            Array.from(caixa.children).forEach((linha, i) => {
                const pct = total > 0 ? (valores[i] / total) * 100 : 0;
                linha.querySelector('.docia-legenda__ponto').style.background = cores[i];
                linha.querySelector('.docia-legenda__valor').textContent =
                    formatarNumero(valores[i]);
                linha.querySelector('.docia-legenda__pct').textContent =
                    pct.toFixed(1).replace('.', ',') + '%';
            });
            if (recorteSet) marcarRecorteNaLegenda(caixa, recorteSet);
        };


        /*  As chaves CRUAS (`FALSO VÁLIDO`) na ordem em que a legenda as desenha: é o
            que o clique manda ao servidor, enquanto o rótulo é o que se lê. Guardadas
            na pintura porque a legenda é redesenhada a cada resposta.  */
        let chavesDoVeredito = [];

        /** `FALSO VÁLIDO` -> `Falso válido`: a view manda a chave em caixa alta. */
        const rotuloDoVeredito = (nome) => nome.charAt(0)
            + nome.slice(1).toLocaleLowerCase('pt-BR');

        if (document.getElementById('ia-legenda-veredito')) {
            document.getElementById('ia-legenda-veredito').addEventListener('click', (evento) => {
                const item = evento.target.closest('.docia-legenda__item');
                if (!item) return;
                const chave = item.dataset.chave;
                if (recorteVereditos.has(chave)) recorteVereditos.delete(chave);
                else recorteVereditos.add(chave);
                //  Marcar ANTES de pedir: a resposta demora ~200 ms e o clique não
                //  pode ficar mudo até lá — ver `marcarRecorteNaLegenda`.
                marcarRecorteNaLegenda(item.parentElement, recorteVereditos);
                recarregar();
            });
        }

        const desenharRosca = (id, nomes, valores, cores, rotuloDoCentro) => {
            const alvo = document.getElementById(id);
            if (!alvo || typeof ApexCharts === 'undefined') return;

            const totalCru = valores.reduce((a, b) => a + b, 0);
            const minVisual = Math.ceil(totalCru * 0.03);
            const inflado = valores.map((v) => (v > 0 && v < minVisual) ? minVisual : v);

            const opcoes = opcoesDeRosca(id, nomes, inflado, cores,
                                         alturaDoDesenho(id, alturaDe(alvo), alvo.clientWidth),
                                         valores, rotuloDoCentro);
            if (graficos[id] && graficos[id].__tipo === 'donut') {
                graficos[id].updateOptions(opcoes, false, false);
                return;
            }
            if (graficos[id]) { graficos[id].destroy(); delete graficos[id]; }
            alvo.innerHTML = '';
            graficos[id] = new ApexCharts(alvo, opcoes);
            graficos[id].__tipo = 'donut';
            graficos[id].render();
        };

        const desenhar = (id, categorias, valores, cores, base, formato, virada = false, totalParaPct = 0) => {
            const alvo = document.getElementById(id);
            if (!alvo || typeof ApexCharts === 'undefined') return;
            /*  A folga sai da BASE quando quem chama informa uma — é o que põe os dois
                gráficos de mensalidade na mesma régua. Sem isso cada card se
                normalizava pelo próprio máximo, e "Bateu 8.936" desenhava do mesmo
                tamanho que "Bateu 25.585" no card ao lado: duas barras iguais dizendo
                números que diferem em três vezes.  */
            /*  DEITADO A FOLGA É MEDIDA, não arbitrada. Em pé o rótulo é o número
                sozinho em cima da coluna e cabe em 12% do eixo. Deitado ele é número E
                percentual escritos DEPOIS da ponta da barra, e aí a folga não é uma
                proporção: é a largura de um texto contra a largura do card. Qualquer
                fator fixo acerta numa janela e erra na outra — 1,35 servia ao card de
                509px (janela de 1600) e, no de 396px (janela de 1280), desenhava
                "13.629 (89,5%)" 24px POR CIMA da própria barra.  */
            const faixa = virada ? larguraDaFaixa(categorias) : 0;
            const teto = Math.max(base || 0, ...valores, 1)
                * (virada ? fatorDeitado(alvo, valores, faixa, totalParaPct) : 1.12);
            const opcoes = virada
                ? opcoesDeBarraHorizontal(categorias, valores, cores, teto, alturaDe(alvo), faixa, formato, totalParaPct)
                : opcoesDeBarra(categorias, valores, cores, teto, alturaDe(alvo), formato);
            if (graficos[id] && graficos[id].__tipo === 'bar') {
                graficos[id].updateOptions(opcoes, false, false);
                return;
            }
            /*  `__tipo` guardado na instância: o card do veredito pode ter sido
                desenhado como rosca antes, e reaproveitar a instância trocando só as
                opções deixa o Apex com metade da configuração de cada forma.  */
            if (graficos[id]) { graficos[id].destroy(); delete graficos[id]; }
            alvo.innerHTML = '';
            graficos[id] = new ApexCharts(alvo, opcoes);
            graficos[id].__tipo = 'bar';
            graficos[id].render();
        };

        /* ==================================================================
           O GRÁFICO DE INCONSISTÊNCIAS
           ==================================================================
           ROSCA, a mesma forma do Veredito da IA — a pergunta aqui também é de
           REPARTIÇÃO: de tudo o que a IA apontou, quanto é cada apontamento. Em
           barras, o nome de cada uma era uma frase de até 64 caracteres ("Situação
           acadêmica do documento diverge da esperada pelo sistema"), e a faixa que
           essas frases exigiam à esquerda comia metade do card. Na rosca o nome sai
           do desenho e vai para a legenda, que é uma lista — e lista é onde frase
           longa se lê, inteira e uma sob a outra.

           "SEM INCONSISTÊNCIAS" NÃO É UMA INCONSISTÊNCIA. A IA escreve essa frase
           na mesma coluna que as outras e ela é a MAIS frequente de todo documento
           — 6.738 no RIAF, 7.965 no contrato, 14.511 no histórico. Ela é opção
           legítima da barra de filtros ("me mostre os limpos") e continua lá, mas
           num gráfico chamado INCONSISTÊNCIAS ela era a maior fatia e ainda entrava
           na conta de "ocorrências" da linha de base, inflando o problema com o que
           não é problema.

           O QUE NÃO VIRA FATIA É SOMADO, e não calado: são até 47 frases distintas
           num só recorte, e a paleta da casa não tem 47 cores que se distingam duas
           a duas (ver a nota da rosca do veredito). As mais frequentes ficam com uma
           fatia cada, e o resto entra como uma última fatia cinza que diz de quantas
           frases ela é feita. Nenhuma ocorrência fica fora do total do centro.
           ================================================================== */

        /*  A frase que a IA escreve quando não achou problema nenhum, na forma
            normalizada da view (`_chave_da_inconsistencia`): sem acento e minúscula,
            porque ela vem grafada das duas maneiras.  */
        const SEM_INCONSISTENCIA = 'sem inconsistencias';

        /*  QUANTAS FRASES VIRAM FATIA. Quem manda é a LEGENDA, não o anel: um anel
            aceita quantas fatias se queira, mas fatia cujo nome não está escrito em
            lugar nenhum não diz nada. Com a lista ao lado do anel (ver
            `.docia-legenda--lado`) cabem quatorze linhas de ~20px na altura do card,
            e treze deixam a última sem encostar na borda de baixo.  */
        const FATIAS_DE_INCONSISTENCIA = 13;

        /*  A RAMPA DE CORES DAS FATIAS — a paleta da casa não tem treze degraus.

            Ela tem oito, e três deles são cinzas (`#A3A3A3`, `#888888`, `#444444`):
            de fato são CINCO cores para gastar. Com sete fatias já dava para ver o
            aperto — as duas últimas saíam cinza, e a de baixo encostava na cinza da
            cauda, que é justamente a que não podia ser confundida com nenhuma.

            Em vez de inventar cores novas, cada cor da casa rende três fatias: ela
            mesma, uma mais escura e uma mais clara. São as MESMAS cinco cores, na
            mesma ordem, percorridas três vezes — o que muda entre as voltas é o tom.
            Assim duas fatias vizinhas no anel nunca são o mesmo matiz, e as duas que
            partilham matiz ficam a cinco posições uma da outra.

            A ordem das voltas não é decorativa: base, escuro e só então claro. As
            fatias vêm da maior para a menor, e é a menor que fica com o tom mais
            lavado — o pedacinho de anel que ninguém ia distinguir de perto de todo
            jeito. Os três cinzas ficam de fora da conta: aqui o cinza tem trabalho
            fixo, que é ser a cauda.  */
        const MATIZES_DA_CASA = [0, 1, 2, 3, 5];
        const VOLTAS_DE_TOM = [0, -0.3, 0.42];   /*  < 0 escurece, > 0 clareia  */

        /*  Mistura a cor com preto (alvo 0) ou branco (alvo 255) na proporção pedida,
            canal a canal. Devolve em hex porque é o que a legenda escreve no
            `style="background:"` e o que o Apex já recebe do resto do arquivo.  */
        const puxarTom = (hex, alvo, peso) => {
            const cru = parseInt(hex.slice(1), 16);
            const canal = (deslocamento) => {
                const c = (cru >> deslocamento) & 255;
                return Math.round(c + (alvo - c) * peso);
            };
            return '#' + [16, 8, 0].map((d) => canal(d).toString(16).padStart(2, '0')).join('');
        };

        const rampaDeInconsistencia = (tema) => {
            const cores = [];
            VOLTAS_DE_TOM.forEach((volta) => MATIZES_DA_CASA.forEach((i) => {
                const cor = PALETA_OVG[tema][i];
                cores.push(volta === 0
                    ? cor
                    : puxarTom(cor, volta > 0 ? 255 : 0, Math.abs(volta)));
            }));
            return cores;
        };

        const pintarInconsistencias = (corpo) => {
            const id = 'ia-gr-inconsistencias';
            const alvoBase = document.getElementById('ia-base-inconsistencias');
            const legenda = document.getElementById('ia-legenda-inconsistencias');
            const alvo = document.getElementById(id);
            if (!alvo) return;

            /*  A legenda é o nome das fatias: sem fatia, ela não tem o que dizer — e
                sem lista, a coluna dela também não tem por que existir. A classe é o
                que devolve a largura inteira ao anel para o aviso de vazio ficar
                centrado no card (ver `.docia-anel-e-lista--sozinho`).  */
            const linha = alvo.parentElement;
            const soOAnel = (sim) => {
                if (linha) linha.classList.toggle('docia-anel-e-lista--sozinho', sim);
            };
            const limparLegenda = () => {
                if (legenda) legenda.innerHTML = '';
                soOAnel(true);
            };

            if (!corpo.processados) {
                if (alvoBase) alvoBase.textContent = 'nenhum documento processado';
                limparLegenda();
                mostrarVazio(id, 'fa-hourglass-half',
                             'A IA ainda não leu nenhum documento neste recorte.');
                return;
            }

            const todas = (corpo.inconsistencias || [])
                .filter((i) => semAcento(i.frase) !== SEM_INCONSISTENCIA)
                .sort((a, b) => b.linhas - a.linhas);

            if (!todas.length) {
                if (alvoBase) alvoBase.textContent = '';
                limparLegenda();
                mostrarVazio(id, 'fa-check-circle',
                             'Nenhuma inconsistência encontrada neste recorte.');
                return;
            }

            /*  A CAUDA OCUPA UMA DAS VAGAS — daí o `- 1`. Sem descontar, ela
                empurraria para fora a menos frequente das que iam ser mostradas, e o
                gráfico ficaria uma fatia mais cheio do que a lista comporta.  */
            soOAnel(false);
            const mostradas = todas.length > FATIAS_DE_INCONSISTENCIA
                ? todas.slice(0, FATIAS_DE_INCONSISTENCIA - 1)
                : todas;
            const cauda = todas.slice(mostradas.length);
            const ocorrencias = todas.reduce((soma, i) => soma + i.linhas, 0);

            const nomes = mostradas.map((i) => i.frase);
            const valores = mostradas.map((i) => i.linhas);
            if (cauda.length) {
                nomes.push('Outras ' + formatarNumero(cauda.length) + ' inconsistências');
                valores.push(cauda.reduce((soma, i) => soma + i.linhas, 0));
            }

            if (alvoBase) {
                alvoBase.innerHTML = '<span class="text-red-500 font-medium">'
                    + formatarNumero(ocorrencias) + ' ocorrências em '
                    + formatarNumero(corpo.processados) + ' documentos lidos</span>'
                    + ' &middot; ' + formatarNumero(todas.length) + ' tipos';
            }

            /*  O CINZA É O DEGRAU QUE A PALETA RESERVA para o que não é um assunto
                próprio, e a cauda é exatamente isso — o mesmo papel que ele faz em
                "não localizado". As frases ficam com a rampa, na ordem dela, que é a
                ordem das cores da casa repetida em três tons.  */
            const tema = temaAtual();
            const cinza = PALETA_OVG[tema][4];
            const degraus = rampaDeInconsistencia(tema);
            const cores = nomes.map((_, i) => (cauda.length && i === nomes.length - 1)
                ? cinza : degraus[i % degraus.length]);

            desenharRosca(id, nomes, valores, cores, 'Ocorrências');
            /*  SEM CLIQUE, ao contrário da legenda do veredito: a última linha é uma
                SOMA de frases, não uma frase, e não há filtro que ela possa pedir. O
                recorte por inconsistência continua onde ele é exato, na telinha da
                barra de filtros, que lista as 47 e aceita várias de uma vez.  */
            pintarLegendaRosca('ia-legenda-inconsistencias', nomes, valores, cores);
        };

        /* ==================================================================
           A TELINHA DE INCONSISTÊNCIAS
           ==================================================================
           Mesma forma do filtro de Instituições, e pela mesma razão: são até 48
           frases INTEIRAS ("Mensalidade com desconto no contrato é menor que o
           esperado"), e nenhuma barra lateral de 335px lê isso. Na telinha cada
           frase cabe numa linha, há busca e há o painel do que já foi escolhido.

           AS OPÇÕES VÊM DO SERVIDOR porque são o que a IA ESCREVEU, e mudam com
           o documento: 14 no contrato, 48 no RIAF, 10 no histórico, nenhuma em
           Benefícios e Financiamento.

           DUAS SELEÇÕES, como no modal de IES: `inconsistenciasEscolhidas` é o
           que está VALENDO na consulta, e `emEdicao` é o que está sendo mexido
           dentro da telinha. Sem essa separação, "Cancelar" não teria o que
           desfazer — cada clique já teria mudado a tela por baixo.
           ================================================================== */

        let opcoesInconsistencia = [];
        let emEdicao = new Set();

        const elInc = (id) => document.getElementById(id);

        /** Normaliza para busca: sem acento, minúsculo. "MENSALIDADE" acha "mensalidade". */
        const semAcento = (texto) => String(texto)
            .toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

        const buscaInc = () => semAcento(elInc('ia-inc-busca') ? elInc('ia-inc-busca').value : '');

        const pintarListaInc = () => {
            const caixa = elInc('ia-inc-lista');
            if (!caixa) return;

            const termo = buscaInc();
            const visiveis = termo
                ? opcoesInconsistencia.filter((o) => semAcento(o.frase).includes(termo))
                : opcoesInconsistencia;

            if (!opcoesInconsistencia.length) {
                caixa.innerHTML = '<div class="docia-inc-vazio">'
                    + '<i class="fa-solid fa-circle-check docia-inc-vazio__icone"></i>'
                    + '<span>Este documento não traz inconsistências da IA.</span></div>';
                return;
            }
            if (!visiveis.length) {
                caixa.innerHTML = '<div class="docia-inc-vazio">'
                    + '<i class="fa-solid fa-magnifying-glass docia-inc-vazio__icone"></i>'
                    + '<span>Nenhuma inconsistência com esse texto.</span></div>';
                return;
            }

            caixa.innerHTML = visiveis.map((o) =>
                '<label class="docia-inc-item">'
                + '<input type="checkbox" class="sr-only" value="' + escaparHtml(o.frase) + '"'
                + (emEdicao.has(o.frase) ? ' checked' : '') + '>'
                + '<span class="docia-inc-item__caixa"></span>'
                + '<span class="docia-inc-item__texto">' + escaparHtml(o.frase) + '</span>'
                + '<span class="docia-inc-item__n">' + formatarNumero(o.linhas) + '</span>'
                + '</label>').join('');
        };

        const pintarSelecionadasInc = () => {
            const caixa = elInc('ia-inc-selecionadas');
            const contagem = elInc('ia-inc-contagem');
            if (contagem) contagem.textContent = emEdicao.size;
            if (!caixa) return;

            if (!emEdicao.size) {
                caixa.innerHTML = '<div class="flex flex-col items-center justify-center h-full opacity-40">'
                    + '<i class="fa-solid fa-inbox text-4xl text-gray-400 mb-3"></i>'
                    + '<div class="text-center text-gray-500 text-sm font-medium">'
                    + 'Nenhuma inconsistência selecionada.<br>Use o painel ao lado para adicionar.</div></div>';
                return;
            }

            caixa.innerHTML = Array.from(emEdicao).map((frase) =>
                '<div class="docia-inc-escolhida">'
                + '<span class="docia-inc-escolhida__texto">' + escaparHtml(frase) + '</span>'
                + '<button type="button" class="docia-inc-escolhida__x" data-remover="'
                + escaparHtml(frase) + '" aria-label="Remover">'
                + '<i class="fa-solid fa-xmark"></i></button></div>').join('');
        };

        /** O texto do botão na barra: é a única pista do filtro com a telinha fechada. */
        const atualizarRotuloInc = () => {
            const alvo = elInc('ia-inconsistencias-texto');
            if (!alvo) return;
            const n = inconsistenciasEscolhidas.size;
            alvo.textContent = n === 0 ? 'Todas as inconsistências'
                : n === 1 ? Array.from(inconsistenciasEscolhidas)[0]
                : n + ' inconsistências selecionadas';
        };

        const abrirInc = () => {
            const modal = elInc('modal-inconsistencias');
            if (!modal) return;
            // A edição começa do que já está aplicado: abrir e sair no "Cancelar"
            // não pode mudar nada.
            emEdicao = new Set(inconsistenciasEscolhidas);
            const busca = elInc('ia-inc-busca');
            if (busca) busca.value = '';
            const limpar = elInc('ia-inc-limpar-busca');
            if (limpar) limpar.classList.add('hidden');
            pintarListaInc();
            pintarSelecionadasInc();
            modal.style.display = 'flex';
        };

        const fecharInc = () => {
            const modal = elInc('modal-inconsistencias');
            if (modal) modal.style.display = 'none';
        };

        const aplicarInc = () => {
            inconsistenciasEscolhidas = new Set(emEdicao);
            atualizarRotuloInc();
            fecharInc();
            recarregar();
        };

        if (elInc('ia-btn-inconsistencias')) {
            elInc('ia-btn-inconsistencias').addEventListener('click', abrirInc);
        }
        if (elInc('ia-inc-fechar')) elInc('ia-inc-fechar').addEventListener('click', fecharInc);
        if (elInc('ia-inc-cancelar')) elInc('ia-inc-cancelar').addEventListener('click', fecharInc);
        if (elInc('ia-inc-aplicar')) elInc('ia-inc-aplicar').addEventListener('click', aplicarInc);
        if (elInc('ia-inc-limpar')) {
            elInc('ia-inc-limpar').addEventListener('click', () => {
                emEdicao.clear();
                pintarListaInc();
                pintarSelecionadasInc();
            });
        }

        /*  Ouvintes DELEGADOS nos dois painéis: as listas são redesenhadas a cada
            clique e a cada tecla da busca, e um ouvinte por item deixaria um por
            frase e por redesenho — no RIAF são 48 de cada vez.  */
        if (elInc('ia-inc-lista')) {
            elInc('ia-inc-lista').addEventListener('change', (evento) => {
                const caixa = evento.target.closest('input[type="checkbox"]');
                if (!caixa) return;
                if (caixa.checked) emEdicao.add(caixa.value);
                else emEdicao.delete(caixa.value);
                pintarSelecionadasInc();
            });
        }
        if (elInc('ia-inc-selecionadas')) {
            elInc('ia-inc-selecionadas').addEventListener('click', (evento) => {
                const botao = evento.target.closest('[data-remover]');
                if (!botao) return;
                emEdicao.delete(botao.dataset.remover);
                pintarListaInc();
                pintarSelecionadasInc();
            });
        }
        if (elInc('ia-inc-busca')) {
            elInc('ia-inc-busca').addEventListener('input', (evento) => {
                const limpar = elInc('ia-inc-limpar-busca');
                if (limpar) limpar.classList.toggle('hidden', evento.target.value.length === 0);
                pintarListaInc();
            });
        }
        if (elInc('ia-inc-limpar-busca')) {
            elInc('ia-inc-limpar-busca').addEventListener('click', () => {
                const busca = elInc('ia-inc-busca');
                if (!busca) return;
                busca.value = '';
                elInc('ia-inc-limpar-busca').classList.add('hidden');
                pintarListaInc();
                busca.focus();
            });
        }

        /*  Fechar clicando fora e com Esc: a telinha cobre a tela inteira e, sem
            isso, o único jeito de sair é acertar o "x".  */
        if (elInc('modal-inconsistencias')) {
            elInc('modal-inconsistencias').addEventListener('click', (evento) => {
                if (evento.target.id === 'modal-inconsistencias') fecharInc();
            });
        }
        document.addEventListener('keydown', (evento) => {
            const modal = elInc('modal-inconsistencias');
            if (evento.key === 'Escape' && modal && modal.style.display === 'flex') fecharInc();
        });

        /**
         * Recebe a lista do servidor a cada resposta.
         * A LISTA IGNORA O PRÓPRIO FILTRO (ver `api_resumo_ia`): ela é o menu, não o
         * resultado. Se encolhesse ao marcar a primeira frase, não haveria como
         * marcar a segunda.
         */
        const receberInconsistencias = (lista, documento) => {
            opcoesInconsistencia = lista || [];
            const nome = elInc('ia-inc-documento');
            if (nome && documento) nome.textContent = nomeDoDocumento(documento).toLowerCase();
            atualizarRotuloInc();
            // Só repinta a telinha se ela estiver aberta; fechada, `abrirInc` repinta.
            const modal = elInc('modal-inconsistencias');
            if (modal && modal.style.display === 'flex') {
                pintarListaInc();
                pintarSelecionadasInc();
            }
        };

        const pintarGraficos = (corpo) => {
            const tema = temaAtual();

            /*  VEREDITO — os cinco que a tela pediu. A linha de base diz quantas
                linhas do recorte ficaram FORA deles (ausentes, inadimplentes e
                corrompidos): sem ela o card passaria por retrato do todo e o total
                não bateria com o da tabela abaixo.  */
            const veredito = corpo.veredito || {};
            const nomes = Object.keys(veredito);
            const somaVeredito = nomes.reduce((s, n) => s + veredito[n], 0);
            const base = document.getElementById('ia-base-veredito');
            if (base) {
                /*  Com os oito estados a rosca cobre o recorte inteiro, e a base é
                    só o total. A ressalva só aparece se um dia o motor inventar um
                    estado que esta lista não conhece — ver `fora_do_grafico`.  */
                /*  A BASE DIZ SOBRE QUANTAS LINHAS A ROSCA FALA. Ela cobre só os
                    processados, e sem esta linha o total dela contradiria o da tabela
                    logo abaixo sem nada na tela explicando por quê.  */
                if (corpo.processados === corpo.total) {
                    base.innerHTML = formatarNumero(corpo.total) + ' documentos lidos';
                } else {
                    base.innerHTML = '<span class="text-red-500 font-medium">' + formatarNumero(corpo.processados) + ' lidos de ' + formatarNumero(corpo.total) + ' documentos</span>';
                }
            }
            /*  A ROSCA MOSTRA SÓ O QUE A IA LEU. Pendentes, não processados e
                inadimplentes descrevem a AUSÊNCIA de leitura — num gráfico chamado
                "Veredito da IA" eles respondiam outra pergunta, e ainda esmagavam as
                duas fatias que a tela existe para vigiar (Falso Válido e Falso
                Inválido somam 268 contra 48.475 de não-leitura).

                Cinco fatias cabem folgado nos seis degraus da OVG, sem inventar cor.  */
            const legendaVeredito = document.getElementById('ia-legenda-veredito');
            const somaVerdc = nomes.reduce((s, n) => s + (veredito[n] || 0), 0);

            if (somaVerdc === 0) {
                if (legendaVeredito) legendaVeredito.innerHTML = '';
                mostrarVazio('ia-gr-veredito', 'fa-circle-info',
                             'A IA ainda não leu nenhum documento neste recorte.');
            } else {
                const cores = PALETA_OVG[tema];
                chavesDoVeredito = nomes;
                const rotulos = nomes.map(rotuloDoVeredito);
                const valores = nomes.map((n) => veredito[n] || 0);
                desenharRosca('ia-gr-veredito', rotulos, valores, cores, 'Documentos');
                pintarLegendaRosca('ia-legenda-veredito', rotulos, valores, cores, chavesDoVeredito, recorteVereditos);
            }

            /* ------------------------------------------------------------------
               A FAIXA DE NÚMEROS
               ------------------------------------------------------------------ */

            const escrever = (id, valor, base) => {
                const alvoValor = document.getElementById(id);
                const alvoBase = document.getElementById(id + '-base');
                if (alvoValor) alvoValor.textContent = valor;
                if (alvoBase) alvoBase.textContent = base || '';
            };

            const bolsa = corpo.bolsa || {};
            const totalBolsa = (bolsa.Parcial || 0) + (bolsa.Integral || 0);
            const fatia = (n) => (totalBolsa > 0
                ? (n / totalBolsa * 100).toFixed(1).replace('.', ',') + '% dos beneficiários'
                : '');

            /*  BENEFICIÁRIOS é PESSOA e DOCUMENTOS é LINHA — o mesmo CPF aparece em
                mais de uma inscrição no mesmo semestre (714 no contrato de 2025-1), e
                é por isso que os dois números não se somam nem se igualam.  */
            escrever('ia-kpi-beneficiarios', formatarNumero(corpo.beneficiarios),
                     'CPFs distintos no recorte');
            escrever('ia-kpi-documentos', formatarNumero(corpo.total),
                     formatarNumero(corpo.processados) + ' lidos pela IA');
            escrever('ia-kpi-parcial', formatarNumero(bolsa.Parcial || 0),
                     fatia(bolsa.Parcial || 0));
            escrever('ia-kpi-integral', formatarNumero(bolsa.Integral || 0),
                     fatia(bolsa.Integral || 0));

            /*  AS DUAS DIFERENÇAS. Moeda com sinal: negativo é o documento cobrando
                MENOS do que o sistema espera, e o sinal é metade do recado.  */
            const dif = corpo.diferencas || {};
            [['sem_desconto', 'ia-kpi-dif-sem'], ['com_desconto', 'ia-kpi-dif-com']]
                .forEach(([chave, id]) => {
                    const valor = document.getElementById(id);
                    const base = document.getElementById(id + '-base');
                    const medida = dif[chave] || {};
                    if (!medida.tem_dado) {
                        if (valor) valor.textContent = '—';
                        if (base) base.textContent = 'sem valor lido neste recorte';
                        if (valor && valor.parentElement) valor.parentElement.title = '';
                        return;
                    }
                    if (valor) valor.textContent = formatarMoeda(medida.soma);
                    if (base) {
                        base.textContent = formatarNumero(medida.coincidem)
                            + ' de ' + formatarNumero(medida.linhas) + ' coincidem';
                    }
                    if (valor && valor.parentElement) {
                        let texto_tooltip = 'Os valores da coleta batem exatamente com os do documento.';
                        if (medida.pct > 0) {
                            texto_tooltip = 'Comparado ao documento, a coleta tem um AUMENTO de ' + formatarNumero(medida.pct) + '%. Isso significa que o valor no sistema é maior (estamos pagando mais caro).';
                        } else if (medida.pct < 0) {
                            texto_tooltip = 'Comparado ao documento, a coleta tem uma QUEDA de ' + formatarNumero(Math.abs(medida.pct)) + '%. Isso significa que o valor no sistema é menor (estamos pagando a menos).';
                        }
                        
                        valor.parentElement.title = texto_tooltip;
                    }
                });

            /*  MENSALIDADE — só dos PROCESSADOS. `tem_dado` falso é o documento que
                não carrega esse valor (o histórico), e ali desenhar uma barra de
                "não localizado" em 100% acusaria a IA de não achar o que não existe.  */
            const ordem = corpo.ordem_mensalidade || ['Bateu', 'Maior', 'Menor', 'Não localizado'];

            [['ia-gr-msd', 'ia-base-msd', 'sem_desconto'],
             ['ia-gr-mcd', 'ia-base-mcd', 'com_desconto']].forEach(([idGr, idBase, chave]) => {
                const medida = (corpo.mensalidade || {})[chave] || {};
                const contagem = medida.contagem || {};
                const alvoBase = document.getElementById(idBase);

                if (!corpo.processados) {
                    if (alvoBase) alvoBase.textContent = 'nenhum documento processado';
                    mostrarVazio(idGr, 'fa-hourglass-half',
                                 'A IA ainda não leu nenhum documento neste recorte.');
                    return;
                }
                if (!medida.tem_dado) {
                    if (alvoBase) alvoBase.textContent = '';
                    mostrarVazio(idGr, 'fa-ban',
                                 'Este documento não traz valor de mensalidade.');
                    return;
                }
                if (alvoBase) {
                    if (corpo.processados === corpo.total) {
                        alvoBase.innerHTML = formatarNumero(corpo.total) + ' documentos lidos';
                    } else {
                        alvoBase.innerHTML = '<span class="text-red-500 font-medium">' + formatarNumero(corpo.processados) + ' lidos de ' + formatarNumero(corpo.total) + ' documentos</span>';
                    }
                }
                /*  A régua dos dois é o TOTAL DE PROCESSADOS, que é a mesma base
                    das duas medidas. É o que deixa os cards comparáveis lado a
                    lado — a leitura óbvia de dois gráficos vizinhos é comparar as
                    barras, e réguas diferentes fariam essa leitura mentir.  */
                
                //  Uma palavra por balde (ver `ROTULO_MENSALIDADE`), e a faixa dos
                //  nomes sai da medida delas.
                const cats = ordem.map((b) => ROTULO_MENSALIDADE[b] || b);
                const vals = ordem.map((b) => contagem[b] || 0);
                const colors = CORES_MENSALIDADE(tema);
                desenhar(idGr, cats, vals, colors, corpo.processados, 'numero', true, corpo.processados);

            });

            pintarInconsistencias(corpo);
        };

        /*  Contador de pedidos: filtro clicado em sequência devolve respostas que
            podem voltar fora de ordem, e a antiga chegando depois repintaria a
            tabela com o recorte que já não está na barra.  */
        let pedidoAtual = 0;

        /*  Ficou uma consulta por fazer enquanto a aba estava escondida? Ver
            `recarregar` e o ouvinte de `docia:aba`.  */
        let pendenteDeRecarga = false;

        /*  A última resposta dos gráficos, guardada para repintar na troca de tema
            sem ir ao servidor: o recorte não mudou, só as cores.  */
        let ultimoResumo = null;

        /*  DUAS CHAMADAS PARA O MESMO RECORTE, e não uma. A tabela tem teto de
            linhas e os gráficos contam o recorte inteiro — juntar as duas faria a
            resposta da tabela carregar contagens que ela não usa, ou os gráficos
            herdarem o teto dela e passarem a mentir. `pedidoAtual` vale para as
            duas: é o mesmo clique.  */
        const recarregarResumo = (minhaVez) => {
            fetch(URL_RESUMO + '?' + parametros().toString())
                .then((resposta) => resposta.json())
                .then((corpo) => {
                    if (minhaVez !== pedidoAtual) return;
                    if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');
                    ultimoResumo = corpo;
                    receberInconsistencias(corpo.inconsistencias, corpo.documento);
                    pintarGraficos(corpo);
                })
                .catch((erro) => {
                    if (minhaVez !== pedidoAtual) return;
                    console.error('[Análise IA] Falha ao buscar o resumo:', erro);
                    /*  DIZER QUE FALHOU, em vez de deixar as barras anteriores no ar.
                        Sem isto o pedido que falha deixa os gráficos com os números do
                        recorte ANTERIOR — e eles não parecem velhos, parecem a
                        resposta ao filtro que acabou de ser clicado. A tabela ao lado
                        já marca "falhou" no selo; os gráficos precisavam do mesmo.  */
                    ultimoResumo = null;
                    ['ia-base-veredito', 'ia-base-msd', 'ia-base-mcd',
                     'ia-base-inconsistencias'].forEach((id) => {
                        const alvo = document.getElementById(id);
                        if (alvo) alvo.textContent = 'não foi possível atualizar';
                    });
                    ['ia-gr-veredito', 'ia-gr-msd', 'ia-gr-mcd',
                     'ia-gr-inconsistencias'].forEach((id) =>
                        mostrarVazio(id, 'fa-triangle-exclamation',
                                     'Erro ao carregar. Refaça o filtro para tentar de novo.'));
                    /*  As duas legendas nomeiam fatias que já não estão na tela. A
                        de inconsistências leva junto a coluna dela, para o recado de
                        erro ficar centrado no card e não na fatia de 28% do anel.  */
                    ['ia-legenda-veredito', 'ia-legenda-inconsistencias'].forEach((id) => {
                        const alvo = document.getElementById(id);
                        if (alvo) alvo.innerHTML = '';
                    });
                    const linhaInc = document.getElementById('ia-gr-inconsistencias');
                    if (linhaInc && linhaInc.parentElement) {
                        linhaInc.parentElement.classList.add('docia-anel-e-lista--sozinho');
                    }
                });
        };

        const recarregar = () => {
            atualizarContadores();
            pintarFiltrosAtivos();
            if (!el.corpo || !el.cabecalho) return;

            /*  ABA ESCONDIDA NÃO CONSULTA. As duas abas dividem a mesma barra e o
                mesmo botão "Atualizar", então tudo o que acontece lá chega aqui —
                e responder a cada clique com uma consulta de 63 colunas para uma
                tabela que ninguém está vendo é gastar duas vezes para mostrar uma.

                A DÍVIDA FICA ANOTADA e é paga no instante em que a aba abre (ver o
                ouvinte de `docia:aba`), então quem troca de aba encontra o recorte
                de agora — o que se perde é a consulta invisível, não o dado.  */
            if (!esteEstaVisivel()) {
                pendenteDeRecarga = true;
                return;
            }
            pendenteDeRecarga = false;

            marcarContagem('<b>...</b>', true);
            const minhaVez = ++pedidoAtual;
            recarregarResumo(minhaVez);

            fetch(URL_TABELA + '?' + parametros().toString())
                .then((resposta) => resposta.json())
                .then((corpo) => {
                    if (minhaVez !== pedidoAtual) return;
                    if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'resposta inesperada');

                    const linhas = corpo.linhas || [];
                    const total = corpo.total_rows || 0;

                    /*  QUAL documento vem da RESPOSTA, e não da caixa marcada: se a
                        rota tiver caído no de reserva por um parâmetro torto, é ele que
                        está na tela e é o que o título tem de dizer. Já o NOME sai da
                        própria caixa — o rótulo da resposta é o do motor (`CONTRATO`,
                        `BENEFÍCIOS`), e repeti-lo aqui deixaria o título no singular ao
                        lado de um controle escrito "Contratos".  */
                    if (el.titulo && corpo.documento) {
                        el.titulo.textContent = 'ANÁLISE DA IA — ' + nomeDoDocumento(corpo.documento);
                    }

                    /*  Quando corta, o selo DIZ que cortou: a rota tem teto de linhas
                        (ver `_limite_da_tabela`), e um "184.484" sobre 200 linhas na
                        tela seria mentira. Zero também aparece — é resultado, não
                        ausência de resultado, e sem o selo o filtro parece não ter
                        rodado.  */
                    marcarContagem(`<b>${formatarNumero(linhas.length)}</b>`
                          + `<span class="docia-contagem__de">de</span><b>${formatarNumero(total)}</b>`);

                    if (el.rolagem) el.rolagem.scrollTop = 0;
                    pintar(corpo.colunas || [], linhas);
                })
                .catch((erro) => {
                    if (minhaVez !== pedidoAtual) return;
                    console.error('[Análise IA] Falha ao buscar a tabela:', erro);
                    marcarContagem('falhou');
                    avisoNaTabela('Erro ao carregar a tabela.', 'text-red-400');
                });
        };

        /*  O filtro de instituições e a troca de abas disparam `docia:recarregar`
            ao aplicar a seleção ou quando a visualização exige atualização.  */
        window.addEventListener('docia:recarregar', recarregar);

        /* ==================================================================
           AS ETIQUETAS DE FILTRO ATIVO
           ==================================================================
           Mesma peça da outra aba, e pelo mesmo motivo: as linhas da tabela podem
           estar sendo recortadas por CINCO lugares — a barra lateral, a telinha de
           inconsistências, a busca, a legenda da rosca e o teto — e quatro deles
           ficam fora do campo de visão de quem está lendo a tabela.

           O PERÍODO E O DOCUMENTO SÃO FIXOS (sem X): a tela impõe exatamente um de
           cada, e um segundo caminho para removê-los deixaria a consulta sem o
           parâmetro — que do lado do servidor significa "todos", o oposto do que o
           X promete. Eles aparecem porque precisam ser LIDOS, não removidos.
           ================================================================== */

        const chip = (tipo, valor, acao, fixo) =>
            `<span class="docia-chip${fixo ? ' docia-chip--fixo' : ''}"
                  >
                <span class="docia-chip__tipo">${escaparHtml(tipo)}</span>
                <span class="docia-chip__valor">${escaparHtml(valor)}</span>
                ${fixo ? '' : `<button type="button" class="docia-chip__x" data-acao="${acao}"
                        aria-label="Remover o filtro ${escaparHtml(valor)}">
                    <i class="fa-solid fa-xmark"></i>
                </button>`}
            </span>`;

        const elFiltrosTabela = document.getElementById('ia-tabela-filtros');

        const pintarFiltrosAtivos = () => {
            if (!elFiltrosTabela) return;
            const etiquetas = [];

            marcados(caixasSemestre).forEach(
                (v) => etiquetas.push(chip('Semestre', v, 'semestre:' + v, true)));
            marcados(caixasDocumento).forEach(
                (v) => etiquetas.push(chip('Documento', v, 'documento:' + v, true)));

            [['Vínculo', 'filter-vinculo', 'vinculo'],
             ['Perfil', 'filter-perfil', 'perfil'],
             ['Mudou IES', 'filter-mudou-ies', 'mudou_ies'],
             ['Mudou bolsa', 'filter-mudou-bolsa', 'mudou_bolsa']].forEach(([rotulo, classe, acao]) => {
                marcados(nosFiltros('.' + classe)).forEach(
                    (v) => etiquetas.push(chip(rotulo, v, acao + ':' + v)));
            });

            const iesEscolhidas = iesDaAba();
            if (iesEscolhidas.length) {
                etiquetas.push(chip('IES', iesEscolhidas.length === 1
                    ? iesEscolhidas[0]
                    : iesEscolhidas.length + ' instituições', 'ies:*'));
            }

            inconsistenciasEscolhidas.forEach(
                (frase) => etiquetas.push(chip('Inconsistência', frase, 'inconsistencia:' + frase)));

            recorteVereditos.forEach(
                (v) => etiquetas.push(chip('Veredito', rotuloDoVeredito(v), 'veredito:' + v)));

            const campo = document.getElementById('ia-tabela-busca');
            const termo = (campo && campo.value || '').trim();
            if (termo) etiquetas.push(chip('Busca', termo, 'busca:*'));

            /*  O botão só aparece quando há algo REMOVÍVEL. Com apenas o período e o
                documento na faixa — que são fixos — "Limpar filtros" não teria o que
                limpar, e um botão que não faz nada é pior do que nenhum.  */
            const removiveis = etiquetas.length
                - marcados(caixasSemestre).length - marcados(caixasDocumento).length;
            if (removiveis > 0) {
                etiquetas.push('<button type="button" class="docia-chip docia-chip--acao"'
                    + ' data-acao="tudo">Limpar filtros</button>');
            }

            elFiltrosTabela.innerHTML = etiquetas.join('');
            elFiltrosTabela.classList.toggle('hidden', etiquetas.length === 0);
            elFiltrosTabela.classList.toggle('flex', etiquetas.length > 0);
        };

        if (elFiltrosTabela) {
            elFiltrosTabela.addEventListener('click', (evento) => {
                const botao = evento.target.closest('[data-acao]');
                if (!botao) return;
                //  `split` só no PRIMEIRO `:`: a frase de inconsistência tem vírgulas e
                //  pode ter dois-pontos, e parti-la em todos truncaria o valor.
                const [tipo, valor] = String(botao.dataset.acao).split(/:(.*)/);

                const desmarcar = (classe) => nosFiltros('.' + classe)
                    .forEach((caixa) => { if (caixa.value === valor) caixa.checked = false; });

                if (tipo === 'vinculo') desmarcar('filter-vinculo');
                else if (tipo === 'perfil') desmarcar('filter-perfil');
                else if (tipo === 'mudou_ies') desmarcar('filter-mudou-ies');
                else if (tipo === 'mudou_bolsa') desmarcar('filter-mudou-bolsa');
                else if (tipo === 'ies') {
                    if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                } else if (tipo === 'inconsistencia') {
                    inconsistenciasEscolhidas.delete(valor);
                    atualizarRotuloInc();
                } else if (tipo === 'veredito') recorteVereditos.delete(valor);
                else if (tipo === 'busca') {
                    const campo = document.getElementById('ia-tabela-busca');
                    if (campo) campo.value = '';
                    const limpar = document.getElementById('ia-btn-limpar-busca');
                    if (limpar) limpar.classList.add('hidden');
                } else if (tipo === 'tudo') {
                    //  TUDO menos o período e o documento: eles são obrigatórios, e
                    //  zerá-los deixaria a tela sem recorte nenhum — que não é um
                    //  estado que ela saiba mostrar.
                    ['filter-vinculo', 'filter-perfil', 'filter-mudou-ies', 'filter-mudou-bolsa']
                        .forEach((classe) => nosFiltros('.' + classe)
                            .forEach((caixa) => (caixa.checked = false)));
                    if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                    inconsistenciasEscolhidas.clear();
                    atualizarRotuloInc();
                    recorteVereditos.clear();
                    const campo = document.getElementById('ia-tabela-busca');
                    if (campo) campo.value = '';
                    const limpar = document.getElementById('ia-btn-limpar-busca');
                    if (limpar) limpar.classList.add('hidden');
                } else {
                    return;
                }
                recarregar();
            });
        }

        /* ==================================================================
           BUSCA, EXPANDIR E COPIAR — a mesma tabela da outra aba
           ================================================================== */

        /*  A BUSCA NÃO SAI A CADA TECLA: ela vai ao servidor, e "2090214" dispararia
            sete requisições sobre 80 mil linhas cujas respostas podem voltar fora de
            ordem — a tela terminaria mostrando o resultado de "209". 350 ms é o
            intervalo em que uma digitação normal não gera pedido no meio da palavra e
            ainda parece imediato ao parar.  */
        const campoBuscaTabela = document.getElementById('ia-tabela-busca');
        const btnLimparBusca = document.getElementById('ia-btn-limpar-busca');
        if (campoBuscaTabela) {
            let relogio = null;
            let anterior = campoBuscaTabela.value;
            campoBuscaTabela.addEventListener('input', () => {
                if (btnLimparBusca) {
                    btnLimparBusca.classList.toggle('hidden', campoBuscaTabela.value.length === 0);
                }
                // Teclas que não mudam o texto (setas, Ctrl) não são uma busca nova.
                if (campoBuscaTabela.value === anterior) return;
                anterior = campoBuscaTabela.value;
                clearTimeout(relogio);
                relogio = setTimeout(recarregar, 350);
            });
        }
        if (btnLimparBusca && campoBuscaTabela) {
            btnLimparBusca.addEventListener('click', () => {
                campoBuscaTabela.value = '';
                btnLimparBusca.classList.add('hidden');
                campoBuscaTabela.focus();
                recarregar();
            });
        }

        /*  EXPORTAR leva os mesmos parâmetros da tabela, MENOS o `expandido`: o teto
            é da tela, e o arquivo é sempre completo. `location.assign` e não `fetch`:
            a resposta é um anexo, e quem sabe salvar anexo é o navegador.  */
        const btnExportar = document.getElementById('ia-btn-exportar');
        if (btnExportar) {
            btnExportar.addEventListener('click', () => {
                const consulta = parametros();
                consulta.delete('expandido');
                window.location.assign(URL_EXPORTAR + '?' + consulta.toString());
            });
        }

        /*  EXPANDIR. O card precisa SAIR da árvore para cobrir a janela: `.menu-shell`
            tem `backdrop-blur`, e `backdrop-filter` cria bloco contendo para
            descendentes `position: fixed` — de dentro dela o `inset: 1rem` passaria a
            valer contra a casca e o card pararia antes da borda da tela. É a mesma
            armadilha que os dois modais contornam vivendo fora da casca.

            A âncora é um COMENTÁRIO que fica no lugar do card enquanto ele está no
            `body`; ao fechar, `replaceWith` o devolve exatamente de onde saiu, sem
            depender de índice — que mudaria se o markup mudasse.  */
        const btnExpandir = document.getElementById('ia-btn-expandir');
        const cardTabela = document.getElementById('ia-card-tabela');
        if (btnExpandir && cardTabela) {
            const ancora = document.createComment('ia-card-tabela');
            let expandido = false;

            const alternar = (abrir) => {
                if (abrir) {
                    cardTabela.replaceWith(ancora);
                    document.body.appendChild(cardTabela);
                } else if (ancora.parentNode) {
                    ancora.replaceWith(cardTabela);
                }
                expandido = abrir;
                cardTabela.classList.toggle('docia-detalhamento--expandido', abrir);
                btnExpandir.classList.toggle('docia-botao-ativo', abrir);
                btnExpandir.setAttribute('aria-pressed', abrir ? 'true' : 'false');
                const icone = document.getElementById('ia-icone-expandir');
                if (icone) icone.className = 'fa-solid text-xs ' + (abrir ? 'fa-compress' : 'fa-expand');
                // O teto de linhas muda com o tamanho (200 no card, 500 expandido),
                // então a consulta tem de ser refeita.
                recarregar();
            };

            btnExpandir.addEventListener('click', () => alternar(!expandido));
            // Esc fecha: expandido, o card cobre a tela e o botão sai do campo de visão
            // de quem estava lendo o fim da tabela.
            document.addEventListener('keydown', (evento) => {
                if (evento.key === 'Escape' && expandido) alternar(false);
            });
        }

        /* ------------------------------------------------------------------
           COPIAR A COLUNA INTEIRA
           ------------------------------------------------------------------
           Leva o RECORTE, e não a página: a tabela mostra 200 linhas de até 80 mil,
           e copiar o que está à vista responderia a pergunta errada. A rota devolve
           a coluna inteira sob os mesmos filtros (`apenas_coluna`).  */

        const avisar = (mensagem, deuCerto) => {
            let caixa = document.getElementById('toast-container');
            if (!caixa) {
                caixa = document.createElement('div');
                caixa.id = 'toast-container';
                /*  ABAIXO DO CABEÇALHO, e não colado no topo: em `top-4` o aviso
                    nasce sobre o botão "Voltar" e tapa a única saída da tela por
                    quatro segundos. O valor é inline porque o Tailwind do portal é
                    bundle purgado — classe nova falharia em silêncio.  */
                caixa.className = 'fixed right-4';
                caixa.style.top = '7.5rem';
                caixa.style.zIndex = '99999';
                document.body.appendChild(caixa);
            }
            const aviso = document.createElement('div');
            aviso.className = 'docia-aviso ' + (deuCerto ? 'docia-aviso--ok' : 'docia-aviso--erro');
            aviso.innerHTML = '<i class="fa-solid ' + (deuCerto ? 'fa-check' : 'fa-xmark')
                + ' docia-aviso__icone"></i><span>' + escaparHtml(mensagem) + '</span>';
            caixa.appendChild(aviso);
            setTimeout(() => aviso.remove(), 4000);
        };

        const copiar = (texto) => {
            if (navigator.clipboard && window.isSecureContext) {
                return navigator.clipboard.writeText(texto);
            }
            /*  Reserva para HTTP: `navigator.clipboard` só existe em contexto seguro,
                e o portal é servido por um túnel que nem sempre é HTTPS.  */
            return new Promise((resolve, reject) => {
                const campo = document.createElement('textarea');
                campo.value = texto;
                campo.style.position = 'fixed';
                campo.style.left = '-999999px';
                document.body.appendChild(campo);
                campo.select();
                try {
                    if (document.execCommand('copy')) resolve(); else reject();
                } catch (erro) {
                    reject(erro);
                } finally {
                    campo.remove();
                }
            });
        };

        if (el.cabecalho) {
            el.cabecalho.addEventListener('click', (evento) => {
                const botao = evento.target.closest('.docia-btn-copiar-coluna');
                if (!botao) return;
                const coluna = botao.dataset.coluna;
                if (!coluna) return;

                const original = botao.innerHTML;
                botao.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                botao.disabled = true;

                const consulta = parametros();
                // O teto não vale aqui: quem copia quer a coluna inteira do recorte.
                consulta.delete('expandido');
                consulta.append('apenas_coluna', coluna);

                fetch(URL_TABELA + '?' + consulta.toString())
                    .then((resposta) => resposta.json())
                    .then((corpo) => {
                        botao.innerHTML = original;
                        botao.disabled = false;
                        if (corpo.status !== 'ok') throw new Error(corpo.mensagem || 'falhou');
                        const valores = (corpo.valores || [])
                            .map((v) => String(v).trim()).filter((v) => v !== '');
                        if (!valores.length) {
                            avisar('A coluna está vazia neste recorte.', false);
                            return;
                        }
                        copiar(valores.join('\n'))
                            .then(() => avisar(formatarNumero(valores.length)
                                               + ' valores copiados.', true))
                            .catch(() => avisar('Não foi possível copiar.', false));
                    })
                    .catch((erro) => {
                        botao.innerHTML = original;
                        botao.disabled = false;
                        console.error('[Análise IA] Falha ao copiar a coluna:', erro);
                        avisar('Não foi possível ler a coluna.', false);
                    });
            });
        }

        /* ==================================================================
           MODO DE VISUALIZAÇÃO
           ==================================================================
           Não são duas telas: são duas leituras do mesmo recorte. Por isso a
           troca não vai ao servidor — os filtros continuam valendo, e o que
           muda é o que está no ar.
           ================================================================== */

        const aplicarModo = (modo) => {
            const emRelatorios = modo === 'relatorios';
            if (vistaPerformance) vistaPerformance.style.display = emRelatorios ? 'none' : 'flex';
            if (vistaRelatorios) vistaRelatorios.style.display = emRelatorios ? 'flex' : 'none';
        };

        radiosModo.forEach((radio) => radio.addEventListener('change', () => {
            if (!radio.checked) return;
            if (window.dociaLembrarModo) window.dociaLembrarModo(radio.value);
            aplicarModo(radio.value);
        }));

        const exclusividadeSemestre = (evento) => {
            if (!evento.target.checked) {
                evento.target.checked = true;
                return;
            }
            caixasSemestre.forEach((caixa) => {
                if (caixa !== evento.target) caixa.checked = false;
            });
            recarregar();
        };
        caixasSemestre.forEach((caixa) => caixa.addEventListener('change', exclusividadeSemestre));

        /*  DOCUMENTO É ESCOLHA ÚNICA E OBRIGATÓRIA — diferente da aba Envios &
            Pendências, onde ele é atalho de fatia e pode ficar vazio.

            Aqui a tabela mostra todas as colunas DA ABA escolhida, e as abas não têm o
            mesmo conjunto: dois marcados não teriam cabeçalho possível, e nenhum
            marcado não teria aba de onde ler. Marcar outro troca; clicar no que já está
            aceso não apaga, porque "nenhum documento" não é um estado desta tela.  */
        const exclusividadeDocumento = (caixa) => {
            if (caixa.checked) {
                caixasDocumento.forEach((outra) => {
                    if (outra !== caixa) outra.checked = false;
                });
                return true;
            }
            caixa.checked = true;
            return false;
        };

        caixasDocumento.forEach((caixa) => caixa.addEventListener('change', () => {
            if (!exclusividadeDocumento(caixa)) return;
            /*  As frases do documento que sai não existem no que entra — as do RIAF
                falam de assinatura, as do contrato de mensalidade. Levá-las adiante
                deixaria um recorte impossível valendo em silêncio, e a tabela
                voltaria vazia sem nada na barra explicando por quê.  */
            inconsistenciasEscolhidas.clear();
            atualizarRotuloInc();
            recarregar();
        }));

        /*  OS QUATRO PARES SE EXCLUEM: "Ativo E Desligado" marcados é o mesmo
            recorte de nenhum dos dois, e o controle prometeria uma decisão para
            aceitar uma contradição. Mesma regra da aba Envios & Pendências.

            Continuam sendo caixas, e não rádio, por causa do terceiro estado:
            rádio não desmarca com um segundo clique, e "tanto faz" é a resposta
            mais comum das quatro perguntas. Marcar um apaga o outro; clicar no
            que já está aceso apaga ele mesmo, pelo comportamento nativo da caixa.

            UM ouvinte com as duas coisas dentro, e não dois registrados à parte:
            na mesma caixa eles disparam na ordem em que foram registrados, e a
            consulta precisa sair DEPOIS de o par ter sido desfeito — senão ela
            ainda leva os dois valores.  */
        const exclusivo = (classe) => {
            const caixas = nosFiltros('.' + classe);
            caixas.forEach((caixa) => caixa.addEventListener('change', () => {
                if (caixa.checked) {
                    caixas.forEach((outra) => {
                        if (outra !== caixa) outra.checked = false;
                    });
                }
                recarregar();
            }));
        };

        ['filter-vinculo', 'filter-perfil',
         'filter-mudou-ies', 'filter-mudou-bolsa'].forEach(exclusivo);

        /*  "RESTAURAR PADRÃO" É DA ABA QUE ESTÁ NA TELA. O botão é um só, no
            cabeçalho da barra, e os dois módulos o escutam — sem esta saída, um
            clique aqui zeraria também o recorte da aba vizinha, que a pessoa não
            está vendo e não pediu para mexer.  */
        const botaoLimpar = document.getElementById('btn-clear-filters');
        if (botaoLimpar) {
            botaoLimpar.addEventListener('click', () => {
                if (!esteEstaVisivel()) return;
                nosFiltros(
                    '.filter-semestre, .filter-vinculo, .filter-perfil,'
                    + ' .filter-mudou-ies, .filter-mudou-bolsa'
                ).forEach((caixa) => (caixa.checked = false));
                // O documento não zera: volta ao padrão, que é o CONTRATO.
                caixasDocumento.forEach((caixa) =>
                    (caixa.checked = caixa.value === 'CONTRATO'));
                inconsistenciasEscolhidas.clear();
                atualizarRotuloInc();
                // O filtro de IES vive noutro escopo e não se zera sozinho: sem
                // isto o botão limparia a barra e deixaria as instituições presas.
                if (typeof window.resetFiltroIES === 'function') window.resetFiltroIES();
                recarregar();
            });
        }

        /*  TROCA DE TEMA REPINTA, sem ir ao servidor. As cores das barras são
            degraus próprios de cada tema (ver `PALETA_OVG`), não uma inversão
            automática do claro — e os rótulos dos eixos seguem os tokens de
            texto, que também mudam.  */
        document.addEventListener('ggci:tema', () => {
            if (ultimoResumo) pintarGraficos(ultimoResumo);
        });

        /* ==================================================================
           OS GRÁFICOS ACOMPANHAM A CAIXA
           ==================================================================
           MESMO MECANISMO DE `ajustarAlturas` EM `dash_documentos_ia.js`, e não
           uma segunda ideia: as cinco roscas da outra aba já resolveram este
           problema, e a versão anterior daqui errava nos três pontos que a de lá
           acerta. Era isso que entortava a rosca quando a barra de filtros abria.

           1. ZERAR `min-height` ANTES DE MEDIR. Depois de renderizar, o Apex
              escreve `min-height: <altura>px` INLINE na nossa caixa. Isso anula o
              `min-height: 0` do template e trava o piso da caixa na maior altura
              que ela já teve: ela cresce, mas nunca encolhe. Medir sem zerar é
              medir o passado.

           2. SÓ REDESENHAR SE A MEDIDA DO DESENHO MUDOU. Abrir a barra muda a
              LARGURA dos cards, não a altura — e a largura das BARRAS o Apex
              acompanha sozinho, pelo `resize` da janela. Sem esta guarda, cada
              quadro da animação disparava `updateOptions` nos quatro gráficos, e
              cada chamada redesenha o SVG inteiro. A rosca aparecia oval porque
              estava sendo redesenhada no meio da transição, medindo uma caixa que
              ainda estava a caminho. (Nos ANÉIS a largura conta para o tamanho do
              desenho — ver `alturaDoDesenho` —, e é por isso que a guarda compara o
              que vai ser desenhado, e não a caixa.)

           3. ESPERAR A TRANSIÇÃO TERMINAR. A barra leva 500 ms; medir antes disso
              é medir uma largura intermediária. `requestAnimationFrame`, que era o
              que estava aqui, faz exatamente o contrário: mede a cada quadro.

           O `resize` da janela que o botão da barra dispara (ver `forcarResize` em
           `dash_documentos_ia.js`) é o que reavisa a LARGURA; este observador
           cuida da ALTURA. Os dois juntos são o que a outra aba já tinha.
           ================================================================== */
        const ajustarAlturasIA = () => {
            Object.keys(graficos).forEach((id) => {
                const alvo = document.getElementById(id);
                if (!alvo || !graficos[id]) return;

                alvo.style.minHeight = '0px';
                const altura = alvo.clientHeight;
                /*  Caixa sem altura é caixa escondida — esta aba pode estar fora
                    da tela. Medir aqui gravaria o piso de 140px como se fosse a
                    altura boa, e ela voltaria assim quando a aba abrisse.  */
                if (!altura) return;

                /*  A GUARDA COMPARA A MEDIDA DO DESENHO, e não a da caixa: nos anéis
                    a largura entra na conta da altura (ver `alturaDoDesenho`), então
                    comparar só a altura da caixa deixaria passar em branco a barra de
                    filtros abrindo — que muda a largura e mais nada. Nas barras as
                    duas medidas são a mesma coisa, e a guarda segue valendo o que
                    valia: largura sozinha não redesenha.  */
                const desenho = alturaDoDesenho(id, altura, alvo.clientWidth);
                if (graficos[id].__alturaAplicada === desenho) return;
                graficos[id].__alturaAplicada = desenho;

                graficos[id].updateOptions(
                    { chart: { height: desenho } }, false, false);
            });
        };

        /*  O OBSERVADOR OLHA AS CAIXAS, e não só a vista inteira — é o que a outra
            aba já faz (`caixasDeGrafico()` em `dash_documentos_ia.js`).

            A vista sozinha não bastava porque ela quase nunca muda de altura: quem
            muda é a REPARTIÇÃO dela. `pintarGraficos` desenha a rosca e só depois
            escreve a base dos seis KPIs do topo; a linha de texto que nasce ali
            empurra 9px para fora da faixa dos gráficos, a caixa encolhe, o desenho
            fica maior do que ela — e a vista, que não mudou de tamanho, não avisava
            ninguém. Medido na bancada: svg de 191px numa caixa de 182px, em toda
            carga da página.  */
        if (window.ResizeObserver) {
            let pendente = null;
            const observador = new ResizeObserver(() => {
                clearTimeout(pendente);
                pendente = setTimeout(ajustarAlturasIA, 250);
            });
            if (vistaPerformance) observador.observe(vistaPerformance);
            ['ia-gr-veredito', 'ia-gr-msd', 'ia-gr-mcd', 'ia-gr-inconsistencias'].forEach((id) => {
                const caixa = document.getElementById(id);
                if (caixa) observador.observe(caixa);
            });
        }

        /* ==================================================================
           QUANDO ESTA ABA ENTRA NA TELA
           ==================================================================
           DUAS COISAS ACONTECEM, e nenhuma delas é recarregar a página.

           A CONSULTA PENDENTE. Enquanto a aba está escondida, `recarregar` não
           vai ao servidor: seria uma consulta de 63 colunas para uma tabela que
           ninguém está vendo, a cada clique dado na outra aba. Em vez disso ela
           anota que ficou devendo, e é aqui que a dívida se paga — a aba abre já
           com o recorte atual, não com o de quando foi fechada.

           A MEDIDA DOS GRÁFICOS. O Apex mede a caixa na hora de desenhar, e
           enquanto a aba está escondida a caixa não tem largura nenhuma: um
           gráfico renderizado ali nasce com 0 de largura e é isso que chega
           torto na tela. O `resize` da janela reavisa a largura, e
           `ajustarAlturasIA` a altura.

           O `requestAnimationFrame` espera o CSS aplicar o `display` novo: no
           mesmo quadro do evento a caixa ainda mede zero.
           ================================================================== */
        document.addEventListener('docia:aba', (evento) => {
            if (!evento.detail || evento.detail.aba !== 'analise') return;
            requestAnimationFrame(() => {
                if (pendenteDeRecarga) recarregar();
                window.dispatchEvent(new Event('resize'));
                ajustarAlturasIA();
            });
        });

        /*  O modo LEMBRADO manda, e o marcado no HTML é a reserva — ver
            `estado_aba.js`. Os rádios também são reescritos, senão a barra
            mostraria "Performance" aceso com a vista de Relatórios no ar.  */
        const marcado = Array.from(radiosModo).find((radio) => radio.checked);
        const modoInicial = window.dociaModoLembrado
            ? window.dociaModoLembrado((marcado && marcado.value) || 'performance',
                                       ['performance', 'relatorios'])
            : ((marcado && marcado.value) || 'performance');
        radiosModo.forEach((radio) => (radio.checked = radio.value === modoInicial));
        aplicarModo(modoInicial);
        recarregar();
    };

    document.addEventListener('DOMContentLoaded', iniciar);
    document.addEventListener('turbo:load', iniciar);
})();
