# Ember Low: design notes

The coder works from this file, `tokens.css`, `frames/frames.css` (a reference implementation of the build maths), and `svg/`. Every number below was checked in a rendered frame. Screenshots are in `shots/`.

## 1. Visual idea

**A shoe-maker's spec sheet.** The page is a raw-canvas table (`--color-surface`, greige `#E5E0D8`). On it lies a near-white drawing sheet (`--color-sheet`) holding the dashed cut line of the shoe. Parts arrive on the sheet one at a time, and each is pinned with a pattern-maker's numbered tag on a fine leader line. The canvas upper also gets a grainline arrow, the mark that shows which way the weave runs. Beside the sheet, the progress nav is a parts list. Its numbered dots match the tags on the sheet, and each dot turns into a check once that part is on.

- **The one memorable element:** the build sheet, where the cut line gets filled part by part and each part gets its numbered tag. Everything else is quiet: plain left-aligned type, one red, no decoration on the page chrome.
- **Red (`#A5202D`, the shoe's own canvas) is used only for actions** (Skip to buy, Add to cart) **and the current step** (step label, current dot). Nothing else on the page is red, so the shoe stays the loudest red thing.
- **Cut while designing:** corner registration marks on the sheet, a fine paper grain overlay, dimension lines with measurements (they would be invented specs), a mono face for tags, ALL-CAPS labels and eyebrows, card shadows, gradient washes, a second accent colour, and an arrow glyph on links.
- **Avoided generic tells:** this is not cream with a serif and terracotta, since the surface is a cool-leaning greige and the type is a DIN-style grotesque. It has no hairline broadsheet rules and no identical rounded cards. Radii vary by role: 3px for the paper sheet, 6px for controls, round for tags.

## 2. Source measurements (verify nothing else)

- `inputs/photos/red-sneaker.png` is **612 × 551 px**. I read this from `naturalWidth`/`naturalHeight` in the browser; the plan's estimate of 544 was 7 px short.
- **V1 side view box:** sheet x 36..348, y 32..180 (312 × 148). All build coordinates are V1-local.
- **Insole box (from V3):** sheet x 44..146, y 256..319 (102 × 63).
- **Gallery view boxes** (x, y, w, h in sheet px; checked in `shots/product-1280.png`):

| View | Box | Thumbnail label |
|---|---|---|
| Side (V1) | 36, 32, 312, 148 | Side view |
| Front (V2) | 408, 24, 134, 158 | Front view |
| Top (V3) | 34, 224, 312, 112 | Top view |
| Back (V4) | 428, 196, 114, 168 | Back view |
| Rear 3/4 (V5) | 52, 372, 246, 152 | Rear three-quarter view |
| Low front 3/4 (V6) | 340, 370, 252, 154 | Low front three-quarter view |

- `background-size` and `background-position` formula for any box (x, y, w, h): size `calc(612 / w * 100%) calc(551 / h * 100%)`, position `calc(x / (612 - w) * 100%) calc(y / (551 - h) * 100%)`. See `.cut` and `.view` in `frames/frames.css`.

## 3. Layers (must keep exactly)

The source of truth is `svg/layer-map.svg`, rendered in `shots/layer-map.png`. Panel B of that file assembles all layers on blue: there are no gaps and no white inside any polygon. Panel C shows each layer alone. Panel E checks the eyelet rings and stitch traces on the source.

| Layer | Arrives | Polygon notes |
|---|---|---|
| `sole` | step 1 | Everything below the split line (3.6,125.5)–(224,122)–(309,116.5), including the black stripe. |
| `sidewall-toe` | step 2 | White band from the split line up to the canvas, plus the toe bumper. |
| `insole` | step 4 | From V3: the tan region only, with the toe-side cut edge rounded. |
| `upper` | step 3 | Red canvas including the tan collar sliver, with a hole over the lace area. `.fill` (flat `--color-upper-fill: #931C25`) sits under it and closes the hole until the laces arrive. |
| `laces` | step 5 | Laces, eyelets and the eyelet stay: the hole area plus the lace loops that rise above the canvas edge. |

- **Stacking order in the blend group, bottom to top:** sole, sidewall-toe, insole, upper (fill under cut), laces.
- **Seam rule.** Where two parts meet, the part that arrives *later* overlaps the earlier one by 0.6 V1 units, and the earlier one stops 0.4 short of the true edge. Assembled, the overlap is invisible because the pixels are identical. Without it, anti-aliased clip edges leave a hairline, and a red sliver of the not-yet-arrived upper shows on the sidewall. Both problems appeared in my first renders and are fixed.
- **Clip-paths** are written as `polygon(calc(x * var(--x)) calc(y * var(--y)), …)` with `--x: 0.32051282%` (100/312) and `--y: 0.67567568%` (100/148). The V1 numbers stay readable and editable. Copy the blocks from `frames/frames.css` verbatim.
- **Multiply gotcha (must keep):** `.shoe__body` carries the settle transform, which makes it a stacking context. It must paint `background: var(--color-sheet)` plus `box-shadow: 0 0 0 3rem var(--color-sheet)`, and the sheet needs `overflow: clip`. Otherwise the multiply group blends against transparency and the sheet's white shows.
- **Result at p = 1:** the side view is reproduced pixel for pixel (`shots/stage-6-1280.png`).

## 4. Overlay SVG (`svg/shoe-overlay.svg`, inline it)

- **viewBox and placement.** The viewBox is `0 0 312 148`, laid exactly over the layer box with `overflow: visible`. Tags reach x −15..326 and y −24..174, which is why the shoe width is `min(560px, 88cqw, 148cqh)` inside the sheet.
- **Hooks are classes,** because ids repeat in the static list: `.outline`, `.outline-reveal-path` (in a `<mask>`, because the cut line is dashed), `.stitches > .stitch` (collar, vamp), `.eyelets > .eyelet` ×6, `.callout.callout--{sole,toe,upper,insole,laces}` each with `.callout-leader`, `.callout-pin` and `.callout-tag`, and `.grainline` inside `callout--upper`.
- **Drawable paths.** Every stroked path has `pathLength="1"`, so draw it with `stroke-dasharray: 1` and animate `stroke-dashoffset` from 1 to 0.
- **Eyelet centres (V1):** (111.1,45) (134.3,53.6) (157.9,62.9) (181.4,70.7) (206,77.9) (231.4,85.7), r 4.6. They sit on the source eyelets (layer map, panel E).
- **Other artwork:** `svg/contact-shadow.svg` goes *behind* the layer group, inside `.shoe__body`. `svg/mark.svg` is the top-bar mark (use it next to HTML text). `svg/wordmark.svg` is the lock-up for previews. `svg/favicon.svg` is the favicon. `svg/icons.svg` holds the chevron, check and alert icons.

## 5. Motion spec

The scroll mapping is linear: `--p` goes 0 to 1 over the track. Easing lives in the maths: `e = t(2 − t)` is a quadratic ease-out for entrances, and `s = t²(3 − 2t)` is smoothstep for the insole sink. Each window uses `t = clamp(0, (p − a) / (b − a), 1)`. Transforms are given as percentages of the layer box, so they scale with the shoe.

| # | Range | What moves | Exact values |
|---|---|---|---|
| 0 | 0–8% | Cut line already drawn at p = 0. Intro text leaves. | `.outline` opacity .7. Intro opacity `1 − o` and translateY `−16px·o`, with o over .04–.08. In the site, one load-time draw-on of the cut line (900ms, `--ease-out`) when motion is allowed. |
| 1 | 8–24% | Sole rises | `a .08 b .18`, translateY `(1−e)·24%`, opacity t. Tag 1 shows .14–.24. |
| 2 | 24–40% | Toe cap and sidewall slide in from the toe | `a .24 b .34`, translateX `(1−e)·13%`. Tag 2 shows .32–.40. |
| 3 | 40–60% | Upper drops; stitches draw; grainline | `a .40 b .52`, translateY `(1−e)·−36%`. Stitches draw .52–.58, then drop to 35% opacity by .60 and fade out .94–.98. Tag 3 and grainline show .52–.60. |
| 4 | 60–78% | Insole appears, hovers, sinks behind the upper | Box at V1 x 1, y 56.5, 102 × 63, `scale(.8, .42)`. `--lift = 1 + .12(1 − t₁) − s₂`, translateY `lift · −101.587%`. t₁ .60–.64 (appear), s₂ .68–.76 (sink), opacity `t₁ · (1 − t₃)` with t₃ .76–.78. Tag 4 shows .62–.685. |
| 5 | 78–94% | Eyelet rings draw one by one, then laces drop | Rings draw .78–.84 (ring i over its sixth of the window) and fade .90–.94. Laces `a .84 b .92`, translateY `(1−e)·−16%`. Tag 5 shows .86–.94. |
| 6 | 94–100% | Settle | `.shoe__body` translateY `(1−e)·−1.5%` and scale `.96 + .04e`. Contact shadow opacity e. Cut line fades .88–.96. |

- **Callout fades:** opacity `in · out`, with `in = clamp(0,(p−a)/.02,1)` and `out = clamp(0,(b−p)/.02,1)`. The leader and grainline draw over the first 3% of the window.
- **Captions:** same slot, windows 8–24, 24–40, 40–60, 60–78, 78–102, with 2% fades and an 8px rise on entry.
- **Snap values** (static figures and jump targets): .20, .36, .58, .665, 1. Jumping to step 5 in pinned mode uses .93.
- **UI motion:** hover and press use `--duration-base` / `--duration-quick` with `--ease-out`. Thumbnails cross-fade over 200ms. The sticky bar fades and slides 100% from the bottom over 200ms. With reduced motion there are no transitions.
- **Static mode** (reduced motion, no JS, `?build=static`): `frames/static-list.html`. Five figures, each a sheet with the component at its snap `--p` and the caption beside it (desktop) or below it (mobile). There is no sticky stage and no motion. Figures 1–4 hide the shoe from assistive tech (`aria-hidden`) because the figcaption says it. Figure 5 has a real alt text.

## 6. Colour and contrast

All ratios below were printed by `agentflow contrast`.

**Light scheme (page chrome)**

| Pair | Ratio |
|---|---|
| text `#1F1A1B` on surface `#E5E0D8` | 13.08 AAA |
| text on sheet `#F7F5F1` | 15.78 AAA |
| text on raised `#F2EFEA` (sticky bar, size options) | 14.99 AAA |
| muted `#5B5250` on surface | 5.78 AA |
| muted on sheet | 6.97 AA |
| muted on raised | 6.62 AA |
| primary `#A5202D` on surface (step label, Skip to buy) | 5.62 AA |
| primary on sheet | 6.78 AA |
| primary on raised | 6.44 AA |
| white on primary (button text) | 7.38 AAA |
| white on primary-hover `#8C1A26` | 9.17 AAA |
| selected size: surface `#E5E0D8` on text `#1F1A1B` | 13.08 AAA |
| control border `#6E6566` on surface (UI, needs 3:1) | 4.30 pass |
| control border on raised | 4.93 pass |
| cut line `#6E6566` on sheet | 5.19 |
| focus ring `#1F1A1B` on surface / sheet | 13.08 / 15.78 (needs 3:1) |
| tag numeral `#F7F5F1` on tag `#1F1A1B` | 15.78 |

**Dark scheme (page chrome only; the sheet stays light)**

| Pair | Ratio |
|---|---|
| text `#F3EEE8` on surface `#1B1416` | 15.72 AAA |
| text on raised `#261D20` | 14.23 AAA |
| muted `#B9AEA8` on surface / raised | 8.36 / 7.57 AAA |
| primary `#EE6670` on surface / raised | 5.84 / 5.29 AA |
| button text `#1B1416` on primary | 5.84 AA |
| button text on primary-hover `#F49AA0` | 8.61 AAA |
| selected size `#1B1416` on `#F3EEE8` | 15.72 |
| control border `#8F8582` on surface / raised | 5.05 / 4.57 |
| focus `#F3EEE8` on surface | 15.72 |

Two traps, both handled in `tokens.css`:

- **`#EE6670` on the sheet fails (2.85).** Inside `.sheet` the tokens re-point to the light values: primary goes back to `#A5202D`, text and focus to `#1F1A1B`. The dark-mode focus colour would also be invisible on the sheet without this.
- **Muted `#6E6566` on surface is 4.30.** That is fine for borders and the cut line but not body text, so it is never used for text on the surface.

## 7. Type

- **Display:** `Bahnschrift, "DIN Alternate", "DIN Condensed", "D-DIN", "Roboto Condensed", "sans-serif-condensed", "Arial Narrow", …, system-ui`, bold, `font-stretch: 87.5%`. This is DIN lettering, the standard for engineering drawings, and it ships with Windows (Bahnschrift), macOS/iOS (DIN Alternate) and Android (sans-serif-condensed). Use it for the H1, part names, the price, the wordmark, tag numerals and the closing line.
- **Body:** the system UI stack.
- **Self-hosting:** no web fonts are downloaded, per the plan. If the coder can self-host an OFL DIN-like face (for example D-DIN) in `site/fonts/`, it would make every platform match; it is optional.
- **Scale** (classic typographic scale 14 / 16 / 18 / 21 / 24 / 36 / 48 / 72): H1 `clamp(44px … 72px)`, leading .95, −0.01em; part name 32–48px, leading 1.2; price 36px; captions 18px; body 16px, leading 1.5; small 14px.
- **Line length:** captions max 24rem (about 45 characters), body max 34rem (about 65). All text is left-aligned and the shoe is centred in its sheet.
- **Screenshot caveat:** the headless renderer has none of the display faces, so the screenshots fall back to a plain grotesque (Inter or Liberation). On Windows, Mac and Android the headings will be narrower DIN.

## 8. Layout and wireframes

**360 px, pinned stage** (`shots/stage-*-375.png`). The stage height is `100svh − 48px`, with rows sheet / text / nav and `align-content: space-between`.

```
┌──────────────────────────────┐
│ ▰ Ember Low     [Skip to buy]│ 48px top bar, sticky
│┌────────────────────────────┐│
││          sheet             ││ clamp(15rem, 50svh, 27rem)
││   (insole/tags room above) ││ shoe ≤ 88cqw, about 300px
││      ▁▁▂▃▅▆ shoe ▆▅▃▂      ││
│└────────────────────────────┘│
│ Step 3 of 5        (red)     │ intro OR caption, one slot
│ Canvas upper       (32px)    │
│ Red canvas, stitched in …    │
│                              │
│ ●──●──③──○──○                │ five 44px targets, track line
└──────────────────────────────┘
```

**1440 px, pinned stage**

```
┌───────────────────────────────────────────────────────────────┐
│ ▰ Ember Low                                     [Skip to buy] │ 56px
│ ┌ text 18–26rem ┐   ┌──────────── sheet ────────────────────┐ │
│ │ Step 3 of 5   │   │                                       │ │
│ │ Canvas upper  │   │          ③                            │ │
│ │ Red canvas …  │   │    ╭──╮ ╱                             │ │
│ │               │   │  ▁▅▆▆▆▆▅▃▂▁  (shoe ≤ 560px)           │ │
│ │ ✓ Sole        │   │  ▀▀▀▀▀▀▀▀▀▀▀                          │ │
│ │ ✓ Toe cap …   │   │                                       │ │
│ │ ③ Canvas upper│   │                                       │ │
│ │ ○ Insole …    │   └───────────────────────────────────────┘ │
│ │ ○ Eyelets …   │                                             │
└───────────────────────────────────────────────────────────────┘
```

**Opening.** Same grid. The intro (H1, sub, cue) sits in the caption slot and the sheet shows only the cut line (`stage-0`).

**Product, 360 px.** The skip target scrolls to just under the top bar (`scroll-margin-top: var(--bar-height)`).

```
│ Ember Low            69 EUR │ name 32px / price 36px
│ Red canvas low-top…  Price includes tax
│┌────────── sheet ──────────┐│ 16:10 viewer, shoe ≈ 300px
│└───────────────────────────┘│
│ [▣][ ][ ][ ][ ][ ]          │ six 44px+ thumbnails
│ Size (EU)                   │
│ [36][37][38][39][40][41]    │ 6-column grid, 44px tall
│ [42][43][44][45][46]        │
│ [        Add to cart       ]│ 52px, ends about 650px down
│ ✓ status / ! error          │
│ Free returns… Delivered…    │
│ What it is made of 1–5      │
│ Ready to wear on day one.   │
```

At 360 × 740, after "Skip to buy", the name, price, finished shoe, sizes and the Add to cart button are all on screen (`shots/product-375.png`; the button's bottom edge is at about 650px).

**Product, 1440 px.** Columns 7fr / 5fr. The viewer is sticky on the left, with thumbnails under it. On the right: name, lead, price, tax line, sizes (6 per row), the full-width CTA, status, terms, the made-of list and the closing line.

**Sticky bar (below 768 px).** Fixed bottom bar on `--color-surface-raised` with a 1px top border: name and price on the left, a 48px "Add to cart" on the right, plus the safe-area inset. The footer gets enough bottom padding that the bar never covers text (`shots/sticky-bar-375.png`).

**Static list.** H1 and a static sub-line, then five figures: sheet left (7fr) and caption right (5fr) on desktop, stacked on mobile (`shots/static-list-*.png`).

**Above 1440 px,** content caps at `--page-max` (84rem) and centres. The shoe never exceeds 560px anywhere, including the product viewer, where `.view` width is ≤ native × 1.8.

## 9. Copy deck (final)

- **Skip links:** "Skip to content" (first in the tab order), "Skip to buy" (top bar).
- **H1:** Built layer by layer.
- **Sub (pinned):** Five parts. One everyday sneaker. Scroll to see how it comes together.
- **Sub (static mode):** Five parts. One everyday sneaker. Here is how it comes together.
- **Cue:** Scroll to build it
- **Stage aria-label:** Red canvas sneaker, built in five steps: sole, toe cap and sidewall, canvas upper, insole and lining, eyelets and laces.
- **Progress nav** `aria-label`: Build steps. Link names are "Step N of 5: Part" plus the material:

| N | Part | Material line | Caption |
|---|---|---|---|
| 1 | Sole | Rubber | A flat rubber sole with a single black stripe. |
| 2 | Toe cap and sidewall | Rubber | A rubber toe cap and sidewall that wipe clean. |
| 3 | Canvas upper | Canvas, contrast thread | Red canvas, stitched in contrast thread. |
| 4 | Insole and lining | Fabric | A soft fabric lining and insole, tan and plain. |
| 5 | Eyelets and laces | Metal, flat lace | Six pairs of metal eyelets and flat white laces. |

- **Product name:** Ember Low (placeholder). **Lead:** Red canvas low-top on a white rubber sole.
- **Price:** 69 EUR (placeholder). **Tax line:** Price includes tax
- **Size legend:** Size (EU), with sizes 36–46 (placeholder).
- **CTA:** Add to cart, which reads "Added to cart" for 2 s after a successful add.
- **Size error:** Choose a size to add to cart.
- **Success status:** Added to cart: Ember Low, EU 42. This is a demo, so no order was placed.
- **Returns:** Free returns within 30 days. (placeholder)
- **Delivery:** Delivered in 2 to 4 working days. (placeholder)
- **Made-of heading:** What it is made of. Items: Rubber sole with a single black stripe; Rubber toe cap and sidewall; Red canvas upper, contrast stitching; Fabric insole and lining; Metal eyelets and flat white laces.
- **Closing line:** Ready to wear on day one.
- **Footer:** Demo page. The name, price, sizes, returns and delivery terms are placeholders.
- **Sticky bar:** `aria-label` "Quick add to cart", with name, price and Add to cart.
- **Thumbnail labels:** Side view, Front view, Top view, Back view, Rear three-quarter view, Low front three-quarter view.
- **Alt texts:**
  - Side: Red canvas low-top sneaker from the side: white rubber sole with a black stripe, white toe cap, white laces through six metal eyelets.
  - Front: The sneaker from the front, angled: white rubber toe cap and white laces crossing the red tongue.
  - Top: The sneaker from above: tan insole and lining inside, white laces across the red canvas, rounded white toe.
  - Back: The sneaker from the back: red heel with a centre seam, tan lining at the collar, white sole with a black stripe.
  - Rear three-quarter: The sneaker from behind at an angle: tan lining, laces hanging loose, black stripe along the sole.
  - Low front three-quarter: The sneaker from the front at a low angle: white toe cap, one lace end hanging loose, black stripe along the sole.
  - Static figure 5: The finished sneaker from the side: red canvas upper, white rubber sole with a black stripe, white laces through six metal eyelets.

The copy has no brand names, no origin, sustainability, certification or handmade claims, no countdowns and no stock counts.

## 10. Accessibility details to keep

- **Focus.** The ring is 3px in `--color-focus` with a 2px offset. Size radios show the ring on their visible `span`. Inside `.sheet` the focus colour is always dark.
- **Targets.** All targets are at least 44 × 44: nav dots, sizes, thumbnails, top-bar links. The current dot grows to 36px inside its 44px target.
- **Mobile nav names.** Part names in the nav are visually hidden on mobile, not `display: none`, so they stay in the accessible name.
- **Error state.** Size borders turn `--color-error`, and the message has an alert icon, so the error is not shown by colour alone. The live region for success is `role="status"`. Show the error and success lines one at a time, never together. The product frame shows the error line at the bottom only as a reference.

## 11. Deviations from the plan (and why)

1. **Folder layout.** SVGs live in `design/svg/` (the role brief asks for `svg/`). The plan's `design/shoe-outline.svg` is `design/svg/shoe-overlay.svg`, because it holds the outline, stitches, eyelets and callouts. The layer map is `design/svg/layer-map.svg`. The frames are `design/frames/stage-0…6.html` plus `product.html` and `static-list.html`. `design/mockup.html` is a contact sheet of all of them.
2. **The cut line is drawn at p = 0,** with an optional one-time load draw-on, instead of drawing over 0–6%. Otherwise the opening frame would be an empty sheet.
3. **The intro fades at 4–8%,** not 6–12%, so it never overlaps caption 1, which fades in at 8–10%.
4. **Transforms are in % of the shoe box,** not px, so mobile and desktop match. 24% ≈ 64px, 13% ≈ 72px, 36% ≈ 96px and 16% ≈ 44px at 560px. The insole uses `scale(.8, .42)` instead of `.38` (it read as a stick at .3–.38) and is hidden behind the upper at rest.
5. **The sticky add-to-cart bar appears after the build** (when the track has scrolled past) and hides while the real button is visible. The brief says "after the build", and a bar during the build would cover the mobile progress nav.
6. **Static step 5 uses p = 1** (the finished shoe), so the static list ends on the same state as the animation.
7. **Upper-fill colour is `#931C25`,** not the sampled `#A5202D`. After multiply the lighter red read as a patch (comparison in `_probe/fill-test.html`).

## 12. Known gaps

- **Dark mode and reduced motion** were not rendered, because the helper cannot emulate media queries. Both are specified in tokens and CSS and need a check in a real browser.
- **Display fonts** are not present in the screenshot renderer; see the type caveat in section 7.
- **The toe-cap seam** still shows a faint pink anti-alias line at step 2 (the source pixels themselves), visible only at 100% zoom.
- **`design/_probe/`** holds my measurement pages (grids, zooms, fill test). They are not deliverables; delete them freely.
