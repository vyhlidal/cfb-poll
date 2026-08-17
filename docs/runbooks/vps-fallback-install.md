# Runbook: install the VPS fallback

**Nothing here has been done.** The units in [`ops/systemd/`](../../ops/systemd/)
are delivered as text. No agent has touched the Hostinger VPS, and this document
is the procedure for a human who is about to.

**What you are installing.** ADR 0002's fallback clock: a systemd timer that runs
the identical weekly job at Tuesday 08:30 America/Los_Angeles, two and a half
hours after
the n8n primary, and exits 0 in about forty seconds when the week is already
published. It runs [`ops/bin/weekly.sh`](../../ops/bin/weekly.sh), which is the
same file GitHub Actions runs. There is no second implementation to keep in sync.

**Before you start.** The VPS is a Hostinger KVM 2: 2 vCPU, 8 GB, Ubuntu 24.04,
already running n8n. n8n is the primary clock for this same poll, so the job is
niced and IO-idled to keep a fit from starving the scheduler. Read
[`sunday-automation.md`](sunday-automation.md) first; the switch-on order there
puts this step sixth for a reason.

---

## 1. A user that owns nothing else

```bash
sudo adduser --system --group --home /var/lib/cfbpoll --shell /usr/sbin/nologin cfbpoll
sudo install -d -o cfbpoll -g cfbpoll -m 0755 /var/lib/cfb-poll
sudo install -d -o cfbpoll -g cfbpoll -m 0755 /var/lib/cfb-poll/uv-cache
```

`/var/lib/cfb-poll` is `HOME` for the job. The unit sets `ProtectHome=true`, so
the real home directories are invisible to it, and `uv` needs somewhere writable
for its cache.

## 2. The checkout

```bash
sudo install -d -o cfbpoll -g cfbpoll -m 0755 /opt/cfb-poll
sudo -u cfbpoll git clone https://github.com/vyhlidal/cfb-poll /opt/cfb-poll
sudo -u cfbpoll git -C /opt/cfb-poll config --global --add safe.directory /opt/cfb-poll
```

**The checkout is how the arming switch reaches this machine.** `cfbpoll guard`
reads `ops/arming.toml` out of the working tree, so flipping a trigger in git and
pulling here is what arms or disarms the timer. Keep it on `main` and pull it
before each season; a fallback running month-old code is a fallback publishing a
month-old model.

## 3. uv, which is the only prerequisite

```bash
sudo -u cfbpoll env HOME=/var/lib/cfb-poll sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo install -m 0755 /var/lib/cfb-poll/.local/bin/uv /usr/local/bin/uv
uv --version
```

The unit's `PATH` is `/usr/local/bin:/usr/bin:/bin`, which is why `uv` is copied
there rather than left in the service user's `~/.local/bin`.

```bash
sudo -u cfbpoll env HOME=/var/lib/cfb-poll UV_CACHE_DIR=/var/lib/cfb-poll/uv-cache \
  sh -c 'cd /opt/cfb-poll && uv sync --locked'
```

## 4. The archive, once

The first sync is about 0.55 GB and every file is sha256-checked against the
committed lockfile. Do it now, by hand, so the first timed run is not also the
first download.

```bash
sudo -u cfbpoll env HOME=/var/lib/cfb-poll UV_CACHE_DIR=/var/lib/cfb-poll/uv-cache \
  sh -c 'cd /opt/cfb-poll && uv run cfbpoll archive sync --source sportsdataverse --verify'
```

## 5. The secret, in one root-owned file

```bash
sudo install -d -m 0750 -o root -g cfbpoll /etc/cfb-poll
sudo install -m 0640 -o root -g cfbpoll \
  /opt/cfb-poll/ops/systemd/weekly.env.example /etc/cfb-poll/weekly.env
sudo nano /etc/cfb-poll/weekly.env      # paste CFBD_API_KEY, set FIXTURES
sudo chmod 0640 /etc/cfb-poll/weekly.env
```

