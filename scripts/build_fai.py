"""
Federal Award Insights — build the site data from trimmed USAspending files.

Run:
  python3 build_fai.py --core <ai-1-core dir> --nsf <dir with universe3.json>
                       [--assistance <dir of *_trimmed.csv.gz>] [--contracts <dir>]
                       [--nsf-raw <nsf_raw_rows.json>] --out <site dir>

Writes into <out>:
  data/agg.json          institution x agency x sub-agency x FY x assistance/contracts, CFDA rollups, entity list
  data/aw/<NN>.json      awards for each entity, sharded 64 ways by entity id (fetched on demand)
  data/build_report.json totals, exclusions, unmatched UEIs (the reconciliation trail)

Rules (README, 13 Oct 2026):
  - dollars = federal_action_obligation summed per (award, fiscal year of the action)
  - assistance: keep assistance_type_code 04/05 only; drop Title IV CFDAs
  - contracts: drop FFRDC / M&O lab-management money (ffrdc_exclusions.json UEIs + PIIDs,
    plus descriptions that name M&O of a national laboratory or an FFRDC). UARCs are kept.
  - recipients: crosswalk v2 types campus / other / system / institute / foreign are kept;
    hospital and exclude are dropped; campus UNITIDs whose IPEDS sector is for-profit (3,6,9) are dropped.
  - if no NSF assistance file is present, NSF assistance falls back to NSF's own award rows
    (obligated to date, counted in the award's fiscal year), flagged as a stand-in.
"""
import argparse, csv, gzip, glob, json, os, re, sys, collections, hashlib, datetime
csv.field_size_limit(sys.maxsize)

YEARS = [2022, 2023, 2024, 2025, 2026]
COPY = "© 2026 Award Insights · awardinsights.org · analysis, crosswalk and compilation; underlying federal data is public"
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
def clean(t):
    """Text from the data can never carry markup: control characters dropped, markup characters swapped for look-alikes."""
    if not isinstance(t, str): return t
    return _CTRL.sub(" ", t).replace("<", "‹").replace(">", "›").replace('"', "”").replace("`", "'").strip()
def code(t, pat, default=""):
    """Fixed-format codes (program numbers, states, ids) must match their pattern exactly."""
    t = (t or "").strip()
    return t if re.fullmatch(pat, t) else default
ID_RE = r"[A-Za-z0-9][A-Za-z0-9-]{0,80}"
AGENCIES = {  # treasury code -> (short, name)
    "049": ("NSF", "National Science Foundation"), "075": ("HHS other", "HHS: other divisions"), "075N": ("NIH", "National Institutes of Health"),
    "075C": ("CDC", "Centers for Disease Control and Prevention"), "075H": ("HRSA", "Health Resources and Services Administration"),
    "075S": ("SAMHSA", "Substance Abuse and Mental Health Services Administration"), "075M": ("CMS", "Centers for Medicare & Medicaid Services"),
    "097": ("DOD", "Defense"), "089": ("DOE", "Energy"), "080": ("NASA", "NASA"),
    "012": ("USDA", "Agriculture"), "013": ("DOC", "Commerce"), "014": ("DOI", "Interior"),
    "015": ("DOJ", "Justice"), "019": ("State", "State"), "036": ("VA", "Veterans Affairs"),
    "068": ("EPA", "Environmental Protection Agency"), "069": ("DOT", "Transportation"),
    "070": ("DHS", "Homeland Security"), "072": ("USAID", "USAID"), "086": ("HUD", "Housing and Urban Development"),
    "091": ("ED", "Education"), "1601": ("DOL", "Labor"), "417": ("NEA", "National Endowment for the Arts"),
    "418": ("NEH", "National Endowment for the Humanities"), "474": ("IMLS", "Institute of Museum and Library Services"),
}
# Congressionally directed spending (earmarks): kept, tagged, shown apart from competitive totals.
EARMARK_CFDA = {"93.493", "11.617", "11.469", "11.071", "14.251", "17.289", "16.753", "43.014", "66.202",
                "10.730", "10.723", "10.741", "20.534", "12.599"}
EARMARK_FAIN = {"P116Z": "FIPSE Community Project Funding", "S215K": "ED elementary/secondary Community Project Funding"}
EARMARK_TEXT = re.compile(r"CONGRESSIONALLY (DIRECTED|IDENTIFIED|RECOMMENDED|MANDATED)|COMMUNITY PROJECT FUNDING|DIRECTED SPENDING", re.I)
# Formula / mandatory money coded as project grants: dropped (not winnable through a proposal).
FORMULA_FAIN = {"P031B": "Strengthening HBCUs (Title III Part B)", "P031E": "HBCU FUTURE Act mandatory",
                "P031K": "Strengthening Historically Black Graduate Institutions", "P031D": "Tribal Colleges Part F mandatory",
                "P031P": "Predominantly Black Institutions formula grants"}
FORMULA_CFDA = {"84.425": "HEERF pandemic relief"}
def fain_prefix(f):
    m = re.match(r"([A-Z]+\d{3}[A-Z])", f or "")
    return m.group(1) if m else ""
TITLE_IV = {"84.063", "84.268", "84.033", "84.007", "84.379", "84.038", "84.032", "84.408"}
# HRSA student loan capital (school-held revolving loan funds): student aid, out of scope like Title IV
STUDENT_LOAN = {"93.342": "Health Professions Student Loans / Loans for Disadvantaged Students", "93.364": "Nursing Student Loans", "93.264": "Nurse Faculty Loan Program"}
COMPETITIVE_ASSIST = {"04", "05"}
COMPETED_CONTRACT = {"FULL AND OPEN COMPETITION", "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES",
                     "COMPETED UNDER SAP", "COMPETITIVE DELIVERY ORDER"}
FFRDC_DESC = re.compile(r"\bFFRDC\b|FEDERALLY FUNDED RESEARCH AND DEVELOPMENT CENTER|\bM&O CONTRACT|"
                        r"MANAGEMENT AND OPERATIONS? OF (THE )?[A-Z .,&-]*(NATIONAL LAB|LABORATORY)", re.I)
NSF_DIR_CFDA = {"ENG": "47.041", "MPS": "47.049", "GEO": "47.050", "CSE": "47.070", "BIO": "47.074",
                "SBE": "47.075", "EDU": "47.076", "O/D": "47.083", "TIP": "47.084"}
