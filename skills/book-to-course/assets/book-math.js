// @ts-check
/* book-to-course: renders <span class="tex" data-tex="..."> with KaTeX; works for content added later (quiz feedback). */
/** @typedef {{ render(tex: string, el: HTMLElement, opts: object): void }} Katex */
(function () {
  /** @returns {Katex | undefined} looked up lazily: the CDN script may load after this one */
  function getKatex() { return /** @type {any} */ (window).katex; }
  function renderAll() {
    var katex = getKatex();
    if (!katex) return;
    var k = katex; // KaTeX CDN unreachable: the raw $TeX$ stays visible
    document.querySelectorAll('.tex:not([data-done])').forEach(function (/** @type {Element} */ el0) {
      var el = /** @type {HTMLElement} */ (el0);
      el.setAttribute('data-done', '1');
      try {
        k.render(el.getAttribute('data-tex') || '', el,
          { displayMode: el.getAttribute('data-display') === '1', throwOnError: false, strict: 'ignore', trust: false });
      } catch (e) { /* leave the raw source */ }
    });
  }
  function init() { renderAll(); new MutationObserver(renderAll).observe(document.body, { childList: true, subtree: true }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
