from heartbeat import HeartbeatMonitor


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_no_alert_before_threshold():
    clock = FakeClock()
    monitor = HeartbeatMonitor(stale_threshold_seconds=100, now_fn=clock)

    clock.advance(50)
    assert monitor.record_failure() is False


def test_alerts_once_when_crossing_threshold_then_stays_quiet():
    clock = FakeClock()
    monitor = HeartbeatMonitor(stale_threshold_seconds=100, now_fn=clock)

    clock.advance(150)
    assert monitor.record_failure() is True  # first crossing: alert

    clock.advance(50)
    assert monitor.record_failure() is False  # still stale, no repeat alert


def test_success_resets_and_reports_recovery_only_if_alerted():
    clock = FakeClock()
    monitor = HeartbeatMonitor(stale_threshold_seconds=100, now_fn=clock)

    assert monitor.record_success() is False  # never alerted, nothing to recover from

    clock.advance(150)
    assert monitor.record_failure() is True  # now alerted

    assert monitor.record_success() is True  # recovers from the alerted state

    clock.advance(150)
    assert monitor.record_failure() is True  # clock was reset by the success above, so this alerts again
