"""Operations: the machinery that decides whether the Sunday job runs at all.

Nothing in here fits a model, ranks a season or writes a poll. It answers two
questions that the pipeline itself cannot answer about itself:

  * `guard` — is this week already published, and is this trigger allowed to
    fire? Three independent clocks (n8n dispatch, GitHub `schedule:`, the VPS
    systemd timer) share one job, and the only thing keeping them from
    double-publishing is that all three ask this first (ADR 0002).
  * `preflight` — which verbs the weekly job calls are still stubs? The pipeline
    is a partial build, and a job that dies halfway through is a worse answer
    than a job that says up front exactly which four commands are missing.

Both are deliberately offline-first and cheap. `guard` spends at most one CFBD
call (`/calendar`), and only when it is asked to resolve the live week.
"""

from __future__ import annotations
