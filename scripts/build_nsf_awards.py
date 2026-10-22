"""
NSF Award Insights' award file, assigned to institutions with Federal's crosswalk.   © 2026 Award Insights

    python3 -I scripts/build_nsf_awards.py            write inputs/nsf/awards4.json and coverage.json
    python3 -I scripts/build_nsf_awards.py --check    exit 1 if they differ from what the crosswalk gives (deploy runs this)

Source: inputs/nsf-raw/nsf_raw_rows.json (NSF's own award records). Each award goes to the recipient id's entity in
crosswalk_uei_v2.json, by the same rule as Federal's entity_for(): hospitals, excluded ids and for-profit campuses are
left out. The NSF tool lists Carnegie institutions only (universe3.json), so awards to system offices, independent
institutes and foreign institutions are left out here though Federal shows them as their own entities.
Row: [unitid, year, intended $, division, program codes, obligated $, award id, title (cut at 120 characters)].
"""
import argparse, csv, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
IN = ROOT / "inputs"
ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); A = ap.parse_args()

cw = json.load(open(IN / "ai-1-core/crosswalk/crosswalk_uei_v2.json"))
hd = {r["UNITID"]: r for r in csv.DictReader(open(IN / "ai-1-core/ipeds/hd2025.csv", encoding="utf-8-sig"))}
inU = {d["u"] for d in json.load(open(IN / "nsf/universe3.json"))}
raw = json.load(open(IN / "nsf-raw/nsf_raw_rows.json"))

def unit(uei):
    c = cw.get(uei)
    if not c or c["type"] != "campus": return None
    if hd.get(c["id"], {}).get("SECTOR", "") in ("3", "6", "9"): return None
    return c["id"] if c["id"] in inU else None
def title(t):
    t = t.strip()
    return t if len(t) <= 120 else t[:117].rstrip() + "…"

rows = [[u, r["yr"], round(r["intn"] or 0), r["div"], r["pgm"], round(r["obl"] or 0), r["id"], title(r["title"])]
        for r in raw if (u := unit(r["uei"]))]
cov = {"n_all": len(raw), "d_all": sum(r["intn"] or 0 for r in raw), "n_in": len(rows), "d_in": sum(x[2] for x in rows)}
aw = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
P, C = IN / "nsf/awards4.json", IN / "nsf/coverage.json"
if A.check:
    old = json.load(open(P)); was = {x[6]: x[0] for x in old}
    now = {r[6] for r in rows}
    diff = [r for r in rows if was.get(r[6]) != r[0]] + [x for x in old if x[6] not in now]
    if aw != P.read_text() or json.load(open(C)) != cov:
        print(f"NSF awards differ from the crosswalk ({len(diff)} awards): run scripts/build_nsf_awards.py and commit"); sys.exit(1)
    print(f"NSF awards follow the crosswalk ({len(rows):,} awards)"); sys.exit(0)
P.write_text(aw); json.dump(cov, open(C, "w"))
print(f"wrote {P.relative_to(ROOT)}: {len(rows):,} of {len(raw):,} awards, ${cov['d_in']/1e9:.2f}B of ${cov['d_all']/1e9:.2f}B")
