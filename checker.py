"""Checks BookMyShow for the watches in watches.json and emails on:
  1. a new show that has seats,
  2. a known show going from sold out to available,
  3. seats being released in a known show (a price category's available
     count going up, e.g. blocked seats unblocked).

Single pass by default (fits a cron job). Set LOOP_INTERVAL_SECONDS and
LOOP_MAX_SECONDS to keep one process refreshing in a loop instead — see
.github/workflows/check.yml."""

import logging
import os
import signal
import sys
import time

from bms_client import extract_shows, fetch_raw_showtimes
from config import Watch, load_watches
from notifier import send_email
from state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bms-checker")

# Seat-count increase in a category needed to alert (decreases never alert).
MIN_SEAT_INCREASE = 1
MAX_CONSECUTIVE_FAILURES = 10


def _check_watch(watch: Watch, state: dict) -> tuple[bool, list[str]]:
    """Returns (fetch_ok, alert_lines). Mutates `state` with current values."""
    try:
        data = fetch_raw_showtimes(watch.event_code, watch.region_code)
    except Exception:
        log.exception("Failed to fetch showtimes for %s (%s)", watch.movie, watch.city)
        return False, []

    shows = extract_shows(data, watch.theatres)
    if not shows:
        log.info("No shows found yet for %s in %s", watch.movie, watch.city)
        return True, []

    alerts = []
    for show in shows:
        key = f"{watch.event_code}|{show.id}"
        prev = state.get(key)
        label = f"{show.venue_name} — {show.date} {show.show_time}"

        if show.available and not (prev or {}).get("available", False):
            kind = "NEW" if prev is None else "AVAILABLE AGAIN"
            seats = ", ".join(f"{n}: {c}" for n, c in show.categories.items())
            alerts.append(f"[{kind}] {label}" + (f" ({seats})" if seats else ""))
        elif prev is not None and "categories" in prev:
            released = [
                f"{name}: {prev['categories'].get(name, 0)} -> {count}"
                for name, count in show.categories.items()
                if count - prev["categories"].get(name, 0) >= MIN_SEAT_INCREASE
            ]
            if released:
                alerts.append(f"[SEATS RELEASED] {label} — " + "; ".join(released))

        state[key] = {
            "available": show.available,
            "venue": show.venue_name,
            "date": show.date,
            "time": show.show_time,
            "categories": show.categories,
        }

    log.info("Checked %d show(s) for %s in %s, %d alert(s)", len(shows), watch.movie, watch.city, len(alerts))
    return True, alerts


def run_once(watches: list[Watch] | None = None) -> bool:
    """One pass over every watch. Returns False if any fetch failed or the
    email couldn't be sent (state is then not saved, so the alert is
    retried next pass)."""
    watches = watches if watches is not None else load_watches()
    state = load_state()
    ok = True
    sections = []

    for watch in watches:
        fetched, alerts = _check_watch(watch, state)
        ok = ok and fetched
        if alerts:
            sections.append(f"{watch.movie} ({watch.city}):\n" + "\n".join(alerts))

    if sections:
        try:
            send_email("BMS alert: seats available", "\n\n".join(sections))
        except Exception:
            log.exception("Failed to send notification email; will retry next pass")
            return False
        log.info("Sent notification email (%d movie section(s))", len(sections))

    save_state(state)
    return ok


def run_loop(interval: float, max_runtime: float, run=run_once, sleep=time.sleep, clock=time.monotonic) -> int:
    """Calls `run` every `interval` seconds until `max_runtime` has elapsed.
    Transient failures are logged and tolerated; MAX_CONSECUTIVE_FAILURES in
    a row returns 1 so the workflow run shows red."""
    start = clock()
    iteration = 0
    failures = 0
    code = 0
    reason = "max_runtime"

    try:
        while clock() - start < max_runtime:
            iteration += 1
            ok = run()
            failures = 0 if ok else failures + 1
            uptime = clock() - start
            log.info("uptime=%dh%02dm iteration=%d ok=%s", uptime // 3600, uptime % 3600 // 60, iteration, ok)
            if failures >= MAX_CONSECUTIVE_FAILURES:
                reason, code = f"{failures} consecutive failures", 1
                break
            sleep(interval)
    except KeyboardInterrupt:
        reason = "interrupted (SIGTERM/SIGINT — runner stopped or cancelled)"

    uptime = clock() - start
    summary = f"Ran {int(uptime // 3600)}h{int(uptime % 3600 // 60):02d}m, {iteration} check(s). Stopped: {reason}."
    log.info(summary)
    _write_job_summary(summary)
    return code


def _write_job_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(f"### BMS checker uptime\n\n{text}\n")


def _on_sigterm(signum, frame):
    raise KeyboardInterrupt


def _cli() -> int:
    """Loop mode if LOOP_INTERVAL_SECONDS is set, else a single pass that
    exits non-zero on failure (so a failed run shows red on Actions)."""
    interval = os.environ.get("LOOP_INTERVAL_SECONDS")
    if interval:
        signal.signal(signal.SIGTERM, _on_sigterm)
        return run_loop(float(interval), float(os.environ.get("LOOP_MAX_SECONDS", "21000")))
    return 0 if run_once() else 1


if __name__ == "__main__":
    sys.exit(_cli())
