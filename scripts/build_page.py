"""
Assemble the Federal Award Insights page.
  python3 build_page.py --head head.html --body body.html --preview <site>/artifact_page.html --public <site_pub>
Preview: one self-contained page (inline script), for the Claude preview.
Public:  index.html + minified app.js, strict Content-Security-Policy, copyright notices, robots.txt.
"""
import argparse, hashlib, re, subprocess, pathlib
ap = argparse.ArgumentParser()
ap.add_argument("--head", required=True); ap.add_argument("--body", required=True)
ap.add_argument("--preview"); ap.add_argument("--public")
ap.add_argument("--terser", default="terser")
A = ap.parse_args()
COPY = "© 2026 Award Insights · awardinsights.org · All rights reserved."
head = open(A.head).read()
head = head.replace("<title>NSF Award Insights</title>", "<title>Federal Award Insights</title>")
head = re.sub(r'<meta name="description" content="[^"]*">',
              '<meta name="description" content="What institutions like yours receive from __NAG__ federal agencies in project grants, cooperative agreements and contracts, by year, agency and program, against peers you choose.">', head)
body = open(A.body).read()
# source lines follow the data: agency count and archive date from the Federal build's agg.json
import json, datetime
_m = json.load(open(pathlib.Path(A.public) / "data" / "agg.json"))["meta"] if A.public and (pathlib.Path(A.public) / "data" / "agg.json").exists() else {}
_d = datetime.date.fromisoformat(_m["archive"]) if _m.get("archive") else None
for t_, v_ in {"__NAG__": str(_m.get("n_agencies", "")), "__ARCH__": _d.strftime("%b %-d, %Y") if _d else ""}.items():
    head = head.replace(t_, v_); body = body.replace(t_, v_)
if A.preview:
    page = head + body.replace("__DATAV__", "dev")
    page = page.replace('<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">\n', "")
    page = page.replace("</style></head><body>", "</style>", 1).replace("</body></html>", "")
    open(A.preview, "w").write(page)
if A.public:
    out = pathlib.Path(A.public); out.mkdir(parents=True, exist_ok=True)
    m = re.search(r'<script type="module">(.*?)</script>', body, re.S)
    dv = hashlib.sha1()   # data version: every data file's bytes, so a refresh changes it
    for f in sorted((out / "data").rglob("*.json")): dv.update(f.read_bytes())
    js = m.group(1).replace("__DATAV__", dv.hexdigest()[:10])
    src = out / "app.src.js"; src.write_text(js)
    subprocess.run([A.terser, str(src), "--module", "--compress", "--mangle", "-o", str(out / "app.js")], check=True)
    src.unlink()
    app = out / "app.js"; app.write_text(f"/*! {COPY} */\n" + app.read_text())
    csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
           "base-uri 'none'; form-action 'none'")
    h = head.replace("<meta charset=utf8>", f'<meta charset=utf8>\n<meta http-equiv="Content-Security-Policy" content="{csp}">\n'
                     f'<meta name="referrer" content="strict-origin-when-cross-origin">\n<meta name="copyright" content="{COPY}">\n<!-- {COPY} -->', 1)
    v = hashlib.sha1(app.read_bytes()).hexdigest()[:10]   # content fingerprint: a new build is never served from a stale cache
    page = h + body[:m.start()] + f'<script type="module" src="app.js?v={v}"></script>' + body[m.end():]
    (out / "index.html").write_text(page)
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /data/\n")
    print("public page:", (out / "index.html").stat().st_size, "bytes; app.js:", (out / "app.js").stat().st_size, "bytes")
