# Brief review: red canvas sneaker scroll-build landing page

Request as written: *"Landing page for this red canvas sneaker: as you scroll, the shoe is built from its materials."*

## 1. What is clear
- **One product, one page.** A landing page for a single low-top red canvas sneaker.
- **One core mechanic.** Scroll progress drives the shoe being assembled from its materials. This is the whole idea, and the brief keeps it.
- **Industry context.** E-commerce. The audience is mostly mobile shoppers with little patience. Product imagery comes first, price and add-to-cart are prominent, and there are no fake-urgency tricks.

## 2. What is missing or ambiguous

| Gap | Why it matters downstream | Decision taken |
|---|---|---|
| No brand or product name | The copy, title and visual identity all need one. | Placeholder name **"Ember Low"** (**Assumption**). The operator swaps it. |
| No price, sizes, shipping or returns | An e-commerce landing page needs a purchase block, and the industry profile demands clear pricing and returns. | Placeholder values, clearly marked as such in the brief. |
| "Materials" are not listed | The build sequence needs real layers. The image shows the shoe but not what it is made of. | Layers inferred from the image (section 5). Material claims are kept generic and unverified. |
| Is the page a story or a shop? | A pure story fails mobile shoppers who want to buy. | The page is a story with a persistent, lightweight buy path. It is not a full shop. |
| No material photos, only one product sheet | The build can't show real fabric or rubber close-ups. | The build is an illustrated or diagrammatic assembly made from the supplied views (see fix F1). |
| Tone, brand colours, fonts | The designer would have to guess. | Brand-led, warm, plain-spoken. The palette is derived from the shoe (**Assumption**). |
| Timeline, tech | None given. | House default: vanilla HTML/CSS/JS, no build step. |

## 3. Risks
1. **Image is an illustration sheet, not a photo.** It shows 6 views on a white background, and the shading looks like a vector or 3D render. "Built from materials" can't be done with real photographic layers. The page has to fake the assembly convincingly from these 6 views.
2. **Low resolution.** The sheet displays at roughly 600 px wide, so each view is about 250–330 px. Dimensions were not measured because I had no tool to read them. A hero at 1440 px wide, or on a 2–3x phone screen, will look soft if a view is enlarged to fill it.
3. **Look-alike and licensing risk.** The shoe is a classic canvas low-top and strongly resembles a well-known branded silhouette. The sheet also looks like a stock-site asset. The operator needs to confirm they own or license the image for commercial use. The copy must not use any third-party brand name or imply an affiliation.
4. **Scroll-jacking on mobile.** Long pinned scroll sequences make impatient mobile shoppers bounce. The sequence must be short and skippable, and the buy button must always be reachable.
5. **Motion and accessibility.** The whole story is motion. It needs a static, readable fallback for `prefers-reduced-motion` and for keyboard and screen-reader users.
6. **Unsupported claims.** Words like "sustainable", "organic cotton" or "handmade" can't be supported from the image. They are not used.

## 4. Fixes, suggestions and why

### Fixes (the result would be wrong, or the work would stall, without these)
- **F1. Treat the image as a 6-view sheet and slice it.** The views are side, top, front 3/4, back, rear 3/4 and front 3/4 low. The next agent should cut out the views, using a transparent PNG/WebP or CSS clipping on the white background. Why: the white background clashes with any non-white page surface.
- **F2. Decide the build as a layered exploded-view assembly.** Layers are sole, toe cap and sidewall, canvas upper, insole, laces and eyelets, and stitching accents. Layers are revealed or moved into place with `transform` and `opacity`. Why: it meets the performance rule and the brief's intent without needing new photography.
- **F3. Keep the build short.** About 5 stages over roughly 3–4 screen heights on mobile. Why: the audience has little patience.
- **F4. Add a purchase block and a sticky add-to-cart.** It carries price (including tax statement), size selector, returns and shipping. All values are placeholders. Why: the industry profile requires clear pricing and returns, and the page has to convert.
- **F5. Provide a static fallback.** With reduced motion, show all the stages as a stacked list or grid. Why: WCAG 2.2 AA and the house rules.

### Suggestions (optional improvements)
- Show a progress indicator ("Step 3 of 5: Canvas upper") that also works as a skip-to-buy anchor.
- Finish by rotating through the six views as a gallery, so the sheet is fully used.
- Add a color-picker teaser only if the operator supplies more colorways. It is **not** in scope now.
- Use the shoe's deep red as the one accent, on a warm neutral canvas, so the product shines (this matches the industry palette tendency).

## 5. Photo assessment: `inputs/photos/red-sneaker.png`

**What it shows:** One red canvas low-top sneaker, shown 6 times in a 2×3 layout on a pure white background. Colour is a deep, slightly muted crimson. Visible details:
- Canvas upper with visible fabric texture and light contrast stitching.
- White rubber toe cap and white rubber foxing and sidewall, with a single black stripe running along the midsole.
- Metal eyelets, about 6 per side, and flat white cotton-style laces.
- A tan/khaki fabric insole and inner lining.
- A rear heel panel with a vertical seam.
- No logos, no star patch, no text.

**Views, by position:**
1. Top left: pure side profile (lateral). This is the best hero and best "profile" layer reference.
2. Top right: front 3/4 view, high angle. It shows toe cap and lacing.
3. Middle left: top-down view. It shows the insole, lacing pattern and toe cap outline.
4. Middle right: back view. It shows the heel and heel seam.
5. Bottom left: rear 3/4 view with the lace tail hanging.
6. Bottom right: front 3/4 view, low angle. It has the strongest sense of depth.

**Quality:**
- **Resolution:** low, roughly 600 px across the whole sheet. Usable at about 300 px per view on mobile. Soft if scaled up. Dimensions are approximate and not measured.
- **Background:** pure white with soft drop-shadow edges on some views. Not a clean cut-out. It needs masking (F1).
- **Lighting:** consistent across all six views, with a top-left light and soft shading. This makes it easy to combine views.
- **Watermarks, people, locations:** none seen. There is no privacy concern, but see the licensing risk above.

**Usable as-is?** No. It works as a source after slicing and cleaning. It is acceptable for mid-size product visuals on mobile. For a large desktop hero, request a higher-resolution original.

**Suggested uses:**
- Hero: the side profile (view 1), at the end of the build.
- Build layers: derived from views 1 and 3 by masking regions. Sole and toe cap come from the side view. The insole comes from the top view. The laces come from the top view.
- Closing gallery: all six views.
- Colour source: sample the red, white, black stripe and tan insole for the palette. Contrast is checked in the brief's palette note, where relevant.

## 6. Questions for the operator, each with the default I assumed

1. **Brand and product name?** Default: placeholder "Ember Low".
2. **Price and currency?** Default: placeholder 69 EUR, tax included. Replace with the real price.
3. **Sizes and availability?** Default: EU 36–46 shown as a selector, with no stock counters or urgency messaging.
4. **Returns and shipping terms?** Default: placeholder "free returns within 30 days, delivery in 2–4 working days". It must be replaced with the operator's real policy before launch.
5. **What are the real materials?** Default: generic wording ("cotton-style canvas", "rubber sole", "metal eyelets"), with no origin, sustainability or certification claims.
6. **Do you own or license the image?** Default: assumed yes for this build, and flagged for confirmation.
7. **Is a higher-resolution or photographic source available?** Default: no. The build is made from the supplied sheet.
8. **Where does "Buy" go?** Default: a demo add-to-cart interaction on the page only. There is no real cart or checkout.
9. **Language?** Default: English.
