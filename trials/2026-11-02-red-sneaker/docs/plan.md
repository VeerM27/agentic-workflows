# Plan: "Ember Low" scroll-build landing page

Inputs: `docs/brief.md`, `docs/brief-review.md`, `inputs/photos/red-sneaker.png`.
Every agent works from this file. Placeholders (name Ember Low, 69 EUR, EU 36–46, returns, delivery) stay marked as placeholders everywhere, including the README and the page footer.

---

## 1. Overview

A one-product landing page for a red canvas low-top sneaker. While the visitor scrolls, the shoe is assembled on a pinned stage from five groups of parts (sole, toe cap and sidewall, canvas upper, insole and lining, eyelets and laces). Once it is complete, the page lands on a product section with the finished shoe, a six-view gallery, price, size selector and add-to-cart (demo only). A "Skip to buy" link is always visible, and a sticky add-to-cart bar appears on mobile.

### Page sections, top to bottom
1. **Top bar** (`header`): wordmark "Ember Low", "Skip to buy" link (target `#product`). Always visible, compact.
2. **Build** (`section#build`): a 400 svh track with a sticky 100 svh stage. Contents: headline and cue, the layered shoe, the caption for the current step, and a progress nav ("Step 3 of 5: Canvas upper") whose five links jump to steps. In reduced-motion, no-JS and static mode this becomes a stacked list of five figures.
3. **Product** (`section#product`): finished-shoe viewer with six thumbnails, name, price with "includes tax", size radio group, "Add to cart", returns and delivery lines, and the closing line "Ready to wear on day one." On desktop the buy panel is sticky beside the viewer.
4. **Footer**: placeholder-content notice ("Demo page. Name, price and policies are placeholders"), image-rights note is README only.
5. **Sticky bar** (`aside`, mobile only, below 768 px): name, price, "Add to cart". Appears after the build starts to end, hides while the real add-to-cart button is on screen.

### Technical approach
- Static HTML, CSS and vanilla ES modules in `site/`. No build step, no dependencies.
- **One scroll variable.** The build is a single component that reads a unitless custom property `--p` (0 to 1, scroll progress through the build track). Every layer derives its own progress with `clamp()` and `calc()`, then sets `transform` and `opacity` from that. One set of layer rules serves both drivers:
  - **CSS driver** (browsers with `animation-timeline`): `@property --p` (`<number>`, `inherits: true`) animated by a `scroll()`/`view()` timeline on the track. No JS per frame.
  - **JS driver** (fallback): a passive scroll listener with `requestAnimationFrame` writes `--p` to the `.build` element. Reads happen once per frame (`getBoundingClientRect` of the track), writes are a single custom property.
  - Selected in `site/js/boot.js` by `CSS.supports('animation-timeline: scroll()')`. Testing hook: `?driver=js` forces the JS driver, `?build=static` forces the static list.
- **Three modes**, set as `data-build` on `<html>` by `boot.js` before first paint:
  - `pinned` (default when JS runs and motion is allowed)
  - `static` (`prefers-reduced-motion: reduce`, `?build=static`, or no JS; no JS is the CSS default because `boot.js` is what turns `pinned` on)
  - Reduced-motion changes are live (`matchMedia` listener).
- **Layer technique, needs no image tools.** The source is one sheet with six views. Each build layer is a `div` whose `background-image` is the sheet, positioned to the side view (view 1) and cut with a static `clip-path: polygon()`. Layers are stacked inside one group (`isolation: isolate; mix-blend-mode: multiply`) over a light stage panel. Multiply makes the sheet's white background disappear, and the layers composite normally inside the group. Only `transform` and `opacity` change. Assembled state equals the original view 1 pixel for pixel.
- Colours of the shoe are never recoloured. Everything else (outline, stitch traces, eyelet rings, leader lines, callout ticks) is inline SVG using stroke and opacity.
- Keep the stage panel light in dark mode (page chrome goes dark, stage and viewer panels stay light) because the multiply technique needs a light backdrop.

---

## 2. Scroll storyboard

Track height `400svh` (stage `100svh`, so scroll distance = 300 svh, inside the 3–4 screen budget). `p` = progress 0–1 over that distance. Same ranges on all screen sizes.

Parts named in a believable order: outsole and stripe, rubber foxing and toe bumper, cotton-style canvas upper with contrast stitching, fabric insole and lining, metal eyelets and flat cotton-style laces. Generic wording only: no origin, sustainability or handmade claims.

