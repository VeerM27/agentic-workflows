# agentflow — notes for Claude Code

Declarative multi-agent workflows on the Claude API. Engine code is in `agentflow/`; the owner's
personal configuration is everything else (agents, workflows, profiles, skills, agentflow.yaml).

## Layout
- `agentflow/config.py` — agent/workflow YAML schema; strict keys (`_AGENT_KEYS`, `_STEP_KEYS`, ...). Add new keys there.
- `agentflow/orchestrator.py` — steps, lanes (variants), review loops, checkpoints, pause/resume, run.json state.
- `agentflow/agent.py` — one agent's streamed tool-use loop; system prompt = preamble + role + house style + skills.
- `agentflow/tools.py` — tool schemas + `ToolExecutor._tool_<name>` implementations.
- `agentflow/skills.py` — skills manifest/lockfile/vendoring; `agentflow/project.py` — agentflow.yaml.
- `agentflow/checkpoints.py` — approvers (terminal/pause/auto/scripted) and the gallery page.

## Conventions
- Agents don't hard-code models; use aliases from `agentflow.yaml` (`default`, `fast`) or omit `model`.
- Every YAML file starts with `version: 1`. Unknown keys are errors.
- New agent: copy the closest file in `agents/`; producers write files and finish with `complete_task`,
  reviewers only read and finish with `submit_review`. Say exactly which files to produce.
- Skills: add to `skills/skills.yaml`, run `agentflow skills sync`, commit `skills/` (vendor + lock).
  Never edit files under `skills/vendor/` by hand (hash-verified); put own skills in `skills/local/`.
- Industry knowledge goes in `profiles/industries/*.md`; standing preferences in `profiles/house-style.md`.

## Checks before committing
```bash
pytest -q
for w in workflows/*.yaml; do agentflow validate "$w"; done
agentflow skills verify
```
Tests are offline (scripted fake client in `tests/fakes.py`); never call the real API in tests.