NSF_DIR_NAME = {"ENG": "Engineering", "MPS": "Mathematical & Physical Sciences", "GEO": "Geosciences",
                "CSE": "Computer & Information Science & Engineering", "BIO": "Biological Sciences",
                "SBE": "Social, Behavioral & Economic Sciences", "EDU": "STEM Education", "O/D": "Office of the Director",
                "TIP": "Technology, Innovation & Partnerships"}
NSF_CFDA_TITLE = {"47.041": "Engineering", "47.049": "Mathematical and Physical Sciences", "47.050": "Geosciences",
                  "47.070": "Computer and Information Science and Engineering", "47.074": "Biological Sciences",
                  "47.075": "Social, Behavioral, and Economic Sciences", "47.076": "STEM Education",
                  "47.083": "Integrative Activities", "47.084": "Technology, Innovation and Partnerships",
                  "47.079": "International Science and Engineering", "47.078": "Polar Programs"}
SMALL = {"and", "of", "for", "the", "in", "on", "to", "a", "an", "or", "at", "by", "with", "from"}
UPPER = {"LLC", "STEM", "NIH", "NASA", "HIV", "AIDS", "USDA", "EPA", "NSF", "DOD", "II", "III", "IV", "TRIO", "GEAR", "UP", "K-12",
         "STTR", "SBIR", "USAID", "FIPSE", "IES", "NIFA", "NOAA", "NIST", "COVID-19", "EPSCOR", "MRI", "CAREER",
         "NIEHS", "NIOSH", "AHRQ", "SAMHSA", "HRSA", "CDC", "FDA", "DHS", "DARPA", "ONR", "AFOSR", "HBCU", "HBCUS", "MSI", "HSI",
         "BRAIN", "ARPA-H", "ARPA-E", "US", "U.S.", "NASA's", "STEM-C", "AI", "R&D", "NOFO", "EDA", "NIJ", "OVW", "BJA", "OJJDP", "FAA", "FHWA", "FTA", "NEH", "NEA", "IMLS", "PPHF", "STR", "HCOP", "ACA", "CMS", "MACRA", "PEPFAR", "SED", "CDC-RFA"}
# NIH is shown as its own agency; its institutes and centers are the sub-agencies.
# Grants name the IC in full in awarding_office_name ("NIH National Cancer Institute");
# contracts use acronyms ("NATIONAL INSTITUTES OF HEALTH NIAID").
NIH_ICS = [  # (display name, acronym, keyword in the full name) -- order matters for keyword fallbacks
    ("National Cancer Institute (NCI)", "NCI", "CANCER"),
    ("Allergy and Infectious Diseases (NIAID)", "NIAID", "ALLERGY"),
    ("Aging (NIA)", "NIA", "AGING"),
    ("General Medical Sciences (NIGMS)", "NIGMS", "GENERAL MEDICAL"),
    ("Heart, Lung, and Blood (NHLBI)", "NHLBI", "HEART"),
    ("Neurological Disorders and Stroke (NINDS)", "NINDS", "NEUROLOGICAL"),
    ("Diabetes, Digestive and Kidney Diseases (NIDDK)", "NIDDK", "DIABETES"),
    ("Environmental Health Sciences (NIEHS)", "NIEHS", "ENVIRO"),
    ("Mental Health (NIMH)", "NIMH", "MENTAL HEALTH"),
    ("Child Health and Human Development (NICHD)", "NICHD", "CHILD HEALTH"),
    ("Drug Abuse (NIDA)", "NIDA", "DRUG ABUSE"),
    ("Alcohol Abuse and Alcoholism (NIAAA)", "NIAAA", "ALCOHOL"),
    ("Eye Institute (NEI)", "NEI", "EYE INSTITUTE"),
    ("Advancing Translational Sciences (NCATS)", "NCATS", "TRANSLATIONAL"),
    ("Arthritis, Musculoskeletal and Skin (NIAMS)", "NIAMS", "ARTHRITIS"),
    ("Minority Health and Health Disparities (NIMHD)", "NIMHD", "MINORITY HEALTH"),
    ("Human Genome Research (NHGRI)", "NHGRI", "GENOME"),
    ("Deafness and Communication Disorders (NIDCD)", "NIDCD", "DEAFNESS"),
    ("Biomedical Imaging and Bioengineering (NIBIB)", "NIBIB", "IMAGING"),
    ("Dental and Craniofacial Research (NIDCR)", "NIDCR", "DENTAL"),
    ("Complementary and Integrative Health (NCCIH)", "NCCIH", "COMPLEMENTARY"),
    ("Nursing Research (NINR)", "NINR", "NURSING"),
    ("Fogarty International Center (FIC)", "FIC", "FOGARTY"),
    ("National Library of Medicine (NLM)", "NLM", "LIBRARY OF MEDICINE"),
    ("ARPA-H (administered through NIH)", "ARPA-H", "ADVANCED RESEARCH PROJECTS AGENCY FOR HEALTH"),
    (NIH_OD_NAME := "Office of the Director (Common Fund, ORIP, All of Us, other)", "OD", "OFFICE OF THE DIRECTOR"),
]
NIH_CFDA_IC = {"93.855": "NIAID", "93.856": "NIAID", "93.866": "NIA", "93.859": "NIGMS", "93.837": "NHLBI", "93.838": "NHLBI",
    "93.839": "NHLBI", "93.233": "NHLBI", "93.853": "NINDS", "93.847": "NIDDK", "93.848": "NIDDK", "93.849": "NIDDK",
    "93.242": "NIMH", "93.865": "NICHD", "93.279": "NIDA", "93.273": "NIAAA", "93.867": "NEI", "93.350": "NCATS",
    "93.846": "NIAMS", "93.307": "NIMHD", "93.113": "NIEHS", "93.114": "NIEHS", "93.115": "NIEHS", "93.143": "NIEHS",
    "93.172": "NHGRI", "93.173": "NIDCD", "93.286": "NIBIB", "93.121": "NIDCR", "93.213": "NCCIH", "93.361": "NINR",
    "93.989": "FIC", "93.879": "NLM", "93.393": "NCI", "93.394": "NCI", "93.395": "NCI", "93.396": "NCI", "93.397": "NCI",
    "93.398": "NCI", "93.399": "NCI"}
