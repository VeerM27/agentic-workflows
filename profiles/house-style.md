<!-- Your standing preferences. Every agent reads this. Replace the examples with your own. -->

## Deliverables
- Default stack for web work: semantic HTML, modern CSS (custom properties, grid, container queries),
  vanilla JavaScript ES modules. No build step and no dependencies unless a brief asks for them.
- Every deliverable folder gets a short README: what it is, how to open or run it, and what to tweak.
- Use realistic, industry-appropriate copy; never lorem ipsum.

## Quality bar
- Accessibility: WCAG 2.2 AA minimum (contrast, focus states, keyboard access, labels, alt text).
- Respect `prefers-reduced-motion` and `prefers-color-scheme`.
- Responsive from 360px to 1440px+. Test both ends.
- Performance: animate only `transform`, `opacity` and SVG stroke/fill properties; no layout thrash.

## Design
- Every project should look like it was made for its client: avoid generic SaaS templates.
- Colour tokens are named by role (surface, text, primary, accent...), never by hue.
- Two typefaces at most; prefer system or Google Fonts.

## Naming
- Files and folders in kebab-case. CSS custom properties `--color-*`, `--space-*`, `--radius-*`, `--font-*`.

## Forms without a backend
- If the brief gives no endpoint, the form is a demo: show it only when JavaScript runs (hide it under
  `no-js` and show a one-line note instead), never let it submit anywhere, and don't write copy that
  promises a sign-up ("we'll email you") until a real list exists.
