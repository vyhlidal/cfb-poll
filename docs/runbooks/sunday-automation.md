# Runbook: the Sunday automation

**What this is.** The poll publishes on Sunday morning. This is how, what to
touch when it does not, and the exact order to switch it on.

**Status as of 2026-08-17: BUILT, WIRED, AND ARMED NOWHERE.** Every trigger in
[`ops/arming.toml`](../../ops/arming.toml) is `false`, the n8n workflows are JSON
files that have not been imported, and the systemd units are text files that have
not been installed. Nothing in this repository can publish on its own today.

Design: [ADR 0002](../adr/0002-scheduling.md). Storage:
[ADR 0003](../adr/0003-storage.md) as amended by
[ADR 0015](../adr/0015-cfbd-archive-no-r2.md).

---

## The shape of it

```
  Sunday 06:00 ET   n8n on the Hostinger VPS  ──POST /dispatches──┐
                    (ops/n8n/sunday-dispatch.json)                │
                                                                  ▼
  Sunday ~04:43 ET  GitHub `schedule:` cron ────────────────► weekly.yml
  (drifts 35-216m)  (.github/workflows/weekly.yml)                │
                                                                  ▼
                                                        ops/bin/weekly.sh
                                                                  ▲
  Sunday 08:30 ET   systemd timer on the VPS ─────────────────────┘
                    (ops/systemd/cfb-poll-weekly.timer)

  Sunday 14:00 ET   n8n dead-man's switch ───► email, ONLY if nothing published
                    (ops/n8n/deadman-switch.json)
```

Three clocks, one script, and a fourth thing whose only job is to notice that
none of them worked.

**Why n8n is the clock and GitHub is not.** ADR 0002 measured it. GitHub's
scheduled event drifted 35 to 216 minutes and *dropped about 5% of runs
outright*, and a public repository's schedules are auto-disabled after 60 days of
inactivity, which is fatal across a seven-month offseason. `workflow_dispatch`
goes through a different queue and starts in seconds.

**Why there is one script.** ADR 0002's fallback says "the identical job … no
second implementation". `ops/bin/weekly.sh` is that job. The workflow supplies a
runner and secrets; the systemd unit supplies a user and an environment; neither
transcribes the steps. A test enforces it
(`tests/unit/test_ops_automation.py::test_both_hosts_run_the_same_weekly_script`).

**Why nothing double-publishes.** Every clock's first act is `cfbpoll guard`,
which asks two questions: is this trigger armed in `ops/arming.toml`, and is this
week already published? Either answer wrong and the job exits 0 having written
nothing. Ask it yourself any time:

```bash
uv run cfbpoll guard --trigger schedule --fixtures ../sandbox/cfb-poll-data
```

---

## John's part: the PAT, once

n8n needs to be able to press the button on this one workflow and nothing else.
That is a **fine-grained personal access token**, and it is the only credential
this whole design needs from you.

**Click by click.**

1. Go to <https://github.com/settings/personal-access-tokens/new>.
   (Or: your avatar → **Settings** → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.)
2. **Token name:** `n8n cfb-poll weekly dispatch`
3. **Description:** `Sunday 06:00 ET clock. Fires weekly.yml only.`
4. **Resource owner:** `vyhlidal`
5. **Expiration:** **Custom → one year from today.** Not "No expiration".
   Write the date in your calendar now with a reminder a week before; a clock
   that stops in November because a token expired is the exact silent failure
   this design exists to prevent, and the dead-man's switch will catch it but
   only after a missed Sunday.
6. **Repository access:** **Only select repositories** → pick **`cfb-poll`**.
   Nothing else. Not "All repositories".
7. **Permissions → Repository permissions**, set exactly one:
   - **Actions: Read and write**
   - Leave every other permission at **No access**. (GitHub adds
     *Metadata: Read-only* automatically and will not let you remove it. That is
     expected and it is the only other thing on the list.)
8. **Generate token**, and copy the value. It is shown once.
9. Paste it into n8n, once, as described in the next section. Then close the tab.
   Do not put it in a file, a note, a message, or this repository.

