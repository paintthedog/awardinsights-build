"""
Pull USAspending award data without the website.

Run:   python3 usaspending_pull.py [--out DIR] [--years 2025 2026] [--agency "Small Business Administration" ...]
Needs: Python 3.8+ and `python3 -m pip install requests`

Fetches the pre-built full-year Award Data Archive files (one zip per agency
per fiscal year) into --out (default ./usaspending_downloads). A file is skipped
only when that exact archive (same date in the name) is already there, so a newer
monthly archive is fetched. Retries every request, so it survives USAspending's
dropped connections; just rerun if it gives up.
"""
import warnings; warnings.filterwarnings("ignore")
import argparse, pathlib, json, time, requests

API = "https://api.usaspending.gov/api/v2/"
ap = argparse.ArgumentParser(); ap.add_argument("--out", default="usaspending_downloads")
ap.add_argument("--years", type=int, nargs="*"); ap.add_argument("--agency", nargs="*", help="only these agencies (names as below)")
ARGS = ap.parse_args()
OUT = pathlib.Path(ARGS.out); OUT.mkdir(parents=True, exist_ok=True)

# Agencies by name (matched case-insensitively against USAspending's list; the file
# name carries the Treasury code). Order = rough priority for university research.
AGENCIES = [
    "National Science Foundation", "Department of Health and Human Services", "Department of Defense",
    "Department of Energy", "National Aeronautics and Space Administration", "Department of Agriculture",
    "Department of Commerce", "Department of the Interior", "Department of Education",
    "Environmental Protection Agency", "Department of Transportation", "Department of Homeland Security",
    "Department of Justice", "Department of Veterans Affairs", "Department of State",
    "Agency for International Development", "Department of Labor", "Department of Housing and Urban Development",
    "National Endowment for the Humanities", "National Endowment for the Arts", "Institute of Museum and Library Services",
    # added 2026-10-24: agencies paying colleges that the first pull missed (~$1.4B over FY2022-25)
    "Small Business Administration", "General Services Administration", "Executive Office of the President",
    "Appalachian Regional Commission", "Corporation for National and Community Service", "Social Security Administration",
    "National Archives and Records Administration", "Department of the Treasury", "Nuclear Regulatory Commission",
    "Smithsonian Institution",
]
YEARS = ARGS.years or [2022, 2023, 2024, 2025, 2026]
TYPES = ["assistance", "contracts"]   # grants/coop agreements, and procurement contracts
TRIES = 5

def call(method, url, **kw):
    """requests.get/post with retries on connection drops and 5xx."""
    for attempt in range(TRIES):
        try:
            r = getattr(requests, method)(url, timeout=kw.pop("timeout", 90), **kw)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from server")
            return r
        except Exception as e:
            print(f"    ({method} failed, attempt {attempt+1}/{TRIES}: {str(e)[:90]})")
            time.sleep(30 * (attempt + 1))   # back off harder: refused connections usually mean rate limiting
    return None

def fetch(url, dest):
    """Resumable download: a dropped connection picks up where it left off (.part file)."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(20):
        have = part.stat().st_size if part.exists() else 0
        try:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with requests.get(url, stream=True, timeout=120, headers=headers) as r:
                if r.status_code == 416:            # server says we already have everything
                    part.rename(dest); print("  saved", dest.name, f"{dest.stat().st_size/1e6:.1f} MB"); return True
                r.raise_for_status()
                total = int(r.headers.get("Content-Range", "/0").split("/")[-1] or 0) or (have + int(r.headers.get("Content-Length", 0)))
                mode = "ab" if (have and r.status_code == 206) else "wb"
                if mode == "wb": have = 0
                with open(part, mode) as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk); have += len(chunk)
                        if total and have % (50 << 20) < (1 << 20): print(f"    {have/1e6:.0f} / {total/1e6:.0f} MB", flush=True)
            if total and have < total:
                raise IOError(f"connection ended at {have/1e6:.0f} of {total/1e6:.0f} MB")
            part.rename(dest); print("  saved", dest.name, f"{dest.stat().st_size/1e6:.1f} MB"); return True
        except Exception as e:
            print(f"    (interrupted, attempt {attempt+1}/20, resuming from {have/1e6:.0f} MB: {str(e)[:80]})")
            time.sleep(20 + 15 * attempt)
    print("  giving up on", dest.name, "for now; rerun later and it will resume"); return False

def agency_table():
    r = call("post", API + "bulk_download/list_agencies/", json={"type": "award_agencies"})
    if r is None: raise SystemExit("could not reach the API; try again later")
    ag = r.json().get("agencies", {})
    return ag.get("cfo_agencies", []) + ag.get("other_agencies", [])

def main():
    table = agency_table()
    for name in (ARGS.agency or AGENCIES):
        hits = [a for a in table if a["name"].lower() == name.lower()] or [a for a in table if name.lower() in a["name"].lower()]
        if not hits:
            print(f"{name}: not found in USAspending's agency list; skipping"); continue
        a = hits[0]; aid = a.get("toptier_agency_id", a.get("id")); code = a.get("toptier_code", "")
        print(f"{a['name']} (code {code}, id {aid})")
        for TYPE in TYPES:
          tag = "Assistance" if TYPE == "assistance" else "Contracts"
          for fy in YEARS:
            r = call("post", API + "bulk_download/list_monthly_files/", json={"agency": str(aid), "fiscal_year": fy, "type": TYPE})
            if r is None:
                print(f"  {tag} FY{fy}: could not list files; rerun later"); continue
            if r.status_code != 200:
                print(f"  {tag} FY{fy}: API said {r.status_code}: {r.text[:200]}"); continue
            full = [f for f in r.json().get("monthly_files", []) if "_Full_" in f["file_name"]]
            if not full:
                print(f"  {tag} FY{fy}: no full-year file listed"); continue
            f = full[0]
            if (OUT / f["file_name"]).exists():
                print(f"  {tag} FY{fy}: already have {f['file_name']}"); continue
            if f["agency_name"].lower() != a["name"].lower():
                print(f"  {tag} FY{fy}: API returned {f['agency_name']!r}, not {a['name']!r}; skipping"); continue
            print(f"  {tag} FY{fy}: {f['file_name']} (updated {f['updated_date']})")
            fetch(f["url"], OUT / f["file_name"]); time.sleep(5)   # breathe between files

if __name__ == "__main__":
    main()
