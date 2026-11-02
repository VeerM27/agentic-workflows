# Ember Low: scroll-build landing page

A one-product landing page for a red canvas low-top sneaker. As you scroll, the shoe is put together on a pinned drawing sheet from five parts: sole, toe cap and sidewall, canvas upper, insole and lining, then eyelets and laces. After that comes the product section, with a six-view viewer, price, sizes and a demo "Add to cart".

There is no build step and no dependencies. It uses static HTML, CSS and vanilla JavaScript, makes no network requests outside this folder, and loads no web fonts.

## How to view it

- **Quickest:** open `index.html` straight from disk (`file://`).
- **Static server:** use `agentflow serve <run>` or any static server pointed at this folder, for example `python3 -m http.server` run inside `site/`.

### Test hooks (query string)

| URL | Effect |
|---|---|
| `index.html?driver=js` | Forces the JavaScript fallback driver, even in browsers that support CSS scroll timelines |
| `index.html?build=static` | Forces the static five-figure list that reduced-motion and no-JS visitors see |
| `index.html#step-3` | Jumps to step 3 of the build (`#step-1` to `#step-5`) |
| `index.html#product` | Jumps to the product section, the same target as "Skip to buy" |

The values are checked against a fixed allow-list and are never written into the page.

## Files

```
index.html              markup: pinned build, static list, product, footer, sticky bar
css/tokens.css          design tokens, copied unchanged from design/tokens.css
css/base.css            reset, type, top bar, skip links, focus, buttons
css/build.css           the build: track, sticky stage, --p maths, layers, overlay, static list
css/product.css         viewer, buy panel, footer, mobile sticky bar
js/boot.js              runs in <head> before paint; picks the mode and the driver
js/build-driver.js      JS fallback driver (writes --p on scroll)
js/build-nav.js         progress nav state (current step, finished steps)
js/product.js           viewer, sizes, add to cart, sticky bar
js/main.js              entry point; starts what the current mode needs
assets/red-sneaker-sheet.png   source sheet (612 × 551), byte-for-byte copy of inputs/photos/red-sneaker.png
assets/favicon.svg
```

**Why classic scripts and not ES modules:** Chromium refuses to load `type="module"` scripts from `file://` pages (CORS, origin `null`). The plan requires the page to work from `file://`, and the screenshot tool also opens pages that way. Each file is therefore a small IIFE loaded with `defer`, in a fixed order, and they share one namespace, `window.EmberLow`. To switch back to modules when the site is always served over HTTP, turn each IIFE into `export`s and load `main.js` with `type="module"`.

## How the scroll animation works

1. **One number.** The build component reads one custom property, `--p`, which goes from 0 to 1 as you scroll through the build track. It is registered with `@property` as a `<number>`. Every layer computes its own progress from it, `--t = clamp(0, (p − a) / (b − a), 1)`, then derives its `transform`, `opacity` and SVG `stroke-dashoffset` from `--t`. Nothing else is animated.
2. **The track.** `.build` is `--stage-h + --build-distance` tall (normally 400svh minus the top bar). Inside it, `.build__stage` is `position: sticky`, so it stays pinned for exactly `--build-distance` (300svh) of scrolling.
3. **Two drivers, same visuals.** `js/boot.js` sets `data-driver` on `<html>`:
   - **`css`** (the browser supports `animation-timeline: view()`): `.build` gets a view timeline, `view-timeline-inset` set to the top-bar height, and an `animation-range` from `contain 0%` to `contain 100%`. A linear `@keyframes` animates `--p` from 0 to 1. No JavaScript runs per frame.
   - **`js`** (fallback): `js/build-driver.js` adds one passive scroll listener, batched with `requestAnimationFrame`. Each frame does one `getBoundingClientRect()` read and one `--p` write. An IntersectionObserver pauses the work while the track is off screen.
