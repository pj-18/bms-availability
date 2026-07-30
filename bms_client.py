"""Fetches showtimes from BookMyShow's (unofficial) showtimes API and
extracts the ones for a specific theatre.

BookMyShow does not publish a supported API, and its response shape is
not guaranteed to stay stable, so the parsing here is deliberately
fuzzy/generic (it walks the whole JSON tree looking for venue-shaped and
showtime-shaped dicts by key name) rather than hardcoding an exact path.
If BookMyShow changes their schema, run this file directly to dump the
raw response and adjust the key lists below.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

from constants import EVENT_CODE, REGION_CODE, THEATRE_NAME

SHOWTIMES_URL = "https://in.bookmyshow.com/api/movies-data/showtimes-by-event"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://in.bookmyshow.com/",
    "Accept": "application/json",
}

VENUE_NAME_KEYS = ("venueName", "VenueName", "name", "cinemaName", "CinemaName")
SHOWTIME_LIST_KEYS = ("ShowTimes", "showTimes", "showtimes", "Sessions", "sessions")
SOLD_OUT_STATUSES = {"SOLDOUT", "SOLD_OUT", "HOUSEFULL", "CLOSED"}
AVAILABLE_STATUSES = {"AVAILABLE", "FASTFILLING", "FAST_FILLING", "OPEN"}


@dataclass
class Show:
    id: str
    venue_name: str
    date: str
    show_time: str
    available: bool


def fetch_raw_showtimes(event_code: str = EVENT_CODE, region_code: str = REGION_CODE) -> dict:
    params = {
        "appCode": "MOBAND2",
        "appVersion": "14304",
        "language": "en",
        "eventCode": event_code,
        "regionCode": region_code,
        "subRegion": region_code,
        "bookingChannel": "WEB",
        "country": "IN",
    }
    response = requests.get(SHOWTIMES_URL, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def _walk(node: Any) -> Iterator[dict]:
    """Yield every dict found anywhere in a nested JSON structure."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _is_available(showtime: dict) -> bool:
    status = str(
        showtime.get("Status") or showtime.get("status") or showtime.get("SeatStatus") or ""
    ).upper()
    if status in SOLD_OUT_STATUSES:
        return False
    if status in AVAILABLE_STATUSES:
        return True

    categories = showtime.get("Categories") or showtime.get("categories") or []
    for category in categories:
        seats = category.get("SeatsAvail") or category.get("seatsAvail") or category.get("Available")
        if isinstance(seats, (int, float)) and seats > 0:
            return True
        category_status = str(category.get("Status") or category.get("status") or "").upper()
        if category_status and category_status not in SOLD_OUT_STATUSES:
            return True

    # Unknown/empty status: treat as available so we err on the side of
    # notifying rather than silently missing a show.
    return status not in ("",) or bool(status)


def _parse_showtime(venue_name: str, showtime: dict) -> Show:
    show_time = showtime.get("ShowTime") or showtime.get("showTime") or showtime.get("time") or ""
    date = showtime.get("ShowDate") or showtime.get("date") or ""
    show_id = str(
        showtime.get("SessionId")
        or showtime.get("sessionId")
        or showtime.get("ShowCode")
        or f"{venue_name}|{date}|{show_time}"
    )
    return Show(
        id=show_id,
        venue_name=venue_name,
        date=str(date),
        show_time=str(show_time),
        available=_is_available(showtime),
    )


def extract_shows_for_theatre(data: dict, theatre_name: str = THEATRE_NAME) -> list[Show]:
    theatre_name_lower = theatre_name.lower()
    shows: list[Show] = []

    for node in _walk(data):
        venue_name = next(
            (node[key] for key in VENUE_NAME_KEYS if isinstance(node.get(key), str)),
            None,
        )
        if not venue_name or theatre_name_lower not in venue_name.lower():
            continue

        for key in SHOWTIME_LIST_KEYS:
            showtime_list = node.get(key)
            if isinstance(showtime_list, list):
                shows.extend(_parse_showtime(venue_name, st) for st in showtime_list if isinstance(st, dict))

    return shows


if __name__ == "__main__":
    # Debug helper: `python bms_client.py` fetches the raw response and
    # saves it so you can inspect the real field names and adjust the
    # *_KEYS lists / _is_available above if BookMyShow's schema differs.
    raw = fetch_raw_showtimes()
    out_path = Path("raw_showtimes_dump.json")
    out_path.write_text(json.dumps(raw, indent=2))
    print(f"Saved raw response to {out_path}", file=sys.stderr)

    shows = extract_shows_for_theatre(raw)
    print(f"Found {len(shows)} show(s) for {THEATRE_NAME!r}:")
    for show in shows:
        print(f"  {show.date} {show.show_time}  available={show.available}")
