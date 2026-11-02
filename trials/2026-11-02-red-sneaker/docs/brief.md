# Brief: red canvas sneaker scroll-build landing page

Operator's idea: *Landing page for this red canvas sneaker: as you scroll, the shoe is built from its materials.*

Anything marked **Assumption** was added by the brief reviewer and can be corrected by the operator.

## 1. Goal
Make a visitor understand what the shoe is made of, trust it, and add it to the cart.
- Primary action: add to cart, with a size chosen.
- Feeling: "simple, honest, well made".

## 2. Audience
- Shoppers comparing products, mostly on **mobile**, with little patience.
- **Assumption:** they arrive from social or ads, know what a canvas sneaker is, and want to see the look, the price and the returns quickly.
- Design for 360 px first. It must also work up to 1440 px and beyond.

## 3. Product facts
Seen in the supplied image:
- Low-top sneaker with a deep red canvas upper and visible stitching.
- White rubber toe cap, foxing and sidewall, with a single black stripe.
- Metal eyelets (about 6 per side) and flat white laces.
- Tan fabric insole and lining. Heel seam at the back. No logos or text.

Placeholders, which the operator must replace:
- **Assumption:** name "Ember Low".
- **Assumption:** price 69 EUR, tax included.
- **Assumption:** sizes EU 36–46.
- **Assumption:** returns "free within 30 days", delivery "2–4 working days".
- **Assumption:** one colourway only (red).

Claims rule: use only generic material descriptions. No sustainability, origin, certification or "handmade" claims unless the operator supplies evidence.

## 4. The experience (what happens as the visitor scrolls)
A short pinned scroll sequence where the shoe assembles layer by layer, then a clear buy section.

1. **Opening.** The shoe is shown as separate floating parts or an empty outline, with the headline and a "Scroll to build it" cue. A visible "Skip to buy" link is always available.
2. **Stage 1, Sole.** The white rubber sole and its black stripe appear. The caption names the material.
3. **Stage 2, Toe cap and sidewall.** Rubber toe cap and sidewall join the sole.
4. **Stage 3, Canvas upper.** The red canvas upper drops into place, with its stitching.
5. **Stage 4, Insole and lining.** The tan insole and lining are revealed (a top-down view fits here).
6. **Stage 5, Eyelets and laces.** Metal eyelets and white laces are added. The finished shoe settles into the hero pose.
7. **Reveal.** A gallery of the six views, then the buy block: price, size selector, add to cart, returns, shipping.

Behaviour rules:
- A small progress indicator ("Step 3 of 5, Canvas upper") that is also an anchor to skip ahead.
- The whole build should take about 3–4 screen heights on mobile. **Assumption.**
- After the build, a sticky add-to-cart bar stays visible on mobile.
- Reduced motion: no scroll animation. Show all 5 stages as a stacked list or grid with the same captions. The end state is the same.
- Only `transform`, `opacity` and SVG stroke/fill are animated.

**Assumption:** the build is a layered illustration made by slicing and masking the six views of the supplied sheet. It is not a 3D model and not real photographed layers. It should read as a clean exploded diagram.

## 5. Content
Drafts to refine, not final copy:
- **Headline:** "Built layer by layer."
- **Subhead:** "Five parts. One everyday sneaker. Scroll to see how it comes together."
- **Stage captions:**
  1. Sole: "A flat rubber sole with the single black stripe."
  2. Toe cap and sidewall: "A rubber toe cap and sidewall that wipe clean."
  3. Upper: "Red canvas, stitched in contrast thread."
  4. Insole: "A soft fabric lining and insole, tan and plain."
  5. Laces: "Metal eyelets and flat white laces."
- **CTA:** "Add to cart" (primary), "Skip to buy" (secondary).
- **Trust block:** returns, delivery, and "price includes tax". No countdown timers, no fake stock counts, no pop-ups.
- **Closing line:** "Ready to wear on day one."

## 6. Visual direction
- **Assumption:** a warm neutral surface so the product shines. The shoe's deep red is the single accent and is used for actions. Dark text for contrast.
- Colour tokens are named by role (surface, text, primary, accent). Check contrast with the colour helper before the designer finalises the palette.
- Two typefaces at most, system or Google Fonts.
- Product imagery is large. No tiny product photos.

## 7. Constraints
- Stack: semantic HTML, modern CSS, vanilla JS ES modules. No build step, no dependencies.
- Accessibility: WCAG 2.2 AA. Visible focus states, keyboard access, labelled form controls, alt text on every image, meaningful text alternatives for the animated build.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`.
- Responsive from 360 px to 1440 px and beyond.
- Performance: keep image weight low, use WebP/PNG with the correct sizes, and don't enlarge the source views past their quality. Avoid layout thrash.
- Legal: no third-party brand names or lookalike claims in the copy. The operator must confirm image rights.
- Every deliverable folder has a README. File and folder names in kebab-case.

## 8. Success criteria
- On a 360 px phone, a visitor can see the finished shoe, the price and an add-to-cart button within the first two screens, or after one tap on "Skip to buy".
- The scroll build is smooth, readable and skippable, and is never the only way to reach the purchase block.
- The reduced-motion version carries the same information.
- Text and controls pass WCAG 2.2 AA contrast. All interactive elements work by keyboard.
- No horizontal scroll at 360 px or 1440 px.
- The shoe images look sharp at their displayed sizes.

## 9. Out of scope
- Real cart, checkout, payment, accounts or search.
- Multiple products, listing pages, filters and reviews.
- Additional colourways, or a 3D/WebGL model.
- New photography or retouching beyond slicing and cleaning the supplied sheet.
- Sustainability, origin or certification claims.
- Countdown timers, stock-urgency messages and pop-ups.
- Analytics and cookie banners.
