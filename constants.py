"""Single source of truth for what this checker tracks.

Every other module imports MOVIE_NAME / THEATRE_NAME / CITY from here
instead of hardcoding them, so tracking a different movie or theatre is a
one-file change.
"""

MOVIE_NAME = "The Odyssey"
THEATRE_NAME = "PVR: Palazzo"
CITY = "Chennai"

# --- BookMyShow technical identifiers ---------------------------------
# BookMyShow's showtimes API is keyed by an internal event code (per movie)
# and region code (per city), not by the human-readable names above. There
# is no public endpoint to look these up, so grab them once from your
# browser's DevTools Network tab (see README.md -> "Finding EVENT_CODE and
# REGION_CODE") and paste them in here.
EVENT_CODE = "TODO_FILL_ME_IN"      # e.g. "ET00123456"
REGION_CODE = "TODO_FILL_ME_IN"     # e.g. "CHEN" for Chennai

# --- Scheduling ---------------------------------------------------------
CHECK_INTERVAL_SECONDS = 5 * 60

# --- Heartbeat / health check --------------------------------------------
# If run_scheduler.py goes this long without a single *successful* check
# (fetch raised every cycle, not just "no shows yet"), it emails an alert
# so a silent failure (e.g. BookMyShow changed its response shape) doesn't
# go unnoticed just because no "seats available" email ever fires.
STALE_THRESHOLD_SECONDS = 30 * 60
