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
from constants import CHECK_INTERVAL_SECONDS

_stop = False


def _handle_signal(signum, _frame) -> None:
    global _stop
    log.info("Received signal %s, stopping after this cycle", signum)
    _stop = True


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("Starting BMS availability runner (checking every %ds)", CHECK_INTERVAL_SECONDS)

    next_run = time.monotonic()
    while not _stop:
        run_once()

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
