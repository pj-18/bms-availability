import state
import checker


def _show(status="AVAILABLE"):
    return {
        "venueName": "PVR: Palazzo, Chennai",
        "ShowTimes": [{"ShowTime": "10:00 PM", "ShowDate": "2026-08-01", "Status": status}],
    }


def test_notifies_once_for_a_new_available_show(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(checker, "fetch_raw_showtimes", lambda: _show("AVAILABLE"))
    monkeypatch.setattr(checker, "send_email", lambda subject, body: sent.append((subject, body)))

    checker.run_once()
    assert len(sent) == 1

    checker.run_once()  # nothing changed second time
    assert len(sent) == 1


def test_notifies_again_when_a_known_show_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(checker, "send_email", lambda subject, body: sent.append((subject, body)))

    monkeypatch.setattr(checker, "fetch_raw_showtimes", lambda: _show("SOLDOUT"))
    checker.run_once()
    assert sent == []

    monkeypatch.setattr(checker, "fetch_raw_showtimes", lambda: _show("AVAILABLE"))
    checker.run_once()
    assert len(sent) == 1


def test_fetch_failure_does_not_raise_or_notify(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    sent = []

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(checker, "fetch_raw_showtimes", boom)
    monkeypatch.setattr(checker, "send_email", lambda subject, body: sent.append((subject, body)))

    checker.run_once()  # must not raise

    assert sent == []
