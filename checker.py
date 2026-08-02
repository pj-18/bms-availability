"""One check pass: fetch current showtimes, diff against what we saw last
time, and email if a show is new (or just became available) with seats.

Runs as a single process invocation — no internal scheduling loop — so it
fits a GitHub Actions cron job (see .github/workflows/check.yml) where
each run starts fresh."""

import logging
import sys

from bms_client import extract_shows_for_theatre, fetch_raw_showtimes
from constants import CITY, MOVIE_NAME, THEATRE_NAME
from notifier import send_email
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bms-checker")


def run_once() -> bool:
    """Runs one check pass. Returns True if the fetch from BookMyShow
    succeeded (regardless of whether anything newly available was found),
    False if it raised — callers use this to detect the checker silently
    failing every cycle, as opposed to just "no shows yet"."""
    state = load_state()

    try:
        data = fetch_raw_showtimes()
    except Exception:
        log.exception("Failed to fetch showtimes from BookMyShow")
        return False

    shows = extract_shows_for_theatre(data)
    if not shows:
        log.info("No shows found yet for %s at %s, %s", MOVIE_NAME, THEATRE_NAME, CITY)
        return True

    newly_available = []
    for show in shows:
        was_available = state.get(show.id, {}).get("available", False)
        if show.available and not was_available:
            newly_available.append(show)
        state[show.id] = {
            "available": show.available,
            "venue": show.venue_name,
            "date": show.date,
            "time": show.show_time,
        }

    save_state(state)

    if not newly_available:
        log.info("Checked %d show(s) for %s, nothing new", len(shows), THEATRE_NAME)
        return True

    lines = [f"{show.date} {show.show_time} @ {show.venue_name}" for show in newly_available]
    body = (
        f"New/available show(s) found for {MOVIE_NAME} at {THEATRE_NAME}, {CITY}:\n\n"
        + "\n".join(lines)
    )
    send_email(f"BMS alert: {MOVIE_NAME} seats available at {THEATRE_NAME}", body)
    log.info("Sent notification for %d newly available show(s)", len(newly_available))
    return True


def _cli() -> int:
    """Exit non-zero on a failed fetch so the GitHub Actions run itself
    shows red — that's what makes GitHub's own workflow-failure
    notifications useful here instead of a custom heartbeat."""
    return 0 if run_once() else 1


if __name__ == "__main__":
    sys.exit(_cli())
