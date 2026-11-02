# Trial run: red canvas sneaker scroll-build landing page (2026-11-02)

First real run of `workflows/scroll_landing.yaml`, through Claude Code, with checkpoints auto-approved.

- Idea: "Landing page for this red canvas sneaker: as you scroll, the shoe is built from its materials"
- Input: one six-view product sheet (612×551 PNG), industry `ecommerce-retail`
- Result: all three reviewers approved (no blockers); 57 minutes end to end

| Step | Agent | Time | Output tokens |
|---|---|---|---|
| Skill audit | skill_auditor | — | 3k |
| Brief | brief_reviewer | 1 min | 8k |
| Plan | planner | 4 min | 30k |
| Design | landing_designer (Opus) | 29 min | 183k |
| Build | landing_coder (Opus) | 15 min | 92k |
| Check | page_checker | 5 min | 29k |
| Security | security_reviewer | 1 min | 5k |
| Final | final_reviewer | 1 min | 4k |

**Not included (public repo):** the product image and everything rendered from it (design screenshots),
because the image may be a licensed stock asset. To view the page, put the sheet back at
`site/assets/red-sneaker-sheet.png`, then serve the `site/` folder (e.g. `python -m http.server -d site`).

Contents: `docs/` (brief review, refined brief, plan), `design/` (tokens, frames, SVG, notes),
`site/` (the page), `reports/` (check, security, final), `skill-audit.md`, `run.json` (full run record).
