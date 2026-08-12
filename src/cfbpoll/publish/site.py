"""Build the zero-account static site from out/.

Specified by report 03 §7.1 and §7.2. The implementation lives in site/build.py;
this module is the CLI-facing wrapper so that `cfbpoll site build` and
`make site` are the same code path.

WHY THIS EXISTS AT ALL: a fork that requires a Vercel account, a Neon account and
a custom domain before showing a single ranking is not really forkable.
`make site` must produce a directory of HTML+JSON that opens with
`python -m http.server`.

WHAT THE SITE MUST NOT DO (report 03 §7.2):
  - never fit a model on request. Every rendered number is a SELECT or a file read
  - never render a poll whose run_id has status <> 'published'
  - always show published_at, git_sha and the model constants on screen. beta_w
    in particular belongs in a permanent footer, not a buried methodology page
  - always label weeks before headline_start_week as PROVISIONAL, not "the poll"

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from pathlib import Path


def build(src: Path, dest: Path) -> None:
    """Render the static site from published artifacts."""
    raise NotImplementedError("publish.site.build - scaffold; see report 03 §7.1")
