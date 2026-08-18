"""The projection fixture: `cfb-poll-data/<season>/projection.json`.

The site's contract, defined in `src/lib/cfb-poll/projection.ts` in the sandbox
app, and the two rules it binds this module to are the same two the poll's
fixtures already live under:

  1. THE SITE DERIVES NOTHING. Every number that appears on screen appears
     verbatim in a field here. `projected_wins` is a pre-formatted STRING, not a
     float, because a renderer that decides how many decimal places to show is a
     renderer that can disagree with the artifact.
  2. A MISSING FILE IS A LEGITIMATE ANSWER. The card renders "coming this week"
     rather than an error, so this module's failure mode is "write nothing".

`status` IS AUTHORITATIVE and is never inferred from the row count, which is what
lets a complete projection sit on disk, dark, until somebody decides to show it.

`basis` MUST BE A COMPLETE SENTENCE ending in a full stop: the card prints it and
then continues in the same paragraph, so a fragment produces prose that does not
parse. `_assert_sentence` enforces that here rather than trusting it, because the
failure is invisible in JSON and obvious on the page.

THE DISPLAY FIELDS COME FROM THE POLL'S OWN MACHINERY - `ingest/teams.mark_for`
and the `[display]` logo template - so a team's mark and logo cannot differ
between the projection card and the poll table sitting under it. That is not
tidiness: those two surfaces are on the same page, and a school whose colours
change between them would look like a bug in whichever one the reader trusts
less.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.ingest import cfbd
from cfbpoll.ingest.teams import PALETTE_MARK, load_colors, mark_for
from cfbpoll.projection import PROJECTION_VERSION

__all__ = ["PROJECTION_LABEL", "REBUILD_COMMAND", "SCHEMA_VERSION", "build", "write"]

SCHEMA_VERSION = 1

#: THE COMMAND THAT REBUILDS THIS DOCUMENT, published on the document.
#:
#: The front door used to print the POLL's run receipt under the Projection's
#: board, including "the one command that rebuilds it" pointing at
#: `cfbpoll rank --season 2025 --through-week 16`, which rebuilds a different
#: board, of a different season, by a different machine. A published artifact
#: that cannot name its own rebuild command borrows somebody else's, and a reader
#: who runs the borrowed one gets a different answer and concludes the site is
#: lying rather than confused.
#:
#: The make target rather than the bare CLI, because this one FITS: the recipe is
#: an OLS solve over the design transitions and the carried ratings come off the
#: walk-forward L3, so it needs the single-threaded BLAS pin the target carries
#: and the bare verb does not.
REBUILD_COMMAND = "make projection-fixture FIXTURES=<your data root>"

#: THE MARKER EVERY SURFACE SHOWING THIS DOCUMENT HAS TO CARRY, in the same words
#: everywhere, exactly as `recipes.ALTERNATE_LABEL` works for a poll produced
#: under an alternate lens (ADR 0011 §4). The projection is not the poll (ADR
#: 0010) and the surface most likely to arrive with no context at all is a share
#: card in somebody's timeline, so the label is a published FIELD rather than
#: copy in a renderer: the card cannot draw the board without also being handed
#: the sentence that says what the board is.
#:
#: Short on purpose. It goes in the accent slab above the thesis, where it has one
#: line, and a label that gets truncated to fit is a label that stopped saying the
#: thing it exists to say.
PROJECTION_LABEL = "THE PROJECTION. The poll grades it weekly."


#: Characters report 08 bans from the front door's visible copy. The em dash is
#: the one that matters and the other two are the shapes it arrives under when
#: somebody works around a linter.
_BANNED_PUNCTUATION: tuple[tuple[str, str], ...] = (
    ("—", "em dash"),
    ("–", "en dash"),
    ("--", "a double hyphen standing in for a dash"),
)


def _assert_no_em_dash(field: str, value: str) -> str:
    """Report 08's copy rule, made mechanical.

    THE FAILURE THIS EXISTS FOR ACTUALLY HAPPENED. The first `headline` this
    module shipped carried an em dash, it was printed verbatim in the largest
    type on the card, and it was the only em dash in the front door's entire
    visible text - so the one sentence the page leads with read as the one
    sentence somebody else wrote. Every other string on that page was written
    around the rule; this one was written around a spec that did not mention it.

    A rule the pipeline knows is a rule the pipeline keeps. Report 08's OTHER
    binding rule - no "X, not Y" constructions - cannot be linted, so it stays a
    matter of writing the sentence affirmatively, which is what the `headline`
    below now does.
    """
    for character, name in _BANNED_PUNCTUATION:
        if character in value:
            raise ValueError(
                f"`{field}` contains {name}. Report 08 bans it from the front "
                "door's visible copy, and this field is printed verbatim. Write "
                "the sentence affirmatively instead of splicing two clauses. "
                f"Got: {value!r}"
            )
    return value


def _assert_sentence(field: str, value: str) -> str:
    """A field the card continues from has to end like a sentence, cleanly punctuated."""
    text = _assert_no_em_dash(field, value.strip())
    if not text or text[-1] not in ".!?":
        raise ValueError(
            f"`{field}` must be a COMPLETE SENTENCE ending in a full stop - the "
            f"projection card prints it and continues in the same paragraph. Got: "
            f"{value!r}"
        )
    return text


def _conferences(season: int, archive_root: Any = None) -> dict[str, str | None]:
    """school -> conference for one season, from the archived `/teams/fbs` pull."""
    return {
        str(row.get("school")): (row.get("conference") or None)
        for row in cfbd.archived_teams(season, archive_root)
        if row.get("school")
    }


def _display(team: str, colors: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Logo URLs and the generated mark, exactly as `publish/serving.py` builds them."""
    display = config.get("display") or {}
    entry = colors.get(team)
    team_id = (entry or {}).get("team_id")

    urls: dict[str, str | None] = dict.fromkeys(
        ("logo_url", "logo_url_2x", "logo_url_dark", "logo_url_dark_2x")
    )
    if team_id is not None and bool(display.get("logos", True)):
        template = str(display["logo_url_template"])
        size = int(display.get("logo_size", 64))
        size_2x = int(display.get("logo_size_2x", 128))
        dark = str(display.get("logo_dark_variant", "-dark"))
        urls = {
            "logo_url": template.format(variant="", team_id=team_id, size=size),
            "logo_url_2x": template.format(variant="", team_id=team_id, size=size_2x),
            "logo_url_dark": template.format(variant=dark, team_id=team_id, size=size),
            "logo_url_dark_2x": template.format(variant=dark, team_id=team_id, size=size_2x),
        }

    if str(display.get("mark_colors", "team")) == "palette":
        label = ((entry or {}).get("abbreviation") or team)[:4].upper()
        mark = {"bg": PALETTE_MARK["bg"], "fg": PALETTE_MARK["fg"], "label": label}
    else:
        mark = mark_for(entry, (entry or {}).get("abbreviation") or team)

    return {
        "team_id": int(team_id) if team_id is not None else 0,
        **urls,
        "mark_bg": mark["bg"],
        "mark_fg": mark["fg"],
        "mark_label": mark["label"],
    }


