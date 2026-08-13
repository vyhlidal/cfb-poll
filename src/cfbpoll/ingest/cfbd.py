"""CFBD REST API v2 client - the weekly in-season pull, and the postseason backfill.

Specified by report 01 §3.7 (the Sunday job), §3.6 (endpoints), §4.1 (terms).

THE CALL SEQUENCE IS 22 CALLS AND THE ORDER IS LOAD-BEARING:
   1 GET /info                      quota check FIRST, so the job fails fast and
                                    loud rather than half-completing
   2 GET /calendar                  resolve the current week W; NEVER hardcode it
   3 GET /games?week=W              results
   4 GET /games?week=W+1            next slate, for projections
   5 GET /games/teams?week=W        box scores
   6 GET /drives?week=W
   7 GET /plays?week=W              (year AND week are both required)
   8 GET /stats/game/advanced?week=W
   9 GET /stats/season
  10 GET /stats/season/advanced
  11 GET /ppa/teams
  12 GET /wepa/team/season          (Tier 1+)
13-17 GET /ratings/{sp,srs,elo,fpi,core}   BENCHMARKS ONLY, NEVER INPUTS
  18 GET /rankings                  BENCHMARK ONLY - human polls are constraint 1
  19 GET /records
  20 GET /lines                     BACKTEST BASELINE ONLY, never a feature
  21 GET /games/weather             (Tier 1+)
  22 GET /info/usage?days=7         log what we actually spent

Raw data precedes aggregates, and benchmarks/context come last, so that a
failure late still leaves everything needed to compute a ranking.

Chunky, not chatty: every call is season- or week-scoped, never team-scoped.
CFBD's own guidance - "loop over ~15 weeks rather than 130+ teams". Per-team
looping would cost ~138x more for identical data.

Budget: ~110 calls/month against Tier 1's 5,000. About 45x headroom. On the FREE
tier's 1,000 the same job still fits, and `check_quota` is what keeps it honest:
the guard runs before anything is spent, and the floor is a parameter rather than
a constant so a backfill can demand a bigger cushion than a weekly run.

TERMS (report 01 §4.1): attribution is explicitly NOT required and we give it
anyway, everywhere. Raw CFBD responses must never reach the public repo - they go
to the private archive only (`archive/` is gitignored, and
`tests/unit/test_cfbd_ingest.py` asserts the cfbd subtree is untracked). The key
lives in an Authorization header, never in a URL, and never in the manifest.

TIER GATING IS DISCOVERED, NOT ASSUMED. `/info` returns a `features` object;
report 01 §7 open question 1 flagged the tier-to-feature mapping as [D]. The
gated calls in the weekly sequence are therefore issued as BEST EFFORT: a 401 or
403 on `/wepa/team/season` records the status in the manifest and continues,
because a missing opponent-adjusted benchmark must not cost us a poll.

STATUS: real. `pull_week` runs the full 22-call sequence; `pull_postseason` and
`pull_teams` are the narrow, cheap entry points the backfill used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cfbpoll.config import REPO_ROOT
from cfbpoll.ingest import archive

__all__ = [
    "BASE_URL",
    "BENCHMARK_RATINGS",
    "DEFAULT_ARCHIVE",
    "DEFAULT_MIN_REMAINING",
    "GATED_ENDPOINTS",
    "WEEKLY_CALL_BUDGET",
    "CFBDError",
    "QuotaError",
    "Session",
    "api_key",
    "archived_bodies",
    "archived_games",
    "archived_teams",
    "check_quota",
    "pull_postseason",
    "pull_ratings",
    "pull_teams",
    "pull_week",
    "resolve_week",
]

BASE_URL = "https://api.collegefootballdata.com"

DEFAULT_ARCHIVE = REPO_ROOT / "archive" / "cfbd"

WEEKLY_CALL_BUDGET = 22
"""Steady-state calls per weekly run (report 01 §3.7). Guard against drift."""

DEFAULT_MIN_REMAINING = 200
"""Default quota floor. A weekly run needs 22; the floor leaves room for retries."""

#: Endpoints behind a `UserFeatureAccess` flag (report 01 §3.3). A non-2xx on one
#: of these is recorded and skipped rather than raised - see the module docstring.
GATED_ENDPOINTS: frozenset[str] = frozenset({"/wepa/team/season", "/games/weather", "/scoreboard"})

#: Where `/info` and `/calendar` land: they are not season-scoped and inventing a
#: season directory for them would put a lie in the layout.
META_BUCKET = "_meta"

_ENV_VAR = "CFBD_API_KEY"


class CFBDError(RuntimeError):
    """A CFBD request failed in a way the caller must not paper over."""


class QuotaError(CFBDError):
    """The monthly call quota is exhausted, or too close to it to proceed.

    Deliberately its own type. Report 01 §5.2: "Treat 429 as a distinct alertable
    failure, not a generic retry - retrying a quota error fixes nothing."
    """


def api_key(env: dict[str, str] | None = None) -> str:
    """The bearer token, from the environment, falling back to the repo `.env`.

    The `.env` fallback exists so a local run works without exporting anything,
    and `.env` is the first line of `.gitignore` for the reason report 01 §3.2
    gives: a leaked key is the one catastrophic mistake available to this project.
    """
    source = dict(os.environ if env is None else env)
    value = source.get(_ENV_VAR, "").strip()
    if value:
        return value

    dotenv = REPO_ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, raw = line.partition("=")
            if name.strip() == _ENV_VAR:
                return raw.strip().strip("'\"")

    raise CFBDError(
        f"{_ENV_VAR} is not set and no .env carries it. A fork with no key must "
        "run the SportsDataverse leg instead of failing (report 01 §1)."
    )


@dataclass
class Session:
    """One authenticated conversation with CFBD, counting every call it makes.

    The counter is the point. Quota is a monthly budget shared with the
    basketball API (report 01 §3.3), there is no per-request throttle to notice
    it slipping, and the failure mode is a key temporarily disabled. A run that
    cannot say what it spent cannot be trusted with the next one.
    """

    archive_root: Path = field(default_factory=lambda: DEFAULT_ARCHIVE)
    key: str | None = None
    timeout: float = 30.0
    calls: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # httpx is imported HERE, not at module scope, so that
        # `from cfbpoll.ingest import cfbd` costs nothing and carries no network
        # capability. `archived_games` below is on the model path; opening a
        # socket must take a deliberate act, which is constructing a Session.
        import httpx

        self.archive_root = Path(self.archive_root)
        self._key = self.key or api_key()
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Accept": "application/json",
                # Attribution is not required (terms §5) and we identify
                # ourselves anyway, everywhere, for the reason report 01 §4.3
                # gives about ESPN: a project that would rather not be seen by
                # the host it depends on is doing something it should not.
                "User-Agent": "cfb-poll/0.0.1 (+https://github.com/vyhlidal/cfb-poll)",
            },
            timeout=self.timeout,
        )

    # -------------------------------------------------------------- plumbing

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        bucket: str = META_BUCKET,
        required: bool = True,
    ) -> Any:
        """GET one endpoint, archive the body VERBATIM, then parse.

        Archive-before-parse is the whole discipline (report 01 §5.4). If the
        parse raises, the bytes are already on disk and the failure is
        diagnosable from the archive alone with no second call against quota.
        """
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        response = self._client.get(endpoint, params=clean)
        self.calls += 1

        entry = archive.write_raw(
            response.content,
            endpoint,
            clean,
            self.archive_root,
            bucket=bucket,
            # str(response.url) carries the query string and NOT the key: the key
            # is a header. archive.write_raw asserts that independently.
            url=str(response.url),
            status=response.status_code,
            fetched_at=datetime.now(UTC),
        )
        self.log.append({"endpoint": endpoint, "params": clean, **entry})

        if response.status_code == 429:
            raise QuotaError(
                "HTTP 429 from CFBD: monthly call quota exceeded. This is not "
                "retryable (report 01 §5.2); the key may be disabled until reset."
            )
        if response.status_code >= 400:
            if not required or endpoint in GATED_ENDPOINTS:
                return None
            raise CFBDError(
                f"HTTP {response.status_code} from {endpoint} "
                f"params={clean}: {response.text[:200]}"
            )
        return json.loads(response.content) if response.content else None

    # -------------------------------------------------------------- control

    def info(self) -> dict[str, Any]:
        """GET /info - tier, monthly limit, remaining calls, feature entitlements."""
        payload = self.fetch("/info", bucket=META_BUCKET)
        if not isinstance(payload, dict):
            raise CFBDError(f"/info returned {type(payload).__name__}, expected an object")
        return payload

    def check_quota(self, min_remaining: int = DEFAULT_MIN_REMAINING) -> dict[str, Any]:
        """GET /info; abort the run if `remainingCalls` is below the floor.

        Runs FIRST in every sequence so a run fails fast and loud rather than
        half-completing (report 01 §3.7). The floor is a parameter because the
        right cushion depends on the job: a 22-call weekly run and a backfill
        that will spend a hundred want different answers.
        """
        payload = self.info()
        remaining = payload.get("remainingCalls")
        if remaining is None:
            raise CFBDError("/info did not report remainingCalls; refusing to spend blind")
        if int(remaining) < int(min_remaining):
            raise QuotaError(
                f"CFBD quota guard: {remaining} calls remain, floor is {min_remaining}. "
                "Aborting before anything is spent."
            )
        return payload


# ------------------------------------------------------- reading the archive back
#
# EVERYTHING BELOW IS OFFLINE. These functions never construct a Session, never
# import httpx, and never touch quota. They are what the games loader calls, and
# the "no network on any model or backtest path" invariant depends on that being
# true by construction rather than by discipline.


def archived_bodies(
    endpoint: str,
    bucket: str,
    archive_root: str | Path | None = None,
    *,
    params: dict[str, Any] | None = None,
) -> list[Path]:
    """Every archived body for one endpoint in one bucket, OLDEST FIRST.

    Oldest first because the archive is append-only and the interesting operation
    is the diff: a Sunday pull and a Wednesday re-pull sit side by side, and the
    last element is the current answer. Callers that want "what do we believe
    now" take `[-1]`; callers auditing an upstream correction walk the list.
    """
    directory = Path(archive_root or DEFAULT_ARCHIVE) / bucket
    manifest = archive.manifest_entries(directory / archive.MANIFEST_NAME)
    wanted = {str(k): str(v) for k, v in (params or {}).items()}
    keep: list[tuple[str, Path]] = []
    for entry in manifest:
        if entry.get("endpoint") != endpoint or int(entry.get("status", 0)) != 200:
            continue
        got = {str(k): str(v) for k, v in (entry.get("params") or {}).items()}
        if wanted and any(got.get(k) != v for k, v in wanted.items()):
            continue
        path = directory / str(entry["file"])
        if path.exists():
            keep.append((str(entry["fetched_at"]), path))
    return [path for _, path in sorted(keep)]


def archived_games(
    season: int,
    season_type: str = "postseason",
    archive_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """The newest archived `/games` body for one (season, season_type), parsed.

    Returns `[]` when the private archive does not hold that pull, which is the
    case for every fork: `archive/` is gitignored and CFBD terms §3 bars us from
    republishing raw responses. A missing CFBD archive is a DEGRADED run, not a
    failed one - exactly the posture `_plays_if_needed` already takes toward a
    missing play file - and the loader says so on the frame it returns.
    """
    bucket = _bucket(int(season), season_type, None)
    bodies = archived_bodies(
        "/games",
        bucket,
        archive_root,
        params={"year": season, "seasonType": season_type, "classification": "fbs"},
    )
    if not bodies:
        return []
    payload = json.loads(bodies[-1].read_text(encoding="utf-8"))
    return list(payload) if isinstance(payload, list) else []


def archived_teams(
    season: int, archive_root: str | Path | None = None
) -> list[dict[str, Any]]:
    """The newest archived `/teams/fbs` body for one season, parsed. Offline."""
    bodies = archived_bodies(
        "/teams/fbs", f"{season}/season", archive_root, params={"year": season}
    )
    if not bodies:
        return []
    payload = json.loads(bodies[-1].read_text(encoding="utf-8"))
    return list(payload) if isinstance(payload, list) else []


# ------------------------------------------------------------------ entry points


def check_quota(
    min_remaining: int = DEFAULT_MIN_REMAINING,
    archive_root: str | Path | None = None,
) -> dict[str, Any]:
    """GET /info; abort the run if remainingCalls is below the floor."""
    with Session(archive_root=Path(archive_root or DEFAULT_ARCHIVE)) as session:
        return session.check_quota(min_remaining)


def resolve_week(season: int, archive_root: str | Path | None = None) -> tuple[int, str]:
    """GET /calendar; return (week, season_type). The week is never hardcoded.

    Picks the LAST calendar entry whose `firstGameStart` is in the past, which is
    the week whose results a Sunday job is publishing. Falls back to week 1 of
    the regular season before a season starts.
    """
    with Session(archive_root=Path(archive_root or DEFAULT_ARCHIVE)) as session:
        rows = session.fetch("/calendar", {"year": season}, bucket=META_BUCKET) or []
    now = datetime.now(UTC)
    started = [(r, _parse_ts(r.get("firstGameStart"))) for r in rows]
    played = [(r, ts) for r, ts in started if ts is not None and ts <= now]
    if not played:
        return 1, "regular"
    current = max(played, key=lambda pair: pair[1])[0]
    return int(current["week"]), str(current.get("seasonType", "regular"))


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _bucket(season: int, season_type: str, week: int | None) -> str:
    """`archive/cfbd/2021/postseason` or `.../2026/week-03`.

    Postseason gets its OWN bucket rather than a week directory, because
    postseason week numbering mixes two conventions inside a single season
    (docs/data-findings.md §1) and a `week-01` directory holding January bowls
    would encode that bug into the layout.
    """
    if season_type != "regular":
        return f"{season}/{season_type}"
    return f"{season}/week-{int(week):02d}" if week is not None else f"{season}/season"


def pull_postseason(
    season: int,
    archive_root: str | Path | None = None,
    *,
    min_remaining: int = DEFAULT_MIN_REMAINING,
    box_scores: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    """The 2021-2022 backfill: postseason `/games`, and box scores if they are cheap.

    Two or three calls per season. The SportsDataverse `cfb_schedules_*` series
    carries NO postseason rows at all for 2021 and 2022 (docs/data-findings.md,
    and `ingest/sportsdataverse.py`'s game_type derivation is built around that
    absence), so those two seasons' conference title games are present but their
    bowls and the entire College Football Playoff are simply missing. That is a
    hole in the fit universe for exactly the games the config weights hardest.
    CFBD has them, and this is the cheapest way to get them.
    """
    own = session is None
    sess = session or Session(archive_root=Path(archive_root or DEFAULT_ARCHIVE))
    try:
        if own:
            sess.check_quota(min_remaining)
        params = {"year": season, "seasonType": "postseason", "classification": "fbs"}
        bucket = _bucket(season, "postseason", None)
        games = sess.fetch("/games", params, bucket=bucket) or []
        teams = None
        if box_scores:
            # `/games/teams` documents that one of week/team/conference is
            # required alongside year. Ask season-wide first: if CFBD accepts it
            # that is one call instead of one per postseason week, and if it
            # refuses we learn that from the archived body rather than a guess.
            teams = sess.fetch("/games/teams", params, bucket=bucket, required=False)
        return {"season": season, "games": games, "teams": teams, "calls": sess.calls}
    finally:
        if own:
            sess.close()


def pull_teams(
    season: int,
    archive_root: str | Path | None = None,
    *,
    min_remaining: int = DEFAULT_MIN_REMAINING,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """GET /teams/fbs - id, school, abbreviation, conference, color, alt_color, logos.

    One call per season and cached forever (report 01 §3.7, "cached once per
    season"). This is where team COLORS come from, and they cost no extra call
    because they ride along on a request the weekly job already makes
    (report 06 §8.1).
    """
    own = session is None
    sess = session or Session(archive_root=Path(archive_root or DEFAULT_ARCHIVE))
    try:
        if own:
            sess.check_quota(min_remaining)
        rows = sess.fetch("/teams/fbs", {"year": season}, bucket=f"{season}/season") or []
        return list(rows)
    finally:
        if own:
            sess.close()


#: Third-party ratings CFBD serves, and what each one is. BENCHMARKS ONLY - the
#: allow-list leakage audit is what enforces that, and this tuple is what makes
#: the set enumerable rather than folklore. `core` is CFBD's own, published
#: 2026-08-08 by Bill Radjewski (Rad Sports Analytics LLC).
BENCHMARK_RATINGS: tuple[str, ...] = ("sp", "srs", "elo", "fpi", "core")


def pull_ratings(
    system: str,
    seasons: list[int],
    archive_root: str | Path | None = None,
    *,
    min_remaining: int = DEFAULT_MIN_REMAINING,
    session: Session | None = None,
) -> dict[int, Any]:
    """GET /ratings/{system} for several seasons. BENCHMARK ONLY, NEVER AN INPUT.

    One call per season, plus the one quota check, and no more: this is the
    narrow pull for adding a third-party series to the comparison display, not
    the weekly sequence. `docs/data-sources.md` states the rule these bodies live
    under and `cfbpoll audit-features` is what enforces it - an allow-list check,
    so a rating that reached a design matrix fails closed whether or not anybody
    thought to ban it by name.

    Bodies are archived unmodified under `{season}/season`, which is gitignored:
    CFBD terms §3 bar republishing raw API data, so these never leave this disk.
    What may be published is analysis derived from them, which is the whole
    reason a benchmark is allowed to exist here at all.
    """
    if system not in BENCHMARK_RATINGS:
        raise CFBDError(
            f"unknown ratings system {system!r}; CFBD serves {list(BENCHMARK_RATINGS)}"
        )
    own = session is None
    sess = session or Session(archive_root=Path(archive_root or DEFAULT_ARCHIVE))
    try:
        if own:
            sess.check_quota(min_remaining)
        out: dict[int, Any] = {}
        for season in sorted(set(int(s) for s in seasons)):
            out[season] = sess.fetch(
                f"/ratings/{system}",
                {"year": season},
                bucket=f"{season}/season",
                required=False,
            )
        return out
    finally:
        if own:
            sess.close()


def pull_week(
    season: int,
    week: int,
    archive_root: str | Path | None = None,
    *,
    season_type: str = "regular",
    min_remaining: int = DEFAULT_MIN_REMAINING,
    include_gated: bool = True,
) -> dict[str, Any]:
    """Run the 22-call sequence, archiving each raw body before parsing anything.

    Returns the parsed payloads keyed by a short name, plus `calls` and the
    per-call manifest `log`. Nothing here computes anything: this is a transport,
    and every consumer reads the archive rather than this return value.
    """
    root = Path(archive_root or DEFAULT_ARCHIVE)
    bucket = _bucket(season, season_type, week)
    out: dict[str, Any] = {}
    with Session(archive_root=root) as sess:
        # 1. Quota first, so the job fails before it half-completes.
        out["info"] = sess.check_quota(min_remaining)

        # 2. The week is never hardcoded, even when the caller passed one: the
        #    calendar is archived so the run record can show what CFBD believed
        #    the current week to be at the moment we published.
        out["calendar"] = sess.fetch("/calendar", {"year": season}, bucket=META_BUCKET)

        base = {"year": season, "seasonType": season_type, "classification": "fbs"}

        # 3-4. Results, then next slate for projections.
        out["games"] = sess.fetch("/games", {**base, "week": week}, bucket=bucket)
        out["games_next"] = sess.fetch("/games", {**base, "week": week + 1}, bucket=bucket)

        # 5-8. Detail. Raw data precedes aggregates.
        out["games_teams"] = sess.fetch("/games/teams", {**base, "week": week}, bucket=bucket)
        out["drives"] = sess.fetch("/drives", {**base, "week": week}, bucket=bucket)
        out["plays"] = sess.fetch("/plays", {**base, "week": week}, bucket=bucket)
        out["stats_game_advanced"] = sess.fetch(
            "/stats/game/advanced",
            {"year": season, "week": week, "seasonType": season_type},
            bucket=bucket,
        )

        # 9-12. Season aggregates.
        season_params = {"year": season, "classification": "fbs"}
        out["stats_season"] = sess.fetch("/stats/season", season_params, bucket=bucket)
        out["stats_season_advanced"] = sess.fetch(
            "/stats/season/advanced", season_params, bucket=bucket
        )
        out["ppa_teams"] = sess.fetch("/ppa/teams", season_params, bucket=bucket)
        if include_gated:
            out["wepa_team_season"] = sess.fetch(
                "/wepa/team/season", {"year": season}, bucket=bucket, required=False
            )

        # 13-18. BENCHMARKS ONLY, NEVER INPUTS (report 01 §5.6). `audit-features`
        # is the enforcement; archiving them here is what makes the benchmark
        # comparison reproducible offline.
        for system in ("sp", "srs", "elo", "fpi", "core"):
            params = {"year": season}
            if system == "elo":
                params["week"] = week
            out[f"ratings_{system}"] = sess.fetch(
                f"/ratings/{system}", params, bucket=bucket, required=False
            )
        out["rankings"] = sess.fetch(
            "/rankings", {"year": season, "week": week, "seasonType": season_type}, bucket=bucket
        )

        # 19-21. Context.
        out["records"] = sess.fetch("/records", {"year": season}, bucket=bucket)
        out["lines"] = sess.fetch(
            "/lines",
            {"year": season, "week": week, "seasonType": season_type},
            bucket=bucket,
            required=False,
        )
        if include_gated:
            out["weather"] = sess.fetch(
                "/games/weather", {"year": season, "week": week}, bucket=bucket, required=False
            )

        # 22. Log what we actually spent.
        out["usage"] = sess.fetch("/info/usage", {"days": 7}, bucket=META_BUCKET, required=False)

        out["calls"] = sess.calls
        out["log"] = sess.log
    return out
