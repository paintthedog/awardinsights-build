"""
Reconcile Federal Award Insights with USAspending's live API, for a sample of institutions.   © 2026 Award Insights

    FAI_INPUTS=inputs FAI_SITE=build/site/federal python3 scripts/reconcile_usaspending.py [--out build/reconcile.md]

Two steps for each institution (all of its recipient ids from crosswalk v2), FY2022-26, the 21 agencies in the tool:
  1. SOURCE: USAspending's own total (api.usaspending.gov, spending_by_category/recipient) against the same total from our
     archive files in inputs/trimmed/ -- project grants and cooperative agreements (04/05) and contracts (A-D) separately.
     Checks that the archive download and the trim kept everything. Small gaps in recent years are expected: the live API
     picks up late reports after the archive date (2026-09-06).
  2. BRIDGE: from those archive totals to the figure on the site, rule by rule (formula programs and student-loan funds
     dropped, federal labs dropped, earmarks shown apart, pullbacks of pre-FY2022 money), leaving an unexplained remainder
     that should be ~$0.
Needs network access to api.usaspending.gov. Prints a table and writes a Markdown report; exit code 1 if any
institution's source gap or unexplained remainder is over the tolerance.
"""
import argparse, collections, csv, gzip, glob, json, os, re, sys, time, urllib.request
csv.field_size_limit(10**9)
D = os.environ.get("FAI_INPUTS", "inputs"); SITE = os.environ.get("FAI_SITE", "build/site/federal")
ap = argparse.ArgumentParser(); ap.add_argument("--out", default="build/reconcile.md"); ap.add_argument("--tol", type=float, default=0.02)
A = ap.parse_args()

AGENCIES = ["National Science Foundation", "Department of Health and Human Services", "Department of Defense", "Department of Energy",
            "National Aeronautics and Space Administration", "Department of Agriculture", "Department of Commerce", "Department of the Interior",
            "Department of Education", "Environmental Protection Agency", "Department of Transportation", "Department of Homeland Security",
            "Department of Justice", "Department of Veterans Affairs", "Department of State", "Agency for International Development",
            "Department of Labor", "Department of Housing and Urban Development", "National Endowment for the Humanities",
            "National Endowment for the Arts", "Institute of Museum and Library Services"]
AG_CODES = {"049", "075", "097", "089", "080", "012", "013", "014", "091", "068", "069", "070", "015", "036", "019", "072", "1601", "086", "418", "417", "474"}
YEARS = [2022, 2023, 2024, 2025, 2026]
END = "2026-09-06"                       # archive file date
FY = {y: (f"{y-1}-10-01", f"{y}-09-30" if y < 2026 else END) for y in YEARS}
# the same exclusion rules as build_fai.py (kept in step by hand; a difference shows up as an unexplained remainder)
FORMULA_CFDA = {"84.425"}; FORMULA_FAIN = {"P031B", "P031E", "P031K", "P031D", "P031P"}
STUDENT_LOAN = {"93.342", "93.364", "93.264"}; TITLE_IV = {"84.063", "84.268", "84.033", "84.007", "84.379", "84.038", "84.032", "84.408"}
EARMARK_CFDA = {"93.493", "11.617", "11.469", "11.071", "14.251", "17.289", "16.753", "43.014", "66.202", "10.730", "10.723", "10.741", "20.534", "12.599"}
EARMARK_FAIN = {"P116Z", "S215K"}
EARMARK_TEXT = re.compile(r"CONGRESSIONALLY (DIRECTED|IDENTIFIED|RECOMMENDED|MANDATED|DELEGATED)|COMMUNITY PROJECT (FUNDING|GRANT)|COMMUNITY SPECIAL PROJECT|DIRECTED SPENDING|\bEARMARK", re.I)
EARMARK_KEYS = {x["key"] for x in json.load(open(f"{D}/ai-1-core/earmark_awards.json"))["awards"]}
FFRDC_DESC = re.compile(r"\bFFRDC\b|FEDERALLY FUNDED RESEARCH AND DEVELOPMENT CENTER|\bM&O CONTRACT|"
                        r"MANAGEMENT AND OPERATIONS? OF (THE )?[A-Z .,&-]*(NATIONAL LAB|LABORATORY)", re.I)

