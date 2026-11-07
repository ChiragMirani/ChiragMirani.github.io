"""
Download every input into the data/ folder. Public sources only, no passwords or keys.

  1. Today's version of each FRED series (current-vintage market histories; corrections remain possible).
  2. The archive of original releases (ALFRED) for economic statistics, so the model can use each number as recorded in each archived vintage.
  3. The New York Fed term premium and the Fed's broad dollar index (only for the hindsight comparison).

Run:  python download_data.py        (takes about 10 minutes, mostly for the release archives)
The Fed decision dates (data/fomc_dates.csv) come with the code; they were copied from the Fed's FOMC calendar pages.
"""
# concurrent.futures lets us download several archive files at the same time.
import concurrent.futures as cf
# io lets pandas read text we downloaded straight from memory.
import io
# re finds the list of release dates inside the archive's web page.
import re
# time lets us wait a moment before retrying a failed download.
import time
import json
import hashlib
import os
import uuid
from datetime import datetime, timezone
# urllib downloads files; it comes with Python.
import urllib.request
# Path builds file paths that work on any computer.
from pathlib import Path

# pandas reads and writes the tables.
import pandas as pd
import auction_inputs as A
import market_sources as S

# The data folder, next to this file.
DATA = Path(__file__).resolve().parent / "data"
# The folder for the release archives.
ARCHIVE = DATA / "vintages"
# Make both folders if they aren't there yet.
ARCHIVE.mkdir(parents=True, exist_ok=True)

# Current market histories. The model applies the declared availability lags; these are not complete real-time archives.
FRED = [
    "DGS10", "DGS2",                                          # Treasury yields
    "NASDAQCOM", "NASDAQNQEM",                                # stock indexes
    "DCOILWTICO", "VIXCLS", "VXVCLS", "T10YIE",               # oil, fear gauges, breakeven inflation
    "DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXCAUS", "DEXSZUS", "DEXUSAL",  # six exchange rates for the dollar index
    "GASREGW", "DHHNGSP", "OVXCLS", "WALCL",                  # candidate inputs
    "IRLTLT01DEM156N", "IRLTLT01GBM156N", "IRLTLT01JPM156N",  # foreign yields (comparison data; no fallback in main model)
    "DTWEXBGS", "DTWEXM",                                     # broad dollar index (hindsight comparison only)
]
# Economic statistics rebuilt from the release archive, and how many of the latest months to keep from each release.
ARCHIVED = {"UNRATE": 3, "PCEPILFE": 14, "IRLTLT01DEM156N": 3, "IRLTLT01GBM156N": 3, "IRLTLT01JPM156N": 3}
# The New York Fed term premium file (hindsight comparison only).
ACM = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"


def fetch(url: str) -> bytes:
    """Download one address, trying up to four times if the connection hiccups."""
    # Try a few times.
    for attempt in range(4):
        # Attempt the download.
        try:
            # Open the link, wait up to a minute, and return what comes back.
            with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
                # The raw bytes.
                return r.read()
        # If it failed, wait a little longer each time and try again.
        except Exception:
            # Wait 2, 4, 6 seconds...
            time.sleep(2 * (attempt + 1))
    # After four failures, stop with a clear message.
    raise RuntimeError("could not download " + url)


def release_dates(series: str) -> list:
    """Every date on which the archive recorded a new release of this series (from 1999 on)."""
    # The archive's download page lists every release date.
    page = fetch(f"https://alfred.stlouisfed.org/series/downloaddata?seid={series}").decode()
    # Pull out the dates and keep 1999 onward.
    return sorted(d for d in set(re.findall(r'<option value="(\d{4}-\d{2}-\d{2})"', page)) if d >= "1999-01-01")


def one_release(series: str, date: str, keep: int) -> pd.DataFrame:
    """The values recorded in one dated archive snapshot (only the latest `keep` months)."""
    # Download the series as it stood on that date.
    text = fetch(f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={date}").decode()
    # Read it into a table.
    df = pd.read_csv(io.StringIO(text))
    # Name the columns simply.
    df.columns = ["obs", "value"]
    # Make the values numbers and drop blanks.
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # Keep only the latest months, which is all the model needs.
    df = df.dropna().tail(keep)
    # Remember which release this was.
    df["vintage"] = date
    # Hand back the table.
    return df[["vintage", "obs", "value"]]


def download_snapshot():
    """Commit a complete immutable snapshot; a failed refresh never replaces the last good pointer."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    target = DATA / "snapshots" / stamp
    (target / "vintages").mkdir(parents=True)
    # Reuse already archived vintages. New daily market histories are always downloaded anew.
    previous = DATA
    pointer = DATA / "latest_snapshot.json"
    if pointer.exists():
        rel = json.loads(pointer.read_text())["snapshot"]
        previous = (DATA / rel).resolve()
        if not previous.is_relative_to((DATA / "snapshots").resolve()):
            raise ValueError("Invalid snapshot pointer")
    for s in FRED:
        raw = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}")
        frame = pd.read_csv(io.BytesIO(raw))
        if frame.shape[1] != 2 or frame.empty:
            raise ValueError("Invalid market download: " + s)
        (target / f"{s}.csv").write_bytes(raw)
    for s, keep in ARCHIVED.items():
        cache = previous / "vintages" / f"{s}.csv"
        old = pd.read_csv(cache) if cache.exists() else pd.DataFrame(columns=["vintage", "obs", "value"])
        dates = release_dates(s)
        if not dates:
            raise ValueError("No archive dates returned for " + s)
        missing = [date for date in dates if date not in set(old["vintage"])]
        with cf.ThreadPoolExecutor(8) as pool:
            parts = list(pool.map(lambda date: one_release(s, date, keep), missing))
        pd.concat([old] + parts, ignore_index=True).sort_values(["vintage", "obs"]).to_csv(target / "vintages" / f"{s}.csv", index=False)
    (target / "fomc_dates.csv").write_bytes((DATA / "fomc_dates.csv").read_bytes())
    (target / "acm.xls").write_bytes(fetch(ACM))
    A.download_calendar(target, previous, fetch)
    S.supplement_snapshot(target, fetch)
    files = {str(p.relative_to(target)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in target.rglob('*') if p.is_file()}
    manifest = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "sha256": files,
                "scope": "Current-vintage market histories and cached ALFRED vintages; private research inputs."}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temp = pointer.with_name("latest_snapshot." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps({"snapshot": "snapshots/" + stamp}), encoding="utf-8")
    os.replace(temp, pointer)
    print("Completed snapshot:", target)


if __name__ == "__main__":
    download_snapshot()
