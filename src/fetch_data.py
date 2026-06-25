"""
fetch_data.py
=============
Pull raw prices + distributions for option-income ETFs from Financial Modeling
Prep (FMP) and write them into the data/ folder in the exact format the
screener expects:

    data/<SYM>_prices.csv      columns: date,close      (raw, NON-split-adjusted)
    data/<SYM>_dividends.csv   columns: date,dividend   (raw distribution amounts)

This is the repeatable data-collection step. Run it on YOUR machine (it reaches
FMP directly with your own API key) instead of pulling fund-by-fund through a
chat connector. Re-run it monthly to refresh the whole universe.

Why these endpoints (do not "fix" them to the adjusted versions):
    Prices    -> stable/historical-price-eod/non-split-adjusted
                 RAW traded price. A reverse split shows up as a clean ~Nx jump,
                 which is exactly what the model's split detector needs. (Note:
                 this endpoint labels the close field "adjClose" — the parser
                 tries "close" first, then falls back to "adjClose".)
    Dividends -> stable/dividends
                 Uses the raw "dividend" field, NOT "adjDividend". The raw amount
                 pairs correctly with the raw price series across splits.

Setup (free FMP tier is enough):
    macOS / Linux:        export FMP_API_KEY=your_key_here
    Windows PowerShell:   $env:FMP_API_KEY = "your_key_here"
    Windows CMD:          set FMP_API_KEY=your_key_here

Usage:
    python fetch_data.py TSLY                      # one ticker
    python fetch_data.py TSLY NVDY MSTY ULTY       # several
    python fetch_data.py --all                     # the whole embedded universe
    python fetch_data.py --all --data-dir data     # explicit output folder
    python fetch_data.py --api-key XXXX TSLY        # key on the command line
    python fetch_data.py --list                     # print the embedded universe

Standard library only — no pip installs needed.
"""

import os
import sys
import csv
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

FMP_BASE = "https://financialmodelingprep.com/stable"


# ---------------------------------------------------------------------------
# The universe — option-income / covered-call ETFs by issuer.
#
# This is a broad starting list, not a guarantee every ticker is currently
# live; FMP simply returns nothing for ones it can't find, and the script
# reports that and moves on. Add/remove freely — it's just a Python list.
# ---------------------------------------------------------------------------

UNIVERSE = {
    "YieldMax": [
        "TSLY", "NVDY", "MSTY", "CONY", "ULTY", "YMAX", "YMAG", "AMZY", "NFLY",
        "GOOY", "APLY", "FBY", "MRNY", "OARK", "AIYY", "DISO", "JPMO", "XOMO",
        "PYPY", "SQY", "MARO", "AMDY", "GDXY", "SMCY", "FIAT", "ABNY", "BABO",
        "MSFO", "PLTY", "HOOY", "CVNY", "DIPS", "CRSH", "SNOY", "TSMY", "BIGY",
        "LFGY", "GPTY", "RDTY", "SOXY", "COIY", "BRKY", "FIVY", "RNTY",
    ],
    "Defiance": [
        "QQQY", "JEPY", "IWMY", "WDTE", "SPYT", "QQQT", "USOY", "GLDY", "BTGD",
        "AAPW", "TSLW", "NVW", "MSFW", "AMZW", "METW", "GOOW", "AVGW", "COIW",
        "HOOW", "PLTW",
    ],
    "Roundhill": [
        "QDTE", "XDTE", "RDTE", "YBTC", "YETH", "WEEK", "MAGY", "COVR",
    ],
    "GraniteShares": [
        "TSYY", "NVYY", "AAYY", "MSYY", "METY", "AMYY", "PLYY", "COYY", "HODY",
    ],
    "REX": [
        "FEPI", "AIPI", "BMAX",
    ],
    "NEOS": [
        "SPYI", "QQQI", "IWMI", "BTCI", "CSHI", "IYRI", "HYBI", "TLTI",
    ],
    "GlobalX": [
        "QYLD", "XYLD", "RYLD", "QYLG", "XYLG", "RYLG", "QRMI", "XRMI",
    ],
    "JPMorgan": [
        "JEPI", "JEPQ",
    ],
    "Amplify_Other": [
        "DIVO", "IDVO", "QDPL",
    ],
}


def all_tickers() -> list:
    """Flatten the universe into a de-duplicated, ordered ticker list."""
    seen, out = set(), []
    for syms in UNIVERSE.values():
        for s in syms:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(endpoint: str, symbol: str, api_key: str) -> list:
    """GET an FMP stable endpoint for one symbol; return parsed JSON list.

    Raises RuntimeError with a human-readable message on the common failures
    so a bad key or a quota problem is obvious instead of a raw traceback.
    """
    url = f"{FMP_BASE}/{endpoint}?symbol={symbol}&apikey={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "nav-erosion-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        msg = {
            401: "API key rejected (401). Check FMP_API_KEY.",
            403: "Not on your plan or quota exceeded (403).",
            429: "Rate-limited (429). Wait a bit and retry.",
        }.get(code, f"HTTP {code} from FMP.")
        raise RuntimeError(msg)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}. Check your connection.")

    if isinstance(data, dict) and data.get("Error Message"):
        raise RuntimeError(str(data["Error Message"]))
    if not isinstance(data, list):
        raise RuntimeError("Unexpected response shape (expected a list).")
    return data


