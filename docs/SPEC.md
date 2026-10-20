# Award Insights — working spec

Living spec for awardinsights.org. Read this before changing anything; update it when a decision changes.
Last updated 2026-10-20.

## What the site is
A free, public, static site (GitHub Pages, custom domain awardinsights.org) showing where federal research money goes to U.S. higher-education institutions, alongside peer groups the user chooses. Four tools, being combined into one site:

| Tool | Path (now) | Source | Data |
|---|---|---|---|
| Landing page | `/index.html` | `legacy/landing/index.html` | — |
| NSF Award Insights | `/nsf.html` | `legacy/templates/tpl.html` | `inputs/nsf/{universe3,awards4,proginfo,coverage}.json` |
| Research Activity Designations | `/designations.html` | `legacy/templates/dash_tpl.html` | `inputs/nsf/{rad5,climbers3}.json` |
| Research Portfolio Trends | `/portfolio.html` | `legacy/templates/prof_tpl.html` | `inputs/nsf/profile4.json` |
| Federal Award Insights | `/federal/` | `page/head.html`, `page/body.html`, `scripts/build_fai.py` | USAspending trimmed files (`inputs/trimmed/`, not in git) |

Owner preferences: no personal name on the public site; footer reads "© 2026 Award Insights. All rights reserved." No LLC for now.

## Repositories and deploy
- `paintthedog/awardinsights-build` (private): all source. The single source of truth.
- `paintthedog/awardinsights` (public): output only. `deploy.sh` force-pushes one fresh commit to its `gh-pages` branch. Never edit it by hand.
- **Pending switch:** the live site is still served from `main` of the public repo (the old hand-uploaded pages). After the first `./deploy.sh`, set GitHub → Settings → Pages → Deploy from branch → `gh-pages` / root.
- `./deploy.sh --dry-run` builds everything into `build/site/` and runs all checks. `COMPARE_LIVE=<checkout of public repo>` also checks the four original pages byte for byte against live.
- Checks that stop a deploy: `scripts/verify.py` (Penn State 214777, Howard 131520, NC A&T 199102, New Mexico 187985 totals recomputed from raw files with the zero floor), `verify_cliff.py 214777`, `verify_ic.py 198419 "ALLERGY|NIAID"`.
- Work rule: one place edits at a time. Start a session by pulling; end it by pushing.

