# bms-availability

Checks BookMyShow every 5 minutes for **The Odyssey** at **PVR: Palazzo,
Chennai**, and emails you when a new show is added or an existing show
goes from no seats to seats available.

The movie, theatre and city are constants in [`constants.py`](constants.py)
— every other file imports them from there, so tracking a different
movie/theatre only means editing that one file.

## How it works

BookMyShow doesn't publish a supported public API, so this uses their
internal showtimes endpoint (the same one their website calls) with a
generic/fuzzy JSON parser in [`bms_client.py`](bms_client.py) — it walks
the whole response looking for anything that looks like a venue and a
showtime, rather than hardcoding one exact field path. If BookMyShow
changes their response shape, run `python bms_client.py` directly: it
dumps the raw JSON to `raw_showtimes_dump.json` and prints what it
managed to parse, so you can see what changed and tweak the key lists in
`bms_client.py`.

Every 5 minutes, [`checker.py`](checker.py) fetches the current shows,
compares them against [`state.json`](state.py) (created on first run),
and emails you the diff via [`notifier.py`](notifier.py) if anything
newly has available seats. [`run_scheduler.py`](run_scheduler.py) is the
process that keeps this looping — see "Why not cron" below.

## Setup

1. **Install dependencies**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Find `EVENT_CODE` and `REGION_CODE`** (one-time, ~2 minutes)

   BookMyShow's showtimes API needs its own internal codes, not the movie
   and theatre names. To get them:

   - Open `in.bookmyshow.com` in Chrome, set your city to Chennai, and
     open the page for *The Odyssey*.
   - Open DevTools → Network tab, filter for `showtimes-by-event`.
   - Click the request and check the query params: copy `eventCode` and
     `regionCode`.
   - Paste them into `EVENT_CODE` and `REGION_CODE` in `constants.py`.

3. **Configure email**

   ```bash
   cp .env.example .env
   ```

   Fill in `.env` with your SMTP details. For Gmail, `SMTP_USER` is your
   address and `SMTP_PASSWORD` must be a 16-character
   [App Password](https://myaccount.google.com/apppasswords) (your normal
   Gmail password won't work) — the account needs 2-Step Verification
   turned on to create one. `.env` is git-ignored, so credentials never
   get committed.

4. **Sanity-check parsing before trusting it**

   ```bash
   python bms_client.py
   ```

   This should print the shows it found at PVR: Palazzo along with
   whether each looks available. If it finds 0 shows, double check
   `EVENT_CODE`/`REGION_CODE` and the theatre name spelling in
   `constants.py` against what BookMyShow actually shows for that venue.

5. **Run one check manually**

   ```bash
   python checker.py
   ```

   This is a single pass — fetch, diff against `state.json`, email if
   there's anything new. Safe to re-run; it only emails on new/changed
   availability, not every time.

## Running it every 5 minutes

### Why not cron

Cron (and GitHub Actions' scheduled workflows, which are cron under the
hood) invoke a fresh process on a wall-clock schedule that the OS/CI
scheduler owns — under load, GitHub Actions in particular is known to
delay or skip scheduled runs by several minutes. Instead, `run_scheduler.py`
**is** the schedule: a single long-running process that sleeps between
checks itself, so there's no external trigger to be late.

```bash
python run_scheduler.py
```

Leave it running in a terminal, `screen`/`tmux` session, or better, as a
systemd service so it survives reboots and restarts itself if it ever
crashes:

```bash
# edit the two paths in deploy/bms-availability.service first
sudo cp deploy/bms-availability.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms-availability
sudo systemctl status bms-availability   # check it's running
journalctl -u bms-availability -f        # follow logs
```

To change the check frequency, edit `CHECK_INTERVAL_SECONDS` in
`constants.py`.

## Files

| File | Purpose |
|---|---|
| `constants.py` | Movie/theatre/city + BMS event/region codes + interval |
| `bms_client.py` | Talks to BookMyShow, parses out shows for the theatre |
| `notifier.py` | Sends the email |
| `state.py` | Reads/writes `state.json` (what's already been seen) |
| `checker.py` | One check pass |
| `run_scheduler.py` | Keeps `checker.py` running every N seconds |
| `deploy/bms-availability.service` | systemd unit for persistent running |
