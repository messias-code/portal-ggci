/**
 * === ARQUIVO: apps/automacoes/analise_ia/static/analise_ia/js/log_ia.js ===
 * Propósito: transforma o log cru do motor da Análise IA (texto do `print`) nas linhas
 *   estruturadas do `ConsoleMotor` (static/js/console-motor.js) — o mesmo console da
 *   Renovação de Cadastramento.
 *
 * POR QUE UM LEITOR, E NÃO REGEX DE HTML: o motor roda tarefas em paralelo e os `print`
 * chegam grudados ("…Pulando.[ETL_PROGRESSO] 1/16", "…filtro![ANÁLISE | …"), exceção do
 * Playwright traz "Call log:" em várias linhas e a retentativa sai como "🔄 [tag] │ …".
 * Aqui o texto é primeiro separado em linhas lógicas e cada uma vira UM tipo de linha.
 *
 * Formatos que o motor escreve (levantados dos logs reais em 17/11/2026):
 *   [P1 | P2 | P3] mensagem          → item (⚠️ alerta, ❌ erro, │ Reiniciando = retry)
 *   ! AVISO │ RELATÓRIO │ … │ texto  → item alerta
 *   🚀/🔄/🗄️ início de fase          → comando
 *   🎉 … concluída                   → selo verde;  🎉 Processamento concluído → fim
 *   🚨 [SISTEMA] …                   → selo vermelho
 *   ❌ FALHA CRÍTICA: + traceback    → selo vermelho com a última linha do traceback
 *   ⏱ / 📊 (tempo por bloco), [*_PROGRESSO], Call log → não aparecem
 */
