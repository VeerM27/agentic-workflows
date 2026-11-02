import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


def api_project():
    """The repo's agentflow.yaml, but with the API backend (tests use a scripted API client)."""
    from agentflow.project import load_project

    project = load_project(Path(__file__).parent.parent / "agentflow.yaml")
    project.backend = "api"
    return project
