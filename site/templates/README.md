# site/templates/

HTML templates for the zero-account static site built by `site/build.py`
(research report 03 §7.1).

**Empty on purpose.** No templates exist yet — this is a scaffold.

Two rules the templates must satisfy when they are written, from report 03 §7.2:

1. Every page shows `published_at`, `git_sha`, and the model constants. `beta_w`
   (the win premium) belongs in a permanent footer, not a buried methodology
   page — it is the most contested number in the system and hiding it would be a
   transparency failure.
2. Any week before `headline_start_week` (5) renders as clearly-labelled
   **provisional** output, never as "the poll".

Templates must not fetch anything at runtime beyond the JSON files emitted
alongside them. The site is downstream of files in every branch.
