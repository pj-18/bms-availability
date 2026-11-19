# bms-availability

Refreshes BookMyShow every minute for the movies/theatres in
[`watches.json`](watches.json) and emails you when:

- a **new show** appears with seats,
- a sold-out show becomes **available again**, or
- **seats are released** in a show (a price category's available count goes
  up — e.g. blocked seats unblocked). BookMyShow's showtimes API only gives
  counts per category (Recliner/Prime/…), not individual rows.

Runs entirely on GitHub Actions — no server or VM of your own required.

## Choosing what to track

Edit [`watches.json`](watches.json) — no code changes needed. One entry per
movie per city:

```json
[
  {
    "movie": "The Odyssey",
    "event_code": "ET00...",
    "region_code": "CHEN",
    "city": "Chennai",
    "theatres": ["PVR: Palazzo", "Luxe"]
  }
]
```

`theatres` is matched as a case-insensitive substring of the venue name.
Omit it (or leave it `[]`) to watch **every venue** in the city. Add more
entries to watch more movies/cities; all alerts in one pass go out as a
single email.

## How it works

BookMyShow doesn't publish a supported public API, so this uses their
internal showtimes endpoint (the same one their website calls) with a
generic/fuzzy JSON parser in [`bms_client.py`](bms_client.py) — it walks
the whole response looking for anything that looks like a venue and a
showtime, rather than hardcoding one exact field path. If BookMyShow
changes their response shape, run `python bms_client.py` locally: it
dumps the raw JSON to `raw_showtimes_dump.json` and prints what it
managed to parse, so you can see what changed and tweak the key lists in
`bms_client.py`.

[`checker.py`](checker.py) fetches the current shows for each watch,
compares them against `state.json` (what's already been seen), and emails
via [`notifier.py`](notifier.py). With `LOOP_INTERVAL_SECONDS` set it keeps
refreshing in one process; otherwise it does a single pass.

[`.github/workflows/check.yml`](.github/workflows/check.yml) starts **one
runner that loops** (60 s interval) for 5h50m — GitHub-hosted runners are
hard-killed at **6 hours** — then triggers a fresh run of itself via
`workflow_dispatch`, so coverage is near-continuous. A 30-minute cron is
just a safety net to revive the chain if it ever breaks; a `concurrency`
group stops runs overlapping. `state.json` is carried between runs via
[`actions/cache`](https://github.com/actions/cache).

To see how long a runner actually lasted, open the run's **summary** page
(total uptime, number of checks, why it stopped) or the per-iteration
`uptime=…` log lines. 10 consecutive failed fetches make the run exit
non-zero (red) — turn on GitHub's own "notify me when a workflow fails"
setting (see below).

**Cost:** looping 24/7 uses ~44,000 Actions minutes/month. Public repos
are free; private repos only get 2,000 free minutes/month. Also, the
workflow must be on the default branch for scheduled/dispatched runs.

## Testing before you trust it

Two layers — one you can run right now with no BookMyShow access, one
you need real network + real BMS codes for.

**1. Automated tests (no network, no BMS account needed)**

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

`tests/` covers the parsing logic (`bms_client.py` — matching the right
theatre, reading `Status`, falling back to per-category seat counts) and
the notification logic (`checker.py` — notifies once on a new available
show, notifies again if a sold-out show becomes available, stays silent
on repeat runs, doesn't crash or notify if the fetch fails, and exits
non-zero when it does) — all against mocked BookMyShow responses, so
these prove the logic is correct without touching the real site or
sending a real email.

**2. Real end-to-end check (needs your BMS codes + real internet)**

Automated tests can't catch BookMyShow changing its actual response
shape, so once `event_code`/`region_code`/email are filled in (steps
below), run the real things once each, locally:

```bash
python bms_client.py   # confirms real parsing: should list actual PVR: Palazzo shows
python checker.py      # one real check + potentially one real email
```

If `bms_client.py` finds 0 shows, the parsing needs adjusting (see "How
it works" above) — fix that before relying on it, since a silent parse
failure just looks like "no shows yet," not an error.

## Setup

1. **Find `event_code` and `region_code`** (per movie/city, ~2 minutes)

   BookMyShow's showtimes API needs its own internal codes, not the movie
   and theatre names. To get them:

   - Open `in.bookmyshow.com` in Chrome, set your city to Chennai, and
     open the page for *The Odyssey*.
   - Open DevTools → Network tab, filter for `showtimes-by-event`.
   - Click the request and check the query params: copy `eventCode` and
     `regionCode`.
   - Paste them into `event_code` and `region_code` in `watches.json`,
     and push that change to `main` (this is the one piece of config
     that lives in the repo rather than a secret).

2. **Get a Gmail App Password** (or other SMTP credentials)

   For Gmail: turn on 2-Step Verification, then create a 16-character
   [App Password](https://myaccount.google.com/apppasswords) — your
   normal Gmail password won't work for SMTP.

3. **Add GitHub repo secrets** (Settings → Secrets and variables →
   Actions → New repository secret):

   | Secret | Value |
   |---|---|
   | `SMTP_HOST` | e.g. `smtp.gmail.com` |
   | `SMTP_PORT` | e.g. `587` |
   | `SMTP_USER` | your email address |
   | `SMTP_PASSWORD` | the App Password from step 2 |
   | `EMAIL_TO` | where to send alerts, e.g. `praveenkumar.ponduru@gmail.com` (can differ from `SMTP_USER`) |

4. **Turn on GitHub's workflow-failure notifications** — GitHub Settings
   (your profile, not the repo) → Notifications → under "Actions", set
   notifications for failed workflows you have access to. This is what
   tells you if checks start silently failing (e.g. BookMyShow changed
   something), since `checker.py` exits non-zero in that case.

5. **Test it locally first** (steps 4–5 of "Testing before you trust
   it" above) — sanity-check parsing and a real check pass before
   relying on the scheduled workflow.

6. **Push to `main`** — once `watches.json` has real `event_code`/
   `region_code` and the secrets are set, the `BMS availability check`
   workflow starts on the next 30-minute cron tick. Start it right away
   from the Actions tab (`Run workflow` button — `workflow_dispatch` is
   enabled); it then keeps itself going.

## Things to know about the schedule

- Cron is only the safety net; the loop interval is `LOOP_INTERVAL_SECONDS`
  in `check.yml` (default 60). Cron is best-effort and can run late.
- GitHub **automatically disables scheduled workflows** on a repo after
  60 days with no commits/pushes. A push to `main` (or manually
  re-enabling it from the Actions tab) turns it back on.
- To change the check frequency, edit `LOOP_INTERVAL_SECONDS` in
  `.github/workflows/check.yml`.
- To pause checks entirely (e.g. once tickets are booked), disable the
  workflow from the Actions tab (`... → Disable workflow`) and cancel the
  current run — cancelling doesn't restart it.

## Files

| File | Purpose |
|---|---|
| `watches.json` | What to track: movies, BMS event/region codes, cities, theatres |
| `config.py` | Loads/validates `watches.json` |
| `bms_client.py` | Talks to BookMyShow, parses out shows for the theatre |
| `notifier.py` | Sends the email |
| `state.py` | Reads/writes `state.json` (what's already been seen) |
| `checker.py` | Check pass + optional refresh loop; emails on new/available/released seats |
| `.github/workflows/check.yml` | Long-running looping job that re-dispatches itself; cron safety net |
