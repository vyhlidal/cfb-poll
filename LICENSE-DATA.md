# Data and output licensing

The **code** in this repository is MIT — see [LICENSE](./LICENSE). This file
covers the **data**: what we publish, what we republish, and what we deliberately
do not.

---

## 1. Our published ratings and rankings — CC BY 4.0

Everything this project computes and publishes — the weekly poll, the Résumé and
Power ratings, rank intervals, the retroactive grid, predictions, backtest metrics,
and the model-parameter records — is released under the
**[Creative Commons Attribution 4.0 International License (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)**.

You may share and adapt it, including commercially, for any purpose, provided you
give appropriate credit, link to the license, and indicate if changes were made.

Suggested attribution:

> Ratings from cfb-poll (https://github.com/vyhlidal/cfb-poll), CC BY 4.0.

We chose an attribution license over public domain for one reason: a ranking that
travels without its methodology is exactly the thing this project exists to
replace. The credit line is the pointer back to the math.

---

## 2. Upstream: SportsDataverse — MIT

The historical archive this project is built on comes from
**[`sportsdataverse/sportsdataverse-data`](https://github.com/sportsdataverse/sportsdataverse-data)**
(release tag `cfbfastR_cfb_pbp` and siblings), and the
**[`cfbfastR`](https://github.com/sportsdataverse/cfbfastR)** R package that
produces it. Both are MIT licensed, and that grant is what makes this project's
reproducibility claim possible: **we may republish their archive**, so a stranger
can recompute every ranking we have ever published without an API key, an account,
or anyone's permission.

The upstream notices, reproduced as MIT requires:

> MIT License. Copyright (c) 2023 SportsDataverse.

> MIT License. Copyright (c) 2021 cfbfastR authors.

Republished copies of their assets carry `LICENSE-MIT-sportsdataverse.txt`
alongside them in the release, unmodified.

**Two honest caveats, stated rather than glossed:**

1. The sibling repository `cfbfastR-data` carries **no license file at all**
   (GitHub reports `license: null`). We therefore prefer `sportsdataverse-data`
   release assets for anything we republish.
2. **MIT covers their compilation work, not an upstream rights transfer.** The
   underlying data originates from CollegeFootballData and ESPN. SportsDataverse
   can license their own compilation and code; they cannot transfer rights they do
   not hold. Our cleanest legal position is the correct one: scores, dates, sites
   and opponents are **facts** — uncopyrightable under *Feist v. Rural Telephone* —
   and our published output is model results, not a data feed.

---

## 3. Upstream: CollegeFootballData.com — attribution given, not required

Weekly in-season data comes from **[CollegeFootballData.com](https://collegefootballdata.com)**
(Rad Sports Analytics LLC), via a paid Patreon tier.

Their terms §5 says:

> "**While not required**, it is strongly encouraged that users credit
> CollegeFootballData.com as the data source when using the API in published
> products, academic papers, visualizations, or social media content."

**Attribution is not required. We give it anyway — in the README, on every
published poll, on the site, and in social posts.** It costs nothing, it is what
the maintainer asks, and supporting a solo maintainer whose work an entire field
is built on is simply the right thing to do.

### What we do NOT publish

CFBD terms §3 prohibits "reselling or redistributing data obtained from the API
without explicit permission." Accordingly:

- **Raw CFBD API responses are never published.** They live in a private archive.
  Not in this repository, not in a release asset, not on the site.
- **Derived ratings computed from that data are published**, which the terms
  permit — §5 explicitly contemplates published products and visualizations.
- Checksums and manifests of the private archive are published, so the existence
  and integrity of what we hold is auditable even though the bytes are not.

If we ever want to publish CFBD-sourced raw data, §3 gives the path: ask.

---

## 4. Disclaimer

This project has **no affiliation with the NCAA, its conferences, or any member
institution**, and none with CollegeFootballData.com or SportsDataverse beyond
being a user of their work. All data is unofficial. All ratings are provided
as-is, with no warranty of any kind, and are not offered as betting advice.