NIH_OD = "Office of the Director (Common Fund, ORIP, All of Us, other)"
nih_unmapped = collections.Counter()
def nih_ic(office, amt=0.0, cfda=""):
    o = " " + re.sub(r"[^A-Z0-9-]+", " ", (office or "").upper()) + " "
    for name, acr, kw in NIH_ICS:
        if f" {acr} " in o: return name
    for name, acr, kw in NIH_ICS:
        if " " + kw in o: return name     # word-start match: "IMAGING" must not hit "AGING"
    acr = NIH_CFDA_IC.get(cfda)        # aggregate-office records: place by the IC's own Assistance Listing
    if acr: return next(n for n, a, k in NIH_ICS if a == acr)
    nih_unmapped[(office or "") + " | " + (cfda or "")] += amt
    return NIH_OD
# HHS operating divisions shown as their own agencies. Their grants run through one grants office each,
# so the sub-level is the program (Assistance Listing) for grants and a single Contracts row.
HHS_OPDIV = {"Centers for Disease Control and Prevention": "075C", "Health Resources and Services Administration": "075H",
             "Substance Abuse and Mental Health Services Administration": "075S", "Centers for Medicare and Medicaid Services": "075M"}
CFDA_NAME = {}
def route(ag, subn, office, amt, cfda="", cfda_title=None):
    """agency/sub-agency as shown: NIH (by institute) and CDC/HRSA/SAMHSA/CMS (by program) split out of HHS"""
    if ag != "075": return ag, subn
    s = subn.strip()
    if s == "National Institutes of Health":
        return "075N", nih_ic(office, amt, cfda)
    if s in HHS_OPDIV:
        if cfda_title is None: return HHS_OPDIV[s], "Contracts"
        name = CFDA_NAME.setdefault(cfda, f"{nice(cfda_title) or 'Unspecified program'} ({cfda})" if cfda else "Unspecified program")
        return HHS_OPDIV[s], name
    return ag, subn

def nice(t):
    t = (t or "").strip().replace("_", ": ")
    if not t or not (t.isupper() or " Of " in t): return t
    out = []
    for i, w in enumerate(re.split(r"(\s+|/|-)", t)):
        u = w.upper(); core = u.rstrip(":,;.")
        if core.startswith("(") and core.endswith(")") and 2 < len(core) <= 9: out.append(u); continue
        if core in UPPER: out.append(("EPSCoR" if core == "EPSCOR" else core) + u[len(core):])
        elif i and w.lower() in SMALL: out.append(w.lower())
        else: out.append(w[:1].upper() + w[1:].lower())
    return "".join(out)

ap = argparse.ArgumentParser()
ap.add_argument("--core", required=True); ap.add_argument("--nsf", required=True)
ap.add_argument("--assistance"); ap.add_argument("--contracts"); ap.add_argument("--nsf-raw")
ap.add_argument("--out", required=True)
ap.add_argument("--subawards", help="trimmed subaward files (scripts/usaspending_subaward_trim.py)")
ap.add_argument("--scope", help="program_scope.json: which programs count for money received as a subrecipient")
ap.add_argument("--awards", choices=["shards", "inst"], default="shards",
                help="award files: 64 bundles (preview hosting) or one file per institution (public site)")
A = ap.parse_args()

cw = json.load(open(f"{A.core}/crosswalk/crosswalk_uei_v2.json"))
ents_v2 = json.load(open(f"{A.core}/crosswalk/entities_v2.json"))
ff = json.load(open(f"{A.core}/crosswalk/ffrdc_exclusions.json"))
U = json.load(open(f"{A.nsf}/universe3.json"))
inU = {d["u"] for d in U}
hd = {r["UNITID"]: r for r in csv.DictReader(open(f"{A.core}/ipeds/hd2025.csv", encoding="utf-8-sig"))}

rep = collections.defaultdict(float)          # money report
repn = collections.Counter()
unmatched = collections.defaultdict(lambda: [0.0, "", 0])   # uei -> [$, name, flagged higher-ed]
def ihe_assist(r):
    b = (r.get("business_types_description") or "").upper()
    return int("INSTITUTION OF HIGHER EDUCATION" in b and "OTHER THAN" not in b)
def ihe_contract(r):
    return int(any((r.get(k) or "").lower() in ("t", "true") for k in ("private_university_or_college", "state_controlled_institution_of_higher_learning")))
dropped_entities = collections.defaultdict(float)
ffrdc_hits = collections.defaultdict(float)

def entity_for(uei):
    """crosswalk v2 -> (entity id, kind) or (None, reason)"""
    c = cw.get(uei)
    if not c: return None, "not in crosswalk"
    t = c["type"]
    if t in ("hospital", "exclude"): return None, t
    if t == "campus":
        sec = hd.get(c["id"], {}).get("SECTOR", "")
        if sec in ("3", "6", "9"): return None, "for-profit campus"
        if sec == "0": return c["id"], "system"      # IPEDS administrative unit = system office
        return c["id"], ("carnegie" if c["id"] in inU else "ipeds")
    return c["id"], t   # other / system / institute / foreign

# ---------- accumulators ----------
# award-level: key -> dict(ent, kind, ag, sub, prog, comp, title, fy->$)
AW = {}
SUBS = {}; PROGS = {}
def sub_idx(ag, name):
    k = (ag, clean(name.strip()) or AGENCIES[ag][1])
    if k not in SUBS: SUBS[k] = len(SUBS)
    return SUBS[k]
def prog_idx(cfda, title, ag):
    cfda = code(cfda, r"\d{2}\.\d{3}[A-Za-z]?"); title = clean(title)
    if not cfda: return -1
    if cfda not in PROGS: PROGS[cfda] = [len(PROGS), title, ag]
    return PROGS[cfda][0]

