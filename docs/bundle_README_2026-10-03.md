# Award Insights — project bundle (13 Oct 2026)

Everything needed to build the Federal Award Insights tool and rebuild the three existing tools, without this conversation's history. Read this first.

## What exists today (live on GitHub Pages at awardinsights.org, repo paintthedog/awardinsights)

| Tool | Template | Data | Build |
|---|---|---|---|
| NSF Award Insights | templates/tpl.html | nsf/universe3.json, nsf/awards4.json, nsf/proginfo.json, nsf/coverage.json | scripts/build_ai.py |
| Research Activity Designations | templates/dash_tpl.html | nsf/rad5.json, nsf/climbers3.json | (placeholders `__RAD__`, `__CLIMB__`) |
| Research Portfolio Trends | templates/prof_tpl.html | nsf/profile4.json | (placeholders `__PROF__`, `__NPROF__`) |
| Landing page | templates/landing.html | — | — |

Templates use `__PLACEHOLDER__` injection; build scripts are one-liners that `.replace()` JSON text in. Artifact URLs: NSF `WNgBeApfZvSwGdbT7Mq5f2`, Designations `LaKb1ema14Y2QmDcPst5gn`, Portfolio `DqS5jUrpukrnWNnEgEQpGm`, Landing `3fq7BGuVu7zmoCHrXCEubo`.

Design system (shared by all templates): ground #f1efe8, accent teal #0f6f7c, tier ramp --t1/--t2/--t3, categorical --c1..--c8, highlight --you #e2611f. Fonts: Young Serif for headings (single weight), Readex Pro for everything else; figures regular weight with tabular-nums, bold only for totals. Language rule: describe the data position, never characterize the institution ("peers hold X; this institution does not" — never "wins/loses"). Ranks: competition rank among institution + peers, "T-" for ties, no rank when the institution's value is $0 or the peer group has fewer than 4 members.

## The job: Federal Award Insights

A new site modeled on NSF Award Insights (same two modes, same cards), where **agency** is the top-level dimension (as directorate is for NSF) and sub-agency / program (CFDA) sit below it. If it is better than NSF Award Insights it replaces it and NSF becomes a filter inside it.

### Universe
Every **public or private nonprofit** IPEDS institution with federal money (Carnegie-classified or not), plus non-IPEDS entities typed as institute / foreign / system office. Private for-profits are typed in the crosswalk but **excluded**. Hospitals are excluded (HERD does not count them). Carnegie peers / HERD figures exist only for the 3,282-institution Carnegie universe (nsf/universe3.json); other entities show "no peer data".

### Dollars
USAspending **obligations in the fiscal year they occur** (includes continuing payments on awards made before FY2022 — this is deliberate; it is the money actually flowing). Assistance (grants, cooperative agreements) and **contracts** (once the contract files arrive) shown as a split everywhere; the grants→contracts shift is a thing the tool should make visible. FFRDC / UARC management contracts (JPL→Caltech, Lincoln Lab→MIT, APL→JHU, DOE labs) must be excluded — identify by recipient and by the FFRDC flags in contract records. Carry a **competitive** flag: assistance_type project grant (B) / cooperative agreement (B) = competitive; formula (A), block (A), direct payment (C) = not. FY2026 is partial for all agencies (files dated 6 Sept 2026); DOD FY2026 is especially thin.

### Data (NOT in this zip — on Clinton's laptop in the `trimmed` folder; upload to the build conversation)
210 USAspending Award Data Archive files, FY2022–26, **21 agencies**, assistance + contracts, each trimmed to rows whose recipient UEI is in the crosswalk or is flagged higher-ed. Agencies by Treasury code: NSF 049, HHS 075, DOD 097, DOE 089, NASA 080, USDA 012, Commerce 013, Interior 014, Justice 015, State 019, VA 036, EPA 068, DOT 069, DHS 070, USAID 072, HUD 086, Education 091, Labor 1601, NEA 417, NEH 418, IMLS 474. Campus dollars FY22–26 after the crosswalk: first six ≈ $217B assistance + $18B contracts (FFRDCs out); the other 15 ≈ $19B, led by Commerce $6.2B, Interior $3.0B, DOT $1.7B, Justice $1.3B, USAID $1.1B, EPA $1.0B.

**Title IV student aid (Education)** — CFDA 84.063 Pell, 84.268 Direct Loans, 84.033 FWS, 84.007 FSEOG, 84.379 TEACH, 84.038, 84.032, 84.408 — is $104B to campuses and is **out of scope by default**: flag it `title4` and exclude it from every default view (it follows students, not competition). Its separate financial-aid UEIs are deliberately not crosswalked. Education's remaining $15.5B (Title III/V 84.031, TRIO 84.042/044/047/066/217, FIPSE 84.116, GEAR UP 84.334, IES 84.305/324) stays in, with the competitive flag per CFDA.


