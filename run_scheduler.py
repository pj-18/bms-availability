"""Long-running process that IS the schedule — it sleeps between checks
itself instead of relying on an external cron trigger. This avoids the
delay/skip issues cron (or GitHub Actions' scheduled workflows) can have,
since there's no outside scheduler that can be late or get throttled.

Run it once (`python run_scheduler.py`) and leave it running, e.g. under
systemd (see deploy/bms-availability.service) so it restarts automatically
on crash or reboot.
"""

import signal
import time

from checker import log, run_once
from constants import CHECK_INTERVAL_SECONDS, CITY, MOVIE_NAME, THEATRE_NAME
from heartbeat import HeartbeatMonitor
from notifier import send_email

_stop = False


def _handle_signal(signum, _frame) -> None:
    global _stop
    log.info("Received signal %s, stopping after this cycle", signum)
    _stop = True


def _safe_email(subject: str, body: str) -> None:
    """Heartbeat emails are best-effort — a broken SMTP config must never
    take down the checker loop itself."""
    try:
        send_email(subject, body)
    except Exception:
        log.exception("Failed to send heartbeat email: %s", subject)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("Starting BMS availability runner (checking every %ds)", CHECK_INTERVAL_SECONDS)
    _safe_email(
        "BMS checker started",
        f"Started watching {MOVIE_NAME} at {THEATRE_NAME}, {CITY} every {CHECK_INTERVAL_SECONDS}s.",
    )

    monitor = HeartbeatMonitor()
    next_run = time.monotonic()
    while not _stop:
        if run_once():
            if monitor.record_success():
                _safe_email(
                    "BMS checker recovered",
                    "Checks are succeeding again after a period of failures.",
                )
        elif monitor.record_failure():
            _safe_email(
                "BMS checker alert: no successful check in a while",
                f"No successful BookMyShow check in over "
                f"{monitor.threshold_seconds // 60:.0f} minutes. It may be stuck, "
                "or BookMyShow may have changed something — check the logs.",
            )

        next_run += CHECK_INTERVAL_SECONDS
        sleep_for = next_run - time.monotonic()
        if sleep_for <= 0:
            # A check took longer than the interval; realign instead of
            # drifting further behind.
            next_run = time.monotonic()
            continue

        # Sleep in short slices so a stop signal is picked up promptly
        # instead of waiting out the full interval.
        while sleep_for > 0 and not _stop:
            step = min(sleep_for, 1.0)
            time.sleep(step)
            sleep_for -= step


if __name__ == "__main__":
    main()
