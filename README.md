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

[`heartbeat.py`](heartbeat.py) tracks whether checks are actually
*succeeding*, not just running, so a silent failure (BookMyShow changed
something and every fetch starts erroring) doesn't just look like "no
shows yet." `run_scheduler.py` emails you three kinds of heartbeat
messages: one when it starts, an alert if it goes more than
`STALE_THRESHOLD_SECONDS` (30 min by default) without a single
successful check, and a "recovered" email once checks start succeeding
again.

## Testing before you trust it

There are two layers of testing here — one you can run right now with no
BookMyShow access, one you need real network + real BMS codes for.

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
on repeat runs, and doesn't crash or notify if the fetch fails) — all
against mocked BookMyShow responses, so these prove the logic is correct
without touching the real site or sending a real email.

**2. Real end-to-end check (needs your BMS codes + real internet)**

Automated tests can't catch BookMyShow changing its actual response
shape, so once `EVENT_CODE`/`REGION_CODE`/email are filled in (steps
below), run the real things once each:

```bash
python bms_client.py   # confirms real parsing: should list actual PVR: Palazzo shows
python checker.py      # one real check + potentially one real email
```

If `bms_client.py` finds 0 shows, the parsing needs adjusting (see "How
it works" above) — fix that before relying on it, since a silent parse
failure just looks like "no shows yet," not an error.

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

### Don't want to keep your own machine on 24/7?

`run_scheduler.py` only checks while it's running, so if it's on your
laptop, checks pause whenever the laptop is off, asleep, or offline. If
you want this running around the clock without babysitting your own
machine, put it on a free always-on cloud VM instead — both of these have
an "Always Free" tier (no time limit, no credit card charge as long as
you stay in the free-tier shape):

**Oracle Cloud (Always Free Ampere VM — most generous free tier)**

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (free tier).
2. Create a Compute instance: Ampere A1, `VM.Standard.A1.Flex`, 1 OCPU /
   6 GB RAM, Ubuntu image — this shape is free forever under Always Free.
3. Open port 22 (SSH) in the VM's security list if not already open.
4. SSH in, then:

   ```bash
   sudo apt update && sudo apt install -y python3-venv git
   git clone <your-repo-url>
   cd bms-availability
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in SMTP creds + EMAIL_TO
   nano constants.py      # fill in EVENT_CODE / REGION_CODE
   ```

5. Install as a systemd service (edit the paths in the unit file first,
   using your actual clone path and venv's python):

   ```bash
   sudo cp deploy/bms-availability.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now bms-availability
   ```

**Google Cloud (`e2-micro` free tier)**

Same steps, but create the VM as `e2-micro` in `us-west1`, `us-central1`,
or `us-east1` (the regions covered by GCP's Always Free e2-micro
allowance), Debian/Ubuntu image, then SSH in via `gcloud compute ssh` or
the browser SSH button and follow the same install steps above.

Either way, once the systemd service is enabled, the checker keeps
running even if you close your laptop or lose your home internet — it's
now tied to the cloud VM's uptime, not yours.

## Starting/stopping the VM from GitHub Actions (GCP only)

Once tickets are booked for a show, you'll want to stop paying for/running
the VM entirely rather than just pausing the checker. Two workflows under
the repo's **Actions** tab do this with one click each — **only if the VM
is a GCP instance** (per the free-VM section above):

- **`VM stop`** ([`.github/workflows/vm-stop.yml`](.github/workflows/vm-stop.yml)) — powers the instance off.
- **`VM start`** ([`.github/workflows/vm-start.yml`](.github/workflows/vm-start.yml)) — powers it back on, waits for it to boot and become SSH-reachable, pulls the latest code from `main`, and (re)starts the `bms-availability` service. This is also how code updates reach the VM — there's no separate deploy-on-merge step; starting the VM always runs whatever is currently on `main`.

**One-time setup on the VM:**

```bash
sudo cp deploy/sudoers-bms-availability /etc/sudoers.d/bms-availability
sudo chmod 440 /etc/sudoers.d/bms-availability
# edit DEPLOY_USER in that file first to match the account the workflow SSHes in as
```

This lets the deploy step run `sudo systemctl restart bms-availability`
non-interactively over SSH, without granting broader sudo access.

**One-time setup in GitHub** (repo Settings → Secrets and variables →
Actions → New repository secret):

| Secret | What it is |
|---|---|
| `GCP_SA_KEY` | JSON key for a service account scoped to just start/stop/describe this one instance (not project-wide Compute Admin) |
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_ZONE` | The instance's zone, e.g. `us-central1-a` |
| `GCP_INSTANCE_NAME` | The instance's name |
| `VM_USERNAME` | SSH username on the VM |
| `VM_SSH_KEY` | Private half of an SSH key whose public half is on the VM (`~/.ssh/authorized_keys`) |
| `VM_DEPLOY_PATH` | Path to the repo clone on the VM, e.g. `/home/youruser/bms-availability` |

To trigger either workflow: **Actions tab → "VM stop" or "VM start" → Run
workflow**. `VM start`'s external IP is re-resolved on every run (GCP
assigns a new ephemeral IP on each stop/start unless you've reserved a
static one), so there's no stale-IP secret to keep updated. You'll know
`VM start` actually worked when the "BMS checker started" heartbeat email
arrives — the workflow going green only means the SSH commands ran, not
that the checker is successfully reaching BookMyShow.

## Files

| File | Purpose |
|---|---|
| `constants.py` | Movie/theatre/city + BMS event/region codes + interval + stale threshold |
| `bms_client.py` | Talks to BookMyShow, parses out shows for the theatre |
| `notifier.py` | Sends the email |
| `state.py` | Reads/writes `state.json` (what's already been seen) |
| `checker.py` | One check pass |
| `heartbeat.py` | Tracks success/failure streaks so `run_scheduler.py` knows when to alert |
| `run_scheduler.py` | Keeps `checker.py` running every N seconds; sends heartbeat emails |
| `deploy/bms-availability.service` | systemd unit for persistent running |
| `deploy/sudoers-bms-availability` | Lets the deploy SSH user restart the service passwordlessly |
| `.github/workflows/vm-start.yml` | Actions-tab button: power on VM, deploy latest `main`, start service |
| `.github/workflows/vm-stop.yml` | Actions-tab button: power off VM |
