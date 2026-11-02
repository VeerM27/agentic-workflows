# Ember Low: design folder

This folder holds the visual design for the red canvas sneaker scroll-build landing page. The concept is a shoe-maker's spec sheet: the shoe is assembled part by part on a drawing sheet, and each part gets a numbered tag. Read `design-notes.md` first.

## What is here

| Path | What it is | What the coder takes from it |
|---|---|---|
| `design-notes.md` | Concept, measurements, layer rules, motion spec, contrast table, wireframes, final copy, deviations | Everything: copy, timings, rules |
| `tokens.css` | Colour, type, space, radius and motion tokens, plus the dark scheme and the `.sheet` scope | Copy to `site/css/tokens.css` as is |
| `frames/frames.css` | Working reference CSS for the layout and the whole build component (`--p` maths, clip-paths, overlay states) | Lift the `.shoe`, `.layer*`, `.shoe__overlay` blocks verbatim; adapt the layout |
| `frames/frame.js` | Frame-only helper that stamps the shoe markup | The markup structure to inline in `index.html` (not for the site itself) |
| `frames/stage-0.html` … `stage-6.html` | One static frame per storyboard stage (`--p` = 0, .20, .36, .58, .665, .89, 1) | What must be on screen at each point |
| `frames/product.html` | Product section, buy panel, status and error lines, footer, sticky bar | Product layout and copy |
| `frames/static-list.html` | Reduced-motion and no-JS version | Static mode |
| `mockup.html` | Contact sheet: every frame live at 1440 and 360 px | Overview |
| `svg/layer-map.svg` | Polygons for every layer, gap and white checks, overlay check | Source of truth for the clip-paths |
| `svg/shoe-overlay.svg` | Cut line, stitch traces, eyelet rings, callout tags, grainline | Inline in `index.html` |
| `svg/contact-shadow.svg` | Settle shadow (behind the layers) | Inline |
| `svg/mark.svg`, `svg/wordmark.svg`, `svg/favicon.svg`, `svg/icons.svg` | Mark, lock-up, favicon, chevron/check/alert icons | Copy the favicon to `site/assets/` |
| `shots/` | Screenshots of every frame at 1280 and 375 px, the layer map and the mockup | Visual reference |
| `_probe/` | My measurement pages (scratch, safe to delete) | Nothing |

## How to open

Open any `.html` file directly in a browser (`file://` works; no server or build needed). `mockup.html` shows everything at once. The frames read the image from `../../inputs/photos/red-sneaker.png`; in the site, point `.cut` and `.view` at `assets/red-sneaker-sheet.png`.

## What to tweak

- **Colours, type, spacing:** `tokens.css`.
- **Step timings:** the `--a`/`--b` values and the windows in `frames/frames.css` (mirrored in `design-notes.md`, section 5).
- **Layer shapes:** edit the polygons in `svg/layer-map.svg` first, re-render it, then copy the numbers into the clip-paths. Both use V1-local units.
- **Copy:** `design-notes.md`, section 9. Name, price, sizes, returns and delivery are placeholders to replace, and the operator must confirm the rights to the sneaker image.