def add(key, ent, kind, ag, sub, prog, comp, title, fy, amt, url, ad="", isnew=False, ps="", pe=""):
    # keyed by (award, recipient entity): an award that moves between recipients
    # (PI transfer, campus <-> hospital) credits each recipient only with its own actions
    a = AW.get((key, ent))
    if not a:
        a = AW[(key, ent)] = dict(ent=ent, kind=kind, ag=ag, sub=sub, prog=prog, comp=comp, title=title, fy={}, url=url, iss="", pop="")
    elif comp == 2: a["comp"] = 2
    a["fy"][fy] = a["fy"].get(fy, 0.0) + amt
    # issue date: the award's new-award action if it falls in the window; otherwise its period-of-performance start
    if isnew and ad and (not a["iss"] or ad < a["iss"]): a["iss"] = ad
    if ps and (not a["pop"] or ps < a["pop"]): a["pop"] = ps
    # current end date = the period-of-performance end on the award's most recent action
    if pe and ad >= a.get("pe_ad", ""): a["pe"] = pe; a["pe_ad"] = ad

def agency_of(code):
    code = (code or "").strip()
    return code if code in AGENCIES else None

files_used = {"assistance": [], "contracts": []}
# ---------- latest-data capture: every kept action since RECENT_START, with its date and new-award flag ----------
RECENT_START = "2023-06-01"
RECENT = []   # (date, ent, sub, prog, kind, flag, amt, is_new, key, title)

# ---------- assistance ----------
have_nsf_assist = False
if A.assistance:
    for f in sorted(glob.glob(f"{A.assistance}/**/*.csv.gz", recursive=True)):
        if "ontract" in os.path.basename(f): continue
        files_used["assistance"].append(os.path.basename(f))
        for r in csv.DictReader(gzip.open(f, "rt", newline="")):
            ag = agency_of(r.get("awarding_agency_code"))
            fy = int(r.get("action_date_fiscal_year") or 0)
            amt = float(r.get("federal_action_obligation") or 0)
            if not ag or fy not in YEARS: repn["assist rows outside scope"] += 1; continue
            if ag == "049": have_nsf_assist = True
            cfda = (r.get("cfda_number") or "").strip()
            if cfda in TITLE_IV: rep["assist Title IV dropped"] += amt; continue
            if cfda in STUDENT_LOAN: rep[f"assist student loan capital dropped: {STUDENT_LOAN[cfda]}"] += amt; continue
            if (r.get("assistance_type_code") or "").strip().zfill(2) not in COMPETITIVE_ASSIST:
                rep["assist non-competitive dropped"] += amt; continue
            fp = fain_prefix(r.get("award_id_fain"))
            fwhy = FORMULA_CFDA.get(cfda) or FORMULA_FAIN.get(fp)
            if fwhy: rep[f"assist formula dropped: {fwhy}"] += amt; continue
            desc0 = r.get("prime_award_base_transaction_description") or ""
            earmark = cfda in EARMARK_CFDA or fp in EARMARK_FAIN or bool(EARMARK_TEXT.search(desc0))
            uei = (r.get("recipient_uei") or "").strip()
            ent, kind = entity_for(uei)
            if not ent:
                rep[f"assist dropped: {kind}"] += amt
                if kind == "not in crosswalk":
                    u = unmatched[uei]; u[0] += amt; u[1] = r.get("recipient_name", ""); u[2] |= ihe_assist(r)
                else: dropped_entities[(kind, r.get("recipient_name", "")[:60])] += amt
                continue
            subn = r.get("awarding_sub_agency_name") or ""
            if ag == "049":
                subn = NSF_CFDA_TITLE.get(cfda, "Other NSF")
            key = r.get("assistance_award_unique_key") or ("A:" + (r.get("award_id_fain") or ""))
            ag2, subn = route(ag, subn, r.get("awarding_office_name"), amt, cfda, r.get("cfda_title", ""))
            si = sub_idx(ag2, nice(subn)); pi = prog_idx(cfda, nice(r.get("cfda_title", "")), ag2)
            add(key, ent, 0, ag2, si, pi, 2 if earmark else 1,
                (r.get("prime_award_base_transaction_description") or "")[:400], fy, amt, None,
                ad=(r.get("action_date") or "")[:10], isnew=(r.get("action_type_code") or "").strip() == "A" and amt >= 0,
                ps=(r.get("period_of_performance_start_date") or "")[:10],
                pe=(r.get("period_of_performance_current_end_date") or "")[:10])
            ad = (r.get("action_date") or "")[:10]
            if ad >= RECENT_START:
                RECENT.append((ad, ent, si, pi, 0, 2 if earmark else 1, amt, (r.get("action_type_code") or "").strip() == "A" and amt >= 0, key, desc0))
            rep[f"kept assist {ag2}"] += amt
            if earmark: rep[f"kept assist EARMARK {ag2}"] += amt

# ---------- contracts ----------
if A.contracts:
    for f in sorted(glob.glob(f"{A.contracts}/**/*.csv.gz", recursive=True)):
        if "ontract" not in os.path.basename(f): continue
        files_used["contracts"].append(os.path.basename(f))
        for r in csv.DictReader(gzip.open(f, "rt", newline="")):
            ag = agency_of(r.get("awarding_agency_code"))
            fy = int(r.get("action_date_fiscal_year") or 0)
            amt = float(r.get("federal_action_obligation") or 0)
            if not ag or fy not in YEARS: repn["contract rows outside scope"] += 1; continue
            uei = (r.get("recipient_uei") or "").strip()
            piid, ppiid = r.get("award_id_piid", ""), r.get("parent_award_id_piid", "")
            desc = r.get("prime_award_base_transaction_description") or ""
            why = (ff["ueis"].get(uei) or ff["piids"].get(piid) or ff["piids"].get(ppiid)
                   or ("M&O / FFRDC in description: " + (r.get("recipient_name") or "")[:40] if FFRDC_DESC.search(desc) else None))
            if why: ffrdc_hits[why] += amt; rep["contracts FFRDC excluded"] += amt; continue
            ent, kind = entity_for(uei)
            if not ent:
                rep[f"contract dropped: {kind}"] += amt
                if kind == "not in crosswalk":
                    u = unmatched[uei]; u[0] += amt; u[1] = r.get("recipient_name", ""); u[2] |= ihe_contract(r)
                else: dropped_entities[(kind, r.get("recipient_name", "")[:60])] += amt
                continue
            comp = 1 if (r.get("extent_competed") or "").strip().upper() in COMPETED_CONTRACT else 0
            key = r["contract_award_unique_key"]
            ag2, subn = route(ag, r.get("awarding_sub_agency_name") or "", r.get("awarding_office_name"), amt)
            si = sub_idx(ag2, nice(subn))
            add(key, ent, 1, ag2, si, -1, comp, desc[:400], fy, amt, None,
                ad=(r.get("action_date") or "")[:10], isnew=(r.get("action_type_code") or "").strip() == "" and amt >= 0,
                ps=(r.get("period_of_performance_start_date") or "")[:10],
                pe=(r.get("period_of_performance_current_end_date") or "")[:10])
            ad = (r.get("action_date") or "")[:10]
            if ad >= RECENT_START:
                RECENT.append((ad, ent, si, -1, 1, comp, amt, (r.get("action_type_code") or "").strip() == "" and amt >= 0, key, desc))
            rep[f"kept contracts {ag2}"] += amt

