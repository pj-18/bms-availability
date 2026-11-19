"""Loads what to track from watches.json.

Tracking a different movie/theatre/city means editing watches.json only —
no code changes. Each entry is one movie in one city; `theatres` is
optional (omit or leave empty to watch every venue returned for that city).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

WATCHES_FILE = Path(__file__).parent / "watches.json"
PLACEHOLDER = "TODO_FILL_ME_IN"


@dataclass
class Watch:
    movie: str
    event_code: str
    region_code: str
    city: str
    theatres: list[str] = field(default_factory=list)


def load_watches(path: Path = WATCHES_FILE) -> list[Watch]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path} must contain a non-empty JSON list of watches")

    watches = []
    for i, entry in enumerate(raw):
        try:
            watch = Watch(
                movie=entry["movie"],
                event_code=entry["event_code"],
                region_code=entry["region_code"],
                city=entry["city"],
                theatres=list(entry.get("theatres") or []),
            )
        except KeyError as exc:
            raise ValueError(f"{path} entry #{i + 1} is missing {exc}") from exc
        if PLACEHOLDER in (watch.event_code, watch.region_code):
            raise ValueError(
                f"{path} entry #{i + 1} ({watch.movie!r}) still has a placeholder "
                "event_code/region_code — see README 'Finding event_code and region_code'."
            )
        watches.append(watch)
    return watches