cw = json.load(open(f"{D}/ai-1-core/crosswalk/crosswalk_uei_v2.json"))
ff = json.load(open(f"{D}/ai-1-core/crosswalk/ffrdc_exclusions.json"))
agg = json.load(open(f"{SITE}/data/agg.json"))
U = {d["u"]: d for d in json.load(open(f"{D}/nsf/universe3.json"))}
name = lambda e: (agg["ent"].get(e) or U.get(e) or {"n": e})["n"]

# ---- sample: fixed institutions of each kind, plus a few picked from the data
SAMPLE = ["214777", "170976", "166027", "243744", "228778", "215293", "221759", "187985",   # R1s (Harvard: hospitals)
          "131520", "199102", "175856", "100654",                                          # HBCUs
          "126818", "142115",                                                              # R2 / regional
          "S-190035", "S-124557", "I-WOODS-HOLE-OCEANOGRAPHIC-INSTITUTION"]               # system offices, institute
tot = {e: sum(sum(r[4:9]) for r in rows if r[2] != 2) for e, rows in agg["rows"].items()}   # site totals leave earmarks out
for kind, n in (("Associate's", 2), ("Baccalaureate", 1)):
    SAMPLE += [u for u, d in sorted(U.items(), key=lambda kv: -tot.get(kv[0], 0)) if d.get("ctype") == kind and tot.get(u, 0) > 0][:n]
SAMPLE = [e for e in SAMPLE if e in agg["rows"]]
UEIS = {e: sorted(u for u, v in cw.items() if v.get("id") == e and v["type"] not in ("hospital", "exclude")) for e in SAMPLE}

