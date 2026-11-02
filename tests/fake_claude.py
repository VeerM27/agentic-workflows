#!/usr/bin/env python3
"""A stand-in for the `claude` CLI used in tests (never calls any API).

Env:
  FAKE_CLAUDE_SCRIPT  JSON file: {"agent_name": [action, ...]}, actions consumed in order per agent
  FAKE_CLAUDE_STATE   JSON file tracking how many actions each agent has used
  FAKE_CLAUDE_LOG     JSONL file; one line per call with argv, cwd and whether API keys were present

An action is {"write": {path: content}, "handoff": {...}} (handoff becomes structured_output),
or {"error": "message"} to fail the call (e.g. a usage-limit message).
"""

import json
import os
import re
import sys
from pathlib import Path


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["--version"]:
        print("9.9.9 (Claude Code)")
        return 0
    if argv[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "pro"}))
        return 0

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv else None

    system = opt("--append-system-prompt") or ""
    agent = re.search(r'"([a-z_]+)" agent', system).group(1)
    session = opt("--session-id") or opt("--resume")
    with open(os.environ["FAKE_CLAUDE_LOG"], "a") as log:
        log.write(json.dumps({
            "agent": agent, "argv": argv, "cwd": os.getcwd(), "session": session,
            "new_session": "--session-id" in argv, "prompt": opt("-p"),
            "api_key_present": any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")),
        }) + "\n")

    script = json.loads(Path(os.environ["FAKE_CLAUDE_SCRIPT"]).read_text())
    state_path = Path(os.environ["FAKE_CLAUDE_STATE"])
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    index = state.get(agent, 0)
    actions = script.get(agent, [])
    if index >= len(actions):
        print(json.dumps({"type": "result", "is_error": True, "result": f"no scripted action left for {agent}"}))
        return 1
    state[agent] = index + 1
    state_path.write_text(json.dumps(state))
    action = actions[index]

    usage = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 5}
    if "error" in action:
        print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                          "result": action["error"], "session_id": session, "usage": usage}))
        return 1
    for path, content in action.get("write", {}).items():
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done",
                      "session_id": session, "structured_output": action.get("handoff"), "usage": usage,
                      "total_cost_usd": 0.01}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