| # | Scroll range | On screen | What moves | Copy |
|---|---|---|---|---|
| 0 | **0–8%** Opening | Light stage, faint dashed outline of the side-view shoe, nothing built. Headline, subhead, cue. | Outline draws on (`stroke-dashoffset` 1→0, 0–6%). Cue arrow bobs only while `p = 0`. Headline and subhead fade and rise 6–12%. | H1 "Built layer by layer." Sub "Five parts. One everyday sneaker. Scroll to see how it comes together." Cue "Scroll to build it". |
| 1 | **8–24%** Sole | White rubber sole and the single black stripe, sitting in the outline. | Sole layer rises from `translateY(64px)`, opacity 0→1 over 8–18%. Hold 18–24%. Leader line and tick point at the stripe. | Step 1 of 5: Sole. "A flat rubber sole with the single black stripe." |
| 2 | **24–40%** Toe cap and sidewall | Rubber toe cap and the white side band join the sole. | Layer enters from `translateX(72px)` (front) with opacity 0→1 over 24–34%, settles into the sole line. Hold 34–40%. | Step 2 of 5: Toe cap and sidewall. "A rubber toe cap and sidewall that wipe clean." |
| 3 | **40–60%** Canvas upper | The red canvas upper, with the laces area left open (tongue gap shows as plain dark red). | Upper drops from `translateY(-96px)`, opacity 0→1 over 40–52%. SVG stitch traces draw on along collar and vamp seams (52–58%), then stay at 35% opacity. | Step 3 of 5: Canvas upper. "Red canvas, stitched in contrast thread." |
| 4 | **60–78%** Insole and lining | A tan insole from the top-down view floats above the shoe opening, foreshortened. | Insole appears 60–64% (`translateY(-150px) scaleY(.38)`, opacity 0→1), hovers 64–68% with a leader line and tick, then sinks into the shoe 68–76% (`translateY` to its resting point, hidden behind the upper because the layer sits below it). The tan lining sliver at the collar is already in the upper layer. | Step 4 of 5: Insole and lining. "A soft fabric lining and insole, tan and plain." |
| 5 | **78–94%** Eyelets and laces | Metal eyelets light up, then the flat white laces arrive. | Six SVG eyelet rings draw on (78–84%) and fade by 94%. Laces layer drops from `translateY(-44px)`, opacity 0→1 over 84–92%. | Step 5 of 5: Eyelets and laces. "Metal eyelets and flat white laces." |
| 6 | **94–100%** Settle | The finished shoe in side view, full size. Outline and leader lines gone. Progress nav shows all five complete. | Whole stack scales `.96→1` and translates a few px down onto a faint contact shadow (opacity). Stage unpins at 100% and the product section scrolls in. | No new copy; step 5 caption stays. |

Caption visibility windows (2% fades): step 1 8–24, step 2 24–40, step 3 40–60, step 4 60–78, step 5 78–100.

**Snap table** (used for progress-nav jump targets and for the static frames): step 1 `0.20`, step 2 `0.36`, step 3 `0.58`, step 4 `0.665`, step 5 `1`. Jumping to step 5 uses `0.93` so the page does not leave the pin. Jump links scroll to the marker `#step-N` placed at that progress, with `scroll-behavior: smooth` only when motion is allowed.

**Static mode.** Five `figure`s, each a copy of the same shoe component with `--p` fixed to the snap value, no animation. Each shows the caption and "Step N of 5" as real text. Then the same product section follows.

**Mobile:** the stage is `100svh` minus top bar. The shoe is about 300–340 CSS px wide and centred in the upper part, the caption sits under it, the progress nav is at the bottom with 44 px targets. Desktop (1024+): captions in a left column, shoe up to 560 px wide, vertical progress nav.

---

## 3. Assets

### Source
`inputs/photos/red-sneaker.png`: one sheet, 2×3 views on white. The size is estimated at **about 612 × 544 px** from the render (not measured, because no tool reads dimensions). The coder verifies it with a screenshot or the browser, and updates the numbers below if different.

Estimated view boxes in sheet pixels (x from–to, y from–to; verify before use):