# ---------------------------------------------------------------------------
# Per-ticker fetch + write
# ---------------------------------------------------------------------------

def fetch_prices(symbol: str, api_key: str) -> list:
    """Return [(date, close), ...] oldest-first from the non-split-adjusted feed."""
    rows = _get("historical-price-eod/non-split-adjusted", symbol, api_key)
    out = []
    for r in rows:
        # This endpoint labels the close "adjClose"; try "close" first anyway.
        close = r.get("close", r.get("adjClose", r.get("price")))
        d = r.get("date")
        if d is not None and close is not None:
            out.append((d, float(close)))
    out.sort(key=lambda x: x[0])  # oldest-first
    return out


def fetch_dividends(symbol: str, api_key: str) -> list:
    """Return [(date, dividend), ...] oldest-first using the RAW dividend field.

    An empty dividend history is valid (a brand-new fund may not have paid yet).
    """
    rows = _get("dividends", symbol, api_key)
    out = []
    for r in rows:
        d = r.get("date")
        amt = r.get("dividend", r.get("adjDividend"))
        if d is not None and amt is not None:
            out.append((d, float(amt)))
    out.sort(key=lambda x: x[0])
    return out


def _write_csv(path: Path, header: tuple, rows: list) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def fetch_one(symbol: str, api_key: str, data_dir: Path) -> dict:
    """Fetch + write both CSVs for one ticker. Returns a small status dict."""
    symbol = symbol.upper()
    prices = fetch_prices(symbol, api_key)
    if not prices:
        return {"symbol": symbol, "ok": False, "reason": "no price data"}
    dividends = fetch_dividends(symbol, api_key)

    _write_csv(data_dir / f"{symbol}_prices.csv", ("date", "close"), prices)
    _write_csv(data_dir / f"{symbol}_dividends.csv", ("date", "dividend"), dividends)
    return {
        "symbol": symbol, "ok": True,
        "n_prices": len(prices), "n_dividends": len(dividends),
        "first": prices[0][0], "last": prices[-1][0],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_dotenv(path: Path = None) -> None:
    """Minimal .env loader (no dependencies): read KEY=VALUE lines into os.environ.

    Looks for a .env next to this script, then in the current directory.
    Existing real environment variables win — .env only fills in what's missing,
    so `$env:FMP_API_KEY` or `--api-key` still override the file.
    """
    candidates = [path] if path else [Path(__file__).with_name(".env"), Path(".env")]
    for p in candidates:
        if p is None or not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return  # first file found wins


def resolve_api_key(cli_key) -> str:
    load_dotenv()
    key = cli_key or os.environ.get("FMP_API_KEY")
    if not key:
        sys.exit(
            "No API key. Set FMP_API_KEY or pass --api-key.\n"
            "  macOS/Linux:  export FMP_API_KEY=your_key_here\n"
            "  PowerShell:   $env:FMP_API_KEY = \"your_key_here\"\n"
            "  CMD:          set FMP_API_KEY=your_key_here"
        )
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*", help="Ticker symbols to fetch")
    parser.add_argument("--all", action="store_true",
                        help="Fetch the entire embedded universe")
    parser.add_argument("--list", action="store_true",
                        help="Print the embedded universe and exit")
    parser.add_argument("--api-key", default=None, help="FMP API key (overrides env)")
    parser.add_argument("--data-dir", default="data", help="Output folder (default: data)")
    parser.add_argument("--sleep", type=float, default=0.3,
                        help="Seconds between calls (free-tier friendly)")
    args = parser.parse_args()

    if args.list:
        for issuer, syms in UNIVERSE.items():
            print(f"{issuer:<14} ({len(syms):>2}): {', '.join(syms)}")
        print(f"\nTotal unique: {len(all_tickers())}")
        return

    tickers = all_tickers() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("Give tickers, or --all, or --list.")

    api_key = resolve_api_key(args.api_key)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {len(tickers)} ticker(s) into {data_dir.resolve()}\n")
    ok, failed = [], []
    for i, sym in enumerate(tickers, 1):
        try:
            res = fetch_one(sym, api_key, data_dir)
            if res["ok"]:
                ok.append(res)
                print(f"[{i:>3}/{len(tickers)}] {sym:<6} ✓ "
                      f"{res['n_prices']:>4} px, {res['n_dividends']:>3} div "
                      f"({res['first']} → {res['last']})")
            else:
                failed.append((sym, res["reason"]))
                print(f"[{i:>3}/{len(tickers)}] {sym:<6} — skipped ({res['reason']})")
        except RuntimeError as e:
            failed.append((sym, str(e)))
            print(f"[{i:>3}/{len(tickers)}] {sym:<6} ✗ {e}")
        time.sleep(args.sleep)

    print(f"\nDone. {len(ok)} written, {len(failed)} skipped/failed.")
    if failed:
        print("Not written:")
        for sym, why in failed:
            print(f"  {sym}: {why}")
    print(f"\nNext: python run.py --no-fetch   "
          f"(or: python src/build_board.py --data-dir {args.data_dir})")


if __name__ == "__main__":
    main()
