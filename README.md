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

| Included workflow | What it does |
|---|---|
| `workflows/webapp.yaml` | brief → spec → design (N variants) → build → QA |
| `workflows/design_only.yaml` | text and/or images → designed pages (N variants), checked against design principles |
| `workflows/palettes.yaml` | N accessible colour palettes with font pairings and a visual preview |
| `workflows/svg_scroll_animation.yaml` | scroll-driven SVG animations (N takes), checked for motion quality, performance and accessibility |

**Setting it up for your own work, and keeping it maintainable as models and skills change:**
see **[docs/SETUP.md](docs/SETUP.md)**.

## Quick start

```bash
pip install -e '.[render,dev]'
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

```bash
agentflow run workflows/svg_scroll_animation.yaml \
  -i brief="A mountain range that draws itself as you scroll, sun rising behind it" \
  -i industry=travel-tourism -i variants=3
```

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

## How the Claude calls are made

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
