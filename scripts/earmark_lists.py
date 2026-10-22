"""
Find awards that look like earmarks but aren't tagged, for review at each refresh.   © 2026 Award Insights

    osascript -l JavaScript scripts/pdftext.js <FY2024_enacted_lhhs.pdf> <dir>/FY2024_enacted_lhhs.txt   (each enacted table)
    python3 -I scripts/earmark_lists.py <dir-of-table-text> .

Reads the enacted Community Project Funding / Congressionally Directed Spending tables and the trimmed files. A
candidate is an untagged award to the named institution, within 5% of the listed amount, first obligated within three
years of the act, from the right agency, whose title repeats at least three of the project's words or calls itself an
earmark. Writes earmark_candidates.json (git-ignored scratch). Confirmed ones go in inputs/ai-1-core/earmark_awards.json
by hand; name-only and amount-only matches are not enough (see docs/SPEC.md, earmarks).
"""
import csv, gzip, glob, json, re, sys, os, collections, datetime
csv.field_size_limit(sys.maxsize)
TXT, REPO = sys.argv[1], sys.argv[2]
cw = json.load(open(f"{REPO}/inputs/ai-1-core/crosswalk/crosswalk_uei_v2.json"))
ents = json.load(open(f"{REPO}/inputs/ai-1-core/crosswalk/entities_v2.json"))
U = {d["u"]: d for d in json.load(open(f"{REPO}/inputs/nsf/universe3.json"))}
EARMARK_CFDA = {"93.493", "11.617", "11.469", "11.071", "14.251", "17.289", "16.753", "43.014", "66.202", "10.730", "10.723", "10.741", "20.534", "12.599"}
EARMARK_FAIN = {"P116Z", "S215K"}
EARMARK_TEXT = re.compile(r"CONGRESSIONALLY (DIRECTED|IDENTIFIED|RECOMMENDED|MANDATED|DELEGATED)|COMMUNITY PROJECT (FUNDING|GRANT)|COMMUNITY SPECIAL PROJECT|DIRECTED SPENDING|\bEARMARK", re.I)
EARMARK_KEYS = {x["key"] for x in json.load(open(f"{REPO}/inputs/ai-1-core/earmark_awards.json"))["awards"]}
SUBAG = {"ag": {"012"}, "cjs": {"013", "015", "080", "049"}, "defense": {"097"}, "ew": {"089", "097"}, "fsgg": set(), "homeland": {"070"},
         "interior": {"014", "068"}, "lhhs": {"1601", "075", "091"}, "milcon": {"097", "036"}, "thud": {"069", "086"}}
FYSTART = {2022: "2021-10-01", 2023: "2022-10-01", 2024: "2023-10-01", 2026: "2025-10-01"}

# ---- institutions: names and states
def norm(s): return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s.upper().replace("&", " AND ").replace("’", "'").replace("'", "")).split())
ent_state = {}; names = collections.defaultdict(set)
for u, d in U.items(): ent_state[u] = d.get("s", ""); names[u].add(norm(d["n"]))
for e, d in ents.items(): ent_state.setdefault(e, d.get("state", "")); names[e].add(norm(d["name"]))
for u, v in cw.items():
    if v["type"] not in ("hospital", "exclude") and v.get("id"): names[v["id"]].add(norm(v["name"]))
# name forms: full name, and the part before a campus dash ("UNIVERSITY OF MARYLAND COLLEGE PARK" -> also "UNIVERSITY OF MARYLAND")
forms = collections.defaultdict(set)
for e, ns in names.items():
    for n in ns:
        if len(n) >= 12: forms[n].add(e)
NAMEKEYS = sorted(forms, key=len, reverse=True)

# ---- items: each amount in a table, with the text just before it (recipient and project come before the amount)
AMT = re.compile(r"\$?(\d{1,3}(?:,\d{3}){1,3})(?!\d)")
items = []
for f in sorted(glob.glob(f"{TXT}/FY20*_enacted_*.txt")):
    m = re.search(r"FY(\d{4})_enacted_([a-z_]+)", f); fy, sub = int(m.group(1)), m.group(2).split("_")[0]
    t = open(f).read().replace("-\n", "").replace("\n", " ")
    for a in AMT.finditer(t):
        v = int(a.group(1).replace(",", ""))
        if v < 10000: continue
        ctx = t[max(0, a.start() - 320):a.start()]
        if not re.search(r"UNIVERSIT|COLLEGE|INSTITUTE|SCHOOL OF|RESEARCH FOUNDATION", ctx.upper()): continue
        items.append({"fy": fy, "sub": sub, "amt": v, "ctx": ctx[-220:]})

