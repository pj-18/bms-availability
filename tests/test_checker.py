import pytest

import checker
import state
from config import Watch


def _show(status="AVAILABLE", venue="PVR: Palazzo, Chennai", cats=None, time="10:00 PM"):
    st = {"ShowTime": time, "ShowDate": "2026-08-01", "Status": status}
    if cats is not None:
        st["Categories"] = [{"PriceDesc": n, "SeatsAvail": c} for n, c in cats.items()]
    return {"venueName": venue, "ShowTimes": [st]}


WATCH = Watch("The Odyssey", "ET1", "CHEN", "Chennai", ["PVR: Palazzo"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(checker, "send_email", lambda subject, body: sent.append((subject, body)))

    def serve(payload):
        monkeypatch.setattr(checker, "fetch_raw_showtimes", lambda *a, **k: payload)

    return sent, serve


def test_notifies_once_for_a_new_available_show(env):
    sent, serve = env
    serve(_show("AVAILABLE"))

    assert checker.run_once([WATCH]) is True
    assert len(sent) == 1
    assert "[NEW]" in sent[0][1]

    checker.run_once([WATCH])  # nothing changed second time
    assert len(sent) == 1


def test_notifies_again_when_a_known_show_becomes_available(env):
    sent, serve = env
    serve(_show("SOLDOUT"))
    checker.run_once([WATCH])
    assert sent == []

    serve(_show("AVAILABLE"))
    checker.run_once([WATCH])
    assert len(sent) == 1
    assert "AVAILABLE AGAIN" in sent[0][1]


def test_seat_increase_alerts_but_decrease_does_not(env):
    sent, serve = env
    serve(_show(cats={"Recliner": 4}))
    checker.run_once([WATCH])
    assert len(sent) == 1  # the initial NEW alert

    serve(_show(cats={"Recliner": 2}))  # people booked
    checker.run_once([WATCH])
    assert len(sent) == 1

    serve(_show(cats={"Recliner": 9}))  # blocked seats released
    checker.run_once([WATCH])
    assert len(sent) == 2
    assert "SEATS RELEASED" in sent[1][1] and "Recliner: 2 -> 9" in sent[1][1]


def test_zero_to_positive_category_alerts(env):
    sent, serve = env
    serve(_show(cats={"Recliner": 0, "Prime": 5}))
    checker.run_once([WATCH])
    sent.clear()

    serve(_show(cats={"Recliner": 3, "Prime": 5}))
    checker.run_once([WATCH])
    assert len(sent) == 1 and "Recliner: 0 -> 3" in sent[0][1]


def test_old_state_without_categories_does_not_alert(env):
    sent, serve = env
    state.save_state({"ET1|PVR: Palazzo, Chennai|2026-08-01|10:00 PM": {"available": True}})
    serve(_show(cats={"Recliner": 5}))
    checker.run_once([WATCH])
    assert sent == []


def test_city_wide_watch_covers_all_venues_in_one_email(env):
    sent, serve = env
    serve({"Venues": [_show(venue="PVR: Palazzo"), _show(venue="INOX Marina", time="9:00 PM")]})
    city = Watch("The Odyssey", "ET1", "CHEN", "Chennai", [])

    checker.run_once([city])

    assert len(sent) == 1
    assert "PVR: Palazzo" in sent[0][1] and "INOX Marina" in sent[0][1]


def test_listed_theatres_filter_out_others(env):
    sent, serve = env
    serve({"Venues": [_show(venue="PVR: Palazzo"), _show(venue="INOX Marina", time="9:00 PM")]})

    checker.run_once([WATCH])

    assert "INOX" not in sent[0][1]


def test_state_is_isolated_between_movies(env):
    sent, serve = env
    serve(_show("AVAILABLE"))
    other = Watch("Other Movie", "ET2", "CHEN", "Chennai", ["PVR: Palazzo"])

    checker.run_once([WATCH, other])

    assert len(sent) == 1  # one combined email
    assert "The Odyssey" in sent[0][1] and "Other Movie" in sent[0][1]


def test_fetch_failure_does_not_raise_or_notify(env, monkeypatch):
    sent, _ = env

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(checker, "fetch_raw_showtimes", boom)

    assert checker.run_once([WATCH]) is False
    assert sent == []


def test_email_failure_keeps_state_unsaved_so_it_retries(env, monkeypatch):
    sent, serve = env
    serve(_show("AVAILABLE"))
    monkeypatch.setattr(checker, "send_email", lambda s, b: (_ for _ in ()).throw(RuntimeError("smtp")))

    assert checker.run_once([WATCH]) is False
    assert state.load_state() == {}

    monkeypatch.setattr(checker, "send_email", lambda s, b: sent.append((s, b)))
    assert checker.run_once([WATCH]) is True
    assert len(sent) == 1


def test_cli_single_pass_exit_code(monkeypatch):
    monkeypatch.delenv("LOOP_INTERVAL_SECONDS", raising=False)
    monkeypatch.setattr(checker, "run_once", lambda: True)
    assert checker._cli() == 0

    monkeypatch.setattr(checker, "run_once", lambda: False)
    assert checker._cli() == 1


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, s):
        self.now += s

    def __call__(self):
        return self.now


def test_loop_runs_until_max_runtime():
    clock, calls = FakeClock(), []
    code = checker.run_loop(60, 300, run=lambda: calls.append(1) or True, sleep=clock.sleep, clock=clock)
    assert code == 0 and len(calls) == 5


def test_loop_tolerates_transient_failures():
    clock = FakeClock()
    results = iter([False, False, True, True, True])
    code = checker.run_loop(60, 300, run=lambda: next(results), sleep=clock.sleep, clock=clock)
    assert code == 0


def test_loop_exits_nonzero_after_consecutive_failures():
    clock, calls = FakeClock(), []
    code = checker.run_loop(60, 10**9, run=lambda: calls.append(1) or False, sleep=clock.sleep, clock=clock)
    assert code == 1 and len(calls) == checker.MAX_CONSECUTIVE_FAILURES


def test_loop_stops_cleanly_on_interrupt():
    clock = FakeClock()

    def run():
        raise KeyboardInterrupt

    assert checker.run_loop(60, 300, run=run, sleep=clock.sleep, clock=clock) == 0
