# independent recompute of subawards received and passed through, by fiscal year, straight from the trimmed files
# (rules in docs/SPEC.md, open item 2): crosswalk on both sides; received only under programs in program_scope.json;
# passed through only under prime awards the Federal build counts (re-derived here from the prime files, earmarks aside);
# same amount on the same date once; each subaward floored at zero; no prime's subawards above its own value
# (contract vehicles exempt); same entity on both sides left out.  Non-zero exit stops a deploy.
import csv, gzip, glob, json, collections, re, os, sys
csv.field_size_limit(10**9)
D = os.environ.get("FAI_INPUTS", "inputs")
SITE = os.environ.get("FAI_SITE", "site")
YEARS = [2022, 2023, 2024, 2025, 2026]
targets = {"214777", "131520", "199102"}   # Penn State, Howard, NC A&T
cw = json.load(open(f"{D}/ai-1-core/crosswalk/crosswalk_uei_v2.json"))
ff = json.load(open(f"{D}/ai-1-core/crosswalk/ffrdc_exclusions.json"))
scope = json.load(open(f"{D}/ai-1-core/program_scope.json"))["programs"]
EARMARK_CFDA = {"93.493", "11.617", "11.469", "11.071", "14.251", "17.289", "16.753", "43.014", "66.202",
                "10.730", "10.723", "10.741", "20.534", "12.599"}
EARMARK_TEXT = re.compile(r"CONGRESSIONALLY (DIRECTED|IDENTIFIED|RECOMMENDED|MANDATED)|COMMUNITY PROJECT FUNDING|DIRECTED SPENDING", re.I)
def ent(u):
    c = cw.get((u or "").strip())
    return c["id"] if c and c["type"] not in ("hospital", "exclude") else None

# prime awards the Federal build counts for the targets (same filters as verify.py), and which of them are earmarks
inscope, earmark = set(), set()
for f in glob.glob(f"{D}/trimmed/*.csv.gz"):
    c = "Contract" in f
    for r in csv.DictReader(gzip.open(f, "rt")):
        if ent(r["recipient_uei"]) not in targets: continue
        if not 2022 <= int(r["action_date_fiscal_year"] or 0) <= 2026: continue
        if not c and r["assistance_type_code"] not in ("04", "05"): continue
        if not c and (r["cfda_number"] in ("84.425", "93.342", "93.364", "93.264") or re.match(r"P031[BEKDP]", r["award_id_fain"] or "")): continue
        if c and (r["award_id_piid"] in ff["piids"] or r.get("parent_award_id_piid") in ff["piids"]): continue
        k = r["contract_award_unique_key"] if c else r["assistance_award_unique_key"]
        inscope.add(k)
        if not c and (r["cfda_number"] in EARMARK_CFDA or (r["award_id_fain"] or "")[:5] in ("P116Z", "S215K")
                      or EARMARK_TEXT.search(r.get("prime_award_base_transaction_description") or "")): earmark.add(k)

# every subaward row once per (prime, subawardee, number, date, amount); per-subaward years; per-prime totals
seen = set(); SUB = collections.defaultdict(lambda: collections.defaultdict(float)); ROW = {}; PV = collections.defaultdict(float)
for f in glob.glob(f"{D}/subawards/*.csv.gz"):
    for r in csv.DictReader(gzip.open(f, "rt")):
        fy = int(r["subaward_action_date_fiscal_year"] or 0)
        if fy not in YEARS: continue
        try: a = float(r["subaward_amount"] or 0); pv = float(r["prime_award_amount"] or 0)
        except ValueError: continue
        k = (r["prime_award_unique_key"], r["subawardee_uei"].strip(), r["subaward_number"], r["subaward_action_date"][:10], round(a, 2))
        if k in seen: continue
        seen.add(k); SUB[k[:3]][fy] += a; PV[k[0]] = max(PV[k[0]], pv)
        n = (r["subaward_action_date"], r.get("subaward_sam_report_last_modified_date", ""), r.get("subaward_sam_report_id", ""))
        if k[:3] not in ROW or n > ROW[k[:3]][0]: ROW[k[:3]] = (n, r)   # classify by the most recent row
FLO = {}; PT = collections.defaultdict(float)
for sk, by in SUB.items():
    bal = 0.0; o = {}
    for fy in sorted(by): nb = max(bal + by[fy], 0.0); o[fy] = nb - bal; bal = nb
    FLO[sk] = o; PT[sk[0]] += sum(o.values())
def factor(pk):
    t = PT[pk]
    return 1.0 if t <= PV[pk] * 1.001 or t <= 0 or pk.startswith("CONT_IDV_") else PV[pk] / t

R = collections.defaultdict(lambda: [0.0] * 5); P = collections.defaultdict(lambda: [0.0] * 5)
for sk, by in FLO.items():
    r = ROW[sk][1]; se, pe = ent(sk[1]), ent(r["prime_awardee_uei"])
    if (se not in targets and pe not in targets) or (se and se == pe): continue
    f_ = factor(sk[0]); cn = (r.get("prime_award_cfda_numbers_and_titles") or "").split(";")[0].split(":")[0].strip()
    if se in targets:
        prog = scope.get(cn)
        if not (sk[0].startswith("ASST") and prog is not None and not prog["in"]) and cn not in EARMARK_CFDA:
            for fy, v in by.items(): R[se][YEARS.index(fy)] += v * f_
    if pe in targets and sk[0] in inscope and sk[0] not in earmark:
        for fy, v in by.items(): P[pe][YEARS.index(fy)] += v * f_

site = json.load(open(f"{SITE}/data/sub.json"))["e"]
fail = False
for t in sorted(targets):
    s = site.get(t, {"r": [0] * 5, "p": [0] * 5})
    for lab, raw, got in (("received", R[t], s["r"]), ("passed through", P[t], s["p"])):
        ok = all(abs(a - b) <= 2 for a, b in zip(raw, got)); fail |= not ok
        print(f"{t} {lab:14}: raw {[round(x / 1e6, 2) for x in raw]}M  site {[round(x / 1e6, 2) for x in got]}M  {'OK' if ok else 'MISMATCH'}")
sys.exit(1 if fail else 0)
