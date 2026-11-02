# agentflow

Specialised AI agents that pass work to each other to build a product, with you approving every major step.

You describe each agent once in YAML: its instructions, the arguments it takes (text, files,
images), its tools, and the **Claude Code skills** it should use. Workflows chain agents into steps.
Each step can have a **checker agent** that sends work back until it passes, can explore **several
variants** in parallel, and ends at a **checkpoint** where you approve, pick a variant, or ask for
changes in your own words.

```
brief + photos + industry
   │
   ▼
product_planner ─▶ ux_designer ×3 variants ⇄ design_reviewer ─▶ you pick one ─▶ frontend_engineer ⇄ code_reviewer ─▶ qa_tester
   (you approve)       (each checked, side-by-side gallery)          (you approve)        (you approve)            (you approve)
```

**Runs on your Claude subscription (Pro/Max) through Claude Code. No API key needed.** An API-key
backend is also available (`backend: api` in `agentflow.yaml`).

| Included workflow | What it does |
|---|---|
| `workflows/scroll_landing.yaml` | idea + product photos → skill audit → brief review → plan → design → build → check → security → final review |
| `workflows/webapp.yaml` | brief → spec → design (N variants) → build → QA |
| `workflows/design_only.yaml` | text and/or images → designed pages (N variants), checked against design principles |
| `workflows/palettes.yaml` | N accessible colour palettes with font pairings and a visual preview |
| `workflows/svg_scroll_animation.yaml` | scroll-driven SVG animations (N takes), checked for motion quality, performance and accessibility |

**Setting it up for your own work, and keeping it maintainable as models and skills change:**
see **[docs/SETUP.md](docs/SETUP.md)**.

## Quick start (Pro plan)

```bash
pip install -e '.[render,dev]'
```

```bash
claude auth login          # once, with your Claude Pro/Max account
```

```bash
agentflow doctor           # checks Claude Code login, screenshots, skills
```

```bash
agentflow run workflows/scroll_landing.yaml \
  -i idea="Landing page for our trail shoe: as you scroll, the shoe is built from its materials" \
  -i photos=shoe-side.jpg,shoe-sole.jpg,materials.jpg -i industry=ecommerce-retail
```

```bash
agentflow serve ~/agentflow-runs/<run>    # view the finished page
```

### The scroll-landing pipeline

| # | Step | Agent | Model | You see |
|---|---|---|---|---|
| 0 | Skill audit | `skill_auditor` | fast | updates, redundancies and gaps in every agent's skills; continue, update, or stop |
| 1 | Brief review | `brief_reviewer` | fast | `docs/brief-review.md` (fixes, suggestions, questions) and `docs/brief.md` |
| 2 | Plan | `planner` | fast | `docs/plan.md`: storyboard plus an ordered task list for each agent |
| 3 | Design | `landing_designer` | default | `design/`: tokens, a frame per scroll stage, SVG parts |
| 4 | Build | `landing_coder` | default | `site/`: the working page |
| 5 | Check | `page_checker` | fast | `reports/check.md` |
| 6 | Security | `security_reviewer` | fast | `reports/security.md` |
| 7 | Final review | `final_reviewer` | fast | `reports/final.md`, then "ready to view" |

Steps 5–7 only report. At each one you approve, or send specific fixes (or `all`) to the coder,
who fixes them in the same session; then the check runs again.

`default` and `fast` are model aliases in `agentflow.yaml` (Opus and Sonnet by default).

**Pro-plan usage.** Runs use the same usage limits as your claude.ai chats (a 5-hour window
plus a weekly limit). If a limit is reached mid-run, the run pauses and saves everything.
`agentflow resume <run>` continues in the same agent session after the reset. Use one variant
at a time and keep the skill audit on `on_change` so it only runs when something changed.

At each checkpoint you see a summary, the reviewer verdicts, and a gallery page
(`runs/<run>/checkpoints/<step>.html`) showing every variant side by side. Then:

```
  a [variant]            approve (and continue with that variant)
  r [variant] <feedback> request changes (the agent revises, the reviewer re-checks)
  s                      stop here (resume later)
```

If you'd rather not wait at the terminal, set `approvals.mode: pause` (or pass
`--approve-mode pause`). The run saves itself and exits at each checkpoint, a notification can go
to your phone or Slack, and you continue whenever you're ready:

```bash
agentflow resume runs/20261102-142501-webapp --choose v2
```

```bash
agentflow resume runs/20261102-142501-webapp --feedback "warmer palette, larger headings"
```

A run that crashes, loses its network connection or is interrupted with Ctrl-C resumes the same way.

## Commands

| Command | Purpose |
|---|---|
| `agentflow run WORKFLOW -i name=value … [--inputs-file f.yaml] [--dry-run] [--approve-mode terminal\|pause\|auto] [-y]` | Run a workflow |
| `agentflow resume RUN_DIR [--approve] [--choose v2] [--feedback "…" --lane v2]` | Continue a paused, stopped or crashed run |
| `agentflow validate WORKFLOW` | Check references, arguments, skills (CI-friendly) |
| `agentflow agents` | List agents with their inputs, tools, skills and resolved model |
| `agentflow profiles` | List profile libraries (industries) |
| `agentflow skills list\|sync\|update [names]\|verify` | Manage pinned Claude Code skills |
| `agentflow doctor` | Check Claude Code login, API-key leaks, screenshots, skills |
| `agentflow serve RUN_DIR` | View a finished page at http://127.0.0.1:8000 |
| `agentflow screenshot`, `agentflow contrast`, `agentflow image …` | Helpers the agents use (you can too) |