| View | Position | Box | Use |
|---|---|---|---|
| V1 side | top left | x 36–348, y 32–180 | Hero, all build layers except insole |
| V2 front 3/4 high | top right | x 410–538, y 26–180 | Gallery |
| V3 top-down | middle left | x 36–344, y 226–334 | Insole layer (tan oval at left), gallery |
| V4 back | middle right | x 430–540, y 198–362 | Gallery |
| V5 rear 3/4 | bottom left | x 54–294, y 374–520 | Gallery |
| V6 front 3/4 low | bottom right | x 344–588, y 374–520 | Gallery, finished-product viewer default is V1 |

### How each is used
- **Copy to `site/assets/red-sneaker-sheet.png`** (use `cp`; do not re-encode). If no shell is available, reference the original at `../inputs/photos/red-sneaker.png` and say so in the README.
- **Build layers (V1):** one `div` per layer, same box, same `background` setup, different `clip-path` polygon. Layers: `sole` (everything below and including the black stripe), `sidewall-toe` (the white foxing band above the stripe and the rounded toe bumper), `upper` (red canvas including heel panel and the tan collar sliver, with the lace area left open and filled by a flat dark-red polygon so no laces are baked in), `laces` (the lace and eyelet band, drawn over the open area), `insole` (from V3, tan region only, tight polygon). The designer supplies the polygons (see Designer task 4).
- **Gallery and viewer:** `<img>` per view, using the sheet scaled and offset inside an `overflow: hidden` figure, with `mix-blend-mode: multiply` on a light panel. Real `alt` on each.
- **Sampled colours:** deep red about `#A5202D`, tan insole about `#8A7A63`, white about `#F4F4F2`. The designer re-samples by eye from the sheet.

### Resolution rule
Native view width is about 310 px. Never display a view wider than **about 1.8× native (560 px)**. On 2–3× phones the shoe will be slightly soft; accept it, do not upscale with filters. Compensate in the design with scale (large type, generous stage, a subtle fine grain overlay allowed if cheap) rather than by enlarging the shoe. Operator question: a higher-resolution source would improve the desktop hero.

### Must be drawn as SVG (designer)
- Dashed shoe outline of the side view (viewBox matching V1 box).
- Stitch traces along collar and vamp seams.
- Six eyelet rings at the eyelet positions of V1.
- Leader lines and ticks for sole stripe, insole and eyelets.
- Chevron cue, check mark for completed steps, wordmark, favicon.

### Missing, and fallback needing nothing from the operator
| Missing | Fallback |
|---|---|
| Transparent cut-outs | Multiply blend on a light panel, plus clip-path polygons. If the coder finds working image tooling (PIL, ImageMagick), it may replace the sprite with transparent WebP layers, but it must not be required. |
| Higher resolution | Display cap 560 px; design around it. |
| Real materials, brand, price, policy | Generic wording; placeholder content marked in footer and README. |
| Fonts | System stack designed to look intentional. If self-hosted woff2 can be downloaded, put them in `site/fonts/`. No hotlinked font CDNs. |
| Image rights | README flags it for confirmation. |

---

## 4. Designer

Output folder `design/`. Take an opinionated, subject-specific direction. Suggested starting concept (the designer may change it with a reason): **a pattern-maker's spec sheet**. A pale drawing-sheet stage, fine leader lines and part callouts, red used only for actions and the current step. Avoid the generic traits: cream with terracotta serif, near-black with acid accent, identical rounded cards, tracked caps eyebrows, middle-dot meta strings, "→" on every link. Spend the boldness in one place: the build stage.