def who(ctx):
    n = norm(ctx); st = set(re.findall(r"\b([A-Z]{2})\b", ctx))
    best = []
    for k in NAMEKEYS:
        if k in n:
            cand = [e for e in forms[k] if ent_state.get(e, "") in st] or (list(forms[k]) if len(forms[k]) == 1 else [])
            if cand: best.append((len(k), cand)); break
    return best[0][1] if best else []

# ---- Federal awards from the trimmed files: total per award, with the earmark rule applied
AW = {}
for f in glob.glob(f"{REPO}/inputs/trimmed/*.csv.gz"):
    con = "Contract" in f
    for r in csv.DictReader(gzip.open(f, "rt")):
        c = cw.get((r.get("recipient_uei") or "").strip())
        if not c or c["type"] in ("hospital", "exclude") or not c.get("id"): continue
        if not con and (r.get("assistance_type_code") or "").zfill(2) not in ("04", "05"): continue
        k = r.get("contract_award_unique_key") if con else r.get("assistance_award_unique_key")
        a = AW.get(k) or AW.setdefault(k, {"e": c["id"], "ag": r.get("awarding_agency_code"), "cfda": r.get("cfda_number") or "", "fain": (r.get("award_id_fain") or "")[:5], "fainfull": r.get("award_id_fain") or "",
                                          "first": "9", "amt": 0.0, "desc": (r.get("prime_award_base_transaction_description") or "")[:120], "em": False})
        a["amt"] += float(r.get("federal_action_obligation") or 0); a["first"] = min(a["first"], r.get("action_date") or "9")
        if not con and (a["cfda"] in EARMARK_CFDA or a["fain"] in EARMARK_FAIN or a["fainfull"].startswith("DECR") or k in EARMARK_KEYS or EARMARK_TEXT.search(r.get("prime_award_base_transaction_description") or "")): a["em"] = True
by_e = collections.defaultdict(list)
for k, a in AW.items(): by_e[a["e"]].append((k, a))

# ---- candidates
STOP=set("THE OF AND FOR TO IN A AN ON AT BY WITH FROM INC UNIVERSITY COLLEGE CENTER INSTITUTE PROGRAM PROGRAMS PROJECT PROJECTS FACILITIES FACILITY EQUIPMENT PURCHASE INCLUDING STATE SCHOOL RESEARCH TRAINING SERVICES DEVELOPMENT NEW EXPANSION SUPPORT HEALTH CARE MEDICAL WORKFORCE EDUCATION RELATED".split())
toks=lambda s: {w for w in norm(s).split() if len(w)>3 and w not in STOP and not w.isdigit()}
NEWTEXT=EARMARK_TEXT
cand=[]; seen=set()
for it in items:
    es=who(it["ctx"])
    if not es: continue
    lo=FYSTART[it["fy"]]; hi=(datetime.date.fromisoformat(lo)+datetime.timedelta(days=1100)).isoformat()
    proj=toks(it["ctx"][-170:])
    for e in es:
        for k,a in by_e.get(e,[]):
            if a["em"] or k in seen or not (lo<=a["first"]<=hi): continue
            if SUBAG.get(it["sub"]) and a["ag"] not in SUBAG[it["sub"]]: continue
            r=a["amt"]/it["amt"]
            if not 0.95<=r<=1.02: continue
            ov=proj & toks(a["desc"]); ex=bool(NEWTEXT.search(a["desc"]))
            if len(ov)>=3 or ex: seen.add(k); cand.append({"key":k,"e":e,"amt":round(a["amt"]),"fy":it["fy"],"sub":it["sub"],"cfda":a["cfda"],"why":"wording says earmark" if ex else "title matches project: "+" ".join(sorted(ov)[:6]),"award":a["desc"][:110],"table":it["ctx"][-150:]})
cand.sort(key=lambda c:-c["amt"])
json.dump(cand, open("earmark_candidates.json","w"), indent=1)
print(len(cand),"candidates", f"${sum(c['amt'] for c in cand)/1e6:,.1f}M")
for c in cand: print(f"  ${c['amt']/1e6:6.2f}M {c['e']:9} {c['cfda']:7} {c['why'][:48]:48} | {c['award'][:58]}")
