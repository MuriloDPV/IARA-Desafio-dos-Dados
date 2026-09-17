/* ============================================================
   IARA — interações do site (sem dependências)
   0. Logo e fotos da equipe: placeholder até o arquivo real existir
   1. Menu mobile
   1b. Pill animado do menu (hover/ativo)
   2. Animações de entrada ao rolar (fade-in)
   3. Contadores animados (29%, 78%)
   4. Barras de sinal "acendendo" em sequência
   5. Apresentação: visualizador de slides
   6. Contador ao vivo de atendimentos
   ============================================================ */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // marca que o JS está ativo: os estados iniciais das animações
  // (elementos ocultos, contadores zerados) só valem a partir daqui
  document.documentElement.classList.add("js");

  /* ---------- 0. Logo com placeholder automático ----------
     enquanto assets/img/logo-iara.png não existir, cai num
     círculo roxo com "IARA" — some sozinho quando o arquivo chegar */
  var LOGO_FALLBACK = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%235B21B6'/%3E%3Ctext x='16' y='17' text-anchor='middle' dominant-baseline='middle' font-family='Arial,sans-serif' font-size='8' font-weight='700' fill='%23fff' letter-spacing='.5'%3EIARA%3C/text%3E%3C/svg%3E";
  document.querySelectorAll(".brand-logo").forEach(function (img) {
    img.addEventListener("error", function () {
      img.onerror = null;
      img.src = LOGO_FALLBACK;
    });
  });

  /* ---------- 0b. Fotos da equipe: revela só quando a imagem carrega ----------
     o placeholder quente (ícone + "Foto da equipe aqui") fica visível por
     baixo até o arquivo real existir — nada pra editar quando ele chegar */
  document.querySelectorAll(".photo-slot-img").forEach(function (img) {
    function reveal() { img.classList.add("is-loaded"); }
    if (img.complete && img.naturalWidth > 0) {
      reveal();
    } else {
      img.addEventListener("load", reveal);
    }
  });

  /* ---------- 1. Menu mobile ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    // fecha o menu ao navegar
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---------- 1b. Pill animado do menu ---------- */
  if (nav) {
    var pill = document.createElement("span");
    pill.className = "nav-pill";
    pill.setAttribute("aria-hidden", "true");
    nav.insertBefore(pill, nav.firstChild);

    var navLinks = Array.prototype.slice.call(nav.querySelectorAll("a:not(.btn)"));
    var activeNavLink = nav.querySelector("a.is-active");
    var currentPillLink = null;

    function setPillGeometry(link) {
      pill.style.width = link.offsetWidth + "px";
      pill.style.height = link.offsetHeight + "px";
      pill.style.transform = "translate(" + link.offsetLeft + "px, " + link.offsetTop + "px)";
    }

    function movePillTo(link) {
      currentPillLink = link;
      if (!link) {
        pill.classList.remove("is-visible");
        return;
      }
      setPillGeometry(link);
      pill.classList.add("is-visible");
    }

    function showActivePill() { movePillTo(activeNavLink); }

    // posiciona no item ativo (ou no primeiro item, se nenhum) sem transição
    // antes do primeiro paint, pra evitar o pill "crescendo" do canto ao carregar
    pill.style.transition = "none";
    setPillGeometry(activeNavLink || navLinks[0]);
    if (activeNavLink) pill.classList.add("is-visible");
    currentPillLink = activeNavLink || null;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { pill.style.transition = ""; });
    });

    navLinks.forEach(function (link) {
      link.addEventListener("mouseenter", function () { movePillTo(link); });
      link.addEventListener("focus", function () { movePillTo(link); });
    });
    nav.addEventListener("mouseleave", showActivePill);
    nav.addEventListener("focusout", function (e) {
      if (!nav.contains(e.relatedTarget)) showActivePill();
    });

    // reposiciona sem animar em resize (mudança de layout/largura de fonte)
    var pillResizeRaf = null;
    window.addEventListener("resize", function () {
      if (pillResizeRaf) return;
      pillResizeRaf = requestAnimationFrame(function () {
        pillResizeRaf = null;
        if (!currentPillLink) return;
        var prevTransition = pill.style.transition;
        pill.style.transition = "none";
        setPillGeometry(currentPillLink);
        void pill.offsetHeight;
        pill.style.transition = prevTransition;
      });
    });

    // corrige a largura depois que as fontes web carregarem
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        if (currentPillLink) setPillGeometry(currentPillLink);
      });
    }
  }

  /* ---------- 2 + 3 + 4. Observador de entrada na tela ---------- */
  var observed = document.querySelectorAll(".reveal, .signal.animate, .hero-signal, [data-count]");

  function activate(el) {
    el.classList.add("is-visible");
    if (el.hasAttribute("data-count")) startCounter(el);
  }

  if (reduceMotion || !("IntersectionObserver" in window)) {
    // sem animação: mostra tudo no estado final
    // (o HTML já traz os números finais nos contadores)
    observed.forEach(function (el) {
      el.classList.add("is-visible");
    });
  } else {
    // com animação: zera os contadores antes de observá-los
    document.querySelectorAll("[data-count]").forEach(function (el) {
      el.textContent = "0";
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          activate(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0, rootMargin: "0px 0px -10% 0px" });
    observed.forEach(function (el) { io.observe(el); });
  }

  /* ---------- 3. Contador animado ---------- */
  function startCounter(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    var duration = 1600;
    var start = null;

    function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

    function tick(ts) {
      if (start === null) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      el.textContent = Math.round(easeOut(progress) * target);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* ---------- 5. Apresentação: visualizador de slides ---------- */
  document.querySelectorAll("[data-slide-viewer]").forEach(initSlideViewer);

  /* ---------- 6. Contador ao vivo de atendimentos ----------
     busca /painel/api/estatisticas (mesma origem, o painel já usa
     esse endpoint internamente). Se falhar por qualquer motivo, o
     widget some sem deixar rastro — nunca quebra a página. */
  document.querySelectorAll("[data-live-counter]").forEach(initLiveCounter);

  function initLiveCounter(root) {
    var numberEl = root.querySelector("[data-live-counter-number]");
    if (numberEl) {
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
          numberEl.textContent = total.toLocaleString("pt-BR");
          root.classList.remove("is-loading");
        })
        .catch(function () {
          root.hidden = true;
        });
    }

    /* Badge de versão: busca independente — se falhar, só o badge
       some, o resto do widget (número + texto) continua funcionando. */
    var versionEl = root.querySelector("[data-live-counter-version]");
    if (!versionEl) return;

    fetch("/painel/api/versao")
      .then(function (res) {
        if (!res.ok) throw new Error("resposta não OK");
        return res.json();
      })
      .then(function (data) {
        var versao = data && data.versao;
        if (typeof versao !== "string" || !versao) {
          throw new Error("campo versao ausente ou inválido");
        }
        versionEl.textContent = "v" + versao;
        if (Array.isArray(data.mudancas) && data.mudancas.length) {
          versionEl.title = data.mudancas.join("\n");
        }
        versionEl.hidden = false;
      })
      .catch(function () {
        versionEl.hidden = true;
      });
  }

  function initSlideViewer(root) {
    var total = parseInt(root.getAttribute("data-total"), 10) || 0;
    if (!total) return;

    var img = root.querySelector("[data-slide-img]");
    var currentEl = root.querySelector("[data-slide-current]");
    var totalEl = root.querySelector("[data-slide-total]");
    var prevBtn = root.querySelector("[data-slide-prev]");
    var nextBtn = root.querySelector("[data-slide-next]");
    var dotsWrap = root.querySelector("[data-slide-dots]");
    var fsBtn = root.querySelector("[data-slide-fullscreen]");
    var basePath = root.getAttribute("data-base-path") || "";
    var current = 1;
    var preloaded = {};
    var dots = [];

    if (totalEl) totalEl.textContent = total;

    for (var i = 1; i <= total; i++) {
      var dot = document.createElement("button");
      dot.type = "button";
      dot.className = "slide-dot";
      dot.setAttribute("role", "tab");
      dot.setAttribute("aria-label", "Ir para o slide " + i);
      dot.addEventListener("click", (function (n) {
        return function () { goTo(n); };
      })(i));
      dotsWrap.appendChild(dot);
      dots.push(dot);
    }

    function slideSrc(n) {
      var num = n < 10 ? "0" + n : "" + n;
      return basePath + "slide-" + num + ".jpg";
    }

    function preload(n) {
      if (n < 1 || n > total || preloaded[n]) return;
      preloaded[n] = true;
      var im = new Image();
      im.src = slideSrc(n);
    }

    function render() {
      img.classList.remove("is-loaded");
      img.src = slideSrc(current);
      img.alt = "Slide " + current + " de " + total + " da apresentação da Iara";
      if (currentEl) currentEl.textContent = current;
      dots.forEach(function (d, idx) {
        var active = idx + 1 === current;
        d.classList.toggle("is-active", active);
        d.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (prevBtn) prevBtn.disabled = current === 1;
      if (nextBtn) nextBtn.disabled = current === total;
      preload(current + 1);
      preload(current - 1);
    }

    function goTo(n) {
      if (n < 1 || n > total || n === current) return;
      current = n;
      render();
    }

    img.addEventListener("load", function () { img.classList.add("is-loaded"); });

    if (prevBtn) prevBtn.addEventListener("click", function () { goTo(current - 1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { goTo(current + 1); });

    // setas do teclado: só reagem quando o visualizador está visível na tela
    document.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      var rect = root.getBoundingClientRect();
      var onScreen = rect.top < window.innerHeight && rect.bottom > 0;
      if (!onScreen) return;
      if (e.key === "ArrowLeft") goTo(current - 1);
      else goTo(current + 1);
    });

    // tela cheia
    if (fsBtn) {
      var supportsFs = !!(document.fullscreenEnabled || document.webkitFullscreenEnabled);
      if (!supportsFs) {
        fsBtn.style.display = "none";
      } else {
        fsBtn.addEventListener("click", function () {
          var fsEl = document.fullscreenElement || document.webkitFullscreenElement;
          if (fsEl) {
            if (document.exitFullscreen) document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
          } else {
            if (root.requestFullscreen) root.requestFullscreen();
            else if (root.webkitRequestFullscreen) root.webkitRequestFullscreen();
          }
        });

        function onFsChange() {
          var isFs = document.fullscreenElement === root || document.webkitFullscreenElement === root;
          root.classList.toggle("is-fullscreen", isFs);
          fsBtn.setAttribute("aria-label", isFs ? "Sair da tela cheia" : "Ver em tela cheia");
        }
        document.addEventListener("fullscreenchange", onFsChange);
        document.addEventListener("webkitfullscreenchange", onFsChange);
      }
    }

    render();
  }
})();
