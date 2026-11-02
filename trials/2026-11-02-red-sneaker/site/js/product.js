/*
  Product section: view switcher, size choice, add to cart (demo only) and the mobile sticky bar.
  (Classic deferred script.) No storage, no network. All text is set with textContent.
*/
(function (ns) {
  'use strict';

  var PRODUCT_NAME = 'Ember Low';          // placeholder name, keep in sync with index.html
  var ADD_LABEL = 'Add to cart';
  var ADDED_LABEL = 'Added to cart';
  var ADDED_FOR_MS = 2000;

  function all(scope, selector) {
    return Array.prototype.slice.call(scope.querySelectorAll(selector));
  }

  ns.initViewer = function initViewer(root) {
    var views = all(root, '.viewer__stage .view');
    var thumbs = all(root, '.thumbs button');
    thumbs.forEach(function (thumb) {
      thumb.addEventListener('click', function () {
        var name = thumb.getAttribute('data-view');
        thumbs.forEach(function (t) { t.setAttribute('aria-pressed', String(t === thumb)); });
        views.forEach(function (view) {
          var on = view.getAttribute('data-view') === name;
          view.classList.toggle('is-active', on);
          if (on) view.removeAttribute('aria-hidden');
          else view.setAttribute('aria-hidden', 'true');
        });
      });
    });
  };

  ns.initCart = function initCart(root) {
    var sizes = root.querySelector('.sizes');
    var radios = all(sizes, 'input[type="radio"]');
    var error = root.querySelector('#size-error');
    var statusMsg = root.querySelector('.status__msg');
    var statusText = root.querySelector('.status__text');
    var buttons = all(document, '[data-add-to-cart]');
    var resetTimer = 0;

    function chosen() {
      for (var i = 0; i < radios.length; i++) if (radios[i].checked) return radios[i].value;
      return null;
    }

    function showError() {
      statusMsg.hidden = true;
      statusText.textContent = '';
      error.hidden = false;
      sizes.classList.add('is-invalid');
      radios.forEach(function (r) { r.setAttribute('aria-invalid', 'true'); });
    }

    function clearError() {
      error.hidden = true;
      sizes.classList.remove('is-invalid');
      radios.forEach(function (r) { r.removeAttribute('aria-invalid'); });
    }

    function focusSizes() {
      var smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      sizes.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' });
      radios[0].focus({ preventScroll: true });
    }

    function add() {
      var size = chosen();
      if (!size) {
        showError();
        focusSizes();
        return;
      }
      clearError();
      // Empty first, then fill on the next frame, so a repeated add is announced again.
      statusText.textContent = '';
      statusMsg.hidden = false;
      requestAnimationFrame(function () {
        statusText.textContent = 'Added to cart: ' + PRODUCT_NAME + ', EU ' + size +
          '. This is a demo, so no order was placed.';
      });
      buttons.forEach(function (b) { b.textContent = ADDED_LABEL; });
      clearTimeout(resetTimer);
      resetTimer = setTimeout(function () {
        buttons.forEach(function (b) { b.textContent = ADD_LABEL; });
      }, ADDED_FOR_MS);
    }

    radios.forEach(function (r) { r.addEventListener('change', clearError); });
    buttons.forEach(function (b) { b.addEventListener('click', add); });
  };

  /*
    Sticky bar (mobile only, by CSS): visible once the build has been scrolled past,
    hidden again while the real Add to cart button is on screen.
  */
  ns.initBuyBar = function initBuyBar(bar, buildEnd, mainButton) {
    var pastBuild = false;
    var ctaVisible = false;

    function render() {
      if (pastBuild && !ctaVisible) {
        bar.setAttribute('data-visible', '');
        bar.removeAttribute('inert');
      } else {
        bar.removeAttribute('data-visible');
        bar.setAttribute('inert', '');
      }
    }

    // Past the build once the end marker has risen at least 96px into the viewport (or above it),
    // so the bar never covers the step dots that sit just above the marker at the end of the build.
    new IntersectionObserver(function (entries) {
      var entry = entries[entries.length - 1];
      pastBuild = entry.isIntersecting || entry.boundingClientRect.top < 0;
      render();
    }, { rootMargin: '0px 0px -96px 0px' }).observe(buildEnd);

    new IntersectionObserver(function (entries) {
      ctaVisible = entries[entries.length - 1].isIntersecting;
      render();
    }).observe(mainButton);

    render();
  };
})(window.EmberLow = window.EmberLow || {});