(function () {
    const TAG = /^\[([^\[\]|]+)\|([^\[\]|]+)\|([^\[\]]+)\]\s*(.*)$/;
    const EMOJIS = /⚠️|❌|✅|🛠️|⏱️|🔄|🛑|🚨|🎉|💾|📥|🔍|🗄️|🤖|➕|🌐|🚀/gu;
    const limpar = (t) => t.replace(EMOJIS, '').replace(/->/g, '→').replace(/\s+/g, ' ').trim();

    // Linhas que o motor escreve com emoji e que viram outro tipo de linha.
    const FIXAS = [
        [/^🚀 Iniciando processamento massivo/, () => ({ tipo: 'comando', texto: 'extracao_ia --run' })],
        [/^🔄 Consolidando e limpando/, () => ({ tipo: 'comando', texto: 'consolidacao_ia --run' })],
        [/^🗄️ Analisando regras de negócio/, () => ({ tipo: 'comando', texto: 'ggci_ia --run' })],
        [/^🚀 Inciando limpeza/, () => ({ tipo: 'sub', texto: 'Limpando e recriando os diretórios de extração…' })],
        [/^🌐 Baixando planilhas do ScriptCase \((\d+) tarefas\)/, (m) => ({ tipo: 'sub', texto: `Baixando planilhas do ScriptCase (${m[1]} tarefas)…` })],
        [/^🎉 Extração concluída: (.*?)\.?$/, (m) => ({ tipo: 'selo', cor: 'emerald', rotulo: 'EXTRAÇÃO', texto: m[1] })],
        [/^🎉 Consolidação concluída: (.*?)\.?$/, (m) => ({ tipo: 'selo', cor: 'emerald', rotulo: 'CONSOLIDAÇÃO', texto: m[1] })],
        [/^🎉 Regras aplicadas: (.*?)\.?$/, (m) => ({ tipo: 'selo', cor: 'emerald', rotulo: 'RELATÓRIO', texto: m[1] })],
        [/^🎉 SUPER-EXTRAÇÃO CONCLUÍDA/, () => ({ tipo: 'selo', cor: 'emerald', rotulo: 'CONCLUÍDO', texto: 'Relatório Geral gerado com sucesso!' })],
        [/^🎉 Processamento concluído em (.*?)!?$/, (m) => ({ tipo: 'fim', texto: m[1] })],
        [/^⚠️ EXTRAÇÃO VAZIA/, () => ({ tipo: 'selo', cor: 'yellow', rotulo: 'FILTRO VAZIO', texto: 'Combinação de filtros não gerou dados.' })],
        [/^🚨 \[SISTEMA\] Processo de IA abortado manualmente/, () => ({ tipo: 'selo', cor: 'red', rotulo: 'ABORTADO PELO USUÁRIO', texto: 'Processo interrompido manualmente.' })],
        [/^🚨 \[SISTEMA\] (.*)$/, (m) => ({ tipo: 'selo', cor: 'red', rotulo: 'ABORTADO', texto: m[1] })],
        [/^🛑 Processo abortado: (.*)$/, (m) => ({ tipo: 'selo', cor: 'red', rotulo: 'ABORTADO', texto: m[1] })],
        [/^✅ Gerado com sucesso e colunas ordenadas: .*?([^\\/]+\.xlsx)$/, (m) => ({ tipo: 'sub', texto: `${m[1]} salvo` })],
        [/^➕ Injetados (\d+) registros 'Ausentes' \((\w+)\)/, (m) => ({ tipo: 'sub', texto: `+${m[1]} bolsistas pendentes (${m[2]})` })],
    ];
    // Ruído: diagnóstico de tempo e linhas que só repetem o que outra já diz.
    const OCULTAS = /^(⏱|📊 Timing|🔄 Processando:|🛑 Processo abortado de forma inteligente|🚀 Iniciando GGCI|🔄$)/;

    /** Texto cru → linhas lógicas (sem carimbo de hora, sem marcador de progresso). */
    function separar(cru) {
        return (cru || '')
            .replace(/\[\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}\]\s*/g, '')
            // print paralelo grudado: quebra antes de [tag | …], de marcador e de emoji de abertura
            .replace(/(?<!^|\n)(?=\[[^\[\]|\n]+\|[^\[\]|\n]+\|[^\[\]\n]+\])/g, '\n')
            .replace(/(?<!^|\n)(?=\[(?:EXTRACAO|ETL)_PROGRESSO\])/g, '\n')
            .replace(/(?<!^|\n|🔄 )(?=(?:🚀|🎉|🚨|🌐|🗄️ Analisando|🔄 Consolidando))/gu, '\n')
            .split('\n')
            .map((l) => l.trim())
            .filter((l) => l && !/^\[(?:EXTRACAO|ETL)_PROGRESSO\]/.test(l));
    }

    function interpretar(cru) {
        const linhas = separar(cru);
        const saida = [];
        for (let i = 0; i < linhas.length; i++) {
            let l = linhas[i];

            // Exceção do Playwright: "Call log:" e as linhas "- waiting for …" que seguem.
            if (l === 'Call log:' || /^- (waiting for|navigating to|locator resolved)/.test(l)) continue;

            // Falha crítica: o traceback inteiro vira um selo com a mensagem final.
            if (/^❌ FALHA CRÍTICA/.test(l)) {
                let final = '';
                while (i + 1 < linhas.length && !TAG.test(linhas[i + 1]) && !/^(🚨|🎉|🚀)/u.test(linhas[i + 1])) {
                    i++;
                    if (/^[A-Za-z_.]+(Error|Exception|Invalid|Interrupt)\b.*:/.test(linhas[i]) || /^[A-Za-z_.]+Error$/.test(linhas[i])) final = linhas[i];
                }
                saida.push({ tipo: 'selo', cor: 'red', rotulo: 'FALHA CRÍTICA', texto: final || 'Erro inesperado no motor (detalhes no log do servidor).' });
                continue;
            }

            // Retentativa: "🔄 [tag] │ Reiniciando…" — o emoji pode ter ficado na linha de cima.
            l = l.replace(/^🔄\s*(?=\[)/u, '');
            if (OCULTAS.test(l)) continue;

            const tag = TAG.exec(l);
            if (tag) {
                const campos = [tag[1], tag[2], tag[3]].map((c) => c.trim());
                let msg = tag[4];
                if (/^│/.test(msg)) {
                    const n = /Tentativa (\d+)/.exec(msg);
                    saida.push({ tipo: 'item', nivel: 'retry', campos, texto: n ? `Reiniciando (tentativa ${n[1]})…` : limpar(msg.replace(/^│/, '')) });
                    continue;
                }
                const nivel = msg.includes('❌') ? 'erro' : (msg.includes('⚠️') ? 'alerta' : 'ok');
                saida.push({ tipo: 'item', nivel, campos, texto: limpar(msg) });
                continue;
            }

            const aviso = /^!\s*(.+?)\s*│\s*(.+?)\s*│\s*(.+?)\s*│\s*(.*)$/.exec(l);
            if (aviso) {
                saida.push({ tipo: 'item', nivel: 'alerta', campos: [aviso[1], aviso[2], aviso[3]], texto: aviso[4] });
                continue;
            }

            const fixa = FIXAS.find(([re]) => re.test(l));
            if (fixa) {
                saida.push(fixa[1](fixa[0].exec(l)));
                continue;
            }

            // Qualquer outra linha com emoji de passo vira sub; o resto sai como texto.
            if (/^(💾|📥|🔍|🗄️|🤖|🛠️|✅)/u.test(l)) saida.push({ tipo: 'sub', texto: limpar(l) });
            else if (/^❌/u.test(l)) saida.push({ tipo: 'selo', cor: 'red', rotulo: 'ERRO', texto: limpar(l) });
            else if (/^⚠️/u.test(l)) saida.push({ tipo: 'selo', cor: 'yellow', rotulo: 'AVISO', texto: limpar(l) });
            else saida.push({ tipo: 'texto', texto: limpar(l) });
        }
        return saida;
    }

    const api = { interpretar, separar };
    if (typeof module !== 'undefined') module.exports = api;   // testes no Node
    if (typeof window !== 'undefined') window.LogIA = api;
})();
