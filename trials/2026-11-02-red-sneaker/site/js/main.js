/*
  Ember Low entry (classic deferred script, loaded last). boot.js has already chosen the mode
  (data-build) and the driver (data-driver). This starts and stops what the current mode needs,
  and re-runs when the reduced-motion preference changes.
*/
(function (ns) {
  'use strict';
  var root = document.documentElement;
  if (!ns.createBuildDriver || !ns.createBuildNav || !ns.initCart) return;   // a script failed: boot.js falls back to static
  root.setAttribute('data-ready', '');

  var build = document.querySelector('.build');
  var driver = build ? ns.createBuildDriver(build) : null;
  var nav = build ? ns.createBuildNav(build) : null;

  function sync() {
    var pinned = root.getAttribute('data-build') === 'pinned';
    if (driver) {
      if (pinned && root.getAttribute('data-driver') === 'js') driver.start();
      else driver.stop();
    }
    if (nav) {
      if (pinned) nav.start();
      else nav.stop();
    }
  }

  sync();
  document.addEventListener('ember:modechange', sync);

  var product = document.querySelector('#product');
  if (product) {
    ns.initViewer(product);
    ns.initCart(product);
    var bar = document.querySelector('.buybar');
    var buildEnd = document.querySelector('.build-end');
    var mainButton = document.querySelector('#add-to-cart');
    if (bar && buildEnd && mainButton) ns.initBuyBar(bar, buildEnd, mainButton);
  }
})(window.EmberLow = window.EmberLow || {});
