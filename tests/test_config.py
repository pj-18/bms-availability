import json

import pytest

from config import load_watches


def _write(tmp_path, data):
    p = tmp_path / "w.json"
    p.write_text(json.dumps(data))
    return p


def test_loads_watches_with_optional_theatres(tmp_path):
    p = _write(tmp_path, [{"movie": "M", "event_code": "E", "region_code": "R", "city": "C"}])
    (w,) = load_watches(p)
    assert w.theatres == [] and w.event_code == "E"


def test_placeholder_codes_are_rejected(tmp_path):
    p = _write(tmp_path, [{"movie": "M", "event_code": "TODO_FILL_ME_IN", "region_code": "R", "city": "C"}])
    with pytest.raises(ValueError, match="placeholder"):
        load_watches(p)


def test_missing_field_is_rejected(tmp_path):
    p = _write(tmp_path, [{"movie": "M"}])
    with pytest.raises(ValueError, match="missing"):
        load_watches(p)
