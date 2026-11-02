# Skill audit

No upstream updates are available. Five of the skill attachments need changes. theme-factory is the clearest problem: it is interactive, built for slide decks, and conflicts with the house style. frontend-design is attached to two agents that don't make design decisions. svg-scroll-animation has a file layout and an animation property list that clash with the pipeline. The coder and checker are also missing coverage in a few places.

## Upstream updates

- none

## Findings

1. [major] landing_designer / theme-factory: The skill is written for interactive slide decks. It tells the agent to show theme-showcase.pdf, ask the user which theme they want, and wait for confirmation. A pipeline agent can't do that, so it will stall or invent an answer. The 10 preset themes (Ocean Depths, Tech Innovation, etc.) are generic palettes. They contradict the house style ("avoid generic SaaS templates", "made for its client") and frontend-design's push for a distinctive identity. The skill also names colours and fonts by hue or theme rather than role, and doesn't say how it fits with tokens.css. Its custom-theme path is redundant with frontend-design's token planning.
   Fix: Remove theme-factory from landing_designer. The designer's own instructions and frontend-design already cover tokens, palette and type, and the designer should derive them from the brief.
2. [major] landing_coder / frontend-design: The coder's instructions say to implement `design/` faithfully. frontend-design tells the agent to brainstorm its own palette, type and layout, critique it against the brief, and revise before building. It also says to confirm the subject with the client. That invites the coder to redesign, drifting from the designer's frames and tokens. The skill's ~9KB is also mostly irrelevant to implementation.
   Fix: Remove frontend-design from landing_coder. If CSS-craft guidance is wanted, add a short implementation-focused skill instead: specificity pitfalls, focus states, responsive checks.
3. [major] planner / frontend-design: The planner writes an implementation plan and doesn't design. The skill pushes it toward making aesthetic decisions (palette hex values, typefaces, ASCII wireframes), which belong to landing_designer. That risks the plan over-specifying or conflicting with the designer, and it adds ~9KB of context for little value. The skill's "confirm with the client" step also can't be done here.
   Fix: Remove frontend-design from planner. Keep it only on landing_designer.
4. [major] landing_designer, landing_coder, page_checker / svg-scroll-animation: The skill's "File layout for a deliverable" prescribes `animations/<name>/` with `fallback.js` and a demo page. This conflicts with the plan's layout (`design/svg/`, `site/index.html`, `site/scroll.js`) and with the house style's rule of one README per deliverable folder. Its standards list also allows `clip-path` to be animated, while the house style allows only transform, opacity and SVG stroke/fill. The checker would be told to accept a property that its own performance check should flag.
   Fix: Keep the skill on the designer, coder and checker, because the techniques are useful. Edit the local skill to drop or neutralise the file-layout section, so it defers to plan.md paths and the file names given in the agent instructions. Also change the animated-properties standard to match the house style (transform, opacity, stroke-dashoffset, fill/stroke), or tell the agents that the house style wins.
5. [minor] landing_coder / svg-scroll-animation (redundancy): The coder's instructions already state the CSS scroll-timeline-plus-JS-fallback approach, reduced motion and readable-without-animation. The skill repeats these.
   Fix: Accept the overlap, or trim the repeated guidance from the coder's instructions and point to the skill. This is low priority.
6. [minor] landing_coder / web-security-checklist (gap): The security reviewer will block on things the coder can't see: no inline handlers, no innerHTML, a CSP-compatible structure, self-hosted assets, and EXIF stripped from the photos in `site/assets`. The coder has no skill on these, which risks rework cycles.
   Fix: Attach web-security-checklist to landing_coder, or add a short list of these rules to the coder's instructions.
7. [minor] page_checker (gap): The checker is held to WCAG 2.2 AA, contrast and keyboard checks, but its only skill is svg-scroll-animation. No skill covers accessibility auditing or responsive/performance checking.
   Fix: Add an accessibility and QA checklist skill (WCAG 2.2 AA, focus order, reduced motion, contrast pairs, 360–1440px). Alternatively, spell these checks out in the agent instructions.
8. [minor] security_reviewer / web-security-checklist: The skill says to use a `<meta http-equiv=CSP>` fallback and lists `frame-ancestors` in the policy. `frame-ancestors` is ignored in a meta tag, and the skill doesn't say so. The reviewer's recommended CSP could therefore mislead.
   Fix: Add a note to the skill that `frame-ancestors`, `report-uri` and `sandbox` only work as HTTP headers. This is optional.