# ---------- NSF stand-in ----------
nsf_standin = False
if not have_nsf_assist and A.nsf_raw:
    nsf_standin = True
    for x in json.load(open(A.nsf_raw)):
        if x["fy"] not in YEARS: repn["nsf raw outside FY22-26"] += 1; continue
        if x.get("type", "").startswith(("Contract", "Interagency")): continue
        ent, kind = entity_for(x["uei"])
        amt = float(x["obl"] or 0)
        if not ent:
            rep[f"nsf-standin dropped: {kind}"] += amt
            if kind == "not in crosswalk":
                u = unmatched[x["uei"]]; u[0] += amt; u[1] = x.get("inst", "")
            continue
        d = x.get("dir") if x.get("dir") in NSF_DIR_CFDA else "O/D"
        cfda = NSF_DIR_CFDA[d]
        add("NSF:" + x["id"], ent, 0, "049", sub_idx("049", NSF_DIR_NAME[d]), prog_idx(cfda, NSF_CFDA_TITLE[cfda], "049"),
            1, x.get("title", ""), x["fy"], amt, None)
        rep["kept assist 049 (NSF stand-in)"] += amt

# ---------- funding cliff inputs ----------
# "Current annual funding" = obligations in the 52 weeks ending on the latest action date.
asof = max(x[0] for x in RECENT)
d_asof = datetime.date.fromisoformat(asof)
T12_START = (d_asof - datetime.timedelta(days=363)).isoformat()
for (ad_, ent_, si_, pi_, kind_, flag_, amt_, new_, key_, t_) in RECENT:
    if ad_ >= T12_START:
        a_ = AW.get((key_, ent_))
        if a_ is not None: a_["t12"] = a_.get("t12", 0.0) + amt_
# ---------- awards never count below zero, in total or in any year ----------
# Money pulled back from an award comes off the year it was given (latest first): a year shows what was obligated in it
# and not later pulled back. Pullbacks are mostly routine revisions and closeouts, not cancellations (docs/SPEC.md).
# A pullback larger than everything the award received inside FY2022-26 is returning money obligated before the
# window, which this tool never counted; that part is excluded. Totals equal the old running balance floored at zero.
def kept_by_year(fys):
    kept = {}
    for fy in sorted(fys):
        v = fys[fy]; kept[fy] = max(v, 0.0)
        need = -v
        for p in sorted(kept, reverse=True):
            if need <= 0: break
            if p == fy: continue
            take = min(kept[p], need); kept[p] -= take; need -= take
    return kept
for a_ in AW.values():
    raw = sum(a_["fy"].values()); fl = kept_by_year(a_["fy"])
    if abs(sum(fl.values()) - raw) >= 0.5:
        a_["raw"] = raw; rep["pre-FY2022 returns excluded (awards floored at zero)"] += sum(fl.values()) - raw
        repn["awards floored at zero"] += 1
        rep[f"pre-FY2022 returns excluded {a_['ag']}"] += sum(fl.values()) - raw
    a_["fy"] = fl
    if a_.get("t12", 0.0) < 0:   # current annual funding: an award netting below zero over the last 52 weeks counts as 0
        rep["last-52-week net returns excluded"] -= a_["t12"]; a_["t12"] = 0.0
END12 = (d_asof + datetime.timedelta(days=365)).isoformat(); END24 = (d_asof + datetime.timedelta(days=730)).isoformat()
def end_bucket(pe):
    """0 = scheduled end already passed, 1 = ends within 12 months, 2 = within 24 months, 3 = later, 4 = no end date"""
    if not pe: return 4
    return 0 if pe < asof else 1 if pe <= END12 else 2 if pe <= END24 else 3

# ---------- entities ----------
E = {}   # id -> meta for non-Carnegie entities
for (key, _e), a in AW.items():
    e = a["ent"]
    if e in inU or e in E: continue
    if e in ents_v2:
        v = ents_v2[e]; E[e] = {"n": clean(v["name"]), "c": clean(v.get("city", "")), "s": code(v.get("state", ""), r"[A-Z]{2}"), "k": {"other": "ipeds"}.get(v["type"], v["type"])}
    elif e in hd:
        h = hd[e]; E[e] = {"n": clean(h["INSTNM"]), "c": clean(h["CITY"]), "s": code(h["STABBR"], r"[A-Z]{2}"), "k": "system" if h["SECTOR"] == "0" else "ipeds"}
    else:
        nm = next((c["name"] for c in cw.values() if c.get("id") == e), e)
        E[e] = {"n": clean(nm), "c": "", "s": "", "k": "other"}

# ---------- aggregates ----------
# rows[ent] = list of [sub, kind, comp, nAwards, y22..y26]
R = collections.defaultdict(lambda: collections.defaultdict(lambda: [0] + [0.0] * len(YEARS)))
MASKS = collections.defaultdict(collections.Counter)
CL = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0]))   # ent -> (kind, end bucket) -> [$ last 52 weeks, n awards]
CONC = collections.defaultdict(list)   # distinct-award counts by active-year bitmask (bit i = YEARS[i])
P = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0] + [0.0] * len(YEARS)))  # ent -> (prog, earmark) -> [$, n, $FY22..$FY26]
shards = collections.defaultdict(lambda: collections.defaultdict(list))
SHN = 64
def shard_of(e):   # same hash in the page's JS
    h = 0
    for ch in e: h = (h * 31 + ord(ch)) % 1000003
    return h % SHN
