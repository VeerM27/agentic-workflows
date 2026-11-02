---
name: svg-scroll-animation
description: Techniques and standards for building performant, accessible SVG animations driven by scroll position (path drawing, reveals, parallax, morph-like transitions), with progressive enhancement.
---

# SVG scroll animation

## Default approach: CSS scroll-driven animations, enhanced progressively

1. Author the animation as a normal CSS `@keyframes` animation.
2. Bind it to scroll inside `@supports (animation-timeline: view())`:
   - `animation-timeline: view();` progresses while the element crosses the viewport.
     Tune with `animation-range`, e.g. `animation-range: entry 10% cover 60%;`.
   - `animation-timeline: scroll(root);` progresses with the whole page's scroll.
   - Use `animation-fill-mode: both` and `animation-timing-function: linear` (ease in the keyframes instead).
3. Fallback for browsers without scroll timelines: a small JS module that computes a 0–1 progress
   value per element and writes it to a CSS custom property (`--progress`). Drive the same visual
   change from that property. Use `IntersectionObserver` to only track elements near the viewport,
   one passive `scroll` listener, and `requestAnimationFrame` to batch writes.
4. `@media (prefers-reduced-motion: reduce)`: show the final, fully drawn state with no motion
   (or a simple fade), and skip the JS entirely.

## Techniques

- **Path drawing:** give the path `pathLength="1"`, then `stroke-dasharray: 1; stroke-dashoffset: 1;`
  and animate `stroke-dashoffset` to `0`. With the JS fallback: `stroke-dashoffset: calc(1 - var(--progress))`.
- **Staggered reveals:** one timeline, different `animation-range` per element, or `--i` index
  custom properties multiplied into the range/offset.
- **Parallax layers:** translate groups on the Y axis at different rates; keep to `transform`.
- **Morph-like transitions:** cross-fade between two shapes, or reveal with a mask whose own transform or
  opacity is animated (not the mask's shape).
  True path morphing needs identical point counts; avoid it unless you control both paths.
- **Pinned sequences:** a tall container (e.g. `height: 300vh`) with a `position: sticky` stage;
  drive the stage from `view-timeline` on the container (`view-timeline-name: --story;` then
  `animation-timeline: --story;`).
- **Colour shifts:** animate `fill`/`stroke`, or swap palette tokens via custom properties.

## Standards

- Animate only `transform`, `opacity`, `stroke-dashoffset` and `fill`/`stroke` colour. Static `clip-path`
  shapes (cutting a layer out once) are fine; don't animate `clip-path` itself. Never animate layout
  properties (width/height/top/left/margins) on scroll. Where the operator's house style is stricter, it wins.
- Use `viewBox` and no fixed width/height so the SVG scales; inline the SVG when it is animated.
- Keep SVGs lean: merge paths where possible, round coordinates to 1–2 decimals, remove editor metadata.
- Decorative graphics: `aria-hidden="true"`. Meaningful graphics: `role="img"` with `<title>`
  (and `<desc>` if needed), and make sure the content is understandable without the motion.
- The page must make sense if animations never run; never hide essential content behind them.
- Provide enough scroll distance in demos to see the whole animation, plus short notes on which
  timeline/range values to tweak.
- No dependencies by default. If the brief allows a library, GSAP + ScrollTrigger is the usual
  choice for complex choreography; still provide the reduced-motion path.

## File layout (fallback)

Use the file names and folders your plan and instructions give you. Only when they say nothing, use:

```
animations/<name>/
  index.html      demo page with surrounding content and enough scroll length
  <name>.svg      the artwork (also inlined in index.html)
  styles.css      keyframes, scroll timelines, reduced-motion rules
  fallback.js     progress-variable fallback (only loaded when needed)
  README.md       how it works, what to tweak, browser support notes
```
