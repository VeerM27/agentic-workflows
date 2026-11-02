# security: security_reviewer

**Verdict:** approve

No blockers or majors. The page makes no requests to other origins. It has no inline scripts, styles or event handlers, and nothing in it injects HTML, runs eval, or uses cookies or storage. It makes no network calls, and no email address, key or internal URL appears in `site/`, `docs/` or the README. `?driver` and `?build` are only compared to fixed strings in `site/js/boot.js:16-17` and never written into the DOM. The page has no `<form>`, no external links (so no `target="_blank"`), no iframes, no `package.json` and no source maps. The meta CSP in `site/index.html:6` fits the page: every `url()` in the CSS is the same-origin sheet, the SVG `<use>` and `<mask>` references are same-document, and `--p` is set through the CSSOM, which `style-src 'self'` allows. The remaining issues are hardening items, listed below.

Shell access was denied in this session, so I did not check the PNG for EXIF/XMP metadata with a tool. A text search of `site/assets` found no Exif, XMP, GPS or author strings, but that search may skip binary files, so the metadata check is unconfirmed. I did not run a live CSP test in a browser, test dark mode, or test keyboard or screen-reader use. My review rests on reading the code and on the coder's screenshots.

**Recommended CSP (send as a response header, keep the meta tag as a fallback):**
`Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; manifest-src 'none'; object-src 'none'; media-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; upgrade-insecure-requests`

The page loads no data: URIs, so `data:` can be dropped from `img-src`. If the operator later adds a real checkout, change `form-action` and `connect-src` to that exact origin only.

**Other headers the host should send:** `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`. Optionally add `Cross-Origin-Opener-Policy: same-origin`.

**Operator actions:** confirm the rights to the sneaker image and strip its metadata before publishing. The product name, price, returns and delivery wording are placeholders, and the footer says so. The "Free returns within 30 days" and "Delivered in 2 to 4 working days" lines are still stated as fact and should be replaced or confirmed before launch.

## Issues

1. [minor] site/index.html:6 (meta CSP) and the host configuration: `frame-ancestors` is ignored in a meta CSP, and so are `Strict-Transport-Security`, `X-Content-Type-Options` and `Referrer-Policy` set this way. Until the host sends them as headers, the page could be framed for clickjacking and is not forced onto HTTPS. The README notes this for `frame-ancestors` only.
   Fix: Have the host send the full header set from the summary: the CSP including `frame-ancestors 'none'`, HSTS, nosniff, the Referrer-Policy and a Permissions-Policy. Extend the README's CSP section to list all of them.
2. [minor] site/index.html:6 (`img-src 'self' data:`): `data:` is allowed for images but nothing in the page uses it. Allowing it widens the policy for no reason.
   Fix: Change to `img-src 'self'`, and make the same change in the README's CSP section. Also add `connect-src 'none'`, `object-src 'none'` and `frame-src 'none'` for explicit denial. `default-src 'none'` already blocks them, so this is only a clearer policy.
3. [minor] site/assets/red-sneaker-sheet.png: I could not confirm the file has no embedded metadata (EXIF, XMP or text chunks such as author, software or GPS). The text search found nothing, but I could not run a metadata tool. The README also says the file is a byte-for-byte copy of the input, so any metadata in the input would have shipped.
   Fix: Before publishing, run a metadata tool on the file, for example `exiftool -all= red-sneaker-sheet.png`, or re-save it with a PNG optimiser that drops ancillary chunks. Check the result with `exiftool`. Note in the README that this was done.
4. [minor] site/index.html:12-13 and site/js/boot.js:44-46 (resilience): `js/boot.js` is a blocking script in `<head>`. It uses `window.EmberLow`, which the deferred scripts create, only indirectly through `data-ready`, so the fallback depends on the `load` event. If the sheet image is slow or fails, `load` can be delayed. Until then the page stays in pinned mode, and if a deferred script failed, the pinned stage is not driven. This is a robustness issue, not a vulnerability.
   Fix: Optionally have `boot.js` also check `data-ready` on `DOMContentLoaded` or after a short timeout, not only on `load`. Not required for publishing.
5. [minor] site/index.html:290-293 and site/index.html:310 (copy): The return and delivery promises are stated as fact in the page body. Only the footer says they are placeholders. A visitor could read them as real commitments, and they could have consumer-law implications if the page went live unchanged.
   Fix: Keep the footer notice, and replace the two terms with confirmed wording or remove them before launch. Add the operator's legal, privacy and returns links once they exist. The page currently sets no cookies and has no analytics, so no consent banner is needed. Add one if analytics are added later.
