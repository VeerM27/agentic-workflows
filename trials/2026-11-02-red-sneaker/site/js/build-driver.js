/*
  JS fallback driver for the scroll build. (Classic deferred script; see README for why not a module.)

  Only used when html[data-build="pinned"][data-driver="js"] (no CSS scroll timelines, or ?driver=js).
  It writes one custom property, --p (0..1), on the .build track; css/build.css derives everything else.
  - One passive scroll listener, batched with requestAnimationFrame.
  - One layout read per frame (the track's bounding rect). Sizes are measured on resize only.
  - An IntersectionObserver pauses the work while the track is off screen.
*/
(function (ns) {
  'use strict';

  ns.createBuildDriver = function createBuildDriver(build) {
    var stage = build.querySelector('.build__stage');
    var active = false;
    var near = false;
    var frame = 0;
    var distance = 1;
    var pinTop = 0;
    var observer = null;

    function measure() {
      pinTop = parseFloat(getComputedStyle(stage).top) || 0;     // the sticky offset (top bar height)
      distance = Math.max(1, build.offsetHeight - stage.offsetHeight);
    }

    function write() {
      frame = 0;
      var top = build.getBoundingClientRect().top;
      var p = Math.min(1, Math.max(0, (pinTop - top) / distance));
      build.style.setProperty('--p', p.toFixed(4));
    }

    function request() {
      if (!frame) frame = requestAnimationFrame(write);
    }

    function onScroll() {
      if (near) request();
    }

    function onResize() {
      measure();
      request();
    }

    function start() {
      if (active) return;
      active = true;
      measure();
      observer = new IntersectionObserver(function (entries) {
        near = entries[entries.length - 1].isIntersecting;
        request();             // one last write as the track leaves, so --p lands exactly on 0 or 1
      }, { rootMargin: '25% 0px' });
      observer.observe(build);
      window.addEventListener('scroll', onScroll, { passive: true });
      window.addEventListener('resize', onResize, { passive: true });
      write();
    }

    function stop() {
      if (!active) return;
      active = false;
      near = false;
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      if (observer) observer.disconnect();
      observer = null;
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onResize);
      build.style.removeProperty('--p');
    }

    return { start: start, stop: stop };
  };
})(window.EmberLow = window.EmberLow || {});
