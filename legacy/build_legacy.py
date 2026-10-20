"""
Build the three original tools and the landing page into one site folder.   © 2026 Award Insights

    python3 legacy/build_legacy.py --out build/site [--compare DIR]

- nsf.html           NSF Award Insights          legacy/templates/tpl.html      + inputs/nsf/{universe3,awards4,proginfo,coverage}.json
- designations.html  Research Activity Designations  legacy/templates/dash_tpl.html + inputs/nsf/{rad5,climbers3}.json
- portfolio.html     Research Portfolio Trends   legacy/templates/prof_tpl.html + inputs/nsf/profile4.json
- index.html         landing page                legacy/landing/index.html (copied as is)

Templates take JSON through __PLACEHOLDER__ text replacement, exactly as the pages were first built.
--compare DIR checks the output byte for byte against a folder holding the live pages (a checkout of
the public repo) and exits non-zero on any difference, so a refactor can't change a page by accident.
"""
import argparse, json, os, pathlib, sys, filecmp

ROOT = pathlib.Path(__file__).resolve().parent.parent
T = ROOT / "legacy" / "templates"
N = ROOT / "inputs" / "nsf"
HOME_TAG = '<span class="tag">Prototype</span>'
# the live pages differ slightly here (NSF's link was edited by hand later); kept as is so builds match live
HOME_LINK = '<a class="tag" href="index.html" style="text-decoration:none">Award Insights</a>'
HOME_LINK_NSF = '<a class="tag" href="index.html">Award Insights</a>'

def rd(p): return open(p, encoding="utf-8").read()
def money(d): return f"${d/1e9:.2f}B" if d >= 1e9 else f"${d/1e6:.0f}M"
def home(t, link=HOME_LINK): return t.replace(HOME_TAG, link, 1)

def build(out):
    out.mkdir(parents=True, exist_ok=True)
    u = rd(N / "universe3.json"); n = f"{len(json.loads(u)):,}"
    cov = json.load(open(N / "coverage.json"))
    nsf = (home(rd(T / "tpl.html"), HOME_LINK_NSF).replace("__N__", n).replace("__UNIVERSE__", u)
           .replace("__AWARDS__", rd(N / "awards4.json")).replace("__PROGINFO__", rd(N / "proginfo.json"))
           .replace("__COV__", json.dumps(cov))
           .replace("__NALL__", f"{cov['n_all']:,}").replace("__DALL__", money(cov["d_all"]))
           .replace("__NIN__", f"{cov['n_in']:,}").replace("__DIN__", money(cov["d_in"]))
           .replace("__DPCT__", f"{100*cov['d_in']/cov['d_all']:.0f}%"))
    pr = rd(N / "profile4.json")
    port = home(rd(T / "prof_tpl.html")).replace("__PROF__", pr).replace("__NPROF__", str(len(json.loads(pr))))
    des = home(rd(T / "dash_tpl.html")).replace("__RAD__", rd(N / "rad5.json")).replace("__CLIMB__", rd(N / "climbers3.json"))
    pages = {"nsf.html": nsf, "portfolio.html": port, "designations.html": des, "index.html": rd(ROOT / "legacy" / "landing" / "index.html")}
    for name, txt in pages.items():
        left = [m for m in ("__UNIVERSE__", "__AWARDS__", "__PROF__", "__RAD__", "__CLIMB__", "__COV__", "__NALL__") if m in txt]
        if left: sys.exit(f"{name}: unfilled placeholders {left}")
        open(out / name, "w", encoding="utf-8").write(txt)
        print(f"  {name}: {len(txt.encode())/1e6:.1f} MB")
    return list(pages)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--compare")
    a = ap.parse_args(); out = pathlib.Path(a.out)
    names = build(out)
    if a.compare:
        bad = [p for p in names if not filecmp.cmp(out / p, pathlib.Path(a.compare) / p, shallow=False)]
        if bad: sys.exit(f"differs from live: {bad}")
        print("  identical to the live pages")
