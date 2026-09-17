/* ============================================================
   IARA — página Escala (escala.html)
   Contador ao vivo com animação de contagem: busca o mesmo
   endpoint do widget comum (/painel/api/estatisticas), mas
   anima de 0 até o valor real quando entra na tela.
   Mesmo tratamento de erro silencioso: se a API falhar,
   o widget some sem quebrar a página.
   ============================================================ */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function formatar(n) {
    return n.toLocaleString("pt-BR");
  }

  document.querySelectorAll("[data-live-counter-animate]").forEach(initAnimatedCounter);

  function initAnimatedCounter(root) {
    var numberEl = root.querySelector("[data-live-counter-number]");
    if (!numberEl) return;

    fetch("/painel/api/estatisticas")
      .then(function (res) {
        if (!res.ok) throw new Error("resposta não OK");
        return res.json();
      })
      .then(function (data) {
        var total = data && data.total;
        if (typeof total !== "number" || !isFinite(total) || total < 0) {
          throw new Error("campo total ausente ou inválido");
        }
        root.classList.remove("is-loading");

        // sem animação (preferência do usuário ou navegador antigo):
        // mostra o valor final direto
        if (reduceMotion || !("IntersectionObserver" in window)) {
          numberEl.textContent = formatar(total);
          return;
        }

        numberEl.textContent = "0";
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              io.disconnect();
              animar(numberEl, total);
            }
          });
        }, { threshold: 0.4 });
        io.observe(root);
      })
      .catch(function () {
        root.hidden = true;
      });
  }

  function animar(el, total) {
    var duration = 1800;
    var start = null;

    function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

    function tick(ts) {
      if (start === null) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      el.textContent = formatar(Math.round(easeOut(progress) * total));
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
})();
