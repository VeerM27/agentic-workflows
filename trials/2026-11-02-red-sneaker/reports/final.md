# final: final_reviewer

**Verdict:** approve

Release note: "Ember Low" is a single-page landing site in `site/`. It has a pinned scroll sequence of about 3–4 screens, where the red canvas sneaker is built in five steps (sole, toe cap and sidewall, canvas upper, insole and lining, eyelets and laces). It then reaches a buy section with a six-view viewer, EU 36–46 size picker, add-to-cart, a trust block and a mobile sticky bar. The brief's scroll story is delivered, and the finished shoe is complete and clean. I checked frames rendered at 1280px (p = 0, .36, 1 and the product section) and 375px (top, step 4, product). Each frame matched the storyboard, the progress dot matched the visible step, and nothing overflowed. On mobile, "Skip to buy" shows the name, price, shoe, sizes and Add to cart together. Copy matches the brief, with no invented claims, brand names, timers or pop-ups. The checker and security reviews both approved with only minor items, none of which blocks publishing. I could not test add-to-cart states, keyboard focus, dark mode, reduced-motion emulation, screen readers or real devices, and neither could the earlier reviewers. Look first at the build at scroll positions around 860px (toe cap landing) and 2400px (finished shoe), then tap "Skip to buy". Known limits: the supplied sheet is only about 310px per view, so the shoe is visibly soft at desktop size (a higher-resolution sheet would fix it). The scripts are classic deferred scripts, not ES modules, so the page also works from `file://`. The README documents this. Before launch, the operator must replace the placeholders (name, 69 EUR, sizes, returns and delivery wording), confirm image rights, and strip image metadata. The host must send the security headers, because a meta CSP does not cover `frame-ancestors`, HSTS or nosniff.

## Issues

1. [minor] site/index.html:290-293 (returns and delivery terms) and :310 (footer): "Free returns within 30 days" and "Delivered in 2 to 4 working days" are stated as fact. Only the footer says they are placeholders, so a visitor could read them as real commitments.
   Fix: Before launch, replace them with confirmed terms or remove them. Keep the footer placeholder notice until then.
2. [minor] site/index.html:6 (meta CSP) and the host configuration: The meta CSP allows `data:` images, which nothing uses. `frame-ancestors`, HSTS, nosniff and Referrer-Policy have no effect when set in a meta tag.
   Fix: Change to `img-src 'self'`. Have the host send the full header set from `reports/security.md`, and list it in the README.
3. [minor] site/assets/red-sneaker-sheet.png: Image metadata could not be checked, and the source views are about 310px wide, shown up to about 546px, so the shoe is soft on desktop and high-density phones. Image rights are unconfirmed.
   Fix: Operator action: confirm rights, strip metadata, and supply a higher-resolution sheet if possible (the README explains the `--shoe-max` change).
4. [minor] site/index.html:269 and site/js/product.js:53: The size fieldset always has `aria-describedby` pointing at the hidden error text, and `aria-invalid` is set on individual radio inputs, where it is not supported.
   Fix: Add `aria-describedby` only while the error shows. Put `aria-invalid` on the fieldset or a `role=radiogroup` wrapper.
5. [minor] site/css/build.css:28-36 (--stage-h minimum of 34rem): The 34rem minimum stage height is taller than short viewports (landscape phones, high zoom), so the caption and step nav can fall below the fold while pinned. Skip to buy still works.
   Fix: Add a short-viewport media query that shrinks the stage, or drop the minimum.
6. [minor] site/css/base.css .topbar vs site/css/build.css .build__stage: At 1440px the top bar spans the full width while the content is centred at 84rem, so the edges do not line up.
   Fix: Give the top bar the same max-width and centring as the page content.
7. [minor] site/css/build.css .layer--sidewall-toe clip-path (around p = .36): A faint pink line shows along the top of the sidewall band as it lands. It is cosmetic and disappears under the upper.
   Fix: Nudge the top edge of the sidewall polygon down about 0.5 V1 units.