## How it fits together

```
agentflow.yaml            your settings: model aliases, house style, approvals, notifications
profiles/house-style.md   your standing preferences, given to every agent
profiles/industries/*.md  industry profiles (audience, tone, conventions, compliance)
skills/skills.yaml        Claude Code skills you use (GitHub or local), pinned in skills.lock.json
skills/vendor/            the pinned skill files, committed so runs are reproducible
skills/local/             your own skills
agents/*.yaml             one file per specialist
workflows/*.yaml          pipelines of steps
runs/<run>/               workspace/, checkpoints/, variants/, transcripts/, run.json, events.jsonl
```

### Agents

```yaml
version: 1
name: svg_animator
role: producer                  # producer makes things; reviewer checks things
effort: high                    # model comes from agentflow.yaml unless set (alias or full ID)
tools: [list_files, read_file, write_file, edit_file, render_page, check_contrast]
skills: [svg-scroll-animation, frontend-design]
inputs:
  brief:      { type: text, required: true }
  references: { type: images }
  palette:    { type: text }
system_prompt: |
  You are a motion designer and creative developer...
```

Input types are `text` (use `@file.md` to read from a file), `integer`, `file`, `image`, `images`
(local paths or URLs), and, for workflow inputs, `profile` (a name looked up in a folder such as
`profiles/industries`, or free text).

| Tool | What it does |
|---|---|
| `list_files`, `read_file` | Look at the shared workspace; images are returned so the agent can see them |
| `write_file`, `edit_file`, `delete_file` | Change the workspace (paths can't escape it) |
| `render_page` | Screenshot an HTML file at any width, or at a `scroll_y` position to inspect scroll animations frame by frame (optional `render` extra) |
| `check_contrast` | Exact WCAG contrast ratios for colour pairs |
| `prepare_image` | Inspect, crop, resize, cut out plain backgrounds, export 1×/2× WebP with a `srcset`, strip metadata (never enlarges) |
| `read_skill_file` | Added automatically for agents with skills: read a skill's supporting files |

Producers finish with `complete_task` (summary, files, notes for the next agent). Reviewers finish
with `submit_review` (approve/revise plus issues with location and fix).

### Workflows

```yaml
version: 1
name: design-only
checkpoints: all              # all | none | [step ids]  (default from agentflow.yaml)
inputs:
  brief:    { type: text, required: true }
  industry: { type: profile, library: profiles/industries }
  variants: { type: integer, default: 1 }
steps:
  - id: design
    agent: ux_designer
    skills: [theme-factory]   # extra skills for this step only
    inputs:
      brief: ${inputs.brief}
      industry: ${inputs.industry}
    variants:
      count: ${inputs.variants}
      directions: ${inputs.directions}   # optional; built-in distinct directions fill the rest
    review:
      agent: design_reviewer
      max_rounds: 3
      on_reject: continue      # or fail
    checkpoint: true           # per-step override
```

Later steps reference earlier ones with `${steps.<id>.handoff}` (summary, files, notes, review
outcome, your feedback) or `.summary`, `.files`, `.notes`, `.verdict`, `.issues`.

**Variants** run in parallel, each in its own copy of the workspace with its own creative direction
and review loop. The one you choose becomes the main workspace; the others stay in
`runs/<run>/variants/` for reference.

## How agents run

**`backend: claude-code` (default)** runs each agent as a Claude Code session (`claude -p`) in its
workspace folder, using your subscription:
- **Instructions:** the agent's instructions, your house style and its skills are added to the session.
- **Tools:** file tools only (reviewers can't write), confined to the workspace, plus the
  `agentflow screenshot` / `agentflow contrast` helpers. Anything else is denied automatically.
- **Hand-off:** returned as JSON checked against a schema. Feedback and fixes resume the same session.
- **Billing:** `ANTHROPIC_API_KEY` is removed from the session's environment, so it can't switch to API billing.

**`backend: api`** calls the Claude API directly with an API key:

- Each agent runs its own tool-use loop over **streamed** requests, with **adaptive thinking** and
  `effort` per agent.
- **Prompt caching** covers the system prompt (instructions, house style, skills) and the growing
  conversation.
- **Refusal fallbacks** are on by default (`fallbacks: "default"`): if a safety classifier declines
  a request, the API re-runs it on Anthropic's recommended fallback model. Turn off with
  `defaults.fallbacks: false` or `--no-fallbacks`.
- Tool inputs are checked against their schemas before anything runs. A tool call cut off at the
  token limit is never executed.
- Every request's model, the skills' commits, all conversations and all decisions are recorded in
  the run directory.

**Cost:** each step is one or more long agent conversations, and variants multiply that. A full
`webapp` run with 3 design variants can use several million tokens. `run.json` and the
end-of-run summary show actual usage. Start with a single workflow and `--dry-run`.

## Development

```bash
pytest
```

The tests run offline: scripted agents (`tests/fakes.py`), the real SDK against a local mock of the
streaming API, and skill syncing against a local git repository.
