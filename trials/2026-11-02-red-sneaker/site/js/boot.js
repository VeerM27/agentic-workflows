/*
  Ember Low boot (classic script, runs in <head> before first paint).

  Sets two attributes on <html>:
    data-build  = "pinned" | "static"   (static: reduced motion, ?build=static, or no JS at all,
                                          because the HTML ships with data-build="static")
    data-driver = "css"    | "js"       (css: the browser has scroll-driven animations; ?driver=js forces js)

  Query values are only compared against fixed strings; they are never written into the page.
*/
(function () {
  'use strict';
  var root = document.documentElement;
  var params;
  try { params = new URLSearchParams(window.location.search); } catch (e) { params = null; }
  var forceStatic = !!params && params.get('build') === 'static';
  var forceJs = !!params && params.get('driver') === 'js';

  var cssTimelines = !forceJs && !!(window.CSS && CSS.supports &&
    CSS.supports('animation-timeline: view()') &&
    CSS.supports('view-timeline-inset: 1px'));

  var reduce = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  function apply() {
    var mode = (forceStatic || (reduce && reduce.matches)) ? 'static' : 'pinned';
    root.setAttribute('data-build', mode);
    root.setAttribute('data-driver', cssTimelines ? 'css' : 'js');
  }
  apply();

  // Live changes of the reduced-motion preference: switch modes, then tell main.js.
  if (reduce) {
    var onChange = function () {
      apply();
      document.dispatchEvent(new CustomEvent('ember:modechange'));
    };
    if (reduce.addEventListener) reduce.addEventListener('change', onChange);
    else if (reduce.addListener) reduce.addListener(onChange);
  }

  // Safety net: if main.js never ran (a script failed to load or threw), show the static list,
  // which needs no JavaScript, instead of a pinned stage nobody drives.
  window.addEventListener('load', function () {
    if (!root.hasAttribute('data-ready')) root.setAttribute('data-build', 'static');
  });
})();
