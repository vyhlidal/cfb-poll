"""Static site generator - the fork's front door.

Specified by report 03 §7.1. Reads out/ and writes site/_build: HTML plus the
JSON the pages fetch. No framework, no account, no build server. GitHub Pages
hosts it inside its published limits (1 GB site, 100 GB/month soft bandwidth) and
our site is a few MB.

Pages planned:
    index          the headline poll (L4 Resume) with L3 Power and the gap beside
                   it, plus 90% rank intervals on every row
    team/<id>      rating history, schedule, and the resume-vs-power decomposition
    retro          R(N,N) vs R(N,final) and the "biggest retroactive movers" view
    methodology    every constant, every week, with the config hash and git sha
    connectivity   weeks 1-4: graph diagnostics instead of a ranking

The challenge page's copy lives in the web app rather than here, and when it is
written it needs one more link than it currently plans for: `docs/learn/` is the
beginner path to the same command, seven modules from "what is a terminal" to a
scored challenger. `configs/challengers/README.md` already points at it, and that
page is what the challenge copy is a front door to.

Run as `cfbpoll site build --from out/ --to site/_build`, or `make site`.

STATUS: SCAFFOLD. Nothing is rendered yet.
"""

from __future__ import annotations

from pathlib import Path


def main(src: Path = Path("out"), dest: Path = Path("site/_build")) -> None:
    raise NotImplementedError("site.build.main - scaffold; see report 03 §7.1")


if __name__ == "__main__":  # pragma: no cover
    main()
