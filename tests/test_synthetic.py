"""Validate the NAV erosion model on REALISTIC synthetic data."""
import sys
from pathlib import Path

# This test lives in tests/; the engine lives in ../src. Resolve relative to this
# file so it runs from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import numpy as np
import pandas as pd
from nav_erosion_model import (
    decay_model, fit_decay, find_plateau, backtest,
    compute_total_return, analyze_fund,
)

np.random.seed(7)

launch = pd.Timestamp("2023-01-06")
dates = pd.bdate_range(launch, periods=600)
t = (dates - launch).days.values.astype(float)

# True params: floor $11, premium $9, half-life ~150d
F_true, A_true, k_true = 11.0, 9.0, 0.0046
true_nav = decay_model(t, F_true, A_true, k_true)

noise = np.random.normal(0, 0.3, len(dates))
nav_close = true_nav + noise
nav_close = np.maximum(nav_close, F_true * 0.3)

prices = pd.DataFrame({"date": dates, "close": nav_close})

# Distributions ~1.2% of NAV weekly
dist_dates, dist_amts = [], []
for i, d in enumerate(dates):
    if d.weekday() == 4:
        dist_dates.append(d)
        dist_amts.append(round(nav_close[i] * 0.012, 4))
dividends = pd.DataFrame({"date": dist_dates, "dividend": dist_amts})

print("=== Synthetic Test ===")
print(f"Days: {len(prices)}, Dividends: {len(dividends)}")
print(f"True: F={F_true}, A={A_true}, k={k_true}, half-life={np.log(2)/k_true:.0f}d")
print(f"NAV: ${prices['close'].iloc[0]:.2f} -> ${prices['close'].iloc[-1]:.2f}")
print(f"Total distributions: ${dividends['dividend'].sum():.2f}\n")

result = analyze_fund("SYN", prices, dividends)
fit = result["fit"]
zone = result["zone"]
bt = result["backtest"]

print(f"Fitted: F=${fit.floor:.2f} (true ${F_true:.2f}, error {(fit.floor-F_true)/F_true*100:+.1f}%)")
print(f"        A=${fit.initial_premium:.2f} (true ${A_true:.2f})")
print(f"        k={fit.decay_rate:.5f} (true {k_true:.5f})")
print(f"        half-life={fit.half_life_days:.0f}d, R^2={fit.fit_r2:.3f}\n")

print(f"Plateau: started {zone.plateau_start_date.date()} at NAV ${zone.plateau_start_nav:.2f}")
print(f"  Fair value today: ${zone.fair_value_today:.2f}")
print(f"  Entry band: ${zone.entry_low:.2f} - ${zone.entry_high:.2f}")
print(f"  Expected weekly NAV decay: {zone.expected_weekly_decay_pct:.2f}%\n")

print(f"Backtest:")
print(f"  Strategy:    {bt['strategy_total_return_pct']:+.1f}%")
print(f"  Buy & Hold:  {bt['buy_and_hold_total_return_pct']:+.1f}%")
print(f"  Edge:        {bt['strategy_total_return_pct']-bt['buy_and_hold_total_return_pct']:+.1f}%")
print(f"  Trades: {bt['n_trades']}, Win rate: {bt['win_rate_pct']:.0f}%")
print(f"  Avg win: {bt['avg_win_pct']:+.1f}%, Avg loss: {bt['avg_loss_pct']:+.1f}%")
print(f"  Time in market: {bt['time_in_market_pct']:.0f}%")
for tr in bt["trades"][:10]:
    print(f"  {pd.Timestamp(tr['entry_date']).date()} -> {pd.Timestamp(tr['exit_date']).date()}: "
          f"{tr['return_pct']:+.1f}% ({tr['reason']})")
