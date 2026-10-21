"""
Which Assistance Listings (CFDA) count when a university receives money as a subrecipient.   © 2026 Award Insights

Run on the Mac, from the folder holding the downloads, after the prime pull (reads every full assistance archive once):
    python3 awardinsights-build/scripts/program_scope.py usaspending_downloads awardinsights-build/inputs/ai-1-core/program_scope.json

Subaward files don't say whether the prime award was competitive, so the rule is set per program from the full archive:
a program is out when most of its money nationwide (FY2022-26, positive obligations) is formula (03) or block (02) grants,
the money that reaches institutions through states rather than through a proposal. OVERRIDE holds the few programs
recorded as project grants that are not winnable through a proposal. Earmark programs are handled by the earmark rule.
"""
import csv, io, json, pathlib, sys, zipfile, collections
csv.field_size_limit(sys.maxsize)
OVERRIDE = {"97.036": "FEMA Public Assistance: disaster reimbursement, recorded as project grants but not winnable through a proposal"}
SRC, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
T = collections.defaultdict(lambda: collections.defaultdict(float)); TITLE = {}
for z in sorted(SRC.glob("*_Assistance_Full_*.zip")):
    with zipfile.ZipFile(z) as zf:
        for name in (n for n in zf.namelist() if n.endswith(".csv")):
            with zf.open(name) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline="")):
                    c = (r.get("cfda_number") or "").strip()
                    try: a = float(r.get("federal_action_obligation") or 0)
                    except ValueError: continue
                    if c and a > 0:
                        T[c][(r.get("assistance_type_code") or "").strip().zfill(2)] += a
                        TITLE.setdefault(c, (r.get("cfda_title") or "")[:120])
    print("read", z.name, flush=True)
out = {}
for c, t in sorted(T.items()):
    tot = sum(t.values()); fb = (t.get("02", 0) + t.get("03", 0)) / tot
    out[c] = {"title": TITLE[c], "formula_block": round(fb, 3), "in": fb < .5 and c not in OVERRIDE}
    if c in OVERRIDE: out[c]["why"] = OVERRIDE[c]
OUT.write_text(json.dumps({"_c": "© 2026 Award Insights", "rule": "in = under half of the program's FY2022-26 money nationwide is formula/block grants; programs not listed count as in", "programs": out}, indent=0, ensure_ascii=False))
print(f"{len(out)} programs: {sum(v['in'] for v in out.values())} in, {sum(not v['in'] for v in out.values())} out")
