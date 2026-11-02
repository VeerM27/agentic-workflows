# check: page_checker

**Verdict:** approve

Shippable. I made no changes to `site/` and did not write `docs/check-report.md`, because my role is review only; the evidence is below. All files and references exist, with no inline scripts or styles, external URLs, `innerHTML`, storage or network calls. Total weight is about 300 KB.

I checked the scroll story with the native CSS timeline driver at 1280px and 375px, and spot-checked 768, 1024 and 1440. The frames were p = 0, .1, .2, .36, .5, .58, .665, .72, .85 and 1 at 1280, and p = 0, .2, .36, .58, .665, .85 and 1 at 375. Each frame matches the storyboard and `design/shots`:
- The outline draws on, then the sole rises, the toe cap slides in, the upper drops and the insole hovers, then sinks behind the upper.
- Eyelets draw, laces drop, and the shoe settles with its contact shadow.
- At p = 1 the shoe is complete, with no white patches or gaps.
- The progress dot matches the visible step in every frame, and the finished state matches the source side view.

"Skip to buy" at 375×800 shows the name, price, shoe, sizes and Add to cart together. The sticky bar appears only while the real button is off screen, as planned. No horizontal overflow appears at any width. The shoe never exceeds 560px (about 546px at 1440).

Every text and UI colour pair passes AA in light and dark, per `agentflow contrast`; the lowest is the 4.30:1 control border against 3:1 required. Only `transform`, `opacity` and `stroke-dashoffset` are derived from `--p`, and the rest of the CSS animates only transforms and opacity. The JS driver reads one rect per frame.

Not tested. A blocked file-copy command stopped me making modified copies of the page, and the screenshot tool ignores query strings and hashes:
- Static, reduced-motion and no-JS mode, the `?driver=js` fallback, step-link jumps, and the add-to-cart error and success states. I read the code for these and found no defects.
- Dark mode.
- Real keyboard Tab order and focus rings, screen readers and real devices.
- DIN fonts.

The static-mode `--p` values map correctly to the layer, callout and stitch windows in the CSS.

Remaining items are minor, and the operator can send any to the coder.

## Issues

1. [minor] site/index.html:269 (fieldset.sizes aria-describedby="size-error"); site/js/product.js:53 (aria-invalid on radios): The fieldset always points at the hidden error paragraph. Referenced hidden elements are still read, so screen-reader users hear "Choose a size to add to cart." as the group description before any error. `aria-invalid` is also set on individual radio inputs, where it isn't a supported ARIA attribute.
   Fix: Add `aria-describedby` only in `showError()` and remove it in `clearError()`. Put `aria-invalid` on the fieldset or a `role="radiogroup"` wrapper instead of on each input.
2. [minor] site/css/build.css:28-36 (--stage-h: max(34rem, 100svh - bar)); .build__sheet height clamp: The 34rem (544px) minimum stage height is taller than the viewport on short screens such as phones in landscape, or desktop at 200–400% zoom. The caption and step nav then sit below the fold while the stage is pinned, so the step links are hard to reach. Skip to buy still works.
   Fix: Drop the 34rem minimum, or on short viewports (`@media (max-height: 34rem)`) shrink `.build__sheet` and reduce the stage gaps. Alternatively, in that case let the stage unpin and stack normally.
3. [minor] site/assets/red-sneaker-sheet.png; --shoe-max in site/css/tokens.css: The source views are about 310px wide and are shown up to about 546px, so about 1.75× upscaled on desktop and more than 2.5× on 2–3× phones. The hero and product shots are visibly soft. The brief's "looks sharp at displayed sizes" is only partly met, a limit of the supplied image that the plan accepted. The 214 KB PNG could also be smaller as WebP.
   Fix: Operator action: supply a higher-resolution sheet. The README already explains the swap and the `--shoe-max` change. Optionally convert the sheet to WebP if tooling is available.
4. [minor] site/css/base.css .topbar vs site/css/build.css .build__stage (max-width: var(--page-max)): At 1440px the top bar spans the full width (wordmark at x≈38, Skip to buy at x≈1403), while the page content is centred at 84rem (text at x≈84, sheet ends at x≈1356). The header and content edges don't line up on wide screens.
   Fix: Give `.topbar` the same `max-width: var(--page-max); margin-inline: auto` inner container, or align the content gutters to the bar.
5. [minor] site/css/build.css `.layer--sidewall-toe` clip-path (around p = .36, 1280px): A thin pinkish line is faintly visible along the top edge of the white sidewall band when it lands. Red pixels from the upper's lower edge fall inside the sidewall polygon. It disappears under the upper, so it is cosmetic.
   Fix: Nudge the top edge of the sidewall polygon (the y ≈ 110–111 points) down about 0.5 V1 units, and compare it at p = .36.
