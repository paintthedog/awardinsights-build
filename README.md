# awardinsights-build (private)

Source for awardinsights.org: the landing page, Federal Award Insights, NSF Award Insights, Research Activity Designations and Research Portfolio Trends, served as one site at `/federal/ /nsf/ /designations/ /portfolio/`. Start with `docs/SPEC.md`. Keep this repository **private**: it holds the crosswalk, the build and the review trail.
Only the built site is published (see `deploy.sh`).

| Path | What |
|---|---|
| `scripts/usaspending_pull.py`, `usaspending_trim.py` | download and trim the USAspending Award Data Archive |
| `scripts/usaspending_subaward_pull.py`, `usaspending_subaward_trim.py` | request, download and trim first-tier subawards (received and passed through) |
| `scripts/build_fai.py` | trimmed files → site data (`--awards inst` writes one award file per institution) |
| `scripts/verify.py` | recomputes three institutions from the raw files; non-zero exit stops a deploy |
| `scripts/build_page.py` | assembles the page: minified `app.js`, Content-Security-Policy, copyright notices, robots.txt |
| `scripts/build_shell.py`, `site/` | one site: site bar, landing page, clean URLs + redirects, cross-tool search (`site/shared/site.js`) |
| `page/head.html`, `page/body.html` | Federal page source |
| `legacy/build_legacy.py` | builds the landing page and the three original tools (templates in `legacy/templates/`) |
| `legacy/archive/` | the original one-off build scripts, kept for reference (they expect raw HERD files not in this repo) |
| `inputs/nsf/` | built data for the original tools, plus the Carnegie universe |
| `inputs/nsf-raw/` | all NSF awards FY2022–26 with UEI, for rebuilding `awards4.json` |
| `inputs/subawards/` | trimmed subaward files (git-ignored) |
| `docs/` | the working spec and the original 3 Oct bundle README |
| `inputs/ai-1-core/` | crosswalk v2, FFRDC exclusions, IPEDS HD2025, HERD crosswalk |
| `inputs/nsf/universe3.json` | Carnegie universe with institutional factors |
| `inputs/trimmed/` | trimmed downloads (git-ignored) |

## Refresh
1. `python3 scripts/usaspending_pull.py` then `python3 scripts/usaspending_trim.py` (on the Mac, from the folder holding the downloads)
2. Copy the trimmed `*.csv.gz` into `inputs/trimmed/`
3. `./deploy.sh --dry-run`, look at `build/site/`, then `./deploy.sh`

## One-time setup
- `npm install`
- GitHub: Settings → Pages → Deploy from branch → `gh-pages` / root; keep the custom domain and "Enforce HTTPS" on.
- GitHub account and domain registrar: two-factor on. Pages settings: verify `awardinsights.org` as your domain.
- Domain registration: privacy on.

## Hardening already in the build
- Every text field from the data is stripped of markup characters at build time and again in the browser; codes (program numbers, states, ids) must match their formats.
- Public page: `script-src 'self'`, no inline script, fonts only from Google Fonts, `object-src 'none'`, `base-uri 'none'`.
- `© 2026 Award Insights` in the footer, page head, `app.js` and every data file (`_c`).
- `robots.txt` asks crawlers to skip `/federal/data/`.
