/**
 * Web Worker do Polichat — polling de sincronização em thread separada.
 *
 * Por quê: um setInterval rodando na thread da página é throttled/pausado pelo
 * navegador (Chrome, Firefox, etc.) assim que a aba fica em segundo plano por
 * alguns segundos — é uma economia de bateria/CPU do próprio navegador, não algo
 * que o código da página controla. Um Worker roda numa thread à parte e não sofre
 * esse throttling, então o dashboard continua checando e puxando atualizações do
 * backend mesmo com o usuário em outra aba, janela ou aplicativo.
 */
let ativo = false;
let ticks = 0;

self.onmessage = (e) => {
    if (e.data && e.data.type === 'start') ativo = true;
    if (e.data && e.data.type === 'stop') ativo = false;
};

setInterval(() => {
    if (!ativo) return;
    ticks++;
    if (ticks % 3 !== 0) return;

    fetch(`/dashboards/polichat/api/status-loop/?_t=${Date.now()}`)
        .then(r => r.json())
        .then(data => self.postMessage(data))
        .catch(() => {});
}, 1000);
