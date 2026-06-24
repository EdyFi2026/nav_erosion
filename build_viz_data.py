"""Build visualization data for the artifact."""
import sys
sys.path.insert(0, "/home/claude/nav_erosion")
import json
from pathlib import Path
import pandas as pd
import numpy as np
from screener import load_data
from nav_erosion_model import analyze_fund, decay_model

results = {}
for sym in ["TSLY", "NVDY"]:
    prices, dividends = load_data(sym, Path("/home/claude/nav_erosion/data"))
    r = analyze_fund(sym, prices, dividends)
    fit = r["fit"]
    zone = r["zone"]
    pa = r["prices_active"]
    days = (pa["date"] - fit.launch_date).dt.days.values
    curve = decay_model(days, fit.floor, fit.initial_premium, fit.decay_rate)
    pts = list(zip(
        pa["date"].dt.strftime("%Y-%m-%d").tolist(),
        pa["close"].astype(float).round(4).tolist(),
        curve.round(4).tolist(),
    ))
    results[sym] = {
        "launch": fit.launch_date.strftime("%Y-%m-%d"),
        "floor": round(fit.floor, 2),
        "initial_premium": round(fit.initial_premium, 2),
        "decay_rate": round(fit.decay_rate, 6),
        "half_life": round(fit.half_life_days, 0),
        "r2": round(fit.fit_r2, 3),
        "current_nav": round(fit.current_nav, 2),
        "fair_value_today": round(zone.fair_value_today, 2),
        "entry_high": round(zone.entry_high, 2),
        "entry_low": round(zone.entry_low, 2),
        "plateau_start": zone.plateau_start_date.strftime("%Y-%m-%d"),
        "in_plateau": bool(zone.is_in_plateau_now),
        "expected_weekly_decay_pct": round(zone.expected_weekly_decay_pct, 2),
        "days_into_plateau": int(zone.days_into_plateau),
        "truncation_date": (r["truncation_date"].strftime("%Y-%m-%d")
                            if r["truncation_date"] is not None else None),
        "splits": [[d.strftime("%Y-%m-%d"), int(rt)] for d, rt in r["splits_detected"]],
        "n_obs": int(fit.n_obs),
        "series": pts,
        "backtest": {
            "strategy_pct": round(r["backtest"].get("strategy_total_return_pct", 0), 1),
            "bh_pct": round(r["backtest"].get("buy_and_hold_total_return_pct", 0), 1),
            "n_trades": r["backtest"].get("n_trades", 0),
            "tim_pct": round(r["backtest"].get("time_in_market_pct", 0), 0),
        },
    }

with open("/tmp/viz_data.json", "w") as f:
    json.dump(results, f, default=str)

for s, r in results.items():
    print(f'{s}: {len(r["series"])} points, floor=${r["floor"]:.2f}, R^2={r["r2"]:.2f}')
print("\nSaved viz data: /tmp/viz_data.json")
