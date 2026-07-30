/* Random CRT faults.
   Every so often an element — never more than a fifth of what's on screen —
   flickers for a moment, then settles. Which one, how long and how badly are
   all random, so the fault never lands in the same place twice.

   While an element is flickering it stops working: clicks and typing are
   ignored until it settles, so the picture and the behaviour agree. A blink
   lasts under half a second, and anything you are currently using is never
   chosen — see onScreen(). Nothing here changes layout, text, or state. */
(function () {
  // Someone who asked for less motion gets none of this.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const SELECTOR = [
    '.card', '.step', '.cand', '.sym', '.rule',
    'button', '.btnlink', 'textarea', 'input', 'select',
    '.empty', '.drop', '.peek', 'h1', '.sub', '.meta', 'kbd',
  ].join(',');

  const FLAVOURS = ['g-dim', 'g-surge', 'g-jitter'];  // see style.css
  const MAX_SHARE = 0.20;        // hard ceiling: never more than a fifth at once
  const MIN_GAP = 900;           // ms between bursts — long enough that the
  const MAX_GAP = 5200;          // page reads as steady, with the odd fault

  const lit = new Set();         // elements currently flickering

  const pick = list => list[Math.floor(Math.random() * list.length)];
  const between = (lo, hi) => lo + Math.random() * (hi - lo);

  function onScreen(el) {
    // Never break what someone is using: skip the focused element and any
    // panel containing it, or a flicker could swallow a keystroke.
    if (lit.has(el)) return false;
    if (document.activeElement && el.contains(document.activeElement)) return false;
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0 &&
           box.bottom > 0 && box.top < window.innerHeight;
  }

  function flash(el) {
    const flavour = pick(FLAVOURS);
    const ms = Math.round(between(80, 360));   // short: a blink, not a strobe
    el.style.setProperty('--g-ms', ms + 'ms');
    el.classList.add('glitch', flavour);

    // Dead while it flickers. `inert` stops clicks, typing and tabbing in one
    // go; the CSS pointer-events rule covers browsers without it. Both are
    // undone below, so a fault can never leave a control stuck.
    const wasInert = el.inert;
    el.inert = true;

    lit.add(el);
    setTimeout(() => {
      el.classList.remove('glitch', flavour);
      el.style.removeProperty('--g-ms');
      el.inert = wasInert;
      lit.delete(el);
    }, ms);
  }

  function burst() {
    const targets = Array.from(document.querySelectorAll(SELECTOR)).filter(onScreen);
    if (targets.length) {
      // The cap counts what is already flickering, so overlapping bursts can
      // never push past the fifth-of-the-page limit.
      const room = Math.floor(targets.length * MAX_SHARE) - lit.size;
      // usually one element, occasionally two — bursts are rare, so keep them small
      const count = Math.min(room, Math.random() < 0.25 ? 2 : 1);
      for (let i = 0; i < count; i++) {
        const el = pick(targets);
        if (onScreen(el)) flash(el);
      }
    }
    setTimeout(burst, between(MIN_GAP, MAX_GAP));
  }

  setTimeout(burst, 1500);       // let the page settle before anything breaks
})();
