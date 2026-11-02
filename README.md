# agentflow

Specialised AI agents that pass work to each other to build a product.

You describe each agent once in a YAML file: its instructions, the arguments it accepts (text,
files, images) and the tools it can use. Then you chain agents into a **workflow**. A step can have
a **checker** agent that reviews the work and sends it back with specific issues until it passes.
Every agent in a run works in the same **workspace** folder, so the designer's mockups are right
there for the engineer, and the engineer's code is there for QA.

```
brief + photos ──▶ product_planner ──▶ ux_designer ⇄ design_reviewer ──▶ frontend_engineer ⇄ code_reviewer ──▶ qa_tester
                   docs/spec.md        design/…  (revise until approved)   app/…  (revise until approved)       qa/report.md
```

Agents run on Claude through the official Anthropic Python SDK.

## Quick start

```bash
pip install -e .            # or: pip install -e '.[render,dev]' for screenshots + tests
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or `ant auth login`
```

```bash
agentflow run workflows/webapp.yaml \
  --input brief=@examples/habit-tracker-brief.md \
  --input references=moodboard.png,https://example.com/inspo.png \
  --input brand="Soft greens, rounded shapes, Inter"
```

Each run gets its own directory:

```
runs/20261102-142501-webapp/
├── workspace/          # everything the agents produced: docs/, design/, app/, qa/, inputs/
├── run.json            # per-step status, hand-offs, review verdicts, token usage
├── events.jsonl        # every tool call, retry and result, in order
└── transcripts/        # full conversation of every agent, per round
```

Other commands:

```bash
agentflow run workflows/webapp.yaml --inputs-file examples/inputs.yaml --dry-run   # show the plan, call nothing
```

```bash
agentflow validate workflows/webapp.yaml     # check references, agents and arguments
```

```bash
agentflow agents                             # list agents and the arguments each takes
```

## Concepts

### Agents (`agents/*.yaml`)

```yaml
name: ux_designer
description: Designs pages as static HTML/CSS mockups plus a design system.
role: producer            # producer = makes things; reviewer = checks things
model: claude-opus-5-5
effort: high              # low | medium | high | xhigh | max
tools: [list_files, read_file, write_file, edit_file, render_page]

inputs:                   # the arguments this agent accepts
  brief:      { type: text, description: What to design }
  references: { type: images, description: Photos/screenshots to take direction from }
  brand:      { type: text }

system_prompt: |
  You are a senior product designer who designs in code...
```

| Input type | Value | What the agent receives |
|---|---|---|
| `text` | a string, or `@path` to read it from a file | the text |
| `file` | path to a text file | the file's contents (and a copy in `inputs/`) |
| `image` / `images` | local paths or URLs (comma-separated or a YAML list) | the images themselves (and copies in `inputs/`) |

Inputs can be `required: true` or have a `default:`.

**Tools** available to agents:

