/*
  Design-frame helper (classic script, frames only; the site inlines this markup in index.html).
  Stamps the shoe component, the overlay SVG, the mark and the icons into placeholders,
  and sets the parts-list state from data-step. The canonical artwork lives in ../svg/.
*/
(function () {
  var OUTLINE = 'M3.5,110 L3.5,100 L4,88 L5.7,75 L8.6,62.5 L13.2,50.3 L18,44.3 L22.8,47.2 L28.8,52.7 L34.6,56.6 L40.3,58.5 L50,59.5 L60,59.5 L67.6,58 L74.3,55.7 L81,51.3 L85.8,47 L89.6,41.3 L92.5,35.6 L94,28.8 L94.5,20 L95.6,11.5 L99,4.8 L102.8,2 L106.4,1.9 L109.3,4.2 L119.3,11.5 L131.6,18.2 L154,31.4 L174.6,44.4 L193.6,53.8 L212,64.6 L230.4,72.1 L241.3,74.5 L250.2,75.9 L260.4,77.2 L267,75.7 L276.2,75.7 L286.5,77.2 L295.4,80.9 L302.8,88.5 L307.5,97.6 L309.7,104.8 L310.8,113.5 L310.4,117.2 L308.6,120.6 L300.5,124.4 L290.4,128 L270.4,133.8 L250.3,138.1 L230.2,141 L190.1,144.7 L150,146.8 L100,146.9 L50,146.1 L19.7,144.7 L9.3,143.1 L5.7,140.5 L3,135.3 L2.3,129 L2.3,118 L2.8,112 Z';

  function overlay(n) {
    var c = function (cls, d, tagX, tagY, num, pinX, pinY, extra) {
      return '<g class="callout ' + cls + '">' + (extra || '') +
        '<path class="callout-leader" pathLength="1" d="' + d + '" fill="none" stroke="#1F1A1B" stroke-width=".8"/>' +
        '<circle class="callout-pin" cx="' + pinX + '" cy="' + pinY + '" r="2" fill="#1F1A1B" stroke="#F7F5F1" stroke-width=".8"/>' +
        '<g class="callout-tag"><circle cx="' + tagX + '" cy="' + tagY + '" r="7" fill="#1F1A1B"/>' +
        '<text x="' + tagX + '" y="' + (tagY + 3.2) + '" fill="#F7F5F1">' + num + '</text></g></g>';
    };
    var eyelets = [[111.1, 45], [134.3, 53.6], [157.9, 62.9], [181.4, 70.7], [206, 77.9], [231.4, 85.7]]
      .map(function (e) { return '<circle class="eyelet" pathLength="1" cx="' + e[0] + '" cy="' + e[1] + '" r="4.6"/>'; }).join('');
    return '<svg class="shoe__overlay" viewBox="0 0 312 148" overflow="visible" aria-hidden="true" focusable="false">' +
      '<defs><mask id="outline-reveal-' + n + '" maskUnits="userSpaceOnUse" x="-12" y="-12" width="336" height="172">' +
      '<path class="outline-reveal-path" pathLength="1" fill="none" stroke="#fff" stroke-width="8" stroke-linejoin="round" d="' + OUTLINE + '"/></mask></defs>' +
      '<g class="outline" mask="url(#outline-reveal-' + n + ')"><path class="outline-path" fill="none" stroke="#6E6566" stroke-width="1" stroke-dasharray="3.2 2.4" stroke-linejoin="round" d="' + OUTLINE + '"/></g>' +
      '<g class="stitches" fill="none" stroke="#F7F5F1" stroke-width="1.1" stroke-linecap="round">' +
      '<path class="stitch stitch--collar" pathLength="1" d="M20.5,51.5 C27,58.5 36,63.5 47,64.6 C58,65.6 70,64 78,58.5 C82.5,55.3 86,51.5 88.5,48"/>' +
      '<path class="stitch stitch--vamp" pathLength="1" d="M90,51.6 L176,74.4 L266,98.2"/></g>' +
      '<g class="eyelets" fill="none" stroke="#F7F5F1" stroke-width="1.2">' + eyelets + '</g>' +
      '<g class="callouts" font-weight="700" font-size="9" text-anchor="middle">' +
      c('callout--sole', 'M70,129.5 L50,166', 50, 166, 1, 70, 129.5) +
      c('callout--toe', 'M292,100 L318,64', 318, 64, 2, 292, 100) +
      c('callout--upper', 'M176,94 L212,32', 212, 32, 3, 176, 94,
        '<path class="grainline" pathLength="1" d="M24,98 H92 M28.5,95.2 L24,98 L28.5,100.8 M87.5,95.2 L92,98 L87.5,100.8" fill="none" stroke="#F7F5F1" stroke-width=".9" stroke-linecap="round" stroke-linejoin="round"/>') +
      c('callout--insole', 'M28,22 L-6,-10', -6, -10, 4, 28, 22) +
      c('callout--laces', 'M206,77.9 L246,32', 246, 32, 5, 206, 77.9) +
      '</g></svg>';
  }

  function shadow(n) {
    return '<div class="shoe__shadow"><svg viewBox="0 0 312 148" overflow="visible" aria-hidden="true" focusable="false">' +
      '<defs><radialGradient id="contact-shadow-fill-' + n + '" cx=".5" cy=".5" r=".5">' +
      '<stop offset="0" stop-color="#1F1A1B" stop-opacity=".30"/><stop offset=".7" stop-color="#1F1A1B" stop-opacity=".10"/>' +
      '<stop offset="1" stop-color="#1F1A1B" stop-opacity="0"/></radialGradient></defs>' +
      '<ellipse cx="150" cy="146" rx="158" ry="6" fill="url(#contact-shadow-fill-' + n + ')"/></svg></div>';
  }

  var ICONS = {
    chevron: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6,9 L12,15 L18,9"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5,12.5 L10,17 L19,7"/></svg>',
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12,7.5 V13"/><path d="M12,16.5 V16.6"/></svg>'
  };
  var MARK = '<svg viewBox="0 0 40 24" aria-hidden="true" focusable="false"><path fill="#A5202D" d="M3,15.5 C3,10.5 3.6,7 5.6,4.6 C8.6,8 12.8,8.9 16.6,7.6 C18,4.2 19.4,2 21.6,2 L35.6,11.6 L38,15.5 Z"/><rect x="2" y="15.5" width="37" height="6.5" rx="3" fill="#F7F5F1" stroke="#1F1A1B" stroke-width="1"/><path d="M6,19 H28" stroke="#1F1A1B" stroke-width="1.4" stroke-linecap="round"/></svg>';

  document.querySelectorAll('[data-shoe]').forEach(function (el, i) {
    el.classList.add('shoe');
    el.innerHTML =
      '<div class="shoe__body">' + shadow(i) +
      '<div class="shoe__layers" aria-hidden="true">' +
      '<div class="layer layer--sole cut"></div>' +
      '<div class="layer layer--sidewall-toe cut"></div>' +
      '<div class="layer layer--insole"><div class="cut"></div></div>' +
      '<div class="layer layer--upper"><div class="fill"></div><div class="cut"></div></div>' +
      '<div class="layer layer--laces cut"></div>' +
      '</div>' + overlay(i) + '</div>';
  });
  document.querySelectorAll('[data-icon]').forEach(function (el) { el.innerHTML = ICONS[el.dataset.icon]; });
  document.querySelectorAll('[data-mark]').forEach(function (el) { el.innerHTML = MARK; });

  document.querySelectorAll('.build[data-step]').forEach(function (build) {
    var step = Number(build.dataset.step);
    build.querySelectorAll('.parts li').forEach(function (li, i) {
      var n = i + 1, a = li.querySelector('a'), dot = li.querySelector('.dot');
      if (n < step || step === 6) { li.classList.add('is-done'); dot.innerHTML = ICONS.check; }
      if (n === step || (step === 6 && n === 5)) a.setAttribute('aria-current', 'step');
    });
  });
})();
