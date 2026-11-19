/**
 * === ARQUIVO: static/js/console-motor.js ===
 * Propósito: desenho do "CONSOLE DE PROCESSAMENTO" dos motores (Análise IA e Renovação de
 *   Cadastramento). Uma linha estruturada entra, HTML sai, igual nas duas telas.
 *
 * TIPOS DE LINHA ({tipo, ...}):
 *   comando — `ovg@probem-ai: ~ $ <texto>`, abre uma fase;
 *   item    — `✔ CAMPO │ CAMPO │ CAMPO │ texto`; `nivel` ok | alerta | erro | retry;
 *   sub     — `↳ texto`, passo em andamento, em cinza;
 *   selo    — etiqueta colorida (`cor` emerald | red | indigo | yellow, `rotulo`, `texto`);
 *   fim     — `exit 0 — ✔ Concluído em <texto>`;
 *   texto   — linha solta, sem marcação.
 *
 * TEXTO É DADO: nome de IES, mensagem de erro e trecho de log passam por `esc` antes de virar
 * HTML. As cores são utilitárias que existem no bundle purgado ou no `console.css`.
 */
(function () {
    const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));

    const prompt = (cmd, extra = '', topo = false) => `<div class="flex items-center gap-1 ${topo ? 'mb-1' : 'mt-4 mb-1.5'} font-mono text-[14px] break-words">`
        + '<span class="text-pink-600 font-bold">ovg@probem-ai:</span><span class="text-purple-600"> ~</span>'
        + `<span class="text-purple-400"> $</span><span class="text-purple-900 font-bold"> ${cmd}</span>${extra}</div>`;

    const CORES_SELO = {
        emerald: ['bg-emerald-50', 'border-emerald-200', 'text-emerald-600', 'text-emerald-300', '✔'],
        red: ['bg-red-50', 'border-red-200', 'text-red-600', 'text-red-300', '!'],
        indigo: ['bg-purple-50', 'border-purple-200', 'text-purple-600', 'text-purple-300', '›'],
        yellow: ['bg-yellow-50', 'border-yellow-200', 'text-yellow-600', 'text-yellow-300', '!'],
    };
    const ICONE_ITEM = {
        ok: '<span class="text-green-500">✔</span>',
        alerta: '<span class="text-yellow-500 font-bold">!</span>',
        erro: '<span class="text-red-500 font-bold">✖</span>',
        retry: '<span class="text-purple-400 font-bold">↻</span>',
    };
    const COR_CAMPO = ['text-pink-600 uppercase font-semibold', 'text-purple-600 uppercase', 'text-emerald-600'];
    const SEPARADOR = ' <span class="text-purple-200">│</span> ';

    function linha(l) {
        switch (l.tipo) {
            case 'comando':
                return prompt(esc(l.texto));
            case 'fim':
                return prompt('exit 0', ' <span class="text-gray-500 mx-1">—</span> '
                    + `<span class="text-emerald-400 font-semibold ml-1">✔ Concluído em ${esc(l.texto)}</span>`);
            case 'sub':
                return `<div class="ml-4 my-0.5 text-[13px] text-gray-400">↳ ${esc(l.texto)}</div>`;
            case 'selo': {
                const [bg, borda, cor, barra, icone] = CORES_SELO[l.cor] || CORES_SELO.indigo;
                return `<div class="my-2"><span class="${bg} border ${borda} px-2.5 py-1 rounded shadow-sm inline-flex items-center break-words">`
                    + `<span class="${cor} font-bold text-[11px] uppercase mr-2">${icone} ${esc(l.rotulo)}</span>`
                    + `<span class="${barra} mx-2">|</span><span class="text-purple-800 text-[13px]">${esc(l.texto)}</span></span></div>`;
            }
            case 'item': {
                const campos = (l.campos || []).map((c, i) => `<span class="${COR_CAMPO[i] || COR_CAMPO[2]}">${esc(c)}</span>`);
                return `<div class="ml-4 my-0.5 text-[13px] font-mono break-words">${ICONE_ITEM[l.nivel] || ICONE_ITEM.ok} `
                    + campos.concat(`<span class="text-purple-800">${esc(l.texto)}</span>`).join(SEPARADOR) + '</div>';
            }
            default:
                return `<div class="ml-4 my-0.5 text-[13px] text-purple-800 break-words">${esc(l.texto)}</div>`;
        }
    }

    /** Console inteiro: o comando de entrada, as linhas e o cursor girando enquanto roda. */
    function html(comandoInicial, linhas, rodando) {
        return prompt(esc(comandoInicial), '', true)
            + `<div class="mt-3 font-mono text-[14px] tracking-tight leading-snug text-gray-700">${linhas.map(linha).join('')}</div>`
            + (rodando ? '<span class="console-spinner"></span>' : '');
    }

    window.ConsoleMotor = { html, linha, esc };
})();
