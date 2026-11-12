// @ts-check
/* book-to-course UI: theme toggle, contents drawer, home, keyboard. No dependencies. */
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

  /* ── keyboard (capture phase: runs before main.js) ── */
  function modules() { return $$('.module'); }
  function currentModule() {
    var mid = window.scrollY + window.innerHeight / 2, m = modules();
    for (var i = 0; i < m.length; i++) {
      var top = m[i].getBoundingClientRect().top + window.scrollY;
      if (mid >= top && mid < top + m[i].offsetHeight) return i;
    }
    return -1;
  }
  window.addEventListener('keydown', function (/** @type {KeyboardEvent} */ e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var arrows = ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].indexOf(e.key) > -1;
    if (isOpen()) {
      if (e.key === 'Escape') { setOpen(false); e.preventDefault(); return; }
      if (e.key === 'Tab') {
        var f = $$('a[href], button:not([disabled])', /** @type {HTMLElement} */ (toc)).filter(function (x) { return x.offsetParent !== null; });
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
        return;
      }
      if (arrows) e.stopImmediatePropagation();   // arrows must not page through modules behind the drawer
      return;
    }
    if (!arrows || ['INPUT', 'TEXTAREA', 'SELECT'].indexOf(/** @type {HTMLElement} */ (e.target).tagName) > -1) return;
    var m = modules(), idx = currentModule(), fwd = e.key === 'ArrowDown' || e.key === 'ArrowRight';
    if (fwd && idx === -1 && cover && m[0]) {            // on the cover: go to the first module (main.js would skip it)
      m[0].scrollIntoView({ behavior: behavior() }); e.preventDefault(); e.stopImmediatePropagation();
    } else if (!fwd && idx === 0 && cover) {             // first module: up goes home
      cover.scrollIntoView({ behavior: behavior() }); e.preventDefault(); e.stopImmediatePropagation();
    }
  }, true);

  /* ── scroll spy + progress ── */
  var links = $$('#toc a[data-spy]');
  var spy = links.map(function (a) { return { a: a, el: document.getElementById(a.getAttribute('data-spy') || '') }; })
                 .filter(function (x) { return x.el; })
                 .map(function (x) { return { a: x.a, el: /** @type {HTMLElement} */ (x.el) }; });
  var bar = $('#toc-progress-bar'), pct = $('#toc-pct');
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
    if (pct) pct.textContent = p + '%';
  }
  window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener('resize', update);
  update();
})();
