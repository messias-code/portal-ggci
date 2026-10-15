/* === ARQUIVO: .claude/tools/video/runtime.js ===
   Injetado pelo fazer_video.py na animacao.html. Dá à página uma linha do tempo
   controlada de fora: o Python chama __prepara uma vez e __quadro(t) a cada quadro.

   O que a página ganha:
   - [data-cena="id"]  aparece no início da fala daquela cena e some quando entra a
                       próxima (troca cruzada de 0,35 s). Recebe --t0 e --dur em segundos,
                       e --f0, --f1... com o início de cada frase RELATIVO à cena, para
                       casar a animação com a frase: calc((var(--t0) + var(--f1)) * 1s).
                       [data-fixa] na cena = não some (fica por baixo da seguinte).
   - [data-conta="1251"]  número que sobe até o valor, formatado em pt-BR.
                       Opcionais: data-de (s após o início da cena, ou "f1+0.4" = 0,4 s
                       depois do início da frase 1), data-em (duração),
                       data-casas, data-antes ("R$ "), data-depois.
   - [data-legenda]    recebe o texto da frase que está sendo falada.
   - [data-progresso]  largura vai de 0 a 100% ao longo do vídeo.
   - window.aoQuadro(t, cenas)  gancho para o que CSS não resolve.
   - window.__cena(id) devolve {t0, dur, frases} para a página calcular os seus tempos. */
(function () {
  var CENAS = [], TOTAL = 0, TROCA = 0.35, FRASES = [];
  var fmt = function (v, casas) {
    return v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  };
  var suave = function (x) { return 1 - Math.pow(1 - x, 3); };
  var inicio = function (c, v) {
    var m = /^f(\d+)([+-][\d.]+)?$/.exec(v);
    if (!m) return parseFloat(v);
    var f = c.frases[+m[1]];
    if (!f) throw new Error('cena ' + c.id + ' sem a frase ' + m[1]);
    return f.t0 - c.t0 + parseFloat(m[2] || '0');
  };

  window.__prepara = function (cenas, total) {
    CENAS = cenas; TOTAL = total;
    cenas.forEach(function (c, i) {
      var el = document.querySelector('[data-cena="' + c.id + '"]');
      if (!el) throw new Error('animacao.html sem [data-cena="' + c.id + '"]');
      c.el = el;
      c.fim = i + 1 < cenas.length ? cenas[i + 1].t0 : total + 1;
      el.style.setProperty('--t0', c.t0);
      el.style.setProperty('--dur', c.dur);
      (c.frases || []).forEach(function (f, k) {
        el.style.setProperty('--f' + k, (f.t0 - c.t0).toFixed(3));
        FRASES.push(f);
      });
    });
    document.documentElement.style.setProperty('--total', total);
    if (window.aoPreparar) window.aoPreparar(cenas, total);
    document.body.offsetHeight;  // força o recálculo: as animações nascem com o atraso já certo
  };

  window.__cena = function (id) {
    for (var i = 0; i < CENAS.length; i++) if (CENAS[i].id === id) return CENAS[i];
  };

  window.__quadro = function (t) {
    CENAS.forEach(function (c) {
      var a = Math.min(1, Math.max(0, (t - c.t0 + TROCA) / TROCA));
      var b = c.el.hasAttribute('data-fixa') ? 1 : Math.min(1, Math.max(0, (c.fim - t) / TROCA));
      var o = Math.min(a, b);
      c.el.style.opacity = o;
      c.el.style.visibility = o > 0 ? 'visible' : 'hidden';
      c.el.querySelectorAll('[data-conta]').forEach(function (n) {
        var de = inicio(c, n.dataset.de || '0'), em = parseFloat(n.dataset.em || '1.2');
        var x = Math.min(1, Math.max(0, (t - c.t0 - de) / em));
        var casas = parseInt(n.dataset.casas || '0', 10);
        n.textContent = (n.dataset.antes || '') + fmt(parseFloat(n.dataset.conta) * suave(x), casas) + (n.dataset.depois || '');
      });
    });
    var atual = '';
    FRASES.forEach(function (f) { if (t >= f.t0 - 0.05 && t <= f.t1 + 0.25) atual = f.texto; });
    document.querySelectorAll('[data-legenda]').forEach(function (l) {
      if (l.textContent !== atual) l.textContent = atual;
      l.style.opacity = atual ? 1 : 0;
    });
    document.querySelectorAll('[data-progresso]').forEach(function (p) {
      p.style.width = (100 * Math.min(1, t / TOTAL)) + '%';
    });
    document.getAnimations().forEach(function (an) { an.pause(); an.currentTime = t * 1000; });
    if (window.aoQuadro) window.aoQuadro(t, CENAS);
  };
})();