4. **Progress nav.** Seven invisible zones (`.build__zone`) cover the caption windows. An IntersectionObserver, whose root is shrunk to a 1px line under the top bar, reports which zone is current. `js/build-nav.js` then sets `aria-current="step"` and the finished checkmarks. The step links jump to `.build__marker` elements placed at each step's snap progress.
5. **Static mode.** `<html>` ships with `data-build="static"`, and `boot.js` switches it to `pinned` only when JavaScript runs and reduced motion is not requested. It also switches live if that preference changes. Static mode hides the track (`display: none`) and shows five figures. Each one is the same component with `--p` fixed by a class (`.static-step--1` … `--5`: .20, .36, .58, .665, 1). Only one version is ever rendered, so assistive tech never hears duplicates.
6. **Safety net.** If `main.js` has not run by the `load` event (a script failed), `boot.js` falls back to static mode.
7. **Load moment.** In pinned mode with motion allowed, the dashed cut line draws itself once over 900ms when the page opens. Screenshots taken in the first second may catch it half-drawn.

### Scroll position to `p`

`p = scrollY / build-distance`, where build-distance = 3 × viewport height. In an 800px-tall viewport, p = 0.2 is at `scrollY` 480, p = 0.58 at 1392, p = 0.665 at 1596 and p = 1 at 2400. The product section starts at about 3150.

## What to tweak

| What | Where |
|---|---|
| Scroll length of the build | `--build-distance` in `.build` (`css/build.css`; 300vh / 300svh) |
| When each part moves | `--a` / `--b` on `.layer--sole`, `--sidewall-toe`, `--upper`, `--laces`; `--t1/--t2/--t3` on `.layer--insole`; the settle on `.shoe__body` |
| How far parts travel | The percentages in each layer's `transform` (% of the shoe box) |
| Caption windows | `.caption:nth-child(n) { --a; --b }`. Keep `.build__zone[data-zone]` the same so the nav agrees |
| Step jump targets | `#step-1` … `#step-5 { --snap }` |
| Callout and tag windows | `.callout--*` `--a` / `--b` |
| Layer shapes | The `clip-path: polygon()` blocks, in V1 units (the 312 × 148 side view). Edit `design/svg/layer-map.svg` first, then copy the numbers over |
| Maximum shoe size | `--shoe-max` (560px) in `css/tokens.css` |
| Colours, type, spacing | `css/tokens.css` (copied from `design/tokens.css`; change both) |
| Name, price, sizes, copy | `index.html`; the name is also in `PRODUCT_NAME` in `js/product.js` (used in the success message) |
| "Added to cart" duration | `ADDED_FOR_MS` in `js/product.js` |

### Swapping in a higher-resolution sheet

The background maths assumes a 612 × 551 sheet with the side view at x 36, y 32, size 312 × 148.

- **Same layout, scaled up exactly** (for example 1224 × 1102): replace `assets/red-sneaker-sheet.png` and nothing else changes, because every size and position is a percentage. You can then raise `--shoe-max` to match the new native width × 1.8.
- **Any other layout:** update the sheet size (612 and 551) and the view boxes in `.cut`, `.layer--insole .cut` and the `.view--*` rules, then check the polygons again.

## Accessibility notes

- The animated stage is a single `role="img"` with a text alternative. The captions are a real ordered list, always in the DOM.
- The progress nav uses links with `aria-current="step"` and 44px targets.
- Sizes are a `fieldset` of radio buttons. Choosing no size shows an inline error (icon plus text), sets `aria-invalid` and moves focus to the size group. Adding with a size fills a `role="status"` region.
- Focus rings are 3px, and inside the light drawing sheet they stay dark, even in dark mode.
- Reduced motion gets the static list and no transitions.

## Content Security Policy

`index.html` carries a meta CSP: `default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'`. There are no inline scripts, `<style>` blocks or `style` attributes; the JS driver writes `--p` through the CSSOM, which the policy allows. `frame-ancestors` only works as a response header, so set it on the host, for example `Content-Security-Policy: frame-ancestors 'none'`.

## Placeholder content and image rights

- **Placeholders the operator must replace:** the product name "Ember Low", the price of 69 EUR (tax included), sizes EU 36–46, "Free returns within 30 days" and "Delivered in 2 to 4 working days". The page footer says so too.
- **"Add to cart" is a demo.** It stores nothing, sends nothing and places no order.
- **Image rights:** the operator must confirm the rights to the sneaker image (`assets/red-sneaker-sheet.png`) before publishing.
- **Material wording is generic on purpose.** It makes no origin, sustainability, certification or handmade claims.
