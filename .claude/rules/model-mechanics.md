# Rule: Model Mechanics & Scoring

Load this when working on the decay fit, plateau detection, `entry_score`, or the
erosion classifier.

## The decay model

NAV is modeled as exponential decay toward a floor:

```
NAV(t) = F + A * exp(-k * t)
```

- `F` — asymptotic floor (curve-fit). Bounded: lower = 5th-percentile of closes,
  upper = max close. This prevents the degenerate `F ≈ 0` fit when the underlying
  trends sideways or rallies.
- `A` — initial premium = `NAV_0 - F` (how far above the floor it launched).
- `k` — decay rate per day; **half-life = ln(2) / k**.
- Floor seed: median of the last ~25% of observations (robust against early noise).

Everything is evaluated on a **total-return basis** (distributions reinvested at
the close on ex-date), never on NAV alone.

## Plateau definition

The plateau begins when the model's predicted **weekly** NAV decline drops below
0.5%. From there, distribution income dominates capital decay and total return
turns positive on average. `find_plateau()` solves for that `t` and accepts an
`as_of_date` so it works inside the walk-forward backtest.

## Entry band

- `entry_high = fair_value_today` (the model's NAV expectation today).
- `entry_low = max(F * 1.05, F + 0.3 * remaining_premium_today)` — never buy too
  close to the floor, where model-breakdown risk is highest.

## entry_score (the composite — replaced legacy signal_score)

Each factor is independently 0–1; any single zero hard-zeros the composite:

```
entry_score = band_attractiveness × fit_weight × plateau_gate × breakdown_gate
```

- `band_pos = (price − entry_low) / (entry_high − entry_low)`
  - 0 = bottom of band, 1 = fair value, negative = below band, >1 = above band
- `fit_weight = clamp((R² − 0.50) / 0.40, 0, 1)`
- `band_attractiveness` peaks at `band_pos = 0.25` (lower quarter of the band),
  using five documented control knots — keep that documentation inline.

Prefer this transparent form over any opaque legacy signal.

## Erosion buckets (the essential filter)

The classifier segments the universe into five buckets. **This filter is what
keeps focus on target funds** — low-erosion index-like funds (high R², low yield)
otherwise float to the top of rankings by trivially fitting the decay curve.

| Bucket | Meaning | Target? |
|--------|---------|---------|
| `LOW_EROSION` | Index-like (XRMI, QRMI), high R² | No |
| `MATURE_NEAR_FLOOR` | Within ~12% of floor | **Primary target** |
| `MID_EROSION` | In between | Watch |
| `EARLY_HIGH_PREMIUM` | >45% above floor, most NAV risk | No (too early) |
| `BELOW_FLOOR` | Model breaking down | No |

## Validation discipline

`test_synthetic.py` generates data with known F/A/k and confirms recovery within
~1% (R² ≈ 0.98). Run it after any change to the fit or plateau math before
trusting real-data output.
