# Setting agentflow up for your work, and keeping it future-proof

This guide covers making the pipeline yours (your preferences, industries, skills and
specialists), staying in the loop, and keeping the setup reliable as models, skills and your own
practice change.

## 0. Pro plan (no API key)

`agentflow.yaml` has `backend: claude-code`: every agent runs through Claude Code on your
subscription. Install Claude Code, run `claude auth login` with your Pro/Max account, then run
`agentflow doctor`, which confirms you're logged in.

- **Shared limits:** runs share your plan's 5-hour and weekly usage limits with claude.ai. When a
  limit is hit, the run pauses with everything saved; `agentflow resume <run>` continues in the same
  agent session after the reset (`/usage` in Claude Code shows where you are).
- **Stretching your plan:** keep `skills.audit: on_change` (the audit only runs when agents, skills
  or upstream versions changed). Use `fast` (Sonnet) for reviewers, as configured. Use one variant
  at a time. Approve steps promptly rather than re-running them.
- **API keys:** if `ANTHROPIC_API_KEY` is set in your shell, agentflow removes it for Claude Code
  sessions so the subscription is used. `doctor` warns you about it.
- **Model access:** if your plan doesn't include a model, change the `default` alias in `agentflow.yaml`
  (e.g. to `claude-sonnet-5-5`).
- **Runs folder:** runs are written to `~/agentflow-runs` (outside this repo), so the repo's own
  `CLAUDE.md` doesn't leak into agent sessions.

## 1. One-time setup

