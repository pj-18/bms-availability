from bms_client import extract_shows_for_theatre


def test_extracts_shows_for_matching_theatre_only():
    data = {
        "Venues": [
            {
                "venueName": "PVR: Palazzo, Chennai",
                "ShowTimes": [
                    {"ShowTime": "10:00 PM", "ShowDate": "2026-08-01", "Status": "AVAILABLE"},
                    {"ShowTime": "11:00 PM", "ShowDate": "2026-08-01", "Status": "SOLDOUT"},
                ],
            },
            {
                "venueName": "Some Other Theatre",
                "ShowTimes": [
                    {"ShowTime": "9:00 PM", "ShowDate": "2026-08-01", "Status": "AVAILABLE"},
                ],
            },
        ]
    }

    shows = extract_shows_for_theatre(data, theatre_name="PVR: Palazzo")

    assert len(shows) == 2
    assert all("Palazzo" in s.venue_name for s in shows)
    by_time = {s.show_time: s.available for s in shows}
    assert by_time["10:00 PM"] is True
    assert by_time["11:00 PM"] is False


def test_seat_count_fallback_when_no_top_level_status():
    data = {
        "venueName": "PVR: Palazzo, Chennai",
        "ShowTimes": [
            {"ShowTime": "6:00 PM", "ShowDate": "2026-08-02", "Categories": [{"SeatsAvail": 12}]},
            {
                "ShowTime": "7:00 PM",
                "ShowDate": "2026-08-02",
                "Categories": [{"SeatsAvail": 0, "Status": "SOLDOUT"}],
            },
        ],
    }

    shows = extract_shows_for_theatre(data, theatre_name="PVR: Palazzo")

    by_time = {s.show_time: s.available for s in shows}
    assert by_time["6:00 PM"] is True
    assert by_time["7:00 PM"] is False


def test_no_match_returns_empty_list():
    data = {
        "venueName": "INOX Some Mall",
        "ShowTimes": [{"ShowTime": "1:00 PM", "Status": "AVAILABLE"}],
    }

    assert extract_shows_for_theatre(data, theatre_name="PVR: Palazzo") == []