**Trim v2 (13 Oct, user decision): formula funding is out of scope.** The trimmed assistance files contain only competitive award types — assistance_type_code 04 (project grant) and 05 (cooperative agreement). Formula and block grants (incl. USDA Hatch/Smith-Lever/McIntire-Stennis capacity funds), direct payments, loans and insurance are dropped at trim time, as is Education Title IV. Files carry 29 columns (assistance) / the contract equivalents; `prime_award_base_transaction_description` is capped at 400 characters (NSF abstracts are truncated — full text via the award link or NSF's own files). Any campus totals quoted above that predate this rule include formula money and will come out lower in the build; the build should report the new totals rather than reconcile to the old ones.

### Other files in this bundle
- `contracts/` — USAspending **contract** transactions, FY2022–26, six agencies, trimmed to higher-ed / known-UEI rows (`FY*_<code>_Contracts_*trim*.csv.gz`). Columns include contract key, PIID, obligation, FY, sub-agency, recipient UEI/name, description, PSC/NAICS, extent competed, award type. **Apply `crosswalk/ffrdc_exclusions.json`**: contracts on those UEIs or PIIDs, or whose description names an FFRDC / M&O contract, are lab-management money and excluded ($53.6B: UT-Battelle/ORNL, JPL, LBNL, Lincoln Lab, Argonne, APL, SLAC, PPPL, SEI, Ames). UARCs (GTRI, Penn State ARL, ARL:UT, APL-UW, UH ARL, USC ICT, Stevens SERC) and university labs (Dayton UDRI, Rochester LLE) are **kept** — HERD counts them. The USAspending FFRDC flag column is empty; do not rely on it. After exclusion, university contracts are ~$3.7B/yr (DOD ~$2B, HHS ~$0.7B, NASA ~$0.4B; DOE and NSF ≈ 0) versus ~$45B/yr assistance.
- `assistance/` — one trimmed gzip CSV per USAspending Award Data Archive file (agency × FY), FY2022–26, six agencies (NSF 049, HHS 075, DOD 097, DOE 089, NASA 080, USDA 012), rows limited to UEIs typed in the crosswalk (i.e. not excluded). Columns: award key, FAIN, obligation, action date/FY, agency/sub-agency/office, recipient UEI/name, assistance type, action type, CFDA number/title, award description, period of performance, place-of-performance ZIP/state. Dollars = `federal_action_obligation` summed per (award, FY).
- `crosswalk/crosswalk_uei_v2.json` — **the** UEI crosswalk. `{uei: {type, id, name, src, note}}`. type ∈ campus (id = IPEDS UNITID), system (id = S-<unitid or slug>), institute (I-…), foreign (F-…), other (X-… IPEDS institution outside the Carnegie universe), hospital (id null), exclude (id null). Spine = IPEDS HD2025 UEI column; hand decisions overlay for UEIs IPEDS lacks (affiliated research arms folded to the HERD reporting campus, institutes, foreign, hospitals). Rule for system offices (user's rule, 3 Oct): registrant name containing system / regents / board / central → the IPEDS system-office entity, unless HERD demonstrably reports the money under a campus (Hawaii ARL and UH land-grant → Manoa; Illinois/Southern/Arkansas State registrant names do not say system → campus). Otherwise: IPEDS system-office UNITID when the recipient name says system/board/central; otherwise the campus registration (Illinois→UIUC, Southern→Baton Rouge, Arkansas State→Jonesboro). Hawaii and UPR → system offices (user decision).
- `crosswalk/entities_v2.json` — the non-campus entities (544): name, city, state, IPEDS unitid where one exists, member UEIs.
- `crosswalk/*.xlsx`, `batch1_decisions.py` — the human review trail (three batches + v1→v2 change log). `nsf_era_crosswalk_v1.csv` is the original NSF-only crosswalk, superseded.
- `ipeds/hd2025.csv` — IPEDS directory 2025 (UNITID, name, address, sector, level, control, **UEIS**, system name). Use SECTOR for control (1,4,7 public; 2,5,8 private nonprofit; 3,6,9 for-profit; 0 administrative unit).
- `nsf/` — NSF Award Insights inputs. `awards4.json` rows: `[unitid, award FY, full intended value, division, [program codes], obligated to date, award id, title]`. `nsf_raw_rows.json` = all 51,636 NSF awards FY2022–26 with UEI (rebuild awards4 from it with crosswalk v2 — NC A&T, Missouri State, Nebraska and ~20 others were mis-assigned under v1). `universe3.json` = Carnegie universe with factors (t, hb, ct, alf, reg, sz, ep, hbcu, hsi, msi, lg, cce, wo, aau, aplu, md, herd, hby, ctype, loc, en).
- `herd/herd_ipeds_crosswalk.json` — HERD→IPEDS link/piece/combined/independent rules used by Portfolio and Designations.

### Known reconciliation
USAspending NSF obligations vs NSF's own award files: 90% of award-years match to the dollar; FY2023–25 totals within 1%; FY2026 gap is reporting lag. UEI agrees on 98% of shared awards. So USAspending is trustworthy at award level.

### Site architecture (decided)
Static, GitHub Pages. One aggregates file (institution × agency × sub-agency × FY × assistance/contracts, plus CFDA rollups; ~10–20 MB) loaded once; one small JSON per institution for the awards table (title, program, agency, FY, dollars, USAspending link `https://www.usaspending.gov/award/<assistance_award_unique_key>`), fetched on demand. CSV export, URL-hash state, peer list with remove, directorate→division style roll-up (agency→sub-agency), all as in tpl.html.

### Refresh routine
1. `scripts/usaspending_pull.py` (both assistance and contracts; skips files already present — needs a "newer version" check added)
2. `scripts/usaspending_trim.py` with `known_ueis.txt` (= keys of crosswalk v2) → `trimmed/`
3. Upload trimmed files; run the unmatched-higher-ed pass (business type contains "INSTITUTION OF HIGHER EDUCATION" but not the "OTHER THAN" nonprofit label); decide new UEIs; append to crosswalk v2
4. Rebuild aggregates + per-institution files; copy into repo; push.

### Pocketed
NSF abstract topic model (fit on 51,636 abstracts, labels drafted, not shipped); agency-site enrichment by FAIN (NIH ExPORTER first); award-text search index; amendment-based termination view; "paid so far" toggle for NSF.
