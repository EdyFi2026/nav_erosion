"""
screener.py
============
Main CLI / screener entry point.

Usage:
    # Analyze a single ticker (requires data cached as JSON in ./data/)
    python screener.py TSLY

    # The expected files are:
    #   data/TSLY_prices.json    (FMP historical-price-eod-non-split-adjusted response)
    #   data/TSLY_dividends.json (FMP dividends-company response)

How to get the data using the FMP MCP (in Claude):
    Use the JP FMP MCP `chart` tool with endpoint='historical-price-eod-non-split-adjusted'
    Use the JP FMP MCP `calendar` tool with endpoint='dividends-company'
    Save each response to the data/ folder.
"""
import sys
import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nav_erosion_model import analyze_fund

# Default data cache lives at <project_root>/data (this file is in src/).
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_data(symbol: str, base_dir: Path) -> tuple:
    """Load FMP data for prices and dividends. Prefer CSV, fall back to JSON."""
    pf_csv = base_dir / f"{symbol}_prices.csv"
    pf_json = base_dir / f"{symbol}_prices.json"
    df_csv = base_dir / f"{symbol}_dividends.csv"
    df_json = base_dir / f"{symbol}_dividends.json"

    if pf_csv.exists():
        prices = pd.read_csv(pf_csv, parse_dates=["date"])
    elif pf_json.exists():
        with open(pf_json) as f:
            rows = json.load(f)
        prices = pd.DataFrame([
            {"date": pd.Timestamp(r["date"]),
             "close": float(r.get("adjClose", r.get("close", r.get("price", 0))))}
            for r in rows
        ])
    else:
        raise FileNotFoundError(
            f"No price data for {symbol} at {pf_csv} or {pf_json}")

    if df_csv.exists():
        dividends = pd.read_csv(df_csv, parse_dates=["date"])
    elif df_json.exists():
        with open(df_json) as f:
            rows = json.load(f)
        dividends = pd.DataFrame([
            {"date": pd.Timestamp(r["date"]),
             "dividend": float(r.get("dividend", r.get("adjDividend", 0)))}
            for r in rows
        ])
    else:
        raise FileNotFoundError(
            f"No dividend data for {symbol} at {df_csv} or {df_json}")

    prices = prices.sort_values("date").reset_index(drop=True)
    dividends = dividends.sort_values("date").reset_index(drop=True)
    return prices, dividends


def load_json_data(symbol: str, base_dir: Path) -> tuple:
    """Legacy: kept for backwards-compat."""
    return load_data(symbol, base_dir)


