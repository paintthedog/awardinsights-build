"""
Refresh Award Insights' USAspending data: check, pull what's needed, trim, build, run every check, report.
© 2026 Award Insights. Never publishes: read build/refresh_report.md, then ./deploy.sh on the owner's go-ahead.

    python3 scripts/refresh.py check                 API checks only (minutes): newer archive? agencies we don't pull?
    python3 scripts/refresh.py run                   check, pull the two latest fiscal years, trim, swap, build, all checks, report
    python3 scripts/refresh.py run --all-years       re-pull every fiscal year (first refresh, or when the drift check flags old years)
    python3 scripts/refresh.py run --years 2023      also re-pull these years
    python3 scripts/refresh.py report                rebuild the report from the current build (no network, no pulls)

Folders (outside the repo, in the workspace above it): usaspending_archive/<archive date>/ holds the zips of each pull.
inputs/trimmed/ is replaced as a whole only after the new trim finishes; the previous set is kept in inputs/trimmed_prev/.

Checks and what they catch (see docs/SPEC.md, "Refresh"):
  archive     USAspending republishes the Award Data Archive monthly; a newer date means the current years need a pull
  coverage    agencies paying colleges (USAspending's higher-education recipient type) that we don't pull, above $10M
  reporting   per agency and type, records per month across ALL recipients (from the trim) against the same month a year
              earlier: an agency whose records collapse has stopped reporting, which is not the same as cutting funding
  changes     totals by agency and fiscal year against the previous build: corrections, cancellations, late reports
  drift       scripts/reconcile_usaspending.py: 20 institutions, live API against the archive files, year by year
  build       ./deploy.sh --dry-run (verify*.py), screen_herd.py, NSF crosswalk check, unmatched college ids
"""
import argparse, collections, datetime, glob, json, os, pathlib, re, shutil, subprocess, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent           # the repo
WORK = ROOT.parent                                              # the workspace: downloads live here, not in git
ARCH = WORK / "usaspending_archive"
IN = ROOT / "inputs"; TRIM = IN / "trimmed"; PREV = IN / "trimmed_prev"
REPORT = ROOT / "build" / "refresh_report.md"; STATUS = IN / "reporting_status.json"
API = "https://api.usaspending.gov/api/v2/"
sys.path.insert(0, str(ROOT / "scripts"))

def post(path, body, timeout=180):
    for i in range(4):
        try:
            req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except Exception as e:
            err = e
    raise SystemExit(f"USAspending API unreachable ({path}): {err}")

def pull_agencies():
    """the agency names usaspending_pull.py fetches"""
    src = (ROOT / "scripts" / "usaspending_pull.py").read_text()
    block = src[src.index("AGENCIES = ["):src.index("]", src.index("AGENCIES = ["))]
    return re.findall(r'"([^"]+)"', block)

def fy_now(d=None):
    d = d or datetime.date.today()
    return d.year + (1 if d.month >= 10 else 0)

# ---------------------------------------------------------------- checks against the live API
def check_archive():
    """latest Award Data Archive date (from one agency's listing) against the date of the files we built from"""
    r = post("bulk_download/list_monthly_files/", {"agency": "all", "fiscal_year": fy_now() - 1, "type": "assistance"})
    dates = sorted({m.group(1) for f in r.get("monthly_files", []) if (m := re.search(r"_Full_(\d{8})", f["file_name"]))})
    have = sorted({m.group(1) for f in TRIM.glob("*.csv.gz") if (m := re.search(r"_Full_(\d{8})", f.name))})
    return {"latest": dates[-1] if dates else None, "have": have}

def check_coverage(years=4, floor=10e6):
    """agencies paying higher-education recipients over the last full fiscal years that usaspending_pull.py doesn't fetch"""
    end = fy_now() - 1
    F = {"time_period": [{"start_date": f"{end - years}-10-01", "end_date": f"{end}-09-30"}], "recipient_type_names": ["higher_education"],
         "award_type_codes": ["04", "05", "A", "B", "C", "D"]}
    r = post("search/spending_by_category/awarding_agency/", {"filters": F, "limit": 100, "page": 1})
    ours = {n.lower() for n in pull_agencies()}
    miss = [(x["amount"], x.get("name") or "?") for x in r["results"] if (x.get("name") or "").lower() not in ours and (x["amount"] or 0) >= floor]
    return {"window": f"FY{end - years + 1}–{end}", "missing": sorted(miss, reverse=True)}