### Tasks
1. **Design brief and tokens.** Write `design/design-notes.md` with: concept in one paragraph, palette of 4–6 named role colours with hex, light and dark values, a contrast table from `agentflow contrast` (text on surface, primary on surface, button text on primary, muted text, focus ring, the stage panel), type (max two families, roles, a modular scale, line lengths under 80 characters), spacing and radius scale, motion principles. Write `design/tokens.css` with `--color-*`, `--space-*`, `--radius-*`, `--font-*`, `--text-*` and a `prefers-color-scheme: dark` block. Starting values already checked: `#1E1A18` on `#EFEAE3` 14.4:1; `#A5202D` on `#EFEAE3` 6.2:1; white on `#A5202D` 7.4:1; `#5F5650` on `#EFEAE3` 6.0:1; `#F3EEE8` on `#1B1416` 15.7:1; `#E8505B` on `#1B1416` 4.95:1.
2. **Layout wireframes.** In `design/design-notes.md`, ASCII wireframes for 360 px and 1440 px of: top bar, opening stage, mid-build stage (with caption and progress nav), product section, sticky bar, static list. State alignment (left-aligned text, shoe centred), and where the size selector, price and CTA sit so price, shoe and CTA are visible at once after "Skip to buy" on a 360×740 screen.
3. **Final copy deck** in the same file. Refine the brief drafts, same voice (plain, active, sentence case), including: five captions, progress labels ("Step 3 of 5: Canvas upper"), size error ("Choose a size to add to cart."), success status ("Added to cart: Ember Low, EU 42. This is a demo, so no order was placed."), returns, delivery, "Price includes tax", footer placeholder notice, alt texts for all six views, aria-label for the animated stage ("Red canvas sneaker, built in five steps: sole, toe cap and sidewall, canvas upper, insole and lining, eyelets and laces."). No brand names, no countdowns, no stock counts.
4. **Layer map.** Write `design/layer-map.svg`: the V1 crop (`<image href="../inputs/photos/red-sneaker.png">` with a viewBox of 312×148 and a negative offset of 36,32) with labelled polygons for `sole`, `sidewall-toe`, `upper`, `laces` and an `upper-fill` polygon for the lace area, in V1-local coordinates. Add a second panel for `insole` from V3. Render it with `agentflow screenshot` and check the polygons hug the shoe with no white background inside. State the sheet size you measured or assumed.
5. **Shoe overlay SVG.** `design/shoe-outline.svg` (viewBox 0 0 312 148, V1-local): groups with ids `outline`, `stitches`, `eyelets` (six circles), `callouts` (leader lines for stripe, insole, eyelets), all with `pathLength="1"` on stroked paths so the coder can drive `stroke-dashoffset`. Plus `design/wordmark.svg` and `design/favicon.svg`.
6. **Motion spec.** Table in the notes that restates the storyboard timings with easing (linear for the scroll mapping, ease-out for hover and press), and the static-mode look.
7. **Mockup and screenshots.** `design/mockup.html` (static HTML using `design/tokens.css`) showing key frames: opening, step 3, step 4 (insole hovering), finished state, product section, sticky bar, static list. Render with `agentflow screenshot` at 360 and 1440 px into `design/shots/` (move or copy from `.shots/` if the tool allows; otherwise list the `.shots/` names in the notes). Review each shot critically and fix before handing off.
8. **`design/README.md`**: what is in the folder, how to open the mockup, what the coder must take from each file.

### Acceptance criteria
- Files exist: `design/design-notes.md`, `design/tokens.css`, `design/layer-map.svg`, `design/shoe-outline.svg`, `design/wordmark.svg`, `design/favicon.svg`, `design/mockup.html`, `design/README.md`.
- Every text and background pair listed passes WCAG 2.2 AA (4.5:1 body, 3:1 large text and UI) with ratios printed from the helper. Focus ring contrast at least 3:1 against both surface and stage panel.
- Palette names are roles, not hues. At most two typefaces, each with a fallback stack.
- The layer map screenshot shows the five polygons following the shoe edges; no white background inside any polygon; the assembled polygons cover the whole shoe except the lace area, which `laces` plus `upper-fill` cover.
- Eyelet circle positions sit on the eyelets in the V1 view in a screenshot overlay.
- The design says what the opening, step 3, step 4 and finished frames look like at 360 and 1440 px, and none of them requires enlarging the shoe over 560 px.
- Copy deck contains no third-party brand names and no unsupported claims.
- The notes name the single memorable element and list what was cut.

---

## 5. Coder

Output folder `site/`. Follow `design/` for look, tokens and copy; follow this plan for structure and behaviour.

### Files
```
site/index.html
site/css/tokens.css      (from design/tokens.css)
site/css/base.css        (reset, type, layout, focus, buttons)
site/css/build.css       (stage, layers, --p maths, static mode)
site/css/product.css     (viewer, buy panel, sticky bar, footer)
site/js/boot.js          (classic script, tiny, loaded in <head>)
site/js/main.js          (module entry)
site/js/build-driver.js  (CSS/JS driver selection, JS fallback)
site/js/build-nav.js     (step marker observer, progress nav state)
site/js/product.js       (viewer, size, add-to-cart, sticky bar)
site/assets/red-sneaker-sheet.png
site/assets/favicon.svg
site/README.md
```
Inline the outline SVG in `index.html` so CSS can drive it.

