from bms_client import extract_all_shows, extract_shows, extract_shows_for_theatre


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


def test_parses_category_seat_counts():
    data = {
        "venueName": "PVR: Palazzo",
        "ShowTimes": [
            {
                "ShowTime": "6:00 PM",
                "Categories": [{"PriceDesc": "Recliner", "SeatsAvail": 7}, {"PriceDesc": "Prime", "SeatsAvail": 0}],
            }
        ],
    }
    (show,) = extract_shows_for_theatre(data, "PVR: Palazzo")
    assert show.categories == {"Recliner": 7, "Prime": 0}


def test_extract_all_shows_returns_every_venue():
    data = [
        {"venueName": "A", "ShowTimes": [{"ShowTime": "1", "Status": "AVAILABLE"}]},
        {"venueName": "B", "ShowTimes": [{"ShowTime": "2", "Status": "AVAILABLE"}]},
    ]
    assert {s.venue_name for s in extract_all_shows(data)} == {"A", "B"}
    assert len(extract_shows(data, [])) == 2
    assert [s.venue_name for s in extract_shows(data, ["a"])] == ["A"]


def test_no_match_returns_empty_list():
    data = {
        "venueName": "INOX Some Mall",
        "ShowTimes": [{"ShowTime": "1:00 PM", "Status": "AVAILABLE"}],
    }

    assert extract_shows_for_theatre(data, theatre_name="PVR: Palazzo") == []
