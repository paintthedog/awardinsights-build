"""
Record exactly which input files a build used, so any figure can be reproduced later.   © 2026 Award Insights

    python3 scripts/manifest.py            write inputs/MANIFEST.json (run after each refresh, then commit it)
    python3 scripts/manifest.py --check    compare the files in inputs/ with the manifest; exit 1 on any difference

Covers the git-ignored data inputs (inputs/trimmed/, inputs/subawards/) and the committed reference files the build
reads (crosswalk, program scope). Each file: size, SHA-256, and for data files the number of text lines.
"""
import argparse, csv, gzip, hashlib, json, pathlib, sys, time
csv.field_size_limit(sys.maxsize)
ROOT = pathlib.Path(__file__).resolve().parent.parent
IN = ROOT / "inputs"; OUT = IN / "MANIFEST.json"
GROUPS = {"trimmed": "trimmed/*.csv.gz", "subawards": "subawards/*.csv.gz",
          "reference": ["ai-1-core/crosswalk/crosswalk_uei_v2.json", "ai-1-core/crosswalk/entities_v2.json",
                        "ai-1-core/crosswalk/ffrdc_exclusions.json", "ai-1-core/crosswalk/known_ueis.txt",
                        "ai-1-core/program_scope.json", "ai-1-core/earmark_awards.json", "ai-1-core/program_exclusions.json", "nsf/universe3.json", "nsf-raw/nsf_raw_rows.json"]}

def describe(p):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    d = {"bytes": p.stat().st_size, "sha256": h}
    if p.name.endswith(".csv.gz"): d["lines"] = sum(1 for _ in gzip.open(p, "rt"))   # text lines incl. header (a quoted field can span lines)
    return d

def scan():
    out = {}
    for g, pat in GROUPS.items():
        files = sorted(IN.glob(pat)) if isinstance(pat, str) else [IN / f for f in pat if (IN / f).exists()]
        out[g] = {str(f.relative_to(IN)): describe(f) for f in files}
    return out

ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
now = scan()
if a.check:
    if not OUT.exists(): print("no inputs/MANIFEST.json yet: run scripts/manifest.py after a refresh"); sys.exit(1)
    old = json.load(open(OUT))["files"]; diff = []
    for g in GROUPS:
        o, n = old.get(g, {}), now.get(g, {})
        diff += [f"{g}: new {f}" for f in n.keys() - o.keys()] + [f"{g}: missing {f}" for f in o.keys() - n.keys()]
        diff += [f"{g}: changed {f}" for f in n.keys() & o.keys() if n[f]["sha256"] != o[f]["sha256"]]
    if diff: print("inputs differ from inputs/MANIFEST.json:"); [print("  " + x) for x in diff[:20]]; sys.exit(1)
    print(f"inputs match the manifest ({sum(len(v) for v in now.values())} files)"); sys.exit(0)
summary = {g: {"files": len(v), "lines": sum(x.get("lines", 0) for x in v.values())} for g, v in now.items()}
json.dump({"_c": "© 2026 Award Insights", "written": time.strftime("%Y-%m-%d"), "archive_date": "2026-09-06",
           "summary": summary, "files": now}, open(OUT, "w"), indent=1)
print("wrote", OUT.relative_to(ROOT), summary)