| Tool | What it does |
|---|---|
| `list_files`, `read_file` | Look at the workspace. `read_file` on a PNG/JPEG/GIF/WebP returns the image so the agent can see it |
| `write_file`, `edit_file`, `delete_file` | Change the workspace (paths can't escape it) |
| `render_page` | Screenshot an HTML file in headless Chromium at any width, so designers and reviewers can see the result (optional: needs the `render` extra) |

Every agent also gets one tool that ends its turn and carries its handoff:

- producers call **`complete_task`** with `summary`, `files`, `notes_for_next_agent`. The runner
  rejects handoffs that list files that don't exist.
- reviewers call **`submit_review`** with `verdict` (`approve` / `revise`), `summary`, and
  `issues[]` (`severity`, `location`, `problem`, `fix`).

### Workflows (`workflows/*.yaml`)

```yaml
name: webapp
inputs:
  brief:      { type: text, required: true }
  references: { type: images }

steps:
  - id: spec
    agent: product_planner
    inputs:
      brief: ${inputs.brief}
      references: ${inputs.references}

  - id: design
    agent: ux_designer
    instructions: Design only the home and settings pages.   # optional, per step
    inputs:
      spec: ${steps.spec.handoff}
      references: ${inputs.references}
    review:
      agent: design_reviewer
      max_rounds: 3          # producer gets up to 2 rounds of revisions
      on_reject: continue    # or `fail` to stop the run if never approved
      inputs:
        brief: ${inputs.brief}
```

References:

- `${inputs.<name>}`: a workflow input. A missing optional input is simply left out.
- `${steps.<id>.handoff}`: a formatted handoff (summary, files, notes, review outcome).
- `${steps.<id>.summary|files|notes|verdict|issues}`: individual fields.

**How a review loop works:** after the producer calls `complete_task`, the reviewer starts a fresh
conversation and gets the producer's handoff as its `work` input, plus any `review.inputs`. It
reads the actual files and submits a verdict. On `revise`, the issues go back into the
**producer's own conversation**, so it keeps its context, fixes the files and hands off again. The
loop repeats until the reviewer approves or `max_rounds` runs out.

### Included agents and workflows

| Agent | Role | Produces / checks |
|---|---|---|
| `product_planner` | producer | `docs/spec.md`: pages, features, data, numbered acceptance criteria |
| `ux_designer` | producer | `design/tokens.css`, `design/pages/*.html` mockups, `design/design-notes.md` |
| `design_reviewer` | reviewer | brief fit, hierarchy, consistency, typography, WCAG contrast, responsiveness, fidelity to references |
| `frontend_engineer` | producer | the working app in `app/` (stack is an argument; default is vanilla HTML/CSS/JS) |
| `code_reviewer` | reviewer | bugs, XSS, spec coverage, accessibility, design fidelity |
| `qa_tester` | producer | `qa/report.md`: pass/fail per acceptance criterion with evidence, defects, manual test script |

- `workflows/webapp.yaml`: brief → spec → reviewed design → reviewed build → QA.
- `workflows/design_only.yaml`: text and/or images → designed pages, checked by the design reviewer.

## Adding your own agent

1. Drop a YAML file in `agents/`: name, role, the inputs it takes, tools, and a system prompt
   describing the job, the files it should write and the bar it should hold itself to.
2. Use it in a workflow step and connect its inputs to workflow inputs or earlier steps' outputs.
3. `agentflow validate your-workflow.yaml`.

Some ideas: a `copywriter` that writes page copy before design, an `seo_reviewer`, an
`accessibility_auditor` as a second reviewer, a `backend_engineer` that writes an API to `server/`,
or a `brand_designer` that turns a logo image into tokens.

## Using it from Python

```python
from agentflow import Orchestrator, load_workflow

wf = load_workflow("workflows/design_only.yaml")
result = Orchestrator(wf).run({
    "brief": "Pricing page for a note-taking app, three tiers",
    "references": ["screenshots/competitor.png"],
})
print(result.status, result.workspace)
for step in result.steps:
    print(step.id, step.status, step.rounds, [r.verdict for r in step.reviews])
```

## How the Claude calls are made

- Each agent runs its own tool-use loop (`agentflow/agent.py`) over **streamed** requests
  (`client.beta.messages.stream(...).get_final_message()`), so long file writes don't hit HTTP timeouts.
- **Adaptive thinking** is on. `effort` is set per agent in its YAML.
- **Prompt caching** (`cache_control` on the request) caches the growing conversation, so each
  loop iteration pays full price only for new content.
- **Refusal fallbacks**: on models that support it, requests opt into `fallbacks: "default"`
  (beta `server-side-fallback-2026-07-01`). If a safety classifier declines a request, the API
  re-runs it on Anthropic's recommended fallback model. Turn it off with `--no-fallbacks`
  (or `use_fallbacks=False`).
- Tools use `eager_input_streaming`, so every tool input is checked against its schema before it
  runs. Bad input goes back to the model as an error result. A tool call cut off at `max_tokens`
  is never executed: the request is retried with more room.
- Each agent defaults to `claude-opus-5-5`. Set `model:` per agent to trade quality for cost
  (e.g. `claude-sonnet-5-5` for reviewers).

**Cost:** a full `webapp` run is many long agent conversations (four producers, two reviewers, and
revisions), so expect a few million tokens for a small app. `run.json` and the end-of-run summary
show the exact usage. Try `design_only.yaml` or `--dry-run` first.

## Optional: screenshots for design review

```bash
pip install -e '.[render]'
```

```bash
playwright install chromium
```

If you already have Chrome/Chromium, skip the download by setting
`AGENTFLOW_CHROMIUM=/path/to/chromium`. Without it, `render_page` returns an error and the agents
review the HTML source instead.

## Development

```bash
pip install -e '.[dev]'
```

```bash
pytest
```

The tests run offline. `tests/fakes.py` scripts agent responses, and
`tests/test_sdk_integration.py` drives the real SDK against a local mock of the streaming API.
