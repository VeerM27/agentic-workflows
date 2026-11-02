---
name: web-security-checklist
description: Security and privacy checklist for static and front-end web pages (landing pages, marketing sites, small web apps).
---

# Web security checklist (front end)

## Injection and DOM safety
- No `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, string
  `setTimeout`/`setInterval` with any data that is not a constant.
- No inline event handlers (`onclick=` etc.) and no `javascript:` URLs (they also block a strict CSP).
- URL parameters and `location.hash` are never written into the DOM without escaping.

## Third parties and supply chain
- List every external origin (scripts, styles, fonts, images, iframes, analytics).
- External scripts/styles pinned to exact versions with Subresource Integrity (`integrity` + `crossorigin`).
- Prefer self-hosting; no abandoned or unnecessary libraries.

## Policy and headers (document what the host should send)
- A Content-Security-Policy tailored to the page: `default-src 'self'`; explicit `img-src`, `font-src`,
  `style-src`, `script-src`; no `'unsafe-inline'`/`'unsafe-eval'` unless unavoidable; `frame-ancestors`,
  `base-uri 'self'`, `form-action`.
- `Referrer-Policy: strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff`, HTTPS only (HSTS).
- A `<meta http-equiv="Content-Security-Policy">` fallback where headers can't be set.

## Links, forms and embeds
- `target="_blank"` links have `rel="noopener noreferrer"`.
- Forms post over HTTPS to a stated endpoint, have no secrets in the page, and validate on the server too;
  spam protection noted.
- Iframes are sandboxed and from trusted origins.

## Secrets and privacy
- No API keys, tokens, internal URLs, emails or comments that reveal internals in the shipped files.
- Images stripped of EXIF metadata (GPS location, device, author) before publishing.
- No tracking or cookies without the consent the site's jurisdiction requires; disclose analytics.

## Resilience
- Page works without JavaScript errors if an external resource fails to load.
- No mixed content; all asset paths relative or same-origin.
