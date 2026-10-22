"""
Trim USAspending archive zips to the rows and columns the Award Insights build needs.

Run:   python3 usaspending_trim.py
Reads every zip in ./usaspending_downloads; writes <name>_trimmed.csv.gz into ./trimmed.

Keeps a row when the recipient UEI is in known_ueis.txt OR USAspending flags the
recipient as an institution of higher education. For assistance, keeps only
competitive award types: project grants (04) and cooperative agreements (05) --
formula and block grants, direct payments, loans and insurance are dropped, and
Education Title IV student aid with them. Keeps only the columns the build uses,
and caps the award description at 400 characters.
"""
import warnings; warnings.filterwarnings("ignore")
import argparse, pathlib, zipfile, io, csv, gzip, sys
csv.field_size_limit(sys.maxsize)
# defaults as before; --out lets a re-trim write a fresh set next to the old one
ap = argparse.ArgumentParser(); ap.add_argument("--src", default="usaspending_downloads"); ap.add_argument("--out", default="trimmed")
ap.add_argument("--known", default="known_ueis.txt"); args = ap.parse_args()
SRC = pathlib.Path(args.src); OUT = pathlib.Path(args.out); OUT.mkdir(exist_ok=True)
known = set(l.strip() for l in open(args.known) if l.strip())

IHE_TEXT = ("CONTROLLED INSTITUTION OF HIGHER EDUCATION", "PRIVATE INSTITUTION OF HIGHER EDUCATION")
IHE_FLAGS = ("educational_institution", "private_university_or_college", "state_controlled_institution_of_higher_learning")
COMPETITIVE = {"04", "05"}   # project grant, cooperative agreement
DESC_MAX = 400
TITLE_IV = {"84.063", "84.268", "84.033", "84.007", "84.379", "84.038", "84.032", "84.408"}

KEEP = [
    # shared
    "federal_action_obligation", "action_date", "action_date_fiscal_year",
    "awarding_agency_code", "awarding_agency_name", "awarding_sub_agency_code", "awarding_sub_agency_name",
    "awarding_office_name", "funding_sub_agency_name",
    "recipient_uei", "recipient_name", "recipient_parent_uei", "recipient_parent_name",
    "recipient_city_name", "recipient_state_code",
    "primary_place_of_performance_state_code", "primary_place_of_performance_zip_4",
    "period_of_performance_start_date", "period_of_performance_current_end_date",
    "prime_award_base_transaction_description",
    # assistance
    "assistance_award_unique_key", "award_id_fain", "assistance_type_code", "assistance_type_description",
    "action_type_code", "cfda_number", "cfda_title", "business_types_description", "total_obligated_amount",
    # contracts
    "contract_award_unique_key", "award_id_piid", "parent_award_id_piid", "award_type",
    "product_or_service_code", "product_or_service_code_description", "naics_code", "naics_description",
    "extent_competed", "type_of_contract_pricing", "number_of_offers_received",
    "federally_funded_research_and_development_corp",
    "educational_institution", "private_university_or_college", "state_controlled_institution_of_higher_learning",
]

def truthy(v): return (v or "").strip().lower() in ("t", "true", "1", "y")

for z in sorted(SRC.glob("*.zip")):
    dest = OUT / (z.stem + "_trimmed.csv.gz")
    if dest.exists(): print("have", dest.name); continue
    kept = total = t4 = nc = 0
    zf = zipfile.ZipFile(z)
    with gzip.open(dest, "wt", newline="") as out:
        w = None; cols = None
        for name in zf.namelist():
            if not name.endswith(".csv"): continue
            with zf.open(name) as f:
                r = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                h = next(r); ix = {c: i for i, c in enumerate(h)}
                if w is None:
                    cols = [c for c in KEEP if c in ix]
                    w = csv.writer(out); w.writerow(cols)
                iu = ix.get("recipient_uei"); ib = ix.get("business_types_description"); ic = ix.get("cfda_number")
                it = ix.get("assistance_type_code"); idesc = cols.index("prime_award_base_transaction_description") if "prime_award_base_transaction_description" in cols else None
                fl = [ix[c] for c in IHE_FLAGS if c in ix]
                for row in r:
                    total += 1
                    g = lambda i: row[i] if i is not None and i < len(row) else ""
                    if ic is not None and g(ic) in TITLE_IV: t4 += 1; continue
                    if it is not None and g(it).zfill(2) not in COMPETITIVE: nc += 1; continue
                    keep = g(iu) in known
                    if not keep and ib is not None and any(k in g(ib) for k in IHE_TEXT): keep = True
                    if not keep and any(truthy(g(i)) for i in fl): keep = True
                    if keep:
                        out_row = [g(ix[c]) for c in cols]
                        if idesc is not None and len(out_row[idesc]) > DESC_MAX: out_row[idesc] = out_row[idesc][:DESC_MAX].rstrip() + "…"
                        w.writerow(out_row); kept += 1
    print(f"{z.name}: kept {kept:,} of {total:,} rows" + (f" (dropped {t4:,} Title IV, {nc:,} non-competitive)" if (t4 or nc) else "") + f" -> {dest.stat().st_size/1e6:.1f} MB")