**How to check it later.** The token's page lists "Last used". If the Sunday
dispatch is working, that date is the most recent Sunday.

**If it leaks or you are unsure:** revoke it on the same settings page and make a
new one. It can do exactly one thing — start a workflow run in `cfb-poll` — which
is why it is scoped this way, but there is no reason to leave a doubtful token
alive.

---

## Import the n8n workflows

On the Hostinger VPS's n8n, which already runs 24/7. Both files import inactive.

1. **Credentials → Add credential → Header Auth.**
   - **Name:** `GitHub PAT - cfb-poll Actions`
   - **Header Name:** `Authorization`
   - **Header Value:** `Bearer ` followed by the token from above.
     (The word `Bearer`, one space, then the token.)
   - Save.
2. **Workflows → Import from File →**
   [`ops/n8n/sunday-dispatch.json`](../../ops/n8n/sunday-dispatch.json).
3. Open the **Dispatch weekly.yml** node. Its credential will show as missing,
   because the committed file carries a placeholder id rather than a secret.
   Select `GitHub PAT - cfb-poll Actions`. Save.
4. Check the workflow's **Settings → Timezone** reads `America/New_York`. The
   file sets it; confirm it survived the import, because the cron expression is a
   bare local time and the timezone is the only thing making it Eastern. Getting
   this wrong moves the poll by an hour twice a season, mid-season.
5. **Do not activate yet.** See the switch-on order below.
6. Repeat 2-4 for
   [`ops/n8n/deadman-switch.json`](../../ops/n8n/deadman-switch.json), which
   needs an **SMTP credential** instead (named `thepoll.ai SMTP` in the file) and
   two edits in the **Alert a human** node:
   - `toEmail`: `vyhlidal@gmail.com` today. Change to `john@thepoll.ai` the day
     that mailbox exists.
   - `fromEmail`: `alerts@thepoll.ai` assumes a sending domain. If there is no
     SMTP on this n8n yet, this workflow cannot run and that is a gap, not a
     detail — an unmonitored poll is the failure mode ADR 0002 was written
     against.
   - Also check the **Read the published index** node's URL, and the
     `FIRST_PUBLISH_DATE` line in the **Did this week publish?** node.

### Testing the dispatch without publishing anything

With `ops/arming.toml` still all `false`, hit **Execute Workflow** in n8n. The
HTTP node should return **204**, a run should appear in the Actions tab within
seconds, and that run should finish in well under a minute with a notice reading
`weekly no-op`. That is the whole loop proven end to end, at zero risk: the
credential works, the endpoint works, and the guard refused.

---

## The switch-on order

Do these in order, one Sunday apart where it says so. The point of the staggering
is that when something misbehaves you know which thing it was.

1. **Close the two pipeline gaps first.** `cfbpoll preflight` says which:

   ```bash
   uv run cfbpoll preflight
   ```

   Today it reports `validate` and `publish release` as stubs. **Until both are
   real, `PUBLISH=true` refuses to start** — deliberately, in seconds, before the
   0.55 GB download — so arming a clock before this is done just produces a
   faster failure, not a poll.
2. **Rehearse by hand.** A manual dispatch with `publish` unchecked. It fits and
   writes `out/` and publishes nothing.
3. **Rehearse a publication by hand**, with `publish` checked, on a week you are
   watching.
4. **Arm the primary alone.** Set `n8n = true` in `ops/arming.toml`, commit, push
   to `main`, then activate the n8n dispatch workflow. Leave the other two
   `false`. Watch one Sunday.
5. **Arm the dead-man's switch.** Activate that n8n workflow. Watch one Sunday
   and confirm it stays quiet.
6. **Install and arm the VPS fallback.** Follow
   [the install runbook](vps-fallback-install.md), then set `vps_timer = true`.
   Watch one Sunday: it should exit 0 in about forty seconds because the 06:00
   run already published.
7. **Arm the third string last.** Set `schedule = true`. This is the one that can
   fire hours from where you expect it, so it goes on when the two reliable paths
   are known good and the guard has been proven idempotent three Sundays running.

