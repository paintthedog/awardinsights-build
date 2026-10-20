"""
Pull USAspending SUBAWARD data (first-tier subgrants and subcontracts reported by prime recipients).

Run:   python3 usaspending_subaward_pull.py
Needs: Python 3.8+ and `python3 -m pip install requests`

Unlike prime awards, subawards are not in the pre-built Award Data Archive, so this script asks
USAspending to generate each file (POST bulk_download/awards), waits for it, then downloads it into
./usaspending_subawards. One request per agency per fiscal year; the agencies with the most
pass-through money are requested by quarter so no single file gets too large.
Rerun any time: files already downloaded are skipped, and an interrupted download resumes.
"""
import warnings; warnings.filterwarnings("ignore")
import pathlib, time, requests

API = "https://api.usaspending.gov/api/v2/"
OUT = pathlib.Path("usaspending_subawards"); OUT.mkdir(exist_ok=True)

# Treasury code -> name exactly as USAspending spells it (taken from the prime files)
AGENCIES = {
    "049": "National Science Foundation", "075": "Department of Health and Human Services", "097": "Department of Defense",
    "089": "Department of Energy", "080": "National Aeronautics and Space Administration", "012": "Department of Agriculture",
    "013": "Department of Commerce", "014": "Department of the Interior", "091": "Department of Education",
    "068": "Environmental Protection Agency", "069": "Department of Transportation", "070": "Department of Homeland Security",
    "015": "Department of Justice", "036": "Department of Veterans Affairs", "019": "Department of State",
    "072": "Agency for International Development", "1601": "Department of Labor", "086": "Department of Housing and Urban Development",
    "418": "National Endowment for the Humanities", "417": "National Endowment for the Arts", "474": "Institute of Museum and Library Services",
}
BY_QUARTER = {"075", "097", "012", "091"}   # big pass-through agencies: smaller requests
YEARS = [2022, 2023, 2024, 2025, 2026]
TRIES = 8

def call(method, url, **kw):
    """requests.get/post with retries on connection drops and 5xx."""
    for attempt in range(TRIES):
        try:
            r = getattr(requests, method)(url, timeout=kw.pop("timeout", 120), **kw)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from server")
            return r
        except Exception as e:
            print(f"    ({method} failed, attempt {attempt+1}/{TRIES}: {str(e)[:90]})")
            time.sleep(min(300, 30 * (attempt + 1)))
    return None

def fetch(url, dest):
    """Resumable download: a dropped connection picks up where it left off (.part file)."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(20):
        have = part.stat().st_size if part.exists() else 0
        try:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with requests.get(url, stream=True, timeout=120, headers=headers) as r:
                if r.status_code == 416:
                    part.rename(dest); print("  saved", dest.name, f"{dest.stat().st_size/1e6:.1f} MB"); return True
                r.raise_for_status()
                total = int(r.headers.get("Content-Range", "/0").split("/")[-1] or 0) or (have + int(r.headers.get("Content-Length", 0)))
                mode = "ab" if (have and r.status_code == 206) else "wb"
                if mode == "wb": have = 0
                with open(part, mode) as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk); have += len(chunk)
            if total and have < total:
                raise IOError(f"connection ended at {have/1e6:.0f} of {total/1e6:.0f} MB")
            part.rename(dest); print("  saved", dest.name, f"{dest.stat().st_size/1e6:.1f} MB"); return True
        except Exception as e:
            print(f"    (interrupted, attempt {attempt+1}/20, resuming from {have/1e6:.0f} MB: {str(e)[:80]})")
            time.sleep(20 + 15 * attempt)
    print("  giving up on", dest.name, "for now; rerun later and it will resume"); return False

def windows(fy, quarterly):
    """Federal fiscal year (Oct 1 - Sep 30), whole or by quarter."""
    if not quarterly:
        return [("", f"{fy-1}-10-01", f"{fy}-09-30")]
    return [("Q1", f"{fy-1}-10-01", f"{fy-1}-12-31"), ("Q2", f"{fy}-01-01", f"{fy}-03-31"),
            ("Q3", f"{fy}-04-01", f"{fy}-06-30"), ("Q4", f"{fy}-07-01", f"{fy}-09-30")]

# The API's documentation says prime_award_types may be empty for a subaward-only file, but the live
# server rejects an empty list (422 "below min '1' items"). When that happens we name one tiny prime
# award type so the request passes; the zip then carries a small extra prime-award file, which the trim
# script skips. The first choice that works is reused for the rest of the run.
PRIME_FALLBACKS = [[], ["IDV_E"], ["-1"], ["IDV_B_C"]]
prime_choice = None

def request_file(name, start, end):
    """Ask USAspending to build the file; wait until it is ready; return its URL."""
    global prime_choice
    choices = [prime_choice] if prime_choice is not None else PRIME_FALLBACKS
    r = None
    for prime in choices:
        body = {"filters": {"agencies": [{"type": "awarding", "tier": "toptier", "name": name}],
                            "date_type": "action_date", "date_range": {"start_date": start, "end_date": end},
                            "prime_award_types": prime, "sub_award_types": ["grant", "procurement"]},
                "file_format": "csv"}
        r = call("post", API + "bulk_download/awards/", json=body)
        if r is not None and r.status_code == 200:
            if prime_choice is None:
                prime_choice = prime
                print(f"    (server accepted prime_award_types={prime}; using it for every request)")
            break
        if r is not None and r.status_code == 422 and "prime_award_types" in r.text:
            continue          # try the next fallback
        break                 # some other problem: report it below
    if r is None or r.status_code != 200:
        print(f"    request refused: {getattr(r, 'status_code', 'no response')} {getattr(r, 'text', '')[:200]}"); return None
    j = r.json(); status_url = j.get("status_url"); url = j.get("file_url")
    for _ in range(240):                       # up to ~2 hours for the largest files
        s = call("get", status_url)
        st = s.json().get("status") if s is not None and s.status_code == 200 else None
        if st == "finished": return s.json().get("file_url") or url
        if st == "failed":
            print("    USAspending reported the file failed:", s.json().get("message", "")[:200]); return None
        time.sleep(30)
    print("    still not ready after two hours; rerun later"); return None

def main():
    for code, name in AGENCIES.items():
        print(f"{name} ({code})")
        for fy in YEARS:
            for q, start, end in windows(fy, code in BY_QUARTER):
                dest = OUT / f"FY{fy}{q}_{code}_Subawards.zip"
                if dest.exists():
                    print(f"  FY{fy}{q}: already have {dest.name}"); continue
                print(f"  FY{fy}{q}: requesting {start} to {end}")
                url = request_file(name, start, end)
                if url: fetch(url, dest)
                time.sleep(5)

if __name__ == "__main__":
    main()