def build(
    projection: pl.DataFrame,
    season: int,
    config: dict[str, Any],
    headline: str,
    basis: str,
    note: str | None = None,
    status: str = "published",
    published_at: str | None = None,
    top_n: int | None = None,
    archive_root: Any = None,
    backtest: dict[str, Any] | None = None,
    strength: Any = None,
    contrast: Any = None,
    sigma: float | None = None,
    calibration: Any = None,
    recipe: Any = None,
    source_season: int | None = None,
    generated_at: str | None = None,
    git_sha: str | None = None,
    config_hash: str | None = None,
) -> dict[str, Any]:
    """The fixture document. Every displayed number is a string or a plain scalar.

    `top_n` IS None BY DEFAULT, WHICH MEANS THE WHOLE BOARD. It shipped 25 rows
    until 2026-08-17 and that made a published claim uncheckable: the front door
    says North Dakota State is held at 33rd by the promotion ceiling, and a reader
    who went to look found a board that stopped eight rows above it. Copy that
    invites a reader to check has to be followed by a document they can check it
    in. The site still renders 25 (`ProjectionBoard` slices, and so does every
    share-card variant), so this is additive: the rest of the field is there for
    the reader who looks, and for `projection_grid`, the card that draws all of
    them and could not be built from a 25-row document at all.
    """
    if status not in ("coming", "published"):
        raise ValueError(f"status must be 'coming' or 'published', got {status!r}")

    colors = load_colors()
    conferences = _conferences(season, archive_root)
    ranked = projection.filter(pl.col("projected_rank").is_not_null())
    if top_n is not None:
        ranked = ranked.filter(pl.col("projected_rank") <= int(top_n))
    ranked = ranked.sort("projected_rank")

    rows: list[dict[str, Any]] = []
    for row in ranked.to_dicts():
        team = str(row["team"])
        entry = colors.get(team)
        wins = row.get("projected_wins")
        rows.append(
            {
                "rank": int(row["projected_rank"]),
                "team": team,
                "abbreviation": (entry or {}).get("abbreviation"),
                "conference": conferences.get(team),
                **_display(team, colors, config),
                # PRE-FORMATTED, per the contract. The site formats nothing, so
                # the decimal place is decided here, once, and cannot drift
                # between the card and the JSON a reader downloads.
                "projected_wins": (f"{float(wins):.1f}" if wins is not None else None),
                # THE COLUMN THE BOARD SORTS ON, previously invisible. A reader
                # who could see the ranking and the win total but not the
                # quantity that produced the ranking had no way to tell a
                # deliberate ordering from a broken one.
                "projected_power": _fmt1(row.get("projected_power")),
                # NEUTRAL FIELD: opponent quality only, with venue in
                # `home_games` beside it rather than folded in.
                "schedule_strength": _fmt1(row.get("schedule_strength")),
                "schedule_strength_rank": _int(row.get("schedule_strength_rank")),
                "schedule_field_size": _int(row.get("schedule_field_size")),
                "home_games": _int(row.get("home_games")),
                # True when any opponent on this schedule had to be rated by
                # mean reversion alone. See the contract doc's `opponent_source`
                # section: it is not a defect, it is two kinds of number in one
                # mean, and the card is entitled to know.
                "schedule_is_mixed": _bool(row.get("schedule_is_mixed")),
                # THE LOAD-BEARING FIELD. Every team scored against one real
                # calendar, so this column is comparable straight down the table
                # and the ranking stops needing prose to defend it.
                "wins_on_median_schedule": _fmt1(row.get("wins_on_median_schedule")),
                "note": _note(row),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "season": int(season),
        "status": status,
        "published_at": published_at,
        "grading_start_week": int(config["publication"]["headline_start_week"]),
        # The "this is not the poll" marker, carried as data so every surface
        # shows the same words. Additive: a consumer written against the original
        # field set never reads it and stays valid.
        "label": _assert_sentence("label", PROJECTION_LABEL),
        "headline": _assert_sentence("headline", headline),
        "basis": _assert_sentence("basis", basis),
        "note": _assert_sentence("note", note) if note else None,
        "backtest": _backtest_block(backtest),
        "schedule": _schedule_block(strength, contrast, sigma, calibration),
        "rows": rows,
        # Not in the site's interface, and carried anyway: a published projection
        # that cannot say which recipe made it cannot be graded season over season.
        "projection_version": PROJECTION_VERSION,
        # THE PROJECTION'S OWN RECEIPT. See `_provenance_block`.
        "provenance": _provenance_block(
            season=int(season),
            recipe=recipe,
            source_season=source_season,
            generated_at=generated_at or published_at,
            git_sha=git_sha,
            config_hash=config_hash,
        ),
    }


def _provenance_block(
    *,
    season: int,
    recipe: Any,
    source_season: int | None,
    generated_at: str | None,
    git_sha: str | None,
    config_hash: str | None,
) -> dict[str, Any]:
    """What produced this board, in the board's own document.

    THE FAILURE THIS FIXES IS ON THE PUBLISHED SITE. The front door prints one
    provenance footer on every route, and in August the board above it is the
    Projection while the footer is the Poll's: the poll's run id, the poll's
    hashes, and "the one command that rebuilds it" naming a `cfbpoll rank` of a
    different season. Every word of it is true about a document the reader is not
    looking at. The renderer was not wrong to print what it had; it had nothing
    else, because this artifact carried no receipt of its own.

    UNLIKE `schedule` AND `backtest`, THIS BLOCK IS NEVER NULL. Those two are
    absent when nobody measured the thing they describe, which is the honest
    answer for an unmeasured claim. Provenance is different: something produced
    this file, so the question always has an answer, and a null block would put
    the renderer straight back to borrowing the poll's. Fields the caller could
    not supply are null individually.

    `fit_rule` is ADR 0014's discipline stated about THIS season rather than in
    the abstract. The freeze it replaced ("nothing was ever tuned after 2023")
    stopped being true when `design_transitions` gained 2024 to 2025, and a page
    still printing the freeze is telling a reader the opposite of what the
    pipeline does. Templated, so it cannot go stale the way the sentence it
    replaces did.
    """
    transitions = [
        [int(a), int(b)] for a, b in (getattr(recipe, "transitions", None) or ())
    ]
    window = (
        f"{transitions[0][0]} to {transitions[0][1]} through "
        f"{transitions[-1][0]} to {transitions[-1][1]}"
        if len(transitions) > 1
        else (f"{transitions[0][0]} to {transitions[0][1]}" if transitions else None)
    )
    rule = (
        _assert_sentence(
            "provenance.fit_rule",
            f"This recipe projects {season}, so it was fitted on season transitions "
            f"whose target season finished before {season}, and on nothing else.",
        )
        if transitions
        else None
    )
    return {
        "projection_version": getattr(recipe, "version", None) or PROJECTION_VERSION,
        # The season whose final ratings every team on this board starts from. It
        # is the first term of the recipe and the fact the front door's "every
        # team starts at zero" bullet contradicts, so it is published rather than
        # implied.
        "source_season": int(source_season) if source_season is not None else None,
        "fitted_on_transitions": transitions or None,
        "fit_window": window,
        "fit_rule": rule,
        "generated_at": generated_at,
        "git_sha": git_sha,
        "config_hash": config_hash,
        "rebuild": REBUILD_COMMAND,
    }


def _backtest_block(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """The honest result, as a published field rather than prose anybody hard-codes.

    The site prints nothing it did not read out of a file, so "the AP beat us"
    cannot live in a React component: it has to arrive as a sentence, with the
    numbers that justify it beside it, in the same document as the ranking it
    qualifies. And the sentence is TEMPLATED FROM THE MEASURED VALUES rather than
    written out, so it cannot drift from `demo/projection-backtest.md` the way a
    hand-typed paragraph would the first time the recipe is refitted.

    `summary` is `fit.run(...)["summary"]`. None when the caller has not run the
    backtest, in which case the field is absent and the card says nothing about
    quality, which is the correct behaviour for a claim nobody has measured.
    """
    if not summary:
        return None
    ranks = summary.get("out_of_sample") or {}
    games = summary.get("early_season") or {}
    ours, theirs = ranks.get("projection"), ranks.get("ap_preseason")
    naive = ranks.get("naive_carryover")
    if not ours or not theirs:
        return None

    ap_hits = float(theirs["top25_overlap"])
    our_hits = float(ours["top25_overlap"])
    better = "better" if our_hits > ap_hits else "slightly better"
    leader, trailer = ("this projection", "the AP preseason poll") if our_hits > ap_hits else (
        "the AP preseason poll",
        "this projection",
    )
    first = (
        f"Over three out-of-sample season transitions {leader} ranked the "
        f"following season {better} than {trailer} did, hitting "
        f"{max(ap_hits, our_hits):.1f} of the final top 25 against "
        f"{min(ap_hits, our_hits):.1f}."
    )

    parts = [first]
    if games.get("projection") and games.get("ap_preseason"):
        our_su = float(games["projection"]["su_accuracy"])
        ap_su = float(games["ap_preseason"]["su_accuracy"])
        verb = "was the better predictor of" if our_su > ap_su else "was worse at predicting"
        parts.append(
            f"This projection {verb} September's games, at {our_su:.1%} straight "
            f"up against {ap_su:.1%}."
        )
    if naive:
        parts.append(
            "Both beat the floor of carrying last season's ratings forward "
            f"unchanged, which hits {float(naive['top25_overlap']):.1f}."
        )

    block = {
        "headline": _assert_sentence("backtest.headline", " ".join(parts)),
        "ap_top25_hits": f"{ap_hits:.1f}",
        "projection_top25_hits": f"{our_hits:.1f}",
        "naive_top25_hits": (f"{float(naive['top25_overlap']):.1f}" if naive else None),
        "transitions": 3,
        "source": "demo/projection-backtest.md",
    }
    return block


def _fmt1(value: Any) -> str | None:
    """One decimal place, as a string. The site formats nothing."""
    return None if value is None else f"{float(value):.1f}"


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _schedule_block(
    strength: Any, contrast: Any, sigma: float | None, calibration: Any = None
) -> dict[str, Any] | None:
    """The schedule gloss and its three caveats, every sentence templated.

    ALL FOUR CAVEATS SHIP AS FIELDS rather than as component copy, for the reason
    everything else on this document does: a caution the site hard-codes is a
    caution that stops being true the first time the numbers move and nobody
    re-reads the JSX. `uncertainty_note` is templated off the live sigma,
    `promotion_note` off the live promoted list, and `note` off the live contrast,
    so all three go stale together with the data or not at all.

    Returns None when no schedule was available, which is the correct answer for
    a fork with no CFBD archive: a projection without win totals also has no
    schedule strength, and a card that renders neither is a smaller product
    rather than a broken one.
    """
    if strength is None:
        return None

    block: dict[str, Any] = {
        "median_schedule_team": strength.median_schedule_team,
        "median_schedule_strength": _fmt1(strength.median_schedule_strength),
        "median_schedule_games": int(strength.median_schedule_games),
        "field_size": int(strength.field_size),
        "contrast": None,
        "note": None,
        "uncertainty_note": None,
        "promotion_note": None,
        # The names, as a field, because the surface that prints this caveat needs
        # to say WHO was promoted and the only alternative is hard-coding two
        # school names into a component that nobody re-reads the season a third
        # program comes up. Null in a season with no promotions.
        "promoted_teams": (_join(list(strength.promoted)) if strength.promoted else None),
    }

    if sigma is not None:
        block["uncertainty_note"] = _assert_sentence(
            "schedule.uncertainty_note",
            f"Every win total here comes from a distribution {float(sigma):.1f} "
            "points wide, because in August both teams in a game are projections "
            "rather than measurements. That compresses the spread, so teams "
            "differ by less in these columns than they will by December.",
        )

    if strength.promoted:
        block["promotion_note"] = _promotion_note(
            _join(list(strength.promoted)), calibration
        )

    if contrast is not None:
        block["contrast"] = {
            **contrast.as_dict(),
            "headline": _assert_sentence(
                "schedule.contrast.headline",
                f"{contrast.higher_team} projects "
                f"{contrast.higher_wins:.1f} wins and {contrast.lower_team} projects "
                f"{contrast.lower_wins:.1f}, and {contrast.higher_team} still ranks "
                f"higher. Run each on the other's calendar and the reason is "
                f"plain: {contrast.higher_team} would win "
                f"{contrast.higher_on_lower_schedule:.1f} games on "
                f"{contrast.lower_team}'s schedule, while {contrast.lower_team} "
                f"would win {contrast.lower_on_higher_schedule:.1f} on "
                f"{contrast.higher_team}'s.",
            ),
        }
        # THREE RULED DEFECTS IN ONE GENERATED SENTENCE, fixed together because
        # they shipped together (briefs/regeneration-queue.md item 5, and the SHIP
        # block in voice/site-rewrite/page-1-the-poll.md §6).
        #
        #   "This board"  ->  "This projection". "Board" is out of the site's
        #   vocabulary: two words and no third, the poll and the projection.
        #
        #   "wins on a median schedule"  ->  "projected wins against an average
        #   schedule". Ruled in voice-thepoll-v2.md §6 pair 6. "Median" is a
        #   statistics word doing an ordinary word's job on the surface a
        #   stranger meets first.
        #
        #   "the 138 we rank"  ->  "the 138 the model rates". Corporate we, ruled
        #   in §4's round-1 fix list. The model is the actor and it can be named.
        #
        # THE FIELD NAMES ARE UNCHANGED. `median_schedule_team`,
        # `median_schedule_games` and `field_size` are the fixture contract and
        # the site reads them; only the sentence built out of them moved.
        block["note"] = _assert_sentence(
            "schedule.note",
            "This projection ranks on projected power, so the win column beside "
            "it will sometimes disagree with the order. The column that "
            "reconciles them is projected wins against an average schedule, "
            f"which scores every team against {strength.median_schedule_team}'s "
            f"calendar, the {strength.median_schedule_games} games sitting at "
            f"the middle of the {strength.field_size} the model rates.",
        )
    return block


def _promotion_note(names: str, calibration: Any) -> str:
    """The FCS-promotion caveat, and it had to be rewritten because it went STALE.

    THE SENTENCE THIS REPLACES DESCRIBED A MODEL THAT NO LONGER EXISTS. It said
    any schedule containing a promoted team "is measured against a softer standard
    than the one they are about to be held to, and the bottom of the schedule
    ranking is correspondingly less firm than the numbers make it look". That was
    true while a promoted team carried its FCS-earned rating at face value. ADR
    0014 stopped that: the division boundary is priced from the crossover games,
    a promoted program gets part of it back on the evidence of the programs that
    have actually made the jump, and a ceiling stops the correction extrapolating
    past the best first FBS season on record. Telling a reader about an unfixed
    softness that has been measured and corrected undersells the work AND is
    false, which is a worse failure than vagueness.

    TEMPLATED FROM THE LIVE CALIBRATION, never typed, for the reason every other
    caveat here is: the constants are re-measured on every run, and a number typed
    into a sentence goes stale the first time the archive grows a season.

    The honest caveat is now a different and more interesting one, and it is the
    last clause: the bump rests on however many programs have made the jump, which
    is six. `levers.py` puts it best and this note does not try to beat it.

    A calibration that could not be measured (a fork whose archive holds too few
    crossover games) leaves the ratings carried unchanged, so the softness
    sentence is true again and is what ships.
    """
    opening = (
        f"{names} moved up from FCS this season, so the ratings they bring with "
        "them were earned against FCS opposition."
    )
    if calibration is None or not bool(getattr(calibration, "measured", False)):
        return _assert_sentence(
            "schedule.promotion_note",
            f"{opening} This archive held too few games between the two divisions "
            "to price that move, so those ratings are carried across unchanged and "
            "the bottom of the schedule ranking is less firm than the numbers make "
            "it look.",
        )

    gap = abs(float(calibration.cross_division_gap))
    bump = abs(float(calibration.promotion_bump))
    text = (
        f"{opening} The {int(calibration.n_bridge_games)} games between the two "
        f"divisions in this archive price that rating {gap:.1f} points too high "
        f"against FBS opposition, and the {int(calibration.n_promotion_games)} games "
        f"{int(calibration.n_promoted_teams)} promoted programs have played in their "
        f"first FBS season give {bump:.1f} of it back."
    )
    if getattr(calibration, "promotion_ceiling_team", ""):
        text += (
            " On top of that a ceiling: no promoted team is projected above "
            f"{calibration.promotion_ceiling_team}'s first FBS season in "
            f"{int(calibration.promotion_ceiling_season)}, the best any promoted "
            "program has had."
        )
    text += (
        f" That correction rests on {int(calibration.n_promoted_teams)} programs, "
        "which is the part of it to hold lightly."
    )
    return _assert_sentence("schedule.promotion_note", text)


def _join(names: list[str]) -> str:
    """Oxford-comma join. No dashes, because these strings are front-door copy."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _note(row: dict[str, Any]) -> str | None:
    """One templated clause about this team. Never hand-written, per the contract.

    Names the single largest offseason term - the one thing this projection says
    about a team that carrying last season's rating forward would not have said.
    Teams whose projection is pure mean reversion get no clause rather than a
    manufactured one.
    """
    candidates = {
        "Returning production": row.get("contrib_returning_production") or 0.0,
        "A new head coach": row.get("contrib_coaching_change") or 0.0,
        "Net portal flow": row.get("contrib_net_portal") or 0.0,
    }
    name, value = max(candidates.items(), key=lambda item: (abs(item[1]), item[0]))
    points = float(value)
    if abs(points) < 0.5:
        return None
    text = (
        f"{name} adds {points:.1f} points to the projection."
        if points > 0
        else f"{name} costs the projection {abs(points):.1f} points."
    )
    # The template carries no dash today and this is what keeps that true after
    # somebody rewrites it: these clauses are front-door visible copy too.
    return _assert_no_em_dash("row note", text)


def write(document: dict[str, Any], destination: Path) -> Path:
    """Write `<destination>/<season>/projection.json`. Returns the path."""
    target = Path(destination) / str(document["season"]) / "projection.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return target