# ---------------------------------------------------------------- reporting status from the trim's month counts
def reporting_status(months, asof):
    """per agency code and type: months (in the last 12 settled ones) whose record count fell below a quarter of the same
    month a year earlier (which had 50+); 'since' = the first month of the unbroken run of such months up to the latest"""
    cnt = collections.defaultdict(collections.Counter)
    for stem, m in months.items():
        k = re.match(r"FY\d{4}_(\w+?)_(Assistance|Contracts)_", stem)
        if k:
            for mon, n in m.items(): cnt[(k.group(1), k.group(2))][mon] += n
    last = (datetime.date.fromisoformat(asof).replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")   # latest whole month
    ms = []; d = datetime.date.fromisoformat(last + "-01")
    for _ in range(12): ms.append(d.strftime("%Y-%m")); d = (d - datetime.timedelta(days=1)).replace(day=1)
    ms.reverse()
    out = {}
    for (code, typ), c in cnt.items():
        prev = lambda m: f"{int(m[:4]) - 1}{m[4:]}"
        thin = [m for m in ms if c[prev(m)] >= 50 and c[m] < 0.25 * c[prev(m)]]
        run = []
        for m in reversed(ms):
            if m in thin: run.insert(0, m)
            elif c[prev(m)] >= 50: break
        if run: out[f"{code}:{typ}"] = {"since": run[0], "months": {m: [c[m], c[prev(m)]] for m in run}}
    return out

# ---------------------------------------------------------------- pull, trim, swap
def run(cmd, **kw):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, **kw)

def pull(date, years):
    dest = ARCH / date; dest.mkdir(parents=True, exist_ok=True)
    for i in range(3):   # the pull script resumes; rerun it until nothing is left
        run([sys.executable, str(ROOT / "scripts" / "usaspending_pull.py"), "--out", str(dest), "--years", *map(str, years)], cwd=WORK)
        if not list(dest.glob("*.part")): break
    return dest

def trim_and_swap(dest, years):
    stage = IN / f"trimmed_{dest.name}"
    run([sys.executable, str(ROOT / "scripts" / "usaspending_trim.py"), "--src", str(dest), "--out", str(stage),
         "--known", str(IN / "ai-1-core" / "crosswalk" / "known_ueis.txt")], check=True)
    key = lambda n: re.match(r"(FY\d{4}_\w+?_(?:Assistance|Contracts))_", n).group(1)
    fresh = {key(f.name) for f in stage.glob("*.csv.gz")}
    # carry over files for fiscal years this refresh didn't pull (and their month counts)
    months = json.load(open(stage / "_months.json")) if (stage / "_months.json").exists() else {}
    old = json.load(open(TRIM / "_months.json")) if (TRIM / "_months.json").exists() else {}
    for f in TRIM.glob("*.csv.gz"):
        if key(f.name) not in fresh: shutil.copy2(f, stage / f.name)
    for stem, m in old.items():
        if key(stem) not in fresh: months[stem] = m
    json.dump(months, open(stage / "_months.json", "w"), indent=0)
    if PREV.exists(): shutil.rmtree(PREV)
    if TRIM.exists(): TRIM.rename(PREV)
    stage.rename(TRIM)
    print(f"inputs/trimmed: {len(fresh)} files refreshed, {len(list(TRIM.glob('*.csv.gz'))) - len(fresh)} carried over; previous set in inputs/trimmed_prev/")

# ---------------------------------------------------------------- changes against the previous build
def totals(agg):
    ag = {i: a[1] for i, a in enumerate(agg["ag"])}; sub_ag = {i: s[0] for i, s in enumerate(agg["sub"])}
    T = collections.defaultdict(lambda: [0.0] * 5); E = collections.Counter()
    for e, rows in agg["rows"].items():
        for r in rows:
            if r[2] >= 2: continue
            a = ag[sub_ag[r[0]]]
            for i in range(5): T[a][i] += r[4 + i]
            E[e] += sum(r[4:9])
    return T, E

def changes(prev, cur):
    if not prev: return ["(no previous build to compare)"]
    yrs = cur["meta"]["years"]; Tp, Ep = totals(prev); Tc, Ec = totals(cur)
    L = ["| Agency | " + " | ".join(f"FY{y % 100}" for y in yrs) + " |", "|---|" + "---|" * len(yrs)]
    for a in sorted(set(Tp) | set(Tc), key=lambda a: -sum(Tc.get(a, [0])) ):
        p, c = Tp.get(a, [0] * 5), Tc.get(a, [0] * 5)
        cell = lambda i: "—" if abs(c[i] - p[i]) < 0.5e6 else f"{(c[i] - p[i]) / 1e6:+,.0f}M" + (f" ({(c[i] - p[i]) / p[i]:+.0%})" if p[i] > 1e6 else "")
        if any(abs(c[i] - p[i]) >= 0.5e6 for i in range(5)): L.append(f"| {a} | " + " | ".join(cell(i) for i in range(5)) + " |")
    names = {d["u"]: d["n"] for d in json.load(open(ROOT / "inputs" / "nsf" / "universe3.json"))}
    names.update({e: v.get("n", e) for e, v in cur.get("ent", {}).items() if isinstance(v, dict)})
    big = sorted(((Ec[e] - Ep[e], e) for e in set(Ec) | set(Ep)), key=lambda x: -abs(x[0]))[:15]
    L += ["", "Largest changes by institution (FY totals counted on the site, all years):", ""]
    L += [f"- {names.get(e, e)}: {d / 1e6:+,.1f}M (now {Ec[e] / 1e6:,.1f}M)" for d, e in big if abs(d) >= 1e6]
    return L

