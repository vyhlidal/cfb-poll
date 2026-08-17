# Runbook: the weekly automation

**What this is.** The poll publishes on Tuesday morning, Pacific. This is how,
what to touch when it does not, and the exact order to switch it on.

**Every time on this page is Pacific**, `America/Los_Angeles`, and so is every
time in `ops/`. John lives in PT and ruled on 2026-08-17 that the project stops
carrying two clocks in its head. Nothing here is Eastern any more.

**Status as of 2026-08-17: BUILT, WIRED, AND ARMED NOWHERE.** Every trigger and
every step in [`ops/arming.toml`](../../ops/arming.toml) is `false`, the n8n
workflows are JSON files that have not been imported, and the systemd units are
text files that have not been installed. Nothing in this repository can publish on
its own today, and nothing can write to the website at all.

**The delivery route is decided.** John ruled on 2026-08-17 that GitHub's robot
holds the key: the workflow pushes the published tree into the site repository
itself. That repository auto-deploys, so **arming delivery is arming a live
website**. See [Delivery](#delivery-how-a-poll-reaches-the-website) before you
flip that line, and note it needs the second of the two PATs below.

Design: [ADR 0002](../adr/0002-scheduling.md). Storage:
[ADR 0003](../adr/0003-storage.md) as amended by
[ADR 0015](../adr/0015-cfbd-archive-no-r2.md).

---

## The shape of it

```
  Tue 06:00 PT    n8n on the Hostinger VPS  ──POST /dispatches──┐
                  (ops/n8n/sunday-dispatch.json)                │
                                                                ▼
  Tue ~04:43 PT   GitHub `schedule:` cron ────────────────► weekly.yml
  (drifts 35-216m) (.github/workflows/weekly.yml)               │
                                                                ▼
                                                      ops/bin/weekly.sh
                                                                ▲
  Tue 08:30 PT    systemd timer on the VPS ─────────────────────┘
                  (ops/systemd/cfb-poll-weekly.timer)

  Tue 14:00 PT    n8n dead-man's switch ───► email, ONLY if nothing published
                  (ops/n8n/deadman-switch.json)
```

Three clocks, one script, and a fourth thing whose only job is to notice that
none of them worked.

**The two filenames still say `sunday`.** They are `ops/n8n/sunday-dispatch.json`
and this page. Renaming them would break every link in the ADRs, the README and
`AGENTS.md` for no behavioural gain, so the names are historical and the contents
are correct. The workflow *inside* that file is named
`cfb-poll - weekly dispatch (Tuesday 06:00 PT)`, which is what n8n will show you.

---

## Why Tuesday, and why every clock moved

**The old clock was Sunday 06:00 ET and it was wrong about week 1.** Not
marginally: it published the opening week two days before the opening week was
over. This is the schedule it was wrong about, read from the CFBD API on
2026-08-17.

**Week 1 does not end on Saturday, and it does not end on Sunday either.** The
2026 opener runs Thursday through Labor Day Monday:

| 2026 week 1 | kickoff PT | |
|---|---|---|
| Washington State at Washington | Sun 2026-09-06 13:00 | |
| Wisconsin at Notre Dame | Sun 2026-09-06 16:30 | |
| Louisville at Ole Miss | Sun 2026-09-06 16:30 | |
| **SMU at Florida State** | **Mon 2026-09-07 16:30** | **the last game of week 1** |

2025 had the same shape — Virginia Tech–South Carolina and Notre Dame–Miami on
the Sunday, TCU–North Carolina on Labor Day Monday at 17:00 PT — so this is the
sport's habit, not a 2026 quirk.

**Every other week ends late Saturday, in Hawai'i.** Four to six Saturdays a
season carry a Hawai'i home game kicking 20:59 PT, which is the latest kickoff
slot in the sport and puts the last whistle after midnight Pacific. Weeks 2, 5,
11 and 13 of 2026 all have one.

**And the next week starts on Tuesday afternoon.** From week 5 onward the
MACtion midweek slate opens Tuesday at 16:00 PT. That is the late edge of the
window: publish after it and the poll is describing a week that has already
started playing the next one.

### The whole season, week by week

Last scheduled game of each week, in Pacific. Kickoffs are what CFBD `/games`
carries; the finish column adds 3h45m, which is a long game with overtime rather
than an average one. **Evidence column: `2026` is the real 2026 schedule as
posted; `2025` is last season's actual, used where 2026 has not been filled in
yet.**

| week | last game (PT) | kickoff | est. finish | evidence |
|---:|---|---|---|---|
| 1 | **Mon** SMU at Florida State | 09-07 16:30 | Mon 20:15 | 2026 |
| 2 | Sat New Mexico State at Hawai'i | 09-12 20:59 | Sun 00:44 | 2026 |
| 3 | Sat Fresno State at San José State | 09-19 20:00 | Sat 23:45 | 2026 |
| 4 | Sat Georgia Tech at Stanford | 09-26 19:30 | Sun 00:44 † | 2026 |
| 5 | Sat San José State at Hawai'i | 10-03 20:59 | Sun 00:44 | 2026 |
| 6 | Sat Boise State at Fresno State | 10-10 19:30 | Sun 00:44 † | 2026 |
| 7 | Sat Fresno State at San Diego State | 10-17 19:30 | Sun 00:44 † | 2026 |
| 8 | Sat North Dakota State at New Mexico | 10-24 19:00 | Sun 00:44 † | 2026 |
| 9 | Sat Northern Illinois at UNLV | 10-31 19:30 | Sun 00:44 † | 2026 |
| 10 | Sat Texas State at Oregon State | 11-07 19:30 | Sun 00:44 † | 2026 |
| 11 | Sat North Dakota State at Hawai'i | 11-14 20:59 | Sun 00:44 | 2026 |
| 12 | Sat Utah State at Oregon State | 11-21 19:30 | Sun 00:44 † | 2026 |
| 13 | Sat Sacramento State at Hawai'i | 11-28 20:00 | Sun 00:44 | 2026 |
| 14 | Sat conference championships | 12-05 17:00 | Sat 20:45 | **2025** ‡ |
| 15 | Sat Navy at Army | 12-12 12:00 | Sat 15:45 | 2026 |
| bowls / CFP | scattered Tue–Sat, latest kick 18:15 | — | ~22:00 | **2025** ‡ |

† These weeks carry 36–45 games whose kickoff time is still TBD. CFBD stamps a
TBD game at midnight Eastern on its calendar date, so the **date** is real and
the clock is not. Every one of those TBD dates falls Tuesday through Saturday —
**none on a Sunday or a Monday** — and the latest kickoff slot that exists in the
sport is Hawai'i's 20:59 PT, so the finish column is the worst case, not a guess.

‡ 2026 has no week 14 and no postseason in the feed yet, because championship
participants and bowl assignments are not known in August. Those two rows are
2025's actuals: championship Saturday finished 20:45 PT, and the latest bowl
kickoff of the 2025 postseason was 18:15 PT. Re-read this table each August.

**Midweek games matter for the other edge.** Weeks 6 through 13 all carry
Tuesday and Wednesday MACtion. Those games are early in their own week, so they
never set the *last* game — but the next week's Tuesday games are what stop the
clock drifting later than Tuesday morning.

So the window every clock has to fit inside is:

| | earliest safe | latest safe | |
|---|---|---|---|
| week 1 | Mon 20:15 PT | Thu 17:00 PT | Labor Day nightcap |
| weeks 2–4 | Sun 00:44 PT | Thu 16:30 PT | no midweek games yet |
| weeks 5–13 | Sun 00:44 PT | **Tue 16:00 PT** | MACtion opens the next week |
| championship week | Sat 20:45 PT | Sat 12:00 PT (next) | 2025 evidence |

**`Tuesday 06:00 PT` is the only sane hour inside all of them.** It clears the
Labor Day nightcap by nine and three quarter hours, clears a Hawai'i nightcap by
twenty-nine, and still lands ten hours before the earliest game of the following
week.

**What it costs, said plainly: about 53 hours of staleness on a typical week.**
The last whistle is around 00:44 PT Sunday and the poll goes out at 06:00 PT
Tuesday. A Monday 06:00 PT clock would be 24 hours fresher (29.3 hours) and is
the obvious cheaper answer, and it is rejected for one reason: it fires ten and a
half hours *before* SMU–Florida State kicks off on Labor Day. The failure that
buys is the silent kind this whole design exists to prevent — a week-1 board
published without a game in it, the guard then marking the week published, and
the Tuesday catch-up correctly no-opping on a wrong number that sits on
thepoll.ai until week 2.

**If you want Monday back, here is the price.** `cfbpoll guard` currently asks
two questions: is the trigger armed, and is the week already published. It has no
third question about whether the week's slate is *complete*. Teach it that — a
`/games` check that refuses to publish a week with unplayed games in it — and
Monday 06:00 PT becomes safe and the poll gets a day fresher. That is real work
and it is not done, so until it is, the clock is Tuesday.

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

## John's part: two PATs, one paste each

This design needs exactly two credentials from you, and they do different jobs
in different places. Make them separately, and do not reuse one for both — the
whole reason each is safe is that it can only do its own job.

| | **PAT 1 — the clock** | **PAT 2 — the delivery** |
|---|---|---|
| what it does | lets n8n press "Run workflow" | lets the workflow push the poll to the site |
| repository | `cfb-poll` | `sandbox` |
| permission | Actions: Read and write | Contents: Read and write |
| lives in | an **n8n credential** on the VPS | a **GitHub Actions secret** |
| name | `GitHub PAT - cfb-poll Actions` | `SANDBOX_CONTENTS_PAT` |
| if it leaks | somebody can start a poll run | **somebody can change the website** |

That last row is why they are separate. PAT 1's worst case is a wasted Actions
run. PAT 2 writes to the repository that auto-deploys thepoll.ai.

---

### PAT 1 — the clock. n8n presses the button.

n8n needs to press the button on this one workflow and nothing else.

**Click by click.**

1. Go to <https://github.com/settings/personal-access-tokens/new>.
   (Or: your avatar → **Settings** → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.)
2. **Token name:** `n8n cfb-poll weekly dispatch`
3. **Description:** `Tuesday 06:00 PT clock. Fires weekly.yml only.`
4. **Resource owner:** `vyhlidal`
5. **Expiration:** **Custom → one year from today.** Not "No expiration".
   Write the date in your calendar now with a reminder a week before; a clock
   that stops in November because a token expired is the exact silent failure
   this design exists to prevent, and the dead-man's switch will catch it but
   only after a missed Tuesday.
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

**How to check it later.** The token's page lists "Last used". If the weekly
dispatch is working, that date is the most recent Tuesday.

**If it leaks or you are unsure:** revoke it on the same settings page and make a
new one. It can do exactly one thing — start a workflow run in `cfb-poll` — which
is why it is scoped this way, but there is no reason to leave a doubtful token
alive.

---

### PAT 2 — the delivery. The workflow writes the site.

John ruled the delivery gap on 2026-08-17: **GitHub's robot holds the key.** After
a publishing run passes its gate, the workflow pushes the fixture tree into
`vyhlidal/sandbox` under `cfb-poll-data/`.

> **PUSHING THERE DEPLOYS THE PUBLIC SITE.** That repository auto-deploys from
> `main`, so a successful delivery is thepoll.ai changing a minute or so later.
> There is no staging environment and no review step between this token and the
> internet. It is the most consequential credential in the project.

**Click by click.**

1. Go to <https://github.com/settings/personal-access-tokens/new> again. This is a
   **second, separate token**. Do not edit PAT 1 to add the site repo — a token
   that can both start runs and rewrite the website is two blast radii in one
   string.
2. **Token name:** `cfb-poll delivery to sandbox`
3. **Description:** `Weekly poll publication into cfb-poll-data/. Contents only.`
4. **Resource owner:** `vyhlidal`
5. **Expiration:** **Custom → one year from today.** Same calendar reminder as
   PAT 1, and set it for the same day so there is one renewal errand a year
   rather than two.
6. **Repository access:** **Only select repositories** → pick **`sandbox`**.
   Only that one. Not `cfb-poll`, not "All repositories".
7. **Permissions → Repository permissions**, set exactly one:
   - **Contents: Read and write**
   - Everything else stays **No access**. It does not need Actions, it does not
     need Pull requests, and it must not have them: this token's entire job is to
     add a commit to one directory.
8. **Generate token**, copy it.
9. Paste it into GitHub Actions, once:
   <https://github.com/vyhlidal/cfb-poll/settings/secrets/actions> →
   **New repository secret** →
   - **Name:** `SANDBOX_CONTENTS_PAT` (exactly this; the workflow looks it up by
     name)
   - **Secret:** the token
   - **Add secret**. Then close the tab. Do not put it in a file, a note, a
     message, or this repository.

**Why an Actions secret and not an n8n credential.** n8n starts the run; it does
not do the work. The push happens on the runner, at the end of a job that has
already passed its data-quality gate, so the credential belongs where the push
is.

**How narrow it actually is inside the workflow.** The secret is on two steps —
`Delivery - clone the site repo` and `Delivery - push to the site repo` — and on
no others. It is deliberately *not* job-wide and *not* on the step that runs the
model, the archive sync and every third-party wheel in `uv.lock`. A test enforces
that (`test_the_site_pat_is_scoped_to_the_delivery_steps_only`).

**How to check it later.** The token page's "Last used" should be the most recent
Tuesday, and `vyhlidal/sandbox`'s history should show a `Poll <season> week <NN>`
commit from `cfb-poll robot` for that week.

**If it leaks:** revoke it immediately, and check `sandbox`'s commit history for
anything not authored by `cfb-poll robot <noreply@thepoll.ai>`. Unlike PAT 1,
this one's worst case is visible to the public.

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
4. Check the workflow's **Settings → Timezone** reads `America/Los_Angeles`. The
   file sets it; confirm it survived the import, because the cron expression is a
   bare local time and the timezone is the only thing making it Pacific. Getting
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

Do these in order, one Tuesday apart where it says so. The point of the staggering
is that when something misbehaves you know which thing it was.

1. **Close the two pipeline gaps first.** `cfbpoll preflight` says which:

   ```bash
   uv run cfbpoll preflight
   ```

   That command is the authority on what is missing, not this page: it reads
   each verb's body rather than a list somebody has to remember to update.
   **While it names anything, `PUBLISH=true` refuses to start** — deliberately,
   in seconds, before the 0.55 GB download — so arming a clock before this is
   clean produces a faster failure, not a poll.

   Note the ordering the built `validate` forces: it takes `--from <run dir>`,
   because the bounded week-over-week movement check needs this week's board and
   last week's. So the gate runs *after* the fit and *before* anything
   publishes. `STRICT_VALIDATE` is off by default — four of its eight checks read
   the private CFBD archive or a previous run, so strict-by-default would fail
   every season opener and every fork for reasons that are not data-quality
   problems. Turn it on once the season is running on a machine with the key.
2. **Make both PATs** (above) and put each in its one place: PAT 1 in the n8n
   credential, PAT 2 in the `SANDBOX_CONTENTS_PAT` Actions secret.
3. **Rehearse by hand.** A manual dispatch with `publish` unchecked. It fits and
   writes `out/` and publishes nothing, and delivery never runs because delivery
   only runs on a publishing run.
4. **Rehearse a publication by hand, with delivery still disarmed**, `publish`
   checked, on a week you are watching. This proves the whole pipeline including
   the release bundle **without touching the website**. Do not skip it: it is the
   last point at which a mistake is private.
5. **Arm delivery, and watch that one dispatch closely.** Set
   `[steps] delivery = true`, commit, push to `main`, then run one manual
   dispatch with `publish` checked.

   **This is the step where the public site changes for the first time.** Have
   thepoll.ai open. When the run finishes, check three things in this order: the
   `Delivery - push` step's log says PUSHED; `vyhlidal/sandbox` has a
   `Poll <season> week <NN>` commit from `cfb-poll robot`; the site shows the new
   week a minute or two later. If any of the three is wrong, set `delivery` back
   to `false` and push before doing anything else.

   Then **run the same dispatch a second time** and confirm the delivery step
   reports "nothing to push". That is the idempotency guarantee proven on the
   real repository, and it costs one run.
6. **Arm the primary clock alone.** Set `n8n = true` in `ops/arming.toml`, commit,
   push to `main`, then activate the n8n dispatch workflow. Leave the other two
   `false`. Watch one Tuesday, end to end, all the way to the site.
7. **Arm the dead-man's switch.** Activate that n8n workflow. Watch one Tuesday
   and confirm it stays quiet.
8. **Install and arm the VPS fallback.** Follow
   [the install runbook](vps-fallback-install.md), then set `vps_timer = true`.
   Watch one Tuesday: it should exit 0 in about forty seconds because the 06:00
   run already published.

   Decide before you arm it whether the VPS should deliver too. It can — nothing
   stops `weekly.sh` doing delivery there — but it needs its own copy of PAT 2 in
   `/etc/cfb-poll/weekly.env`, which is a second place a website-writing token
   lives. The conservative choice is to leave the VPS's `SANDBOX_CONTENTS_PAT`
   unset, so the fallback produces the board and a human delivers it on the rare
   Tuesday the primary died.
9. **Arm the third string last.** Set `schedule = true`. This is the one that can
   fire hours from where you expect it, so it goes on when the two reliable paths
   are known good and the guard has been proven idempotent three Tuesdays running.

Reverse in the same order to switch anything off. Flipping a line in
`ops/arming.toml` is a reviewed commit with an author and a date, which is the
point of the file existing rather than a checkbox somewhere.

**The fastest way to stop the site changing** is `delivery = false` pushed to
`main`. That leaves the poll still running and still producing boards, and only
the publication to the website stops — which is usually what you actually want,
rather than killing the clock.

---

## Delivery: how a poll reaches the website

**Decided by John, 2026-08-17: GitHub's robot holds the key.** The workflow
pushes the published tree into `vyhlidal/sandbox` under `cfb-poll-data/` using
PAT 2, at the end of a run that has already passed its gate.

> **THE SITE AUTO-DEPLOYS FROM THAT PUSH.** `vyhlidal/sandbox` deploys `main`
> automatically, so a successful delivery is a live change to thepoll.ai a minute
> or so later. There is no staging step, no preview, and no human between the
> push and the public. Everything below is shaped by that.

### What actually happens, in order

1. **Clone first, publish second.** `ops/bin/deliver-fixtures.sh prepare` clones
   the site repo, and the job publishes the week *straight into that clone*.

   This ordering is not an optimisation, it is a correctness requirement, and it
   is the one thing here most likely to be "simplified" by someone later.
   `publish fixtures` rebuilds `index.json` from whatever is on disk at its
   destination. A runner starts empty, so publishing into a scratch directory
   produces an index naming exactly one week and one season — and copying that
   over the site's `index.json` would erase 2023 and 2025 from the season strip
   while every week document sat there untouched. A silent, total loss of the
   navigation, caused by a step that looked like it only added a file.

2. **Nothing is pushed until the end.** Cloning and writing are local. The site
   repository does not change until `deliver-fixtures.sh push`, which runs after
   the leakage audit, the data-quality gate and the release bundle have all
   passed. **A failed gate leaves the site repo untouched**, and the only
   casualty is a temporary directory.

3. **The commit is the provenance chain.** Each delivery lands as:

   ```
   Poll 2026 week 07 (regular)

     season:     2026
     week:       7 (regular)
     model sha:  <the cfb-poll commit that produced it>
     run:        https://github.com/vyhlidal/cfb-poll/actions/runs/<id>
     files:      5 changed under cfb-poll-data/
   ```

   Authored by `cfb-poll robot <noreply@thepoll.ai>`. That message is the only
   link between a file on thepoll.ai and the run that made it, so it is written
   even on a dull week.

4. **Re-running a week is free.** The fixture documents are a deterministic
   function of the run directory — `published_at` comes from the run record, not
   the wall clock — so an unchanged week stages no diff, makes no commit and
   pushes nothing. The site's history never accumulates empty markers.

### Three switches, all of which must be on

Delivery is off unless *all* of these are true, and any one of them off makes it
skip with a notice rather than fail:

- `[steps] delivery = true` in [`ops/arming.toml`](../../ops/arming.toml) —
  committed `false`. Note there is **no human exemption** here, unlike
  `[triggers]`: a manual dispatch does not deploy the site. Rehearsing the whole
  job without touching the website is the point.
- The `SANDBOX_CONTENTS_PAT` Actions secret exists (PAT 2 above).
- `SKIP_DELIVERY` is not `true`.

### Rehearsing it without a website

`ops/bin/deliver-fixtures.sh` takes `SANDBOX_REMOTE`, so a local path stands in
for GitHub, and `ARMING_FILE` points at a scratch switch so nothing armed gets
committed. `DRY_RUN=true` makes the commit and stops before the push:

```bash
git init --bare /tmp/stand-in.git         # ... seeded with a cfb-poll-data/ tree
printf '[steps]\ndelivery = true\n' > /tmp/armed.toml

export ARMING_FILE=/tmp/armed.toml SANDBOX_REMOTE=/tmp/stand-in.git \
       SANDBOX_CONTENTS_PAT=unused DELIVERY_CLONE=/tmp/site-clone \
       SEASON=2023 WEEK=12 SEASON_TYPE=regular
FIXTURES="$(ops/bin/deliver-fixtures.sh prepare)"
uv run cfbpoll publish fixtures --from out --out "$FIXTURES"
DRY_RUN=true ops/bin/deliver-fixtures.sh push
```

### The token never reaches disk or a log

It is handed to git through `GIT_ASKPASS`, so it is not written into
`.git/config` the way a tokenised remote URL would be, not visible in `ps`, and
not in the workflow transcript. `GIT_TERMINAL_PROMPT=0` means a bad credential
fails instead of hanging. The staging is `git add -- cfb-poll-data`, never
`git add -A`: that repository is somebody else's working tree, and a sweep there
would publish whatever a human left lying around under a poll commit.

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

**"The run went green but the site did not change."** Open the two `Delivery`
steps. `DELIVERY SKIPPED` there names its own reason, and there are only three:
`[steps] delivery` is `false`, `SANDBOX_CONTENTS_PAT` is unset, or nothing
changed because the site already had that week. All three are exit 0 on purpose —
a disarmed delivery is not a failure — so a green run that delivered nothing is
expected while delivery is off, and the step log is where you find out which.

**"Delivery failed with a 403."** PAT 2 expired, was revoked, or is scoped wrong.
Check it has **Contents: Read and write** on `sandbox` and that `sandbox` is in
its repository list. A 404 on the clone usually means the same thing: a
fine-grained token with no access reads as "no such repository".

**"The site's index lost a season."** That is the failure the clone-before-publish
ordering exists to prevent, so something reordered it. Confirm `Delivery - clone
the site repo` ran *before* `Run the weekly job`, and that the job's `FIXTURES`
points inside the clone rather than at `out/data`. Recover by re-publishing the
missing weeks into a clone and delivering once; the week documents themselves are
untouched by this failure, only `index.json` is.

**"I need to stop the site changing but keep the poll running."** Set
`[steps] delivery = false` and push to `main`. Boards keep being produced;
nothing reaches the website.

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