```bash
git clone <your fork of this repo> && cd agentic-workflows
```

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -e '.[render,dev]'
```

```bash
playwright install chromium
```

If you already have Chrome or Chromium installed, skip `playwright install` and set
`AGENTFLOW_CHROMIUM=/path/to/chrome`. Screenshots are what let the design and motion reviewers
*see* the pages and animations instead of only reading code. Then check that everything resolves:

```bash
agentflow skills verify && for w in workflows/*.yaml; do agentflow validate "$w"; done
```

## 2. Make it yours

Personal settings live in a few files, separate from the engine code (`agentflow/`):

| File | What to put there |
|---|---|
| `agentflow.yaml` | Model aliases, default effort, approvals, notification command |
| `profiles/house-style.md` | Standing preferences every agent follows: stack, quality bar, naming, design taste |
| `profiles/industries/*.md` | One file per industry you work in (copy `_template.md`) |
| `skills/skills.yaml` | The Claude Code skills you use, from GitHub or `skills/local/` |
| `agents/*.yaml` | Your specialists. Edit the included ones or add new ones |
| `workflows/*.yaml` | Your pipelines |

### Your house style

Write `profiles/house-style.md` the way you'd brief a new team member: preferred stack, coding
conventions, accessibility and performance bar, how deliverables should be organised, design
principles you always apply, things you never want to see. It is added to every agent's
instructions, so a change there changes everything at once.

### Industries

Run `agentflow profiles` to see what's there. Twelve starter profiles are included (fintech,
healthcare, restaurants, SaaS, e-commerce, real estate, fitness, education, legal, nonprofit,
creative portfolio, travel). Edit them with what you've learned on real projects, and add new ones
from `_template.md`. Any workflow input declared as

```yaml
industry: { type: profile, library: profiles/industries }
```

accepts either a profile name (`-i industry=fintech`) or free text (`-i industry="artisan cheese shop"`).

### Skills from GitHub

Skills are folders with a `SKILL.md`, the same format Claude Code uses. List the ones you use in
`skills/skills.yaml`:

```yaml
skills:
  frontend-design:
    repo: anthropics/skills          # GitHub owner/repo, or any git URL (private repos work with your git credentials)
    path: skills/frontend-design     # folder that contains SKILL.md
    ref: main                        # branch or tag you follow
  my-brand-voice:
    local: local/my-brand-voice      # your own skill, kept in this repo
```

```bash
agentflow skills sync      # downloads, pins the exact commit in skills.lock.json, copies files to skills/vendor/
```

```bash
git add skills && git commit -m "Add skills"
```

Then attach a skill where you want it used:

- **To an agent**, so it is always in effect: `skills: [frontend-design]` in `agents/ux_designer.yaml`.
- **To a single step**: `skills: [theme-factory]` on a workflow step. Only that step's agent gets it.

What an agent receives: the skill's full instructions in its system prompt, a list of the
skill's supporting files, and a `read_skill_file` tool to open them. Skills written for interactive
use ("ask the user which theme...") are adapted automatically. The agent makes the call, records it
in its handoff notes, and you confirm or change it at the checkpoint.

> Some skills ship scripts (Python, shell). agentflow agents can read them but not run them, since they
> only have file tools. `agentflow skills list` flags these. Prefer instruction-based skills, or
> port the script's logic into your own local skill.

Two skills from `anthropics/skills` are set up as examples (`frontend-design`, `theme-factory`,
both Apache-2.0), plus a local `svg-scroll-animation` skill holding the motion techniques the SVG
agents use. Replace or extend them with yours.

### New specialists

Copy the closest agent file and change the role, inputs and prompt. Good prompts say:
what the agent produces and where (exact file paths), the bar it holds itself to, how to check its
own work before handing off, and what to put in its notes. For a checker, list what to check in
priority order and what is worth blocking for versus a minor note.

Examples worth adding for your kind of work: `copywriter` (industry-specific copy before design),
`brand_designer` (logo image in, tokens out), `accessibility_auditor` (a second reviewer on build),
`seo_reviewer`, `illustration_designer` (SVG illustration sets), `backend_engineer`.

## 3. The scroll-landing workflow, step by step

1. **Skill audit (before anything runs).** agentflow checks each pinned GitHub skill for upstream
   commits (without changing anything). The `skill_auditor` agent reads every agent's instructions
   and skills and reports updates worth taking, redundant or conflicting skills, and gaps. Then you
   choose: `c` continue, `u [names]` update and continue, or `s` stop. Pause-mode equivalents:
   `agentflow resume <run> --approve` or `--update-skills frontend-design`. Commit `skills/`
   afterwards if you keep an update.
2. **Brief review.** Reports fixes, suggestions and questions about your idea and photos, and writes
   the refined brief. Correct it with feedback if it assumed wrong.
3. **Plan.** `docs/plan.md` with the scroll storyboard and a numbered task list plus acceptance
   criteria for each later agent.
4. **Design**, then 5. **Build.**
6. **Check**, 7. **Security**, 8. **Final review.** These report only (`reports/<step>.md`). At each
   checkpoint: approve, `r fix issues 1 and 3` / `r all` (sent to the coder, then re-checked), or stop.

To change who does what, edit the agent files (`agents/brief_reviewer.yaml`, `planner.yaml`,
`landing_designer.yaml`, `landing_coder.yaml`, `page_checker.yaml`, `security_reviewer.yaml`,
`final_reviewer.yaml`, `skill_auditor.yaml`). To change which skills each agent loads, edit their
`skills:` list.

### Photos that give the best results

Agents use your photos directly: they crop, cut out and export them with `agentflow image`, and never
redraw or enlarge them. So the photos set the ceiling on sharpness:
- **Resolution:** about 2–3× the size the product will be shown. A shoe shown 560px wide wants source
  views 1,100–1,700px wide. The brief reviewer reports each photo's exact size and warns when it's too small.
- **Background:** plain or white backgrounds cut out cleanly (`agentflow image cutout`). Transparent
  PNG/WebP cut-outs are even better.
- **For "built from its materials" stories:** separate shots of the parts (sole, upper, laces, materials)
  or an exploded-view shoot give a far more convincing build than slicing one picture.
- **Metadata:** exported images always have EXIF/GPS stripped; originals are never shipped.

You can check a photo yourself before a run: `agentflow image info photo.jpg`.

## 4. Staying in the loop

`approvals` in `agentflow.yaml` decides how checkpoints reach you:

| Mode | Behaviour | Good for |
|---|---|---|
| `terminal` | Asks at the terminal and waits | Sitting with it |
| `pause` | Saves, notifies you, exits; continue with `agentflow resume` | Long runs, working from your phone |
| `auto` | Approves automatically | CI, batch generation |

`checkpoints: all` (the default here) stops after every step. Workflows (`checkpoints: [design, build]`)
and steps (`checkpoint: false`) can narrow that.

At a checkpoint you can approve, choose a variant, or send feedback. Feedback goes to the same
agent that did the work, which keeps its context. The reviewer re-checks, then you see the step
again. Your feedback and approval are passed on to later agents in the handoff, so they know what you asked for.

**Notifications.** Set `notify.command` to anything that reaches you: a desktop notification, `ntfy.sh`,
a Slack webhook. It runs at checkpoints, pauses, finishes and failures. The event, run directory,
step, summary and gallery path are passed as `AGENTFLOW_*` environment variables (examples are in
`agentflow.yaml`).

Everything is on disk: `runs/<run>/checkpoints/<step>.html` (gallery), `run.json` (state, verdicts,
usage, models and skill commits used), `events.jsonl` (every tool call and decision),
`transcripts/` (every agent conversation).

## 5. Future-proofing

**Models change → edit one line.** Agents don't name models. They use the `default` alias (or another
alias such as `fast`) defined in `agentflow.yaml`. When a new model ships, update `models.default`,
run one small workflow, compare, and commit. To trial a model on a single agent, set `model:` in
that agent's file.

**Skills change → nothing moves until you say so.** `skills.lock.json` pins every skill to an exact
commit and a content hash, and the files are committed under `skills/vendor/`. Runs refuse to start if
a vendored skill was edited or corrupted, and work even if the upstream repo disappears. To take an
upstream improvement:

```bash
agentflow skills update frontend-design     # shows which files changed
```

```bash
git diff skills/                            # read the new instructions before trusting them
```

Then run a workflow that uses it and commit. Skills are instructions your agents follow, so review
third-party updates the way you'd review a code dependency.

**Config typos fail loudly.** Every YAML file is checked strictly: unknown keys are errors, not
silently ignored. Every file carries `version: 1`, so a future format change can be detected and
migrated instead of misread.

**Runs are reproducible and resumable.** Each `run.json` records the models and skill commits used.
Runs survive crashes and pauses, and resume refuses to continue if the workflow's steps changed underneath it.

**Dependencies are bounded.** `pyproject.toml` pins the Anthropic SDK to a major version range so an
SDK release with breaking changes can't arrive silently. Upgrade deliberately: bump the range, run `pytest`, run one real workflow.

**Keep CI green.** `.github/workflows/ci.yml` runs the tests, validates every workflow and verifies
skills on every push, so a broken agent file or a tampered skill is caught before your next real run.

**Keep a few golden briefs.** Save 3–5 representative briefs (one per kind of job: an SVG animation,
a palette set, a web app in an industry you often work in) in `examples/`. Re-run them after
changing models, skills, prompts or your house style, and compare the checkpoint galleries with
the previous runs. That's the most reliable way to know a change made things better.

**Version-control your practice.** Commit everything except `runs/`. Your prompts, profiles,
house style and local skills are the valuable part. Their git history shows what changed when
output quality changed.

## 6. Extending the engine

- **Approvals from elsewhere** (Slack buttons, a web page): `pause` mode plus `agentflow resume
  --approve/--feedback` is the integration point. Anything that can run a command can answer a checkpoint.
- **New tools**: add a schema and a `_tool_<name>` method in `agentflow/tools.py`, then list the tool in an agent.
- **Library use**: `Orchestrator(workflow, approver=...)` takes any object with
  `confirm_start(plan)` and `decide(view) -> Decision`.

When you ask Claude Code to change this repo, it reads `CLAUDE.md`, which describes these conventions.