def format_report(result: dict, verbose: bool = False) -> str:
    """Build a human-readable text report from analyze_fund result."""
    fit = result["fit"]
    zone = result["zone"]
    bt = result["backtest"]
    symbol = result["symbol"]
    splits = result["splits_detected"]

    lines = []
    lines.append("=" * 72)
    lines.append(f"  {symbol} — NAV-Erosion Analysis")
    lines.append("=" * 72)

    lines.append(f"\nData: {fit.n_obs} trading days analyzed")
    if result.get("truncation_date") is not None:
        lines.append(f"⚠️  History truncated to start at {result['truncation_date'].date()}")
        lines.append(f"   (most recent reverse split or fund relaunch — prior data is in different share units)")
    lines.append(f"Analysis window starts:  {fit.launch_date.date()}")
    lines.append(f"Starting NAV (this epoch): ${fit.nav_0:.2f}")
    lines.append(f"Current NAV:        ${fit.current_nav:.2f}  ({(fit.current_nav/fit.nav_0-1)*100:+.1f}% from epoch start)")
    if splits:
        lines.append(f"Reverse splits in history: {[(d.date().isoformat(), f'1:{r}') for d,r in result.get('splits_detected', [])]}")
    if result.get('regime_changes'):
        lines.append(f"Non-split regime changes:  {[d.date().isoformat() for d in result['regime_changes']]}")

    lines.append("\n--- Decay Model ---")
    lines.append(f"Estimated floor:        ${fit.floor:.2f}")
    lines.append(f"Initial NAV premium:    ${fit.initial_premium:.2f} (launch was ${fit.initial_premium/(fit.floor):.0%} above floor)")
    lines.append(f"Decay rate (per day):   {fit.decay_rate:.5f}")
    lines.append(f"Half-life:              {fit.half_life_days:.0f} days "
                 f"({fit.half_life_days/7:.0f} weeks, {fit.half_life_days/30:.1f} months)")
    lines.append(f"Fit quality (R²):       {fit.fit_r2:.3f}  "
                 f"{'(strong)' if fit.fit_r2 > 0.85 else '(moderate)' if fit.fit_r2 > 0.6 else '(weak — model may not apply)'}")
    lines.append(f"Current % above floor:  {fit.current_pct_above_floor*100:+.1f}%")

    lines.append("\n--- Plateau Detection ---")
    in_plateau = "YES" if zone.is_in_plateau_now else "NOT YET"
    lines.append(f"In plateau now?         {in_plateau}")
    lines.append(f"Plateau started:        {zone.plateau_start_date.date()}  "
                 f"(at NAV ${zone.plateau_start_nav:.2f})")
    lines.append(f"Days into plateau:      {zone.days_into_plateau}")
    lines.append(f"Expected weekly NAV decay: {zone.expected_weekly_decay_pct:.2f}%/wk now")

    lines.append("\n--- Suggested Entry / Exit Range ---")
    lines.append(f"Fair value today:       ${zone.fair_value_today:.2f}  (model's expectation)")
    lines.append(f"BUY zone:               ${zone.entry_low:.2f}  –  ${zone.entry_high:.2f}")
    lines.append(f"  (above this band = paying premium; below = floor breakdown risk)")
    lines.append(f"EXIT trigger:           below ${fit.floor*0.92:.2f}  "
                 f"(8% below estimated floor — indicates underlying weakening)")

    if zone.annualized_yield_at_entry_high:
        lines.append(f"TTM yield at $entry_high: {zone.annualized_yield_at_entry_high*100:.0f}%")
        lines.append(f"TTM yield at $entry_low:  {zone.annualized_yield_at_entry_low*100:.0f}%")

    lines.append("\n--- Where Is It Now? ---")
    nav = fit.current_nav
    if nav > zone.entry_high * 1.03:
        lines.append(f"⚠️  Currently at ${nav:.2f}, ABOVE entry-high (${zone.entry_high:.2f}). "
                     f"Wait for a pullback into the band.")
    elif zone.entry_low <= nav <= zone.entry_high * 1.03:
        lines.append(f"✓ Currently at ${nav:.2f}, INSIDE the buy zone. Conditions look favorable.")
    elif nav < zone.entry_low:
        lines.append(f"⚠️  Currently at ${nav:.2f}, BELOW entry-low (${zone.entry_low:.2f}). "
                     f"Model may be breaking — wait for a new equilibrium to confirm before buying.")

    lines.append("\n--- Walk-Forward Backtest (Patient-Hold strategy) ---")
    if "error" not in bt:
        lines.append(f"Strategy total return:        {bt['strategy_total_return_pct']:+.1f}%")
        lines.append(f"Buy-and-hold total return:    {bt['buy_and_hold_total_return_pct']:+.1f}%")
        if bt.get('buy_at_plateau_hold_total_return_pct') is not None:
            lines.append(f"Buy-at-plateau-and-hold:      {bt['buy_at_plateau_hold_total_return_pct']:+.1f}%")
        edge = bt['strategy_total_return_pct'] - bt['buy_and_hold_total_return_pct']
        lines.append(f"Edge over buy-and-hold:       {edge:+.1f}%")
        lines.append(f"# trades:                     {bt['n_trades']}")
        if bt['n_trades']:
            lines.append(f"Win rate:                     {bt['win_rate_pct']:.0f}%")
            lines.append(f"Avg win / loss:               {bt['avg_win_pct']:+.1f}% / {bt['avg_loss_pct']:+.1f}%")
        lines.append(f"Time in market:               {bt['time_in_market_pct']:.0f}%")
        if verbose and bt['trades']:
            lines.append("\nTrade log:")
            for t in bt['trades']:
                lines.append(f"  {pd.Timestamp(t['entry_date']).date()} → "
                             f"{pd.Timestamp(t['exit_date']).date()}: "
                             f"{t['return_pct']:+.1f}% ({t['reason']})")
    else:
        lines.append(f"  (insufficient data for backtest)")

    lines.append("\n--- Caveats ---")
    lines.append("• The exponential-decay model assumes the underlying asset is in a")
    lines.append("  steady regime. If the underlying makes a sharp move (large rally or")
    lines.append("  crash), the floor will reset and these levels become stale.")
    lines.append("• 'Total return' here assumes distributions are reinvested. If you")
    lines.append("  spend the distributions instead, your TR will be lower.")
    lines.append("• Distributions are taxed as ordinary income (often >20% rate).")
    lines.append("  After-tax returns are notably lower than the pre-tax figures shown.")
    lines.append("• These funds can and do reverse-split when NAV gets too low — this")
    lines.append("  resets the cycle and the 'floor' is not really a floor.")
    lines.append("• Past behavior of the decay parameters is not a guarantee of future")
    lines.append("  behavior. Re-run this analysis monthly to catch regime changes.")
    lines.append("• Not investment advice. This is a research framework.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default=None,
                        help="Ticker symbol (e.g. TSLY)")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                        help="Directory containing <SYM>_prices.json + <SYM>_dividends.json")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show full trade log")
    parser.add_argument("--list", action="store_true",
                        help="List symbols with cached data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(exist_ok=True)

    if args.list:
        syms = sorted({f.stem.split("_")[0]
                       for f in list(data_dir.glob("*_prices.json")) +
                                 list(data_dir.glob("*_prices.csv"))})
        if syms:
            print("Cached symbols:", ", ".join(syms))
        else:
            print(f"No cached data in {data_dir}")
        return

    if not args.symbol:
        parser.error("symbol required (or use --list)")

    prices, dividends = load_data(args.symbol.upper(), data_dir)
    result = analyze_fund(args.symbol.upper(), prices, dividends)
    print(format_report(result, verbose=args.verbose))


if __name__ == "__main__":
    main()