`0640 root:cfbpoll`, never `0644`. The service user reads it; nothing else does.
The job degrades to the MIT archive with no key rather than failing, so a typo
here produces a thinner ranking rather than an outage — check the run's log for
`No CFBD key` if a week looks light.

## 6. Where the published tree goes

```bash
sudo install -d -o cfbpoll -g cfbpoll -m 0755 /srv/cfb-poll-data
```

This must be the directory the website actually reads, or the fallback publishes
into a hole. The unit's `ReadWritePaths` already names it. See "The delivery
gap" in [`sunday-automation.md`](sunday-automation.md) — this is not settled, and
if you install the fallback before it is, `/srv/cfb-poll-data` is where the files
will be sitting when somebody decides.

## 7. The units

```bash
sudo install -m 0644 /opt/cfb-poll/ops/systemd/cfb-poll-weekly.service /etc/systemd/system/
sudo install -m 0644 /opt/cfb-poll/ops/systemd/cfb-poll-weekly.timer   /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/cfb-poll-weekly.service
sudo systemd-analyze calendar 'Tue *-*-* 08:30:00 America/Los_Angeles'
sudo systemctl daemon-reload
```

`systemd-analyze calendar` must print the next three Tuesdays at 08:30 Pacific.
If it rejects the timezone suffix, this machine's systemd is older than 252 and
the fix is `sudo timedatectl set-timezone America/Los_Angeles`, **not** a
hardcoded UTC hour — that would be an hour wrong for half of every season.

## 8. Rehearse before you enable

```bash
sudo systemctl start cfb-poll-weekly.service
journalctl -u cfb-poll-weekly.service -n 200 --no-pager
```

With `ops/arming.toml` still `vps_timer = false`, this must print the guard's
decision and exit 0 having written nothing. That is the whole safety property,
demonstrated on the real machine, before anything is on a clock.

Then rehearse the real thing without arming the timer:

```bash
sudo -u cfbpoll env HOME=/var/lib/cfb-poll UV_CACHE_DIR=/var/lib/cfb-poll/uv-cache \
  TRIGGER=manual PUBLISH=false DRY_RUN=true \
  /opt/cfb-poll/ops/bin/weekly.sh
```

`DRY_RUN=true` prints every command it would run and runs none of them, except
the guard, which is read-only and is the thing you want a real answer from.

## 9. Enable, last

Only after `vps_timer = true` is committed, pushed and pulled here:

```bash
sudo -u cfbpoll git -C /opt/cfb-poll pull
sudo systemctl enable --now cfb-poll-weekly.timer
systemctl list-timers cfb-poll-weekly.timer
```

`list-timers` should show next Tuesday 08:30 Pacific.

---

## Operating it

```bash
systemctl list-timers cfb-poll-weekly.timer            # when does it next fire
systemctl status cfb-poll-weekly.service               # how did the last run go
journalctl -u cfb-poll-weekly.service --since 'last sunday'
sudo systemctl start cfb-poll-weekly.service           # run it now
sudo systemctl disable --now cfb-poll-weekly.timer     # stop the clock
```

**A missed run does not catch up, on purpose.** `Persistent=false`. If the VPS is
down at 08:30 Tuesday, this does not fire at 03:00 Thursday when it comes back —
that is the launchd behaviour ADR 0002 rejected the Mac for. The dead-man's
switch tells a human at 14:00 and the human decides.

**Update procedure each week is nothing.** The job pulls no code itself. Pull
`/opt/cfb-poll` when `main` moves, and re-run `uv sync --locked` if `uv.lock`
changed. A fallback quietly running last month's model is worse than no fallback,
because it publishes something plausible.

**Disk.** The archive is ~0.55 GB and grows ~130 MB a season. `archive/cfbd/` is
tens of MB a season and, since [ADR 0015](../adr/0015-cfbd-archive-no-r2.md), this
machine is its origin — the only other copy is the Mac's, pulled by
[`cfbd-archive-sync.md`](cfbd-archive-sync.md). On a 100 GB disk shared with n8n
that is comfortable for years, and it is worth an alert anyway.