### Tasks
1. **Markup.** Semantic structure from Overview: `header`, `main` with `section#build` and `section#product`, `footer`, mobile `aside` bar. One `h1`. A "Skip to content" link first, then "Skip to buy". Build stage: wrapper `role="img"` with the design's aria-label, all layers and SVG `aria-hidden="true"`. Captions in an `<ol>` in DOM order, always readable by screen readers. Progress `nav aria-label="Build steps"` with five links to `#step-1`…`#step-5`, current one `aria-current="step"`. Step markers are empty absolutely positioned elements at the snap progress.
2. **`boot.js`.** Sets `data-build="pinned|static"` and `data-driver="css|js"` on `<html>` synchronously before paint. Static if reduced motion, `?build=static`, or no JS. Honours `?driver=js`. Re-evaluates when the reduced-motion media query changes.
3. **Build component (`build.css`).** `--p` on `.build`. Per-layer progress `--t: clamp(0, (var(--p) - var(--a)) / (var(--b) - var(--a)), 1)` using the storyboard ranges, set as `--a`/`--b` custom properties per layer. Transforms and opacity are `calc()`s of `--t`. Caption windows by the same method. `@property --p`. In `data-driver="css"`, a `scroll()` timeline on the track (or a named `scroll-timeline` on the track) animates `--p` 0→1 linearly. Sticky stage: `position: sticky; top: 0; height: 100svh` (with `100vh` fallback). Layer `div`s use `will-change: transform, opacity` only while pinned. Polygons from `design/layer-map.svg` converted to percentages.
4. **JS driver (`build-driver.js`).** Passive scroll and resize listeners, rAF throttled, computes `p` from the track rect, writes `--p`. Does nothing when the CSS driver is active or mode is static. Cleans up when switching to static.
5. **Static mode.** Five figures reusing the component with fixed `--p` from the snap table, captions and "Step N of 5" as text, no motion, no sticky stage, no pinned track. Hidden (`display: none`) in pinned mode so the screen reader never hears duplicates, and vice versa.
6. **Progress nav and step state (`build-nav.js`).** IntersectionObserver on step markers sets `data-step` on `.build` and updates the label and `aria-current`. No live-region announcements while scrolling. Keyboard focus on a nav link scrolls to its marker; smooth scrolling only when motion is allowed.
7. **Product section (`product.js`).** Viewer with six thumbnail `button`s (`aria-pressed`, labelled by the view name), cross-fade via opacity, large shoe. Size selector as a `fieldset` with `legend` and radio inputs EU 36–46, labels at least 44×44 px. Add to cart: no size chosen shows the inline error, moves focus to the size group and sets `aria-invalid`/`aria-describedby`; a chosen size shows the success status text in a polite live region. No storage, no network. The button text changes consistently: "Add to cart" then "Added to cart" for 2 seconds.
8. **Sticky bar.** Fixed bottom, mobile only, safe-area inset, shows from step 1 until the real CTA is intersecting, tapping with no size selected scrolls to and focuses the size group. Page bottom padding so it never hides footer text.
9. **Skip to buy.** Top-bar link jumps to `#product`; after the jump the finished shoe, price and size group are in view at 360×740 (check and tune `scroll-margin-top`).
10. **Accessibility and polish.** Visible `:focus-visible` rings (3:1), `prefers-reduced-motion` honoured (also CSS-only for hover transitions), `prefers-color-scheme` tokens, `lang="en"`, title and meta description, `theme-color`, favicon. Meaningful alt on gallery images, none on decorative ones.
11. **Performance.** Only `transform`, `opacity` and SVG stroke properties animate. Sheet loaded once and shared by all layers, `fetchpriority="high"` on the first used image (`<link rel="preload" as="image">` is fine). No layout reads inside scroll handlers except one rect. No libraries. Total page weight under 400 KB excluding fonts.
12. **README (`site/README.md`).** What it is, how to open (`index.html` directly or any static server), query hooks (`?driver=js`, `?build=static`), where to change name, price, sizes, copy, ranges and polygons, how to swap in a higher-resolution sheet, and a clearly worded **placeholder content and image rights** note.

