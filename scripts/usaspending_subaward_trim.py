"""
Trim subaward downloads to the rows Award Insights uses.

Run:   python3 usaspending_subaward_trim.py
Reads every zip in ./usaspending_subawards; writes <name>_trimmed.csv.gz into ./trimmed_subawards.

Keeps a subaward when EITHER side is in the institution universe:
  - the subawardee's UEI is in known_ueis.txt   -> money an institution RECEIVED as a subrecipient
  - the prime recipient's UEI is in known_ueis.txt -> money an institution PASSED THROUGH to others
Also keeps any subawardee that reports itself as a higher-education institution, so new UEIs can be matched.
Keeps only the columns the build uses; descriptions capped at 400 characters.
The first file's full column list is written to subaward_columns.txt (send it along with the trimmed files).
"""
import warnings; warnings.filterwarnings("ignore")
import pathlib, zipfile, io, csv, gzip, sys
csv.field_size_limit(sys.maxsize)

SRC = pathlib.Path("usaspending_subawards"); OUT = pathlib.Path("trimmed_subawards"); OUT.mkdir(exist_ok=True)
known = set(l.strip() for l in open("known_ueis.txt") if l.strip())
DESC_MAX = 400
KEEP = [
    # the prime award
    "prime_award_unique_key", "prime_award_fain", "prime_award_piid", "prime_award_amount", "prime_award_base_action_date",
    "prime_award_awarding_agency_code", "prime_award_awarding_agency_name", "prime_award_awarding_sub_agency_name",
    "prime_award_awarding_office_name", "prime_awardee_uei", "prime_awardee_name", "prime_awardee_parent_uei",
    "prime_award_cfda_numbers_and_titles", "prime_award_type", "prime_award_naics_code", "prime_award_period_of_performance_start_date",
    "prime_award_period_of_performance_current_end_date",
    # the subaward
    "subaward_type", "subaward_fsrs_report_id", "subaward_report_id", "subaward_fsrs_report_year", "subaward_fsrs_report_month",
    "subaward_number", "subaward_amount", "subaward_action_date", "subaward_action_date_fiscal_year", "subaward_description",
    "subawardee_uei", "subawardee_name", "subawardee_dba_name", "subawardee_parent_uei", "subawardee_parent_name",
    "subawardee_country_code", "subawardee_state_code", "subawardee_city_name", "subawardee_business_types",
    "usaspending_permalink", "subaward_last_modified_date",
]
IHE = ("HIGHER EDUCATION", "UNIVERSITY", "COLLEGE")
wrote_cols = False

for z in sorted(SRC.glob("*.zip")):
    zf = zipfile.ZipFile(z)
    for member in zf.namelist():
        if not member.lower().endswith(".csv"): continue
        kind = "Contract" if "contract" in member.lower() or "procurement" in member.lower() else "Assistance"
        dest = OUT / f"{z.stem}_{pathlib.Path(member).stem}_trimmed.csv.gz"
        if dest.exists(): print("have", dest.name); continue
        with zf.open(member) as fh:
            rd = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""))
            if not rd.fieldnames or "subawardee_uei" not in rd.fieldnames and "subaward_amount" not in rd.fieldnames:
                print(f"  skipping {member}: prime-award file, not subawards"); continue
            cols = [c for c in KEEP if c in rd.fieldnames]
            if not wrote_cols:
                pathlib.Path("subaward_columns.txt").write_text("\n".join(rd.fieldnames)); wrote_cols = True
            missing = [c for c in ("subawardee_uei", "prime_awardee_uei", "subaward_amount") if c not in rd.fieldnames]
            if missing: print(f"  {member}: expected columns not found {missing}; see subaward_columns.txt")
            kept = total = rec = pas = 0
            with gzip.open(dest, "wt", newline="") as out:
                w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore"); w.writeheader()
                for r in rd:
                    total += 1
                    sub, prime = (r.get("subawardee_uei") or "").strip(), (r.get("prime_awardee_uei") or "").strip()
                    bt = (r.get("subawardee_business_types") or "").upper()
                    received = sub in known or any(k in bt for k in IHE)
                    passed = prime in known
                    if not (received or passed): continue
                    rec += received; pas += passed
                    if r.get("subaward_description"): r["subaward_description"] = r["subaward_description"][:DESC_MAX]
                    w.writerow(r); kept += 1
        print(f"{dest.name}: kept {kept:,} of {total:,} (received {rec:,}, passed through {pas:,})")
