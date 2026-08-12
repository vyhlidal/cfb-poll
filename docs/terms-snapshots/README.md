# docs/terms-snapshots/

Dated copies of the upstream terms this project depends on. **Empty right now —
the snapshot has not been taken.**

## Why this exists

CFBD's terms §7 lets them change the terms "from time to time," with changes
taking effect **immediately** on posting, and §6 permits revocation at their
discretion. A dependency that can change its rules without notice needs a
compliance baseline we can diff against (report 01 §5.3).

## The required snapshot

**`cfbd-terms-2025-07-01.html`** — CollegeFootballData.com Terms and Conditions,
Effective Date 2025-07-01, owner Rad Sports Analytics LLC. This is the version the
research analysed and the baseline this project is built against.

### A browser render is required. A plain fetch will not work.

Recorded here so nobody wastes an afternoon rediscovering it (report 01 §4.1):

> The page is a client-rendered SPA. A plain HTTP fetch returns a ~956 KB Nuxt
> bundle whose only visible text is "CollegeFootballData.com"; `_payload.json`
> returns 32 bytes; grepping the bundle for "redistribut" or "reselling" finds
> nothing. **The terms are only readable in a browser.**

So: open `https://collegefootballdata.com/terms` in a real browser, let it render,
and save the rendered DOM (or print to PDF) into this directory with the effective
date in the filename. Do not commit a raw `curl` capture — it contains none of the
governing text.

## Cadence

Re-check quarterly and diff against the stored copy. If the terms change, the
diff is the trigger for a compliance review — in particular of §3, which is the
clause that keeps raw CFBD data out of the public repo.

## The clauses that govern this project

- **§3 Prohibited Behavior** — "Reselling or redistributing data obtained from the
  API without explicit permission." This is why the CFBD archive is private and
  the SportsDataverse archive is the one we republish.
- **§5 Attribution** — "While not required, it is strongly encouraged that users
  credit CollegeFootballData.com as the data source." **We credit them anyway,
  everywhere.** It costs nothing, it is what the maintainer asks, and it makes a
  discretionary revocation vanishingly unlikely.
- **§4 Data Accuracy** — all data "as-is," no warranty. Which is why
  `cfbpoll validate` exists and why a failed gate publishes nothing.

Also worth snapshotting when convenient: the MIT license files of
`sportsdataverse/sportsdataverse-data` and `cfbfastR`, since our republishing
rights rest on them.
