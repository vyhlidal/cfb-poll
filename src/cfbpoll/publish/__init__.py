"""Publication targets. Files are canonical; everything else is downstream.

Specified by report 03 §5.1 and §7.1.

    files.py     write out/ - the source of truth for every downstream surface
    release.py   attach out/ to an immutable GitHub Release (the canonical copy)
    serving.py   the ONE builder both publication targets are made from
    postgres.py  load the SERVING SUBSET into Neon (a cache, never the truth)
    fixtures.py  write the same documents as JSON, for the fork and for site dev
    cards.py     the weekly share card: SVG + PNG, generated marks only
    site.py      build the zero-account static site

Nothing renders a number that is not in a published artifact. That is what makes
every number on the page independently recomputable by a stranger, which is the
whole point. The share card obeys the same rule as the two web surfaces: every
figure on it is read out of the published documents, and it computes nothing -
not even the graph layout it draws.

STATUS: `serving`, `postgres`, `fixtures`, `cards`, `poll` and `files` are real.
`release.py` and `site.py` remain stubs.
"""