for (key, _e), a in AW.items():
    tot = sum(a["fy"].values())
    if not any(abs(v) >= 0.5 for v in a["fy"].values()): continue
    row = R[a["ent"]][(a["sub"], a["kind"], a["comp"])]
    row[0] += 1
    for fy, v in a["fy"].items(): row[1 + YEARS.index(fy)] += v
    mask = sum(1 << YEARS.index(fy) for fy, v in a["fy"].items() if abs(v) >= 0.5)   # years this award was active
    MASKS[(a["ent"], a["sub"], a["kind"], a["comp"])][mask] += 1
    if a["prog"] >= 0:
        p = P[a["ent"]][(a["prog"], 1 if a["comp"] == 2 else 0)]; p[0] += tot; p[1] += 1
        for fy, v in a["fy"].items(): p[2 + YEARS.index(fy)] += v
    fys = sorted(a["fy"])
    shards[shard_of(a["ent"])][a["ent"]].append(
        [code(key, r"[A-Za-z0-9_.:-]{1,120}", "invalid-key"), a["kind"], a["sub"], a["prog"], fys[0], fys[-1], round(tot), a["comp"], clean((a["title"][:220] + "…") if len(a["title"]) > 221 else a["title"]),
         sum(1 << YEARS.index(fy) for fy, v in a["fy"].items() if abs(v) >= 0.5),   # [9] = active-year bitmask
         a["iss"] or a["pop"], 1 if a["iss"] else 0,                                # [10] issue date, [11] 1 = exact (new-award action), 0 = from period-of-performance start
         code(a.get("pe", ""), r"\d{4}-\d{2}-\d{2}"), round(a.get("t12", 0.0))]     # [12] current end date, [13] obligations in the last 52 weeks
        + ([round(a["raw"])] if "raw" in a else []))                                 # [14] actual net FY22-26 obligations, only when the award was floored at zero
    if a["comp"] != 2 and a.get("t12", 0) > 0:     # cliff + concentration: active awards, earmarks aside
        c_ = CL[a["ent"]][(a["kind"], end_bucket(a.get("pe", "")))]; c_[0] += a["t12"]; c_[1] += 1
        CONC[a["ent"]].append(a["t12"])

agcodes = sorted({ag for (ag, _n) in SUBS}, key=lambda c: -sum(v for k, v in rep.items() if k.endswith(c) or k.endswith(c + " (NSF stand-in)")))
out = {
    "meta": {
        "years": YEARS, "partial": 2026, "built": datetime.date.today().isoformat(),
        "nsf_standin": nsf_standin,
        "files": {k: len(v) for k, v in files_used.items()},
        "assist_agencies": sorted({AGENCIES[ag][0] for (ag, _), i in SUBS.items()
                                   if any(r for e in R.values() for (s, k, c), r in e.items() if s == i and k == 0)}),
        "contract_agencies": sorted({AGENCIES[ag][0] for (ag, _), i in SUBS.items()
                                     if any(r for e in R.values() for (s, k, c), r in e.items() if s == i and k == 1)}),
        "shards": SHN,
    },
    "ag": [[c, AGENCIES[c][0], AGENCIES[c][1]] for c in agcodes],
    "sub": [None] * len(SUBS),
    "prog": [None] * len(PROGS),
    "ent": E,
    # row = [sub, kind, comp, nAwards, $FY22..$FY26, [[yearMask, nAwards], ...]]
    "rows": {e: [[s, k, c, v[0]] + [round(x) for x in v[1:]] + [sorted([m, n] for m, n in MASKS[(e, s, k, c)].items())]
                 for (s, k, c), v in d.items()] for e, d in R.items()},
    # prog row = [prog, $FY22-26, nAwards, earmark, $FY22..$FY26]
    "progs": {e: [[p, round(v[0]), v[1], em] + [round(x) for x in v[2:]] for (p, em), v in d.items()] for e, d in P.items()},
}
agi = {c: i for i, c in enumerate(agcodes)}
for (ag, name), i in SUBS.items(): out["sub"][i] = [agi[ag], name]
for cfda, (i, title, ag) in PROGS.items(): out["prog"][i] = [cfda, title, agi[ag]]

out["cliff"] = {e: [[k, b, round(v[0]), v[1]] for (k, b), v in d.items()] for e, d in CL.items()}
out["conc"] = {e: [round(sum(sorted(v, reverse=True)[:10])), round(sum(v)), len(v)] for e, v in CONC.items()}
out["meta"]["t12"] = [T12_START, asof]; out["meta"]["end12"] = END12; out["meta"]["end24"] = END24
bad = [e for e in list(out["rows"]) + list(E) if not re.fullmatch(ID_RE, e)]
assert not bad, f"entity ids failing validation: {bad[:5]}"
out["_c"] = COPY; out["meta"]["awards"] = A.awards
os.makedirs(f"{A.out}/data/aw", exist_ok=True)
json.dump(out, open(f"{A.out}/data/agg.json", "w"), separators=(",", ":"))
# universe: the Carnegie file, with every text field cleaned and codes validated
UNI = []
for d in U:
    d = {k: (clean(v) if isinstance(v, str) else v) for k, v in d.items()}
    if not re.fullmatch(ID_RE, str(d.get("u", ""))): continue
    d["s"] = code(d.get("s", ""), r"[A-Z]{2}")
    UNI.append(d)
json.dump(UNI, open(f"{A.out}/data/universe.json", "w"), separators=(",", ":"))
if A.awards == "inst":
    for s_, d in shards.items():
        for e, rows in d.items():
            rows.sort(key=lambda r: -r[6])
            json.dump({"_c": COPY, "a": rows}, open(f"{A.out}/data/aw/{e}.json", "w"), separators=(",", ":"))
else:
    for s_, d in shards.items():
        for e in d: d[e].sort(key=lambda r: -r[6])
        json.dump({"_c": COPY, **d}, open(f"{A.out}/data/aw/{s_:02d}.json", "w"), separators=(",", ":"))

