"""
build_board.py
==============
The board-builder: turns your per-ticker cached data into the multi-fund
ranked board (the master table) — and the one script that actually *calls*
entry_score.py.

What it does, end to end:
    1. Find every ticker with cached data in the data/ folder.
    2. Run the existing model (analyze_fund) on each one.
    3. Pull the per-fund fields the master table needs into a flat record.
    4. Hand the whole board to entry_score.compute_board(), which attaches
       entry_score (+ its component factors) to every fund and sorts by it.
    5. Write ranked_board_<date>.json.

This is the missing link. Before this file existed, ranked_board_*.json was
produced ad-hoc and nothing imported entry_score.py. Now the data flows:

    data/*.csv  ->  analyze_fund (nav_erosion_model.py)
                ->  build_board.py  (assembles records)
                ->  compute_board   (entry_score.py: adds entry_score, sorts)
                ->  ranked_board_<date>.json

So entry_score.py is NOT a stand-alone post-step you run separately, and it is
NOT wired into screener.py (the single-ticker report). It is imported and
called by THIS script. Run the board with:

    python build_board.py --data-dir data
    python build_board.py --data-dir data --out ranked_board_2026-06-22.json

Usage:
    python build_board.py [--data-dir DIR] [--out FILE]
"""

import sys
import json
import argparse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from screener import load_data
from nav_erosion_model import analyze_fund, find_plateau
from entry_score import compute_board


def _round(x, n=2):
    """Round, but pass through None safely."""
    return None if x is None else round(float(x), n)


def discover_tickers(data_dir: Path):
    """Every symbol with a cached *_prices.csv or *_prices.json in data_dir."""
    syms = {f.stem.split("_")[0]
            for f in list(data_dir.glob("*_prices.csv")) +
                     list(data_dir.glob("*_prices.json"))}
    return sorted(syms)


def build_record(symbol: str, data_dir: Path) -> dict:
    """Run the model on one ticker and flatten the result into a board record.

    The plateau/entry band is recomputed "as of" the fund's last data date
    (not the wall clock), so the board is deterministic and aligned to the
    data rather than to whenever you happen to run it.
    """
    prices, dividends = load_data(symbol, data_dir)
    result = analyze_fund(symbol, prices, dividends)

    fit = result["fit"]
    # Recompute the zone as-of the last observed price date for determinism.
    as_of = pd.Timestamp(result["prices_active"]["date"].iloc[-1])
    zone = find_plateau(fit, result["dividends_active"], as_of_date=as_of)

    nav = fit.current_nav
    lo, hi = zone.entry_low, zone.entry_high

    # Where is price relative to the band? (matches screener.py's logic)
    if nav > hi * 1.03:
        status = "ABOVE"
    elif nav < lo:
        status = "BELOW"
    else:
        status = "IN_BAND"

    band_pos = (nav - lo) / (hi - lo) if hi > lo else 0.0

    ttm_high = zone.annualized_yield_at_entry_high
    ttm_yield_pct = _round(ttm_high * 100, 1) if ttm_high is not None else None

    return {
        "symbol": symbol,
        "status": status,
        "in_plateau": bool(zone.is_in_plateau_now),
        "r2": _round(fit.fit_r2, 3),
        "current_nav": _round(nav, 2),
        "floor": _round(fit.floor, 2),
        "entry_low": _round(lo, 2),
        "entry_high": _round(hi, 2),
        "band_pos": _round(band_pos, 2),
        "pct_above_floor": _round(fit.current_pct_above_floor * 100, 1),
        "half_life_days": _round(fit.half_life_days, 0),
        "wk_decay_pct": _round(zone.expected_weekly_decay_pct, 2),
        "ttm_yield_pct": ttm_yield_pct,
        "n_obs": int(fit.n_obs),
        "epoch_start": fit.launch_date.date().isoformat(),
        "splits": len(result["splits_detected"]),
        "as_of_data": as_of.date().isoformat(),
        # entry_score + its components get added by compute_board() below.
    }


def build_board(data_dir: Path) -> dict:
    """Assemble the full board for every cached ticker, then score + sort it."""
    tickers = discover_tickers(data_dir)
    funds, errors = [], []
    latest_date = None

    for sym in tickers:
        try:
            rec = build_record(sym, data_dir)
            funds.append(rec)
            d = rec["as_of_data"]
            if latest_date is None or d > latest_date:
                latest_date = d
        except Exception as e:
            errors.append({"symbol": sym, "error": f"{type(e).__name__}: {e}"})

    board = {
        "as_of": latest_date,          # the newest data date across all funds
        "funds": funds,
        "errors": errors,
    }

    # >>> This is the call that wires in entry_score.py. <<<
    # It mutates each fund (adds entry_score, band_attractiveness, fit_weight,
    # plateau_gate, breakdown_gate) and re-sorts funds by entry_score desc.
    board = compute_board(board)
    return board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data",
                        help="Folder with <SYM>_prices.csv / <SYM>_dividends.csv")
    parser.add_argument("--out", default=None,
                        help="Output path (default: ranked_board_<as_of>.json)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        parser.error(f"data dir not found: {data_dir}")

    board = build_board(data_dir)

    out = args.out or f"ranked_board_{board['as_of']}.json"
    with open(out, "w") as f:
        json.dump(board, f, indent=2, default=str)

    # Console summary so a run is legible at a glance.
    print(f"Board as of {board['as_of']}  ->  {out}")
    print(f"{'rank':>4}  {'sym':<6}{'entry':>7}{'band_attr':>11}"
          f"{'fit_w':>8}{'status':>9}{'plat':>6}")
    print("-" * 51)
    for i, r in enumerate(board["funds"], 1):
        print(f"{i:>4}  {r['symbol']:<6}"
              f"{r.get('entry_score', float('nan')):>7.3f}"
              f"{r.get('band_attractiveness', float('nan')):>11.3f}"
              f"{r.get('fit_weight', float('nan')):>8.3f}"
              f"{r['status']:>9}"
              f"{('yes' if r['in_plateau'] else 'no'):>6}")
    if board["errors"]:
        print(f"\n{len(board['errors'])} error(s):")
        for e in board["errors"]:
            print(f"  {e['symbol']}: {e['error']}")


if __name__ == "__main__":
    main()