### Acceptance criteria
- Opening `site/index.html` (via a static server or `file://`) renders without console errors and without any network request outside the folder.
- With `?driver=js` and with the native driver, the build looks the same at `p` = 0, 0.2, 0.36, 0.58, 0.665, 1 (screenshots at matching scroll positions); at 1 it matches the source side view.
- At `p = 1` the shoe has no gaps, no missing laces, and no white rectangles from the sheet over the stage.
- With `?build=static` or reduced motion: no pinned stage, five figures with captions, no running animation, same final state, no duplicate content for assistive tech.
- Progress nav links jump to the right step; current step labelled; all targets at least 44×44 px.
- "Skip to buy" lands on the product section with shoe, price and size group visible on a 360×740 screen.
- Add to cart without a size shows the error and focuses the size group; with a size shows the success status; keyboard-only works end to end; Tab order follows visual order.
- No horizontal scroll at 360, 768 and 1440 px.
- Shoe never rendered wider than 560 CSS px.
- Contrast and tokens match the design notes.

---

## 6. Checker

Test the built site; fix defects in `site/` directly (small, mechanical fixes), and log every fix. Write `docs/check-report.md`.

### Tasks
1. **Setup.** Confirm `site/` has all files listed in the Coder section and a README.
2. **Frame-by-frame.** With `agentflow screenshot site/index.html --scroll-y …`, capture the build at the scroll positions matching `p` = 0, 0.1, 0.2, 0.36, 0.5, 0.58, 0.665, 0.72, 0.85, 1 at widths 360 and 1440 (use the page's scroll height to convert; note the formula in the report). Repeat with `?driver=js`. Read each screenshot and compare with the storyboard.
3. **Static mode.** Capture `?build=static` full-page at 360 and 1440 and check five figures and captions.
4. **Product section.** Full-page screenshots at 360, 768, 1024 and 1440 px. Check viewer, thumbnails, size group, sticky bar (mobile), footer.
5. **Layout.** No horizontal overflow at 360 and 1440 px (inspect widest elements in screenshots). Check text up to 200% zoom equivalent by rendering at 360 with larger font-size if the helper allows, else by reading the CSS for fixed heights that would clip text.
6. **Accessibility audit by reading code and screenshots.** Heading order, landmark roles, alt text, labels, focus order, focus-ring visibility, `aria-current`, live region use, target sizes, contrast of every colour pair via `agentflow contrast`.
7. **Resolution check.** Confirm the shoe never exceeds 560 CSS px and looks acceptable at its displayed sizes.
8. **Performance review.** List all animated properties; confirm only `transform`, `opacity` and SVG stroke/fill. Check asset weights and that scroll handlers do no layout reads beyond one rect.
9. **Fix and re-test.** Fix defects, re-screenshot, record before/after.

### Acceptance criteria
- `docs/check-report.md` exists with: the scroll-to-`p` formula, a table of every screenshot with pass or fail and the file name in `.shots/`, a defect list (severity, where, fixed or not), and a contrast table with ratios.
- All items in the Coder acceptance list were tested and marked pass, or fail with a reason.
- No blocker or major defect remains open. Anything left is listed with a workaround.
- Anything that could not be tested with the available helpers (for example real device touch, real reduced-motion emulation, real screen reader) is listed explicitly instead of being claimed as passed.

---

## 7. Security

Static front-end, no backend, no data entry beyond a size choice. Review and fix in `site/`; write `docs/security-report.md`.

### Tasks
1. **No third-party requests.** Grep for `http://`, `https://`, `//cdn`, `@import url`, `<link rel="stylesheet" href="http`. Fonts must be local or system. No analytics, no trackers, no cookie banners.
2. **Content Security Policy.** Add a `<meta http-equiv="Content-Security-Policy">` in `site/index.html`, for example `default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'`. Verify the page still works with it (no inline scripts or styles; if inline `style` attributes are used for `--p` in static mode, move them to classes or allow with a documented reason and use a nonce-free alternative such as `data-*` plus CSS rules). Note in the report that `frame-ancestors` can only be set with a response header and give the header text for the host.
3. **JS review.** No `innerHTML`, `eval`, `document.write` or `new Function`. DOM text set with `textContent`. Query parameters (`driver`, `build`) are matched against an allow-list and never inserted into the DOM. No `localStorage`, cookies or network calls.
4. **HTML review.** `rel="noopener noreferrer"` on any external link (there should be none). The add-to-cart control is a `button type="button"` and no `<form action>` exists that could submit anywhere. No sensitive information in comments or README (the operator email must not appear).
5. **Privacy and content.** Placeholder price, policy and name are labelled as placeholders; no fake urgency; no unsupported claims in copy (sustainability, origin, handmade, certified). No third-party brand names or lookalike claims. Flag the image rights question for the operator in the report.
6. **Supply chain.** Confirm no `package.json`, no vendored libraries, no source maps pointing elsewhere.
7. **Fix and re-verify**; list residual risks.

### Acceptance criteria
- `docs/security-report.md` exists, lists each check with pass or fail, the evidence (command or file and line), and the fix applied.
- Zero third-party origins loaded. CSP present and the page still renders, builds, and adds to cart (re-test by screenshot and code read).
- No dynamic HTML injection. Query parameters allow-listed.
- Residual risks (image rights, header-only protections, placeholder content) are stated in plain language.

---

## 8. Final review

Judge the delivered result against the brief; fix only trivial issues, send anything else back with a clear list. Write `docs/final-review.md`.

### Tasks
1. Read `docs/brief.md`, this plan, `docs/check-report.md`, `docs/security-report.md`, then look at the site with `agentflow screenshot` at 360 and 1440 px: opening, steps 1 to 5, finished, product, static mode.
2. Walk the brief's success criteria (section 8) one by one and mark each pass or fail with evidence.
3. Design critique: is there one memorable element, does it look made for this product, are the generic tells (see Designer section) absent, is the copy plain and honest?
4. Check that every promised file exists, READMEs exist in `design/` and `site/`, names are kebab-case, placeholders are marked.
5. Check that open items from the reports are fixed or honestly listed.
6. Issue a verdict: ship, ship with named caveats, or return to a named agent with specific fixes.

### Acceptance criteria
- `docs/final-review.md` exists with the brief's nine success items each marked with evidence, a verdict, and a short list of operator actions: replace name, price, sizes, policies; confirm image rights; supply a higher-resolution source if wanted.
- Nothing in the review claims a check that was not run. Untested items are listed as untested.

---

## 9. Risks and how the plan handles them

| Risk | Handling |
|---|---|
| **Low-resolution, white-background illustration sheet** | Layers cut by `clip-path` from one sheet and blended with `multiply` on a light panel; no cut-out tooling needed. Display cap 560 px. Design relies on scale of type and composition, not on enlarging the shoe. Higher-resolution source is an operator action. |
| **Layer polygons do not match the shoe edge** | Designer builds and screenshots `layer-map.svg` before coding; checker compares `p = 1` with the source view. Lace area uses an explicit `upper-fill` polygon so no baked-in laces appear early. |
| **Multiply makes overlapping layers show through each other** | Multiply is applied once, to the whole layer group, not per layer; layers composite normally inside. Polygons are kept tight so white sheet background is never included. |
| **Mobile performance** | Six `div` layers sharing one image, transform and opacity only, `will-change` only while pinned, CSS driver where supported, a single rAF write in the JS driver, no layout reads beyond one rect. Page weight budget 400 KB. |
| **Animated `@property` runs on the main thread** | Acceptable for one number driving about ten elements; JS driver is the same cost. If the checker sees jank, switch the CSS driver to per-layer keyframes with `animation-range` (the `--t` formulas map directly). |
| **Browsers without scroll timelines** | `boot.js` selects the JS driver; identical visuals through the same `--p`. `?driver=js` makes this testable in any browser. |
| **Reduced motion, no JS, assistive tech** | Static five-figure list with fixed `--p`, same captions and end state; captions always in DOM as an ordered list; the animated stage is one labelled image. Live changes of the preference are handled. |
| **Scroll-jacking and impatient mobile shoppers** | Only 300 svh of pinned scroll, native scrolling (no wheel hijack), "Skip to buy" in the top bar at all times, sticky add-to-cart on mobile, step links in the progress nav. |
| **Mobile browser UI changes viewport height** | `svh` units with `vh` fallback, markers positioned from the track height, not from `innerHeight` in JS. |
| **Dark mode breaks multiply** | Stage and viewer panels stay light in dark mode; only page chrome changes. |
| **Unsupported claims and lookalike/brand risk** | Generic material words only; no brand names; README and footer flag placeholders; image rights flagged for the operator. |
| **Font hotlinking (privacy)** | System or self-hosted fonts only; Security checks it. |
| **Size estimates wrong** (sheet size, view boxes) | All coordinates are marked as estimates; designer and coder verify with screenshots before depending on them. |