# ---------- latest data ----------
# Weeks count back from the latest action date: week 0 = the 7 days ending on that date. Windows of 13/26/52 weeks
# compare exactly with the same weeks one year (52 weeks) earlier.
NW = 160
asof = max(x[0] for x in RECENT)
d_asof = datetime.date.fromisoformat(asof)
RW = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0.0]))   # ent -> (sub,prog,kind,flag,week) -> [nNew, $new, $all]
FEED = collections.defaultdict(list)
for (ad, ent, si, pi, kind, flag, amt, is_new, key, title) in RECENT:
    wk = (d_asof - datetime.date.fromisoformat(ad)).days // 7
    if wk < 0 or wk >= NW: continue
    c = RW[ent][(si, pi, kind, flag, wk)]
    c[2] += amt
    if is_new:
        c[0] += 1; c[1] += amt
        if wk < 52:
            t = title.strip(); t = clean((t[:160] + "…") if len(t) > 161 else t)
            FEED[wk // 4].append([code(ad, r"\d{4}-\d{2}-\d{2}"), ent, si, pi, kind, flag, round(amt), code(key, r"[A-Za-z0-9_.:-]{1,120}", "invalid-key"), t])
# new awards keep sub-agency + program detail; all-obligation dollars roll up to (agency, kind, flag, week)
ALLW = collections.defaultdict(lambda: collections.defaultdict(float))
for e, d in RW.items():
    for (si, pi, kind, flag, wk), v in d.items():
        ALLW[e][(out["sub"][si][0], kind, flag, wk)] += v[2]
recent = {"_c": COPY, "asof": asof, "weeks": NW,
          "rows": {e: [[*k, v[0], round(v[1])] for k, v in d.items() if v[0]] for e, d in RW.items()},
          "all": {e: [[*k, round(v)] for k, v in d.items() if round(v)] for e, d in ALLW.items()}}
recent["rows"] = {e: r for e, r in recent["rows"].items() if r}
json.dump(recent, open(f"{A.out}/data/recent.json", "w"), separators=(",", ":"))
os.makedirs(f"{A.out}/data/feed", exist_ok=True)
for p_, rows in FEED.items():
    rows.sort(key=lambda r: r[0], reverse=True)
    json.dump(rows, open(f"{A.out}/data/feed/{p_:02d}.json", "w"), separators=(",", ":"))
out["meta"]["asof"] = asof
json.dump(out, open(f"{A.out}/data/agg.json", "w"), separators=(",", ":"))
print("recent.json bytes:", os.path.getsize(f"{A.out}/data/recent.json"), "feed rows:", sum(len(v) for v in FEED.values()), "asof", asof)

# ---------- subawards: received as subrecipient, passed through to others (docs/SPEC.md, open item 2) ----------
# (a) both sides resolve through the crosswalk; (b) "received" only under programs a university could win through a
# proposal (program_scope.json), "passed through" only under prime awards counted above (AW); (c) the same amount on the
# same action date counts once, and no prime's subawards count above the prime's own value (contract vehicles exempt);
# each subaward's years are summed with a running balance floored at zero, like the awards; (d) FY2026 is shown as still
# being reported (page); (e) a subaward with the same entity on both sides is left out. Earmarks: tagged, not in totals.
SUBREP = collections.defaultdict(float); SUBN = collections.Counter()
SUBOUT = {}
if A.subawards:
    scope = json.load(open(A.scope))["programs"] if A.scope else {}
    in_aw = {}                                  # prime award key -> earmark? (only awards Federal counts)
    for (k_, e_), a_ in AW.items(): in_aw[k_] = in_aw.get(k_, False) or a_["comp"] == 2
    rows_ = {}; prime_val = {}; prime_name = {}
    for f in sorted(glob.glob(f"{A.subawards}/*.csv.gz")):
        for r in csv.DictReader(gzip.open(f, "rt", newline="")):
            fy = int(r.get("subaward_action_date_fiscal_year") or 0)
            if fy not in YEARS: continue
            try: amt = float(r.get("subaward_amount") or 0); pv = float(r.get("prime_award_amount") or 0)
            except ValueError: SUBN["rows with unreadable amounts"] += 1; continue
            pk = r.get("prime_award_unique_key") or ""; su = (r.get("subawardee_uei") or "").strip()
            d_ = (r.get("subaward_action_date") or "")[:10]
            k = (pk, su, r.get("subaward_number") or "", d_, round(amt, 2))
            if k in rows_: SUBREP["same-date duplicates counted once"] += amt; continue
            rows_[k] = r; prime_val[pk] = max(prime_val.get(pk, 0.0), pv); prime_name[pk] = r.get("prime_awardee_name") or ""
    # each subaward's years: a pullback comes off the year the money was given, as for the awards
    per_sub = collections.defaultdict(lambda: collections.defaultdict(float)); sub_row = {}
    newest = lambda r: (r.get("subaward_action_date") or "", r.get("subaward_sam_report_last_modified_date") or "", r.get("subaward_sam_report_id") or "")
    for k, r in rows_.items():   # a subaward is classified by its most recent row (prime ids and programs can change mid-award)
        sk = k[:3]; per_sub[sk][int(r["subaward_action_date_fiscal_year"])] += k[4]
        if sk not in sub_row or newest(r) > newest(sub_row[sk]): sub_row[sk] = r
    flo = {}
    for sk, by in per_sub.items():
        out_ = kept_by_year(by)
        SUBREP["reductions below zero not counted"] += sum(out_.values()) - sum(by.values())
        flo[sk] = out_
    # ceiling: a prime award's subawards never count above the prime's own value
    ptot = collections.defaultdict(float)
    for sk, by in flo.items(): ptot[sk[0]] += sum(by.values())
    factor = {}; capped = []; idv = []
    for pk, t in ptot.items():
        pv = prime_val.get(pk, 0.0)
        if t <= pv * 1.001 or t <= 0: continue
        if pk.startswith("CONT_IDV_"): idv.append((t, pk, pv)); continue
        factor[pk] = pv / t; capped.append((t - pv, pk, pv, t)); SUBREP["above the prime award's value, not counted"] += t - pv
    SUBN["prime awards capped at their own value"] = len(capped); SUBN["contract vehicles exempt from the cap"] = len(idv)
    UNAME = {d["u"]: clean(d["n"]) for d in U}
    def label(e, raw): return (E[e]["n"] if e in E else UNAME.get(e)) or nice(clean(raw))[:80]
    S_ = collections.defaultdict(lambda: {"r": [0.0] * len(YEARS), "p": [0.0] * len(YEARS), "ra": collections.defaultdict(float),
                                          "pa": collections.defaultdict(float), "rt": collections.defaultdict(float), "pt": collections.defaultdict(float),
                                          "re": 0.0, "pe": 0.0, "rn": 0, "pn": 0})
    for sk, by in flo.items():
        r = sub_row[sk]; pk = sk[0]; f_ = factor.get(pk, 1.0)
        se, _ = entity_for(sk[1]); pe_, _ = entity_for((r.get("prime_awardee_uei") or "").strip())
        tot = sum(by.values()) * f_
        if not any(by.values()): continue   # a subaward paid in one year and pulled back in another nets to 0 but still moves money between years
        if se and se == pe_: SUBREP["same entity on both sides, left out"] += tot; continue
        ag0 = agency_of(r.get("prime_award_awarding_agency_code"))
        cfda = (r.get("prime_award_cfda_numbers_and_titles") or "").split(";")[0].strip()
        cn, ct = (cfda.split(":", 1) + [""])[:2] if cfda else ("", "")
        ag2 = route(ag0, r.get("prime_award_awarding_sub_agency_name") or "", r.get("prime_award_awarding_office_name"), 0.0,
                    cn.strip(), ct.strip() if pk.startswith("ASST") else None)[0] if ag0 else None
        ags = AGENCIES[ag2][0] if ag2 in AGENCIES else "Other"
        if se:     # received as subrecipient
            prog = scope.get(cn.strip())
            if pk.startswith("ASST") and prog is not None and not prog["in"]: SUBREP["received under formula/block programs, left out"] += tot
            elif cn.strip() in EARMARK_CFDA: S_[se]["re"] += tot; SUBREP["received under earmarks (tagged)"] += tot
            else:
                s = S_[se]; s["rn"] += 1
                for fy, v in by.items(): s["r"][YEARS.index(fy)] += v * f_
                s["ra"][ags] += tot; s["rt"][(pe_ or "", label(pe_, r.get("prime_awardee_name")))] += tot; SUBREP["received, counted"] += tot
        if pe_ and pk in in_aw:      # passed through, under an award Federal counts
            if in_aw[pk]: S_[pe_]["pe"] += tot; SUBREP["passed through under earmarks (tagged)"] += tot
            else:
                s = S_[pe_]; s["pn"] += 1
                for fy, v in by.items(): s["p"][YEARS.index(fy)] += v * f_
                s["pa"][ags] += tot; s["pt"][(se or "", label(se, r.get("subawardee_name")))] += tot; SUBREP["passed through, counted"] += tot
        elif pe_: SUBREP["passed through under awards not counted above"] += tot
    top = lambda d_: [[n, e, round(v)] for (e, n), v in sorted(d_.items(), key=lambda x: -x[1])[:10] if v >= 1]
    SUBOUT = {"_c": COPY, "years": YEARS, "partial": 2026, "e": {
        e: {"r": [round(x) for x in s["r"]], "p": [round(x) for x in s["p"]], "rn": s["rn"], "pn": s["pn"],
            "ra": {a: round(v) for a, v in sorted(s["ra"].items(), key=lambda x: -x[1]) if v >= 1},
            "pa": {a: round(v) for a, v in sorted(s["pa"].items(), key=lambda x: -x[1]) if v >= 1},
            "rt": top(s["rt"]), "pt": top(s["pt"]), "re": round(s["re"]), "pe": round(s["pe"])}
        for e, s in S_.items() if (e in inU or e in E) and re.fullmatch(ID_RE, e)}}   # only entities the page can show
    json.dump(SUBOUT, open(f"{A.out}/data/sub.json", "w"), separators=(",", ":"), ensure_ascii=False)
    SUBREP_TOP = {"capped_primes_top": [[pk, prime_name.get(pk, ""), round(pv), round(t)] for x, pk, pv, t in sorted(capped, reverse=True)[:150]],
                  "idv_exempt_top": [[pk, prime_name.get(pk, ""), round(pv), round(t)] for t, pk, pv in sorted(idv, reverse=True)[:60]]}
    print("sub.json bytes:", os.path.getsize(f"{A.out}/data/sub.json"), "entities:", len(SUBOUT["e"]))

# ---------- report ----------
camp = collections.defaultdict(lambda: [0.0] * len(YEARS))
bykind = collections.defaultdict(float)
for e, d in R.items():
    kk = "campus" if (e in inU or E.get(e, {}).get("k") == "ipeds") else E[e]["k"]
    for (s_, k, c), v in d.items():
        bykind[(out["ag"][out["sub"][s_][0]][1], "A" if k == 0 else "C", kk)] += sum(v[1:])
for e, d in R.items():
    if e not in inU and E.get(e, {}).get("k") not in ("ipeds",): continue
    for (s, k, c), v in d.items():
        ag = out["ag"][out["sub"][s][0]][1]
        for i in range(len(YEARS)): camp[(ag, "assistance" if k == 0 else "contracts")][i] += v[1 + i]
report = {
    "money": {k: round(v) for k, v in sorted(rep.items())}, "counts": dict(repn),
    "campus_by_agency": {f"{a} {k}": [round(x) for x in v] for (a, k), v in sorted(camp.items())},
    "ffrdc_excluded": {k: round(v) for k, v in sorted(ffrdc_hits.items(), key=lambda x: -x[1])},
    "dropped_entities_top": [[k[0], k[1], round(v)] for k, v in sorted(dropped_entities.items(), key=lambda x: -x[1])[:60]],
    "unmatched_ueis_top": [[u, n, round(v), f] for u, (v, n, f) in sorted(unmatched.items(), key=lambda x: -x[1][0])[:300]],
    "unmatched_higher_ed": [[u, n, round(v)] for u, (v, n, f) in sorted(unmatched.items(), key=lambda x: -x[1][0]) if f],
    "files": files_used,
    "nih_offices_unmapped": {k: round(v) for k, v in nih_unmapped.most_common(40)},
    "by_kind": {f"{a} {k} {t}": round(v) for (a, k, t), v in sorted(bykind.items())},
}
if A.subawards:
    report["subawards"] = {"money": {k: round(v) for k, v in sorted(SUBREP.items())}, "counts": dict(SUBN), **SUBREP_TOP}
json.dump(report, open(f"{A.out}/data/build_report.json", "w"), indent=1)
print(json.dumps({k: report[k] for k in ("money", "campus_by_agency")}, indent=1))
print("entities with money:", len(R), "awards:", len(AW), "non-Carnegie entities:", len(E))
print("agg.json bytes:", os.path.getsize(f"{A.out}/data/agg.json"))
