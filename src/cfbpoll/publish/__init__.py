"""Publication targets. Files are canonical; everything else is downstream.

Specified by report 03 §5.1 and §7.1.

    files.py     write out/ - the source of truth for every downstream surface
    release.py   attach out/ to an immutable GitHub Release (the canonical copy)
    postgres.py  load the SERVING SUBSET into Neon (a cache, never the truth)
    site.py      build the zero-account static site

Nothing renders a number that is not in a published artifact. That is what makes
every number on the page independently recomputable by a stranger, which is the
whole point.

STATUS: SCAFFOLD.
"""
