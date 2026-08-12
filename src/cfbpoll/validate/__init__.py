"""Validation gates. Both of them can halt a publication, and that is the point.

  data_quality.py - report 01 §5.5. On failure: halt, alert, PUBLISH NOTHING.
                    For a project whose value proposition is trustworthiness,
                    publishing a wrong poll costs far more than publishing late.
  leakage.py      - report 02 §3.10. Fails the build if a banned column reached a
                    model matrix. Constraint 1 is easy to violate by accident.

When this week fails validation, keep last week's published ranking on screen and
say so visibly (report 01 §5.2). Silence is the failure mode that kills weekly
publications; make silence itself the alert.

STATUS: SCAFFOLD.
"""
