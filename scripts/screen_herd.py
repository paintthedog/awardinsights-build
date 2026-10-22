"""
Sanity screen: Federal Award Insights' FY2024 obligations against the federal R&D each institution reported to NSF's
HERD survey for FY2024.   © 2026 Award Insights

    FAI_INPUTS=inputs FAI_SITE=build/site/federal python3 scripts/screen_herd.py [--out build/herd_screen.md]

The two measure different things (obligations vs spending; HERD is R&D only and counts work done through affiliated
hospitals and foundations differently), so they never match. An institution far out of line in either direction is
where crosswalk mistakes hide: money assigned to the wrong place, or missing. This lists those for a person to review;
it doesn't change anything and doesn't stop a build.
"""
import argparse, json, os, statistics
D = os.environ.get("FAI_INPUTS", "inputs"); SITE = os.environ.get("FAI_SITE", "build/site/federal")
ap = argparse.ArgumentParser(); ap.add_argument("--out", default="build/herd_screen.md")
ap.add_argument("--low", type=float, default=0.4); ap.add_argument("--high", type=float, default=2.5)
ap.add_argument("--min", type=float, default=5e6, help="only institutions with at least this much HERD federal R&D")
A = ap.parse_args()

agg = json.load(open(f"{SITE}/data/agg.json")); prof = json.load(open(f"{D}/nsf/profile4.json"))
FED = ["NSF", "HHS", "DOD", "DOE", "NASA", "USDA", "Other agencies"]   # HERD federal funding sources (profile4.json, $ thousands)
yi = agg["meta"]["years"].index(2024)
site = {e: sum(r[4 + yi] for r in rows if r[2] != 2) for e, rows in agg["rows"].items()}
# Portfolio and Federal key a few organizations differently (system offices, institutes): use the site's own links
inst = json.load(open(os.path.join(os.path.dirname(SITE.rstrip("/")), "shared", "inst.json")))
fid = {r[0]: r[4]["federal"] for r in inst["i"] if len(r) > 4 and "federal" in r[4]}
rows = []
for k, d in prof.items():
    herd = sum((d.get("ag", {}).get("2024") or {}).get(a, 0) for a in FED) * 1000
    if herd < A.min: continue
    units = d["units"] if d.get("k") == "comb" else [k]          # combined HERD reports: add up their campuses
    ob = sum(site.get(fid.get(u, u), 0) for u in units)
    rows.append((ob / herd, d["n"], k, herd, ob))
ratios = [r[0] for r in rows]; med = statistics.median(ratios)
flag = sorted([r for r in rows if r[0] < A.low or r[0] > A.high], key=lambda r: r[0])
out = [f"# HERD sanity screen (FY2024)", "",
       f"{len(rows)} HERD reporters with at least ${A.min/1e6:.0f}M federal R&D. Median ratio of Federal obligations to HERD federal R&D: {med:.2f}.",
       f"Flagged: ratio under {A.low} or over {A.high} ({len(flag)}). Low usually means money sits with an affiliated hospital, foundation or a",
       "recipient id the crosswalk doesn't map here; high usually means non-R&D awards (training, education, contracts) or money credited",
       "here that belongs elsewhere.", "", "| Ratio | Institution | id | HERD federal R&D FY24 | Federal obligations FY24 |", "|---|---|---|---|---|"]
out += [f"| {r[0]:.2f} | {r[1]} | {r[2]} | ${r[3]/1e6:,.1f}M | ${r[4]/1e6:,.1f}M |" for r in flag]
os.makedirs(os.path.dirname(A.out) or ".", exist_ok=True); open(A.out, "w").write("\n".join(out) + "\n")
print(f"{len(rows)} institutions; median ratio {med:.2f}; flagged {len(flag)} -> {A.out}")
for r in flag[:12] + flag[-12:]: print(f"  {r[0]:5.2f}  {r[1][:55]:55} HERD ${r[3]/1e6:7.1f}M  site ${r[4]/1e6:7.1f}M")
