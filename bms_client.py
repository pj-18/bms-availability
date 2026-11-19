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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import requests

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
    # seats available per price tier/category, e.g. {"Recliner": 12}.
    # BMS's showtimes API exposes counts per category, not individual rows.
    categories: dict[str, int] = field(default_factory=dict)


def fetch_raw_showtimes(event_code: str, region_code: str) -> dict:
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


CATEGORY_NAME_KEYS = ("PriceDesc", "priceDesc", "CategoryName", "categoryName", "name", "Name")


def _parse_categories(showtime: dict) -> dict[str, int]:
    result: dict[str, int] = {}
    categories = showtime.get("Categories") or showtime.get("categories") or []
    for i, category in enumerate(categories):
        if not isinstance(category, dict):
            continue
        seats = category.get("SeatsAvail")
        if seats is None:
            seats = category.get("seatsAvail", category.get("Available"))
        if not isinstance(seats, (int, float)):
            continue
        name = next((category[k] for k in CATEGORY_NAME_KEYS if isinstance(category.get(k), str)), None)
        result[name or f"category-{i}"] = int(seats)
    return result


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
        categories=_parse_categories(showtime),
    )


def _extract(data: dict, venue_matches) -> list[Show]:
    shows: list[Show] = []
    for node in _walk(data):
        venue_name = next(
            (node[key] for key in VENUE_NAME_KEYS if isinstance(node.get(key), str)),
            None,
        )
        if not venue_name or not venue_matches(venue_name.lower()):
            continue

        for key in SHOWTIME_LIST_KEYS:
            showtime_list = node.get(key)
            if isinstance(showtime_list, list):
                shows.extend(_parse_showtime(venue_name, st) for st in showtime_list if isinstance(st, dict))
    return shows


def extract_shows_for_theatre(data: dict, theatre_name: str) -> list[Show]:
    needle = theatre_name.lower()
    return _extract(data, lambda venue: needle in venue)


def extract_all_shows(data: dict) -> list[Show]:
    """Every venue's shows — used when a watch lists no specific theatres
    (i.e. watch the whole city)."""
    return _extract(data, lambda venue: True)


def extract_shows(data: dict, theatres: list[str]) -> list[Show]:
    """Shows for the listed theatres, or for every venue if none are listed.
    De-duplicated by show id in case theatre names overlap."""
    if not theatres:
        return extract_all_shows(data)
    unique: dict[str, Show] = {}
    for theatre in theatres:
        for show in extract_shows_for_theatre(data, theatre):
            unique.setdefault(show.id, show)
    return list(unique.values())


if __name__ == "__main__":
    # Debug helper: `python bms_client.py` fetches the raw response and
    # saves it so you can inspect the real field names and adjust the
    # *_KEYS lists / _is_available above if BookMyShow's schema differs.
    from config import load_watches

    for watch in load_watches():
        raw = fetch_raw_showtimes(watch.event_code, watch.region_code)
        out_path = Path(f"raw_showtimes_dump_{watch.event_code}.json")
        out_path.write_text(json.dumps(raw, indent=2))
        print(f"Saved raw response to {out_path}", file=sys.stderr)

        shows = extract_shows(raw, watch.theatres)
        print(f"{watch.movie} / {watch.city}: found {len(shows)} show(s):")
        for show in shows:
            print(f"  {show.venue_name} {show.date} {show.show_time}  available={show.available}  {show.categories}")
