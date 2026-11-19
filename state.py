"""Persists what shows we've already seen between runs, so the runner
knows what "newly available" means across restarts."""

import json
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))
