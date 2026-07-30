"""Tracks whether the checker has had a successful BookMyShow check
recently, so run_scheduler.py can alert if checks have been silently
failing for a while (e.g. BookMyShow changed something and every fetch
is now erroring) rather than that only ever looking like "no shows yet".
"""

import time

from constants import STALE_THRESHOLD_SECONDS


class HeartbeatMonitor:
    def __init__(self, stale_threshold_seconds: float = STALE_THRESHOLD_SECONDS, now_fn=time.monotonic):
        self._now = now_fn
        self.threshold_seconds = stale_threshold_seconds
        self._last_success = self._now()
        self._alerted = False

    def record_success(self) -> bool:
        """Call after a successful check. Returns True if this ends a
        period that had triggered an alert (i.e. it's time to send a
        'recovered' notification)."""
        recovered = self._alerted
        self._last_success = self._now()
        self._alerted = False
        return recovered

    def record_failure(self) -> bool:
        """Call after a failed check. Returns True the first time
        failures have gone on long enough to cross the stale threshold
        (i.e. it's time to send an alert) — returns False on every
        subsequent failure until a success resets it, so the alert only
        fires once per stale period."""
        if self._alerted:
            return False
        if self._now() - self._last_success >= self.threshold_seconds:
            self._alerted = True
            return True
        return False