# ---------------------------------------------------------------- report
def report(chk, status, steps, prev_agg):
    cur = json.load(open(ROOT / "build" / "site" / "federal" / "data" / "agg.json"))
    br = json.load(open(ROOT / "build" / "site" / "federal" / "data" / "build_report.json"))
    L = [f"# Refresh report, {datetime.date.today()}", "",
         f"Archive files dated {cur['meta'].get('archive')}; data through {cur['meta'].get('asof')}; {cur['meta'].get('n_agencies')} agencies with money here.", ""]
    L += ["## Steps", ""] + [f"- {'OK' if ok else '**FAILED**'}: {s}" for s, ok in steps] + [""]
    if chk:
        a = chk.get("archive", {}); L += ["## Archive", "", f"Latest on USAspending: {a.get('latest')}; built from: {', '.join(a.get('have', [])) or '—'}", ""]
        c = chk.get("coverage", {}); L += ["## Agencies paying colleges that we don't pull", "", f"{c.get('window')}, higher-education recipients, project grants, cooperative agreements and contracts, $10M+:", ""]
        L += [f"- {n}: ${v / 1e6:,.1f}M" for v, n in c.get("missing", [])] or ["- none"]
        L += [""]
    L += ["## Reporting status (records per month, all recipients, against a year earlier)", ""]
    L += [f"- {k}: thin since {v['since']} ({', '.join(f'{m}: {n} vs {p}' for m, (n, p) in v['months'].items())})" for k, v in sorted(status.items())] or ["- every agency reporting normally"]
    L += ["", "## Changes against the previous build (counted dollars)", ""] + changes(prev_agg, cur)
    un = br.get("unmatched_higher_ed") or []
    L += ["", "## College recipients not in the crosswalk (add to known_ueis/crosswalk)", ""]
    L += [f"- {x}" for x in (un[:20] if isinstance(un, list) else list(un.items())[:20])] or ["- none"]
    L += ["", "Next: read this, look at the site (build/site), then ./deploy.sh only on the owner's go-ahead. Commit inputs/MANIFEST.json and inputs/reporting_status.json."]
    REPORT.parent.mkdir(exist_ok=True); REPORT.write_text("\n".join(L) + "\n")
    print(f"\nreport: {REPORT.relative_to(ROOT)}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("what", choices=["check", "run", "report"])
    ap.add_argument("--all-years", action="store_true"); ap.add_argument("--years", type=int, nargs="*", default=[])
    ap.add_argument("--no-reconcile", action="store_true", help="skip the live-API drift check (slow)")
    A = ap.parse_args()
    chk = {}
    if A.what in ("check", "run"):
        chk["archive"] = check_archive(); print("archive:", chk["archive"])
        chk["coverage"] = check_coverage(); print("agencies not pulled ($10M+):", [n for v, n in chk["coverage"]["missing"]] or "none")
        if A.what == "check": return
    steps = []; prev_agg = None
    pa = ROOT / "build" / "site" / "federal" / "data" / "agg.json"
    if pa.exists(): prev_agg = json.load(open(pa))
    if A.what == "run":
        date = chk["archive"]["latest"]
        if not date: raise SystemExit("no archive date from USAspending")
        years = list(range(2022, fy_now() + 1)) if A.all_years else sorted({fy_now() - 1, fy_now() - 2, *A.years} | ({fy_now()} if fy_now() <= 2026 else set()))
        years = [y for y in years if 2022 <= y <= 2026]          # the site's five-year window (FY2022-26)
        print("pulling", date, "fiscal years", years)
        dest = pull(date, years); steps.append((f"pull {date} FY{years}", not list(dest.glob('*.part'))))
        trim_and_swap(dest, years); steps.append(("trim and swap inputs/trimmed", True))
        steps.append(("manifest", run([sys.executable, str(ROOT / "scripts" / "manifest.py")], cwd=ROOT).returncode == 0))
    months = json.load(open(TRIM / "_months.json")) if (TRIM / "_months.json").exists() else {}
    if A.what == "run":
        steps.append(("build + data checks (deploy.sh --dry-run)", run(["./deploy.sh", "--dry-run"], cwd=ROOT).returncode == 0))
        steps.append(("HERD screen", run([sys.executable, str(ROOT / "scripts" / "screen_herd.py")], cwd=ROOT).returncode == 0))
        if not A.no_reconcile:
            steps.append(("live-API drift check (build/reconcile.md)", run([sys.executable, str(ROOT / "scripts" / "reconcile_usaspending.py")], cwd=ROOT,
                                                                          env={**os.environ, "FAI_INPUTS": str(IN)}).returncode == 0))
    asof = json.load(open(pa))["meta"]["asof"] if pa.exists() else datetime.date.today().isoformat()
    status = reporting_status(months, asof) if months else {}
    json.dump({"_c": "© 2026 Award Insights", "asof": asof, "agencies": status}, open(STATUS, "w"), indent=1)
    report(chk, status, steps, prev_agg if A.what == "run" else None)

if __name__ == "__main__":
    main()