## Data rules (Federal Award Insights)
- Source: USAspending Award Data Archive, FY2022–26 assistance and contracts, 21 agencies (files dated 2026-09-06). Pull/trim with `scripts/usaspending_pull.py` / `usaspending_trim.py` on the Mac.
- Dollars are obligations per fiscal year (sum of each award's actions), not award values.
- Recipients: public and private nonprofit IPEDS institutions plus system offices, independent research institutes and foreign institutions as their own entities, via `inputs/ai-1-core/crosswalk/crosswalk_uei_v2.json`. For-profits (IPEDS sector 3/6/9) and hospitals are excluded. Peers, bands and ranks use the 3,282-institution Carnegie universe (`inputs/nsf/universe3.json`).
- Assistance: competitive project grants and cooperative agreements only (assistance types 04/05).
- Out of scope: formula/block grants, direct payments, loans, student aid — Education Title IV, HEERF (84.425), formula streams reported as project grants (FAIN P031B/E/K/D/P), and HRSA school-held student loan funds (93.342 HPSL/LDS, 93.364 Nursing Student Loans, 93.264 Nurse Faculty Loans; ~$215M).
- Earmarks (congressionally directed spending; identified by CFDA, FAIN series such as P116Z/S215K, or description) are listed and tagged but kept out of totals, ranks and peer comparisons.
- Contracts exclude FFRDC management-and-operating money (`ffrdc_exclusions.json` + description match); UARCs and university labs are kept, as HERD counts them.
- **Zero floor:** each award's fiscal years are summed with a running balance that cannot go below zero. Pullbacks of in-window money stay in the year they happened; returns of money obligated before FY2022 (~$3.3B, mostly closeouts) are not subtracted. Awards whose only window activity is returning older money are not listed. Last-52-week funding per award is floored at zero. Negative "new award" actions are not counted as new awards.
- Agency routing: NIH is its own agency, split by institute/center (from awarding office, CFDA fallback; Office of the Director bucket). CDC, HRSA, SAMHSA, CMS are their own agencies, split by program (CFDA) with contracts in one row. "HHS other" holds ACF, ACL, FDA, ASPR, AHRQ, IHS, OS. NSF splits by directorate.
- Latest view: rolling windows (13/26/52 weeks) ending on the latest action date, compared with the same weeks a year earlier. The latest 8 weeks are provisional (Defense contracts report up to 90 days late); the briefing uses the settled window that leaves them out.
- Current annual funding = obligations in the last 52 weeks. Scheduled end = period-of-performance end on the most recent action (exposure, not expected loss).
- Deobligations do not track the 2025 grant terminations; do not use them as a termination signal.

## Wording rules
Describe the data, never judge the institution: "Programs held by peers, not by X — a place to look, not a requirement"; "below/above", not "short/cushion"; no red/green verdict coloring. Peer comparisons are stated as medians.

## Design system
Young Serif for headings and headline numbers; Readex Pro for everything else (figures tabular). Ground #f1efe8, paper #fff, accent teal #0f6f7c, "this institution" orange #e2611f (`--you`; text uses #c2501a for contrast). Light and dark themes via tokens. Agencies and sub-agencies display by acronym with the full name on hover (`AGFULL`, `SUBNAME`/`SUBAB` in body.html); program rows under CDC/HRSA/SAMHSA/CMS show the Assistance Listing number with the title on hover.

Institution page order: header + KPIs → At a glance (briefing tiles: big number, one line, peer bar) → peer controls → Latest → Obligations by year → Scheduled to end → By agency and sub-agency → Programs (held by peers not here / held here by few peers / above the peer median / all held / earmarks) → Awards link. Every card can be minimized by clicking its title (remembered per browser).

## Protection
Data in separate files under `/federal/data/` (robots-disallowed), minified `app.js`, CSP `script-src 'self'`, build-time and browser-side text sanitizing, copyright string in page, script and every data file. The three original tools are still single-file pages with inline data (to be brought in line).

## Open items
1. **Combine the four tools** (agreed): shared masthead/tab bar and institution search; chosen institution and peers carry between tools; clean URLs `/federal/ /nsf/ /designations/ /portfolio/` with redirects from the old `.html` paths; then apply Federal's protection to the other three.
2. **Subawards:** pull running on the Mac (`scripts/usaspending_subaward_pull.py` — live API rejects empty `prime_award_types`, so it falls back to `["IDV_E"]`). Then trim, then build "received as subrecipient" and "passed through" lines, deduplicating amended reports. Recent years look thin (lag; likely FSRS→SAM.gov reporting change) — size it before showing FY2025–26 subaward trends.
3. Build order agreed earlier: programs going quiet that the institution holds + realism checks on peer-held programs; share over time by agency; contract gap list (defense sub-agencies peers contract with).
4. NSF tool: `awards4.json` should be rebuilt from `inputs/nsf-raw/nsf_raw_rows.json` with crosswalk v2 (NC A&T, Missouri State, Nebraska and ~20 others mis-assigned under v1). Upstream HERD builds (`legacy/archive/`) need raw HERD files not in this repo.
5. Owner tasks: fix the 13 flagged crosswalk entries; methods page; two-factor on GitHub and registrar; domain privacy; verify the domain in GitHub Pages.
6. Considered, not done: log/rescaled bars in the agency card; short hand-written titles for CDC/HRSA program rows; tap-to-see agency legend on phones; moving "Rank among peers" next to the peer controls.
