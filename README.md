# bms-availability

Checks BookMyShow every 5 minutes for **The Odyssey** at **PVR: Palazzo,
Chennai**, and emails you when a new show is added or an existing show
goes from no seats to seats available. Runs entirely on GitHub Actions —
no server or VM of your own required.

The movie, theatre and city are constants in [`constants.py`](constants.py)
— every other file imports them from there, so tracking a different
movie/theatre only means editing that one file.

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

[`checker.py`](checker.py) is a single check pass: fetch the current
shows, compare them against `state.json` (what's already been seen),
email via [`notifier.py`](notifier.py) if anything newly has available
seats, and exit non-zero if the fetch itself failed. There's no
in-process scheduling loop — [`.github/workflows/check.yml`](.github/workflows/check.yml)
runs `python checker.py` once every 5 minutes on a GitHub Actions cron
schedule, and `state.json` is carried between runs via
[`actions/cache`](https://github.com/actions/cache) since each run
starts on a fresh VM.

Because `checker.py` exits non-zero on a failed fetch, a failing run
shows red in the Actions tab — turn on GitHub's own "notify me when a
workflow fails" setting (see below) instead of a custom alerting
mechanism.

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
shape, so once `EVENT_CODE`/`REGION_CODE`/email are filled in (steps
below), run the real things once each, locally:

```bash
python bms_client.py   # confirms real parsing: should list actual PVR: Palazzo shows
python checker.py      # one real check + potentially one real email
```

If `bms_client.py` finds 0 shows, the parsing needs adjusting (see "How
it works" above) — fix that before relying on it, since a silent parse
failure just looks like "no shows yet," not an error.

## Setup

1. **Find `EVENT_CODE` and `REGION_CODE`** (one-time, ~2 minutes)

   BookMyShow's showtimes API needs its own internal codes, not the movie
   and theatre names. To get them:

   - Open `in.bookmyshow.com` in Chrome, set your city to Chennai, and
     open the page for *The Odyssey*.
   - Open DevTools → Network tab, filter for `showtimes-by-event`.
   - Click the request and check the query params: copy `eventCode` and
     `regionCode`.
   - Paste them into `EVENT_CODE` and `REGION_CODE` in `constants.py`,
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
   | `EMAIL_TO` | where to send alerts (can be the same as `SMTP_USER`) |

4. **Turn on GitHub's workflow-failure notifications** — GitHub Settings
   (your profile, not the repo) → Notifications → under "Actions", set
   notifications for failed workflows you have access to. This is what
   tells you if checks start silently failing (e.g. BookMyShow changed
   something), since `checker.py` exits non-zero in that case.

5. **Test it locally first** (steps 4–5 of "Testing before you trust
   it" above) — sanity-check parsing and a real check pass before
   relying on the scheduled workflow.

6. **Push to `main`** — once `constants.py` has real `EVENT_CODE`/
   `REGION_CODE` and the secrets are set, the `BMS availability check`
   workflow starts running automatically every 5 minutes. You can also
   trigger it manually any time from the Actions tab (`Run workflow`
   button — the workflow has `workflow_dispatch` enabled) to test it
   without waiting for the next tick.

## Things to know about the schedule

- GitHub Actions cron is best-effort — under load it can delay a
  scheduled run by several minutes past its `*/5 * * * *` tick. This
  repo previously used a self-hosted VM specifically to avoid that; it
  now runs on Actions cron instead, so occasional lateness is an
  accepted tradeoff for not needing a server.
- GitHub **automatically disables scheduled workflows** on a repo after
  60 days with no commits/pushes. A push to `main` (or manually
  re-enabling it from the Actions tab) turns it back on.
- To change the check frequency, edit the `cron:` line in
  `.github/workflows/check.yml`.
- To pause checks entirely (e.g. once tickets are booked), disable the
  workflow from the Actions tab (`... → Disable workflow`) — no need to
  touch a server or delete anything.

## Files

| File | Purpose |
|---|---|
| `constants.py` | Movie/theatre/city + BMS event/region codes |
| `bms_client.py` | Talks to BookMyShow, parses out shows for the theatre |
| `notifier.py` | Sends the email |
| `state.py` | Reads/writes `state.json` (what's already been seen) |
| `checker.py` | One check pass; exits non-zero on a failed fetch |
| `.github/workflows/check.yml` | Runs `checker.py` on a 5-minute cron schedule |