# ---- step 1a: USAspending's live totals
def api(ueis, codes, start, end):
    body = {"filters": {"recipient_search_text": ueis, "award_type_codes": codes, "time_period": [{"start_date": start, "end_date": end}],
                        "agencies": [{"type": "awarding", "tier": "toptier", "name": n} for n in AGENCIES]},
            "category": "recipient", "limit": 100}
    for attempt in range(5):
        try:
            req = urllib.request.Request("https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=120))
            return sum(x["amount"] or 0 for x in r.get("results", []) if (x.get("uei") or "") in ueis)
        except Exception as ex:
            print(f"   (API retry {attempt + 1}: {str(ex)[:80]})", flush=True); time.sleep(10 * (attempt + 1))
    return None
LIVE = collections.defaultdict(dict)
for e in SAMPLE:
    for kind, codes in (("A", ["04", "05"]), ("C", ["A", "B", "C", "D"])):
        LIVE[e][kind] = {y: api(UEIS[e], codes, *FY[y]) for y in YEARS}
        time.sleep(0.3)
    print(f"  live totals fetched: {name(e)[:50]}", flush=True)

# ---- step 1b + 2: archive totals and the bridge, straight from the trimmed files
who = {u: e for e, L in UEIS.items() for u in L}
RAW = collections.defaultdict(lambda: {"A": collections.Counter(), "C": collections.Counter()})
BR = collections.defaultdict(collections.Counter)            # e -> rule -> $
AW = collections.defaultdict(lambda: collections.defaultdict(float))
for f in glob.glob(f"{D}/trimmed/*.csv.gz"):
    con = "Contract" in f
    for r in csv.DictReader(gzip.open(f, "rt")):
        e = who.get((r.get("recipient_uei") or "").strip())
        if not e: continue
        fy = int(r.get("action_date_fiscal_year") or 0); ag = (r.get("awarding_agency_code") or "").strip()
        if fy not in YEARS or ag not in AG_CODES or (r.get("action_date") or "")[:10] > END: continue
        amt = float(r.get("federal_action_obligation") or 0)
        if con:
            k = r.get("contract_award_unique_key"); RAW[e]["C"][fy] += amt
            desc = r.get("prime_award_base_transaction_description") or ""
            if ff["ueis"].get((r.get("recipient_uei") or "").strip()) or r.get("award_id_piid") in ff["piids"] or r.get("parent_award_id_piid") in ff["piids"] or FFRDC_DESC.search(desc):
                BR[e]["federal labs (FFRDC) dropped"] += amt; continue
            AW[(e, k, 0)][fy] += amt
        else:
            if (r.get("assistance_type_code") or "").strip().zfill(2) not in ("04", "05"): continue
            RAW[e]["A"][fy] += amt
            c = (r.get("cfda_number") or "").strip(); fp = (r.get("award_id_fain") or "")[:5]
            if c in TITLE_IV or c in STUDENT_LOAN: BR[e]["student aid / loan funds dropped"] += amt; continue
            if c in FORMULA_CFDA or fp in FORMULA_FAIN: BR[e]["formula programs dropped"] += amt; continue
            em = c in EARMARK_CFDA or fp in EARMARK_FAIN or bool(EARMARK_TEXT.search(r.get("prime_award_base_transaction_description") or "")) or fp.startswith("DECR") or (r.get("assistance_award_unique_key") or "") in EARMARK_KEYS
            AW[(e, r.get("assistance_award_unique_key"), 2 if em else 1)][fy] += amt
for (e, k, em), fys in AW.items():
    kept = {}
    for fy in sorted(fys):
        kept[fy] = max(fys[fy], 0.0); need = -fys[fy]
        for p in sorted(kept, reverse=True):
            if need <= 0: break
            if p != fy: t = min(kept[p], need); kept[p] -= t; need -= t
    BR[e]["pullbacks of pre-FY2022 money not counted"] -= sum(kept.values()) - sum(fys.values())
    if em == 2: BR[e]["earmarks shown apart"] += sum(kept.values())

# ---- report
lines = ["# Reconciliation with USAspending (live API)", "",
         f"Archive files dated {END}; live API queried {time.strftime('%Y-%m-%d')}. 21 agencies; FY2022–26 through {END}.", "",
         "Source gap compares FY2022–25 only; FY2026 is still being updated after the archive date and is listed by year below.", "",
         "| Institution | Live API | Archive files | Source gap FY22–25 | On site | Bridge (rules) | Unexplained |", "|---|---|---|---|---|---|---|"]
bad = []
m = lambda v: f"${v/1e6:,.1f}M"
for e in SAMPLE:
    live = sum(v or 0 for k in "AC" for v in LIVE[e][k].values()); raw = sum(sum(RAW[e][k].values()) for k in "AC")
    site = tot.get(e, 0); bridge = sum(BR[e].values()); unexpl = raw - bridge - site
    # the source check judges settled years only; FY2026 keeps changing after the archive date (late reports, corrections)
    lv = sum(LIVE[e][k][y] or 0 for k in "AC" for y in YEARS[:-1]); rv = sum(RAW[e][k][y] for k in "AC" for y in YEARS[:-1])
    gap = (rv - lv) / lv if lv else 0
    flag = abs(gap) > A.tol or abs(unexpl) > max(1e4, A.tol * site)
    if flag: bad.append(e)
    lines.append(f"| {name(e)} | {m(live)} | {m(raw)} | {gap:+.1%} | {m(site)} | {m(bridge)} | {m(unexpl)}{' ⚠' if flag else ''} |")
    print(f"{name(e)[:42]:42} live {m(live):>10} archive {m(raw):>10} gap {gap:+6.1%} | site {m(site):>10} rules {m(bridge):>9} unexplained {m(unexpl):>8}{'  CHECK' if flag else ''}", flush=True)
lines += ["", "## Bridge detail and source gaps by year", ""]
for e in SAMPLE:
    lines.append(f"**{name(e)}** ({len(UEIS[e])} recipient ids)  ")
    for rule, v in sorted(BR[e].items(), key=lambda kv: -abs(kv[1])):
        if abs(v) >= 1: lines.append(f"- {rule}: {m(v)}")
    yr = [f"FY{str(y)[2:]} {((RAW[e]['A'][y] + RAW[e]['C'][y]) - ((LIVE[e]['A'][y] or 0) + (LIVE[e]['C'][y] or 0)))/1e6:+,.1f}M" for y in YEARS]
    lines.append(f"- archive minus live, by year: {' · '.join(yr)}")
    lines.append("")
os.makedirs(os.path.dirname(A.out) or ".", exist_ok=True); open(A.out, "w").write("\n".join(lines) + "\n")
print(f"\nreport: {A.out}; {len(bad)} of {len(SAMPLE)} institutions need a look")
sys.exit(1 if bad else 0)
