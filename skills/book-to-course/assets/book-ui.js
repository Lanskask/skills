// @ts-check
/* book-to-course page script: theme toggle, contents drawer, reading progress, quizzes. No dependencies. */
(function () {
  'use strict';
  var root = document.documentElement;
  var KEY = 'b2c-theme';
  /** @param {string} s @param {ParentNode} [c] @returns {HTMLElement | null} */
  function $(s, c) { return (c || document).querySelector(s); }
  /** @param {string} s @param {ParentNode} [c] @returns {HTMLElement[]} */
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  var mqDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var mqMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  function behavior() { return mqMotion && mqMotion.matches ? 'auto' : 'smooth'; }
  /** @param {string | null} v */
  function store(v) { try { if (v) localStorage.setItem(KEY, v); else localStorage.removeItem(KEY); } catch (e) { /* private mode */ } }

  /* ── theme ── */
  var themeBtn = $('#theme-toggle');
  function systemDark() { return !!(mqDark && mqDark.matches); }
  function effective() {
    var s = root.getAttribute('data-theme');
    return s === 'dark' || s === 'light' ? s : (systemDark() ? 'dark' : 'light');
  }
  function syncTheme() {
    if (!themeBtn) return;
    var dark = effective() === 'dark';
    themeBtn.classList.toggle('is-dark', dark);
    themeBtn.setAttribute('aria-pressed', String(dark));
  }
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = effective() === 'dark' ? 'light' : 'dark';
      if (next === (systemDark() ? 'dark' : 'light')) { root.removeAttribute('data-theme'); store(null); }  // back to "follow the system"
      else { root.setAttribute('data-theme', next); store(next); }
      syncTheme();
    });
  }
  if (mqDark && mqDark.addEventListener) mqDark.addEventListener('change', syncTheme);
  syncTheme();

  /* ── contents drawer ── */
  var toc = $('#toc'), backdrop = $('#toc-backdrop'), main = $('#main');
  var openers = $$('[data-toc-open]');
  /** @type {HTMLElement | null} */
  var lastFocus = null;
  function isOpen() { return !!(toc && toc.classList.contains('open')); }
  /** @param {boolean} open @param {boolean} [restoreFocus] @param {HTMLElement} [opener] */
  function setOpen(open, restoreFocus, opener) {
    if (!toc) return;
    toc.classList.toggle('open', open);
    if (backdrop) backdrop.classList.toggle('open', open);
    document.body.classList.toggle('toc-open', open);
    if (main) /** @type {any} */ (main).inert = open;
    openers.forEach(function (b) { b.setAttribute('aria-expanded', String(open)); });
    if (open) {
      lastFocus = opener || /** @type {HTMLElement | null} */ (document.activeElement);   // Safari does not focus buttons on click, so remember the opener explicitly
      var cur = $('a[aria-current="location"]', toc);
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'center' });
      var c = $('.toc-close', toc); if (c) c.focus();
    } else if (restoreFocus !== false && lastFocus && lastFocus.focus) { lastFocus.focus(); }
  }
  openers.forEach(function (b) { b.addEventListener('click', function () { setOpen(!isOpen(), true, b); }); });
  $$('[data-toc-close]').forEach(function (b) { b.addEventListener('click', function () { setOpen(false); }); });
  if (backdrop) backdrop.addEventListener('click', function () { setOpen(false); });
  if (toc) toc.addEventListener('click', function (e) {
    var t = /** @type {Element | null} */ (e.target);
    var a = t && t.closest('a[href^="#"]');
    if (a) setOpen(false, false);
  });

  /* ── home ── */
  var home = $('#nav-home'), cover = $('#home');
  if (home && cover) home.addEventListener('click', function (e) {
    e.preventDefault(); setOpen(false, false);
    if (cover)
    cover.scrollIntoView({ behavior: behavior() });
    try { history.replaceState(null, '', '#home'); } catch (err) { /* file:// */ }
  });
  $$('[data-go]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var t = document.getElementById(a.getAttribute('data-go') || '');
      if (t) { e.preventDefault(); t.scrollIntoView({ behavior: behavior() }); }
    });
  });

  /* ── keyboard: while the drawer is open, keys stay inside it ── */
  window.addEventListener('keydown', function (/** @type {KeyboardEvent} */ e) {
    if (e.altKey || e.ctrlKey || e.metaKey || !isOpen()) return;
    if (e.key === 'Escape') { setOpen(false); e.preventDefault(); return; }
    if (e.key === 'Tab') {
      var f = $$('a[href], button:not([disabled])', /** @type {HTMLElement} */ (toc)).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
      else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      return;
    }
    if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', ' '].indexOf(e.key) > -1 && toc && !toc.contains(/** @type {Node} */ (e.target))) e.stopImmediatePropagation();
  }, true);

  /* ── scroll spy + progress ── */
  var links = $$('#toc a[data-spy]');
  var spy = links.map(function (a) { return { a: a, el: document.getElementById(a.getAttribute('data-spy') || '') }; })
                 .filter(function (x) { return x.el; })
                 .map(function (x) { return { a: x.a, el: /** @type {HTMLElement} */ (x.el) }; });
  var bar = $('#toc-progress-bar'), pct = $('#toc-pct'), top = $('#bar-progress'), where = $('#bar-where');
  var ticking = false;
  function update() {
    ticking = false;
    var y = window.scrollY, line = y + window.innerHeight * 0.35;
    var cur = -1;
    spy.forEach(function (s, i) { if (s.el.getBoundingClientRect().top + y <= line) cur = i; });
    spy.forEach(function (s, i) {
      var active = i === cur, inModule = false;
      if (cur > -1 && s.a.parentElement && s.a.parentElement.classList.contains('toc-module')) {
        var kids = /** @type {HTMLElement} */ (s.a.parentElement).querySelectorAll('a[data-spy]');
        inModule = Array.prototype.indexOf.call(kids, spy[cur].a) > 0;
      }
      if (active || inModule) s.a.setAttribute('aria-current', 'location'); else s.a.removeAttribute('aria-current');
      s.a.classList.toggle('is-read', i < cur && !inModule);
    });
    if (home) home.setAttribute('aria-current', cur === -1 ? 'page' : 'false');
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var p = max > 0 ? Math.min(100, Math.round(y / max * 100)) : 0;
    if (bar) bar.style.width = p + '%';
    if (top) top.style.setProperty('--read', String(p / 100));
    if (where) where.textContent = cur > -1 ? (spy[cur].a.textContent || '').replace(/^\d+/, '').trim() : '';
    if (pct) pct.textContent = p + '%';
  }
  window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener('resize', update);
  update();

  /* ── quizzes: native radios; Check marks each question and explains, Try again clears ── */
  $$('.quiz-container').forEach(function (box) {
    var check = $('.quiz-check-btn', box), reset = $('.quiz-reset-btn', box);
    var qs = $$('.quiz-question-block', box);
    if (!check || !reset) return;
    check.addEventListener('click', function () {
      qs.forEach(function (q) {
        var picked = /** @type {HTMLInputElement | null} */ ($('input:checked', q)), fb = $('.quiz-feedback', q);
        if (!fb) return;
        var right = !!picked && picked.value === q.getAttribute('data-correct');
        $$('.quiz-option', q).forEach(function (o) {
          var inp = /** @type {HTMLInputElement} */ ($('input', o));
          o.classList.toggle('is-right', inp.value === q.getAttribute('data-correct'));
          o.classList.toggle('is-wrong', inp.checked && !right);
        });
        fb.className = 'quiz-feedback ' + (right ? 'is-right' : 'is-wrong');
        fb.setAttribute('role', 'status');
        fb.innerHTML = picked ? '<b>' + box.getAttribute(right ? 'data-right' : 'data-wrong') + '</b>' + q.getAttribute(right ? 'data-explanation-right' : 'data-explanation-wrong')
                              : '<b>' + box.getAttribute('data-pick') + '</b>';
        if (picked) /** @type {HTMLFieldSetElement} */ (q).disabled = true;
      });
      check.disabled = qs.every(function (q) { return /** @type {HTMLFieldSetElement} */ (q).disabled; });
      reset.hidden = false;
    });
    reset.addEventListener('click', function () {
      qs.forEach(function (q) {
        /** @type {HTMLFieldSetElement} */ (q).disabled = false;
        $$('input', q).forEach(function (i) { /** @type {HTMLInputElement} */ (i).checked = false; });
        $$('.quiz-option', q).forEach(function (o) { o.classList.remove('is-right', 'is-wrong'); });
        var fb = $('.quiz-feedback', q); if (fb) { fb.className = 'quiz-feedback'; fb.textContent = ''; }
      });
      check.disabled = false; reset.hidden = true;
    });
  });
})();
