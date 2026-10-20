"""
Put the four tools into one site: shared site bar, clean URLs, redirects, and the institution index.
Runs last, on the finished pages in build/site; the tool templates themselves are not touched.   © 2026 Award Insights

    python3 scripts/build_shell.py --site build/site

- nsf.html, designations.html, portfolio.html  ->  /nsf/, /designations/, /portfolio/ (index.html in each)
- the old .html addresses become small redirect pages that keep the #… part
- federal/index.html gets the site bar in place; index.html is replaced by the new landing page (site/landing.html)
- /shared/: site.js, site.css, redirect.js, and inst.json (every institution in any tool, with which tools cover it)
"""
import argparse, json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
N = ROOT / "inputs" / "nsf"
COPY = "© 2026 Award Insights · awardinsights.org · All rights reserved."
TOOLS = [("federal", "Federal", "Federal Award Insights"), ("nsf", "NSF", "NSF Award Insights"),
         ("designations", "Designations", "Research Activity Designations"), ("portfolio", "Portfolio", "Research Portfolio Trends")]
BIT = {"federal": 1, "nsf": 2, "designations": 4, "portfolio": 8}
OLD = {"nsf": "nsf.html", "designations": "designations.html", "portfolio": "portfolio.html"}
# the home links the original pages carry in their mastheads; the site bar replaces them
HOME_LINKS = ['<a class="tag" href="index.html" style="text-decoration:none">Award Insights</a>',
              '<a class="tag" href="index.html">Award Insights</a>']
# Federal ids for organizations Portfolio lists under another id (checked by hand, 20 Oct 2026)
FED_SAME = {"I-UNIVERSITY-OF-MARYLAND-CENTER-FOR-ENVIRO": "I-UMCES", "I-WOODS-HOLE-OCEANOGRAPHIC-INSTITUTION": "I-WHOI",
            "I-VAN-ANDEL-RESEARCH-INSTITUTE": "I-VAI", "X-MILLS-COLLEGE": "118888"}
HEAD = '<link rel="stylesheet" href="/shared/site.css">\n<script src="/shared/site.js" defer></script>\n</head>'
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'")

def sitebar(tool):
    here = ' aria-current="page"'
    tabs = "".join(f'<a href="/{t}/" data-t="{t}"{here if t == tool else ""} title="{full}">{short}</a>'
                   for t, short, full in TOOLS)
    return (f'<header class="sitebar" data-tool="{tool}"><a class="home" href="/">Award Insights</a>'
            f'<nav aria-label="Tools">{tabs}</nav></header>')

def index(site):
    """Every institution any tool covers: [id, name, state, tools bitmask, {tool: its own id} when that differs].
    pk lists the campuses in each of Portfolio's combined units."""
    rows, pk = {}, {}
    def add(u, n, s, tool, own=None):
        r = rows.setdefault(u, [u, n, s or "", 0]); r[3] |= BIT[tool]
        if own and own != u: (r.append({}) if len(r) == 4 else None); r[4][tool] = own
    universe = json.load(open(N / "universe3.json")); inU = {d["u"] for d in universe}
    prof = json.load(open(N / "profile4.json"))
    for d in universe:
        add(d["u"], d["n"], d.get("s"), "nsf"); add(d["u"], d["n"], d.get("s"), "federal")
    agg = json.load(open(site / "federal" / "data" / "agg.json"))
    for u, d in agg["ent"].items():
        # a system office Federal keys as S-<UNITID> is the same organization Portfolio keys by the UNITID
        same = FED_SAME.get(u) or (u[2:] if u.startswith("S-") and u[2:] in prof and u[2:] not in inU and u[2:] not in agg["ent"] else u)
        add(same, d["n"], d.get("s"), "federal", own=u)
    rad = json.load(open(N / "rad5.json"))
    for d in rad: add(d["u"], d["n"], d.get("st"), "designations")
    for k, d in prof.items():
        if d.get("k") == "comb":
            for u in d["units"]:
                if u in rows: rows[u][3] |= BIT["portfolio"]
            pk[k] = d["units"]          # first unit is the main campus; it stands for the combined unit elsewhere
        else: add(k, d["n"], d.get("st"), "portfolio")
    n = {t: sum(1 for r in rows.values() if r[3] & BIT[t]) for t in BIT}
    why = {"federal": f"covers the {n['federal']:,} institutions and research organizations in its data",
           "nsf": f"covers the {n['nsf']:,} institutions in the 2025 Carnegie universe",
           "designations": f"covers the {len(rad):,} institutions with a 2025 Carnegie research designation (R1, R2 or Research College)",
           "portfolio": f"covers the {len(prof):,} institutions that report R&D to the NSF HERD survey"}
    out = sorted(rows.values(), key=lambda r: r[1])
    print("  institution index:", len(out), "entries;", ", ".join(f"{t} {n[t]:,}" for t in BIT))
    return {"_c": COPY, "t": {t: {"n": n[t], "why": why[t]} for t in BIT}, "i": out, "pk": pk}

def inject(html, tool, name):
    if 'class="sitebar"' in html: return html   # already done (a rerun on the same build)
    if html.count('<div class="masthead">') != 1: sys.exit(f"{name}: expected one masthead")
    if "</head>" not in html: sys.exit(f"{name}: no </head>")   # Designations has a second one inside its print template; the first is the page's
    for h in HOME_LINKS: html = html.replace(h, "")
    return html.replace('<div class="masthead">', sitebar(tool) + '\n  <div class="masthead">', 1).replace("</head>", HEAD, 1)

def stub(tool):
    full = dict((t, f) for t, _, f in TOOLS)[tool]
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{full}</title>'
            f'<link rel="canonical" href="/{tool}/"><script src="/shared/redirect.js"></script>'
            f'<meta http-equiv="refresh" content="0;url=/{tool}/"></head>'
            f'<body><p>{full} has moved to <a href="/{tool}/">/{tool}/</a>.</p></body></html>\n')

def build(site):
    sh = site / "shared"; sh.mkdir(parents=True, exist_ok=True)
    for f in ("site.js", "site.css", "redirect.js"): shutil.copy(SRC / "shared" / f, sh / f)
    (sh / "inst.json").write_text(json.dumps(index(site), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    for tool, old in OLD.items():
        html = (site / old).read_text(encoding="utf-8")
        (site / tool).mkdir(exist_ok=True)
        (site / tool / "index.html").write_text(inject(html, tool, old), encoding="utf-8")
        (site / old).write_text(stub(tool), encoding="utf-8")
    f = site / "federal" / "index.html"
    f.write_text(inject(f.read_text(encoding="utf-8"), "federal", "federal/index.html"), encoding="utf-8")
    land = (SRC / "landing.html").read_text(encoding="utf-8").replace("__SITEBAR__", sitebar("home"))
    land = land.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta http-equiv="Content-Security-Policy" content="{CSP}">\n<!-- {COPY} -->', 1)
    (site / "index.html").write_text(land.replace("</head>", HEAD, 1), encoding="utf-8")
    print("  site bar on 5 pages; redirects:", ", ".join(OLD.values()))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--site", required=True)
    build(pathlib.Path(ap.parse_args().site))
