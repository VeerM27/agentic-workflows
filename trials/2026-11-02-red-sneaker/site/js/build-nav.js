/*
  Progress nav state for the pinned build. (Classic deferred script.)

  Seven invisible "zones" inside the track (.build__zone, see css/build.css) span the caption windows:
  0 opening, 1..5 the steps, 6 the settle. An IntersectionObserver whose root is shrunk to a 1px line
  just under the sticky top bar reports which zone is under that line. Works the same with either
  driver, and does nothing per scroll frame.

  Sets data-step on .build, marks finished parts with .is-done and the current one with
  aria-current="step". No live-region announcements while scrolling.
*/
(function (ns) {
  'use strict';

  ns.createBuildNav = function createBuildNav(build) {
    var stage = build.querySelector('.build__stage');
    var zones = Array.prototype.slice.call(build.querySelectorAll('.build__zone'));
    var items = Array.prototype.slice.call(build.querySelectorAll('.parts li'));
    var inside = new Set();
    var observer = null;
    var current = -1;
    var resizeTimer = 0;

    function setStep(step) {
      if (step === current) return;
      current = step;
      build.setAttribute('data-step', String(step));
      items.forEach(function (li, i) {
        var n = i + 1;
        var link = li.querySelector('a');
        li.classList.toggle('is-done', n < step || step === 6);
        if (n === step || (step === 6 && n === 5)) link.setAttribute('aria-current', 'step');
        else link.removeAttribute('aria-current');
      });
    }

    function observe() {
      if (observer) observer.disconnect();
      inside.clear();
      var line = parseFloat(getComputedStyle(stage).top) || 0;
      var below = Math.max(0, window.innerHeight - line - 1);
      observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var zone = Number(entry.target.getAttribute('data-zone'));
          if (entry.isIntersecting) inside.add(zone);
          else inside.delete(zone);
        });
        if (inside.size) setStep(Math.max.apply(null, Array.from(inside)));
      }, { rootMargin: '-' + line + 'px 0px -' + below + 'px 0px', threshold: 0 });
      zones.forEach(function (zone) { observer.observe(zone); });
    }

    function onResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(observe, 150);
    }

    function start() {
      if (observer) return;
      setStep(0);
      observe();
      window.addEventListener('resize', onResize, { passive: true });
    }

    function stop() {
      if (observer) observer.disconnect();
      observer = null;
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', onResize);
    }

    return { start: start, stop: stop };
  };
})(window.EmberLow = window.EmberLow || {});