Reverse in the same order to switch anything off. Flipping a line in
`ops/arming.toml` is a reviewed commit with an author and a date, which is the
point of the file existing rather than a checkbox somewhere.

---

## The delivery gap — READ THIS, IT IS NOT DECIDED

`cfbpoll publish fixtures` writes the JSON tree the site reads. **The site's tree
lives in a different repository** (`vyhlidal/sandbox`, under `cfb-poll-data/`),
and the GitHub Actions runner has a checkout of `cfb-poll` and nothing else.

So on CI the workflow publishes into `out/data` and uploads it as a build
artifact. **Nothing carries those files to the site.** That is a real gap, it is
on the critical path for week 1, and it needs a decision rather than an
improvisation. The candidates:

- **A cross-repo push.** A second fine-grained PAT with `contents: write` on
  `vyhlidal/sandbox`, and a commit-and-push step in `weekly.yml`. Simple, and it
  puts a token that can write the website into the poll's CI.
- **The release asset.** `cfbpoll publish release` (still a stub) writes the week
  to a `poll-{season}-w{NN}` tag, and the site's build pulls from it. This is what
  ADR 0003 designed and it needs `publish release` to exist.
- **Let the VPS do it.** The systemd fallback already has a real `FIXTURES` path
  on a machine that can serve or sync it, so the VPS becomes the publisher and
  GitHub Actions becomes the compute. Inverts ADR 0002's primary/fallback roles.

Until this is settled, **the VPS path is the only one that lands a file anywhere
a reader can see it**, which is worth knowing before you arm the primary.

---

## When it breaks

**"The dead-man's switch emailed me."** It only sends when the current season's
newest `published_at` in `index.json` is more than 14 hours old, or when it could
not read the index at all. In order:

1. <https://github.com/vyhlidal/cfb-poll/actions/workflows/weekly.yml> — did a run
   happen? What did the guard step print?
2. On the VPS: `systemctl status cfb-poll-weekly.service` and
   `journalctl -u cfb-poll-weekly.service --since 'last sunday'`.
3. n8n's execution list for the dispatch workflow. A 401 there is an expired or
   revoked PAT; a 404 is a wrong repo or workflow name; a 422 is a bad `ref` or a
   bad input.
4. Publish by hand: a manual `workflow_dispatch` with the season and week filled
   in, or on the VPS
   `TRIGGER=manual PUBLISH=true SEASON=2026 WEEK=7 ops/bin/weekly.sh`.

**"A run happened but nothing published."** Read the guard's output at the top of
the log. `armed=false` means `ops/arming.toml`; `already_published=true` means it
was already done and this is correct behaviour; `week_source=unresolved` means the
CFBD key is missing or `/calendar` failed, and the job refused to guess a week.

**"It published the wrong week."** `week_source` says where the week came from. If
it says `calendar`, the CFBD calendar's `firstGameStart` disagreed with what you
expected; re-run with an explicit `--week`. If it says `input`, somebody typed it.

**"Two runs published the same week."** They should not: the second one's guard
sees the first one's document. If it happened, the guard could not see the
evidence — check that `FIXTURES` and `PUBLISHED_URL` point at the tree that
actually got written, because a guard reading the wrong directory is a guard that
always says "not published".

**"I need to stop everything right now."** Set every line in `ops/arming.toml` to
`false` and push to `main`. That disarms all three clocks at once, including runs
already queued, because the guard reads the file out of the checkout at run time.
Deactivating the n8n workflow does the same for the primary and is faster if
you have the console open.

---

## Related

- [`vps-fallback-install.md`](vps-fallback-install.md) — installing the systemd
  unit and timer, which nobody has done.
- [`cfbd-archive-sync.md`](cfbd-archive-sync.md) — the Mac's copy of the private
  archive, which is what replaced the R2 bucket.
- [ADR 0002](../adr/0002-scheduling.md) — why this shape, with the measurements.
- [ADR 0015](../adr/0015-cfbd-archive-no-r2.md) — John's storage ruling.
