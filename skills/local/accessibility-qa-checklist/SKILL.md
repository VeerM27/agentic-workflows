---
name: accessibility-qa-checklist
description: Accessibility (WCAG 2.2 AA), responsive and performance checks for reviewing a finished web page or small web app.
---

# Accessibility and QA checklist

Check each item against the real files and, where you can, rendered screenshots. Report pass/fail with
the exact file and element.

## Perceivable
- Text contrast: 4.5:1 for body text, 3:1 for large text (24px+, or 18.66px+ bold) and for UI
  component boundaries, icons and focus indicators. Measure real pairs (including text over images).
- Every meaningful image has useful `alt`; decorative images have `alt=""` or `aria-hidden="true"`.
  SVG artwork that carries meaning has `role="img"` and an accessible name.
- Information is never conveyed by colour alone (errors, selected states, steps).
- Content stays readable and nothing is cut off at 200% zoom and with text spacing increased.

## Operable
- Everything works with the keyboard alone, in a logical order; no keyboard traps.
- Focus is always visible (WCAG 2.2: not hidden behind sticky headers or bars) and clearly styled.
- Touch targets are at least 24×24px (44×44 recommended), with spacing.
- Skip link to the main content; sticky elements don't cover focused controls.
- Motion: `prefers-reduced-motion` gives a static or minimal version; nothing essential exists only in an
  animation; no flashing more than 3 times per second; scroll-driven sequences can be skipped.

## Understandable and robust
- One `h1`, headings in order, landmarks (`header`, `main`, `nav`, `footer`) used correctly.
- Form controls have visible labels; groups (radio sets) use `fieldset`/`legend`.
- Errors: describe what went wrong and how to fix it; put `aria-invalid` on the control or group that is
  invalid (not on individual radio buttons), and point `aria-describedby` at the error only while it shows.
- Status messages use a live region (`role="status"`), announced once per change.
- ARIA only where native HTML can't do it; every ARIA attribute is valid for its role.

## Responsive
- Check widths 360, 390, 768, 1024, 1280 and 1440px, and a landscape phone (about 844×390).
- No horizontal scrolling of the page; nothing overlaps; tap targets keep their size.
- Pinned/sticky stages fit short viewports (landscape phones, browser zoom) or degrade gracefully.
- Content edges and fixed bars line up at wide widths.

## Performance basics
- Images: sized for their display (1×/2× with `srcset`/`sizes`), modern formats (WebP/AVIF), metadata
  stripped, no image much larger than needed; the largest above-the-fold image is not lazy-loaded.
- Scroll work: only `transform`/`opacity`-type properties animate; listeners are passive and batched with
  `requestAnimationFrame`; work pauses off screen.
- No render-blocking third-party scripts; total page weight reasonable for mobile.
