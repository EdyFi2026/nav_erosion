"""
nav_erosion_model.py
====================
A reusable model for analyzing NAV erosion in covered-call / option-income ETFs
(YieldMax, Defiance, Roundhill, etc.).

Core idea:
-----------
These funds typically follow an exponential decay toward a NAV "floor":

    NAV(t) ~= F + (NAV_0 - F) * exp(-k*t)

where:
    NAV_0 = launch NAV
    F     = asymptotic floor (the long-run equilibrium NAV)
    k     = decay rate (1/days)

The plateau region is where dNAV/dt is small relative to the weekly distribution
yield - i.e. where the income you receive is no longer being mechanically eaten
by capital depreciation.

What matters for an investor is TOTAL RETURN, not NAV. So we evaluate the
strategy on a reinvested-distribution basis.

Inputs:
    - prices: DataFrame with columns ['date', 'close'] (unadjusted / actual NAV-proxy)
    - dividends: DataFrame with columns ['date', 'dividend'] (raw $/share distributions)
    - splits (optional): list of (date, ratio) tuples for reverse splits

Outputs:
    - Fitted decay parameters (F, k, NAV_0)
    - Plateau bounds (entry_high, entry_low) - the price band where the fund is
      in its productive zone
    - Health score - how well total return is being preserved
    - Backtest results - what the strategy would have returned historically
"""

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def decay_model(t, F, A, k):
    """Exponential decay toward a floor. A = (NAV_0 - F)."""
    return F + A * np.exp(-k * t)


@dataclass
class FundFit:
    symbol: str
    launch_date: pd.Timestamp
    floor: float            # F  (estimated equilibrium NAV)
    initial_premium: float  # A  (how far above floor it started)
    decay_rate: float       # k  (per day)
    half_life_days: float   # ln(2)/k
    nav_0: float            # F + A
    current_nav: float
    current_pct_above_floor: float   # (NAV - F) / F
    fit_r2: float
    n_obs: int
    # Splits adjustment factor: the cumulative multiplier needed to convert
    # historical raw prices into a "split-adjusted to today" series.
    split_adj_applied: bool = False


def detect_splits(prices: pd.DataFrame, ratio_threshold: float = 1.8) -> list:
    """Detect probable reverse splits.

    A real reverse split shows up as a clean integer-ratio jump (2x, 3x, 5x, 10x).
    To distinguish reverse splits from other regime changes (like a fund
    relaunching at a higher NAV after a redemption event):
      - the jump must be very close to an integer ratio (within 5%)
      - AND the NAV before the jump must have eroded substantially (NAV
        in the bottom 30% of the 60-day pre-jump range), which is the
        typical trigger for a reverse split.
    """
    p = prices.sort_values("date").reset_index(drop=True)
    splits = []
    for i in range(60, len(p)):
        prev, curr = p.loc[i-1, "close"], p.loc[i, "close"]
        if prev <= 0:
            continue
        ratio = curr / prev
        if ratio <= ratio_threshold:
            continue
        # Must be a clean integer ratio
        cleanest = None
        for candidate in [2, 3, 4, 5, 6, 8, 10]:
            if abs(ratio - candidate) / candidate < 0.05:
                cleanest = candidate
                break
        if cleanest is None:
            continue
        # Pre-jump context: NAV must have been low
        recent_window = p.loc[i-60:i-1, "close"]
        if prev > recent_window.quantile(0.30):
            # NAV was not depressed — probably not a reverse split
            continue
        splits.append((p.loc[i, "date"], cleanest))
    return splits


def detect_regime_changes(prices: pd.DataFrame, ratio_threshold: float = 1.5) -> list:
    """Detect non-split discontinuities (sharp positive jumps that aren't
    reverse splits). These represent fund relaunches or NAV resets — the
    model should be fit only on data AFTER the most recent regime change."""
    p = prices.sort_values("date").reset_index(drop=True)
    splits = set(d for d, _ in detect_splits(p))
    changes = []
    for i in range(60, len(p)):
        prev, curr = p.loc[i-1, "close"], p.loc[i, "close"]
        if prev <= 0:
            continue
        ratio = curr / prev
        if ratio < ratio_threshold:
            continue
        if p.loc[i, "date"] in splits:
            continue
        changes.append(p.loc[i, "date"])
    return changes


def adjust_for_splits(prices: pd.DataFrame, dividends: pd.DataFrame,
                      splits: list) -> tuple:
    """Adjust historical prices and dividends DOWN by split factors so the
    series is continuous in 'today's share units'.

    For each split on date D with ratio R, all data BEFORE D is divided by R.
    """
    p = prices.copy().sort_values("date").reset_index(drop=True)
    d = dividends.copy().sort_values("date").reset_index(drop=True)
    p["close_adj"] = p["close"].astype(float)
    d["dividend_adj"] = d["dividend"].astype(float)

    for split_date, ratio in splits:
        split_date = pd.Timestamp(split_date)
        mask_p = p["date"] < split_date
        mask_d = d["date"] < split_date
        p.loc[mask_p, "close_adj"] = p.loc[mask_p, "close_adj"] / ratio
        d.loc[mask_d, "dividend_adj"] = d.loc[mask_d, "dividend_adj"] / ratio

    return p, d


def fit_decay(prices: pd.DataFrame, symbol: str = "") -> FundFit:
    """Fit the F + A*exp(-k*t) model to a price series.

    `prices` must have columns: 'date', 'close_adj' (split-adjusted).

    The floor parameter is bounded between the 5th percentile of observed
    closes and the maximum close, to prevent degenerate fits to F=0 when
    the underlying is trending sideways or rallying.
    """
    p = prices.dropna(subset=["close_adj"]).sort_values("date").reset_index(drop=True)
    if len(p) < 20:
        raise ValueError(f"Not enough observations for {symbol}: {len(p)}")

    launch = p["date"].iloc[0]
    t = (p["date"] - launch).dt.days.values.astype(float)
    y = p["close_adj"].values.astype(float)

    nav_0_guess = float(y[0])
    # Use median of last ~25% of data as a more robust floor seed than q25
    tail = y[int(len(y) * 0.75):]
    floor_guess = float(np.median(tail))
    A_guess = max(nav_0_guess - floor_guess, 0.01)
    k_guess = 0.005

    # Floor must be at least the 5th percentile (sanity bound)
    floor_lower = float(np.percentile(y, 5)) * 0.5
    floor_upper = float(np.max(y))

    try:
        popt, _ = curve_fit(
            decay_model, t, y,
            p0=[floor_guess, A_guess, k_guess],
            bounds=([floor_lower, 0.0, 1e-5],
                    [floor_upper, nav_0_guess * 2, 1.0]),
            maxfev=10000,
        )
        F, A, k = popt
    except Exception:
        F, A, k = float(np.median(tail)), 0.0, 1e-4

    y_pred = decay_model(t, F, A, k)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    current_nav = float(y[-1])
    half_life = np.log(2) / k if k > 0 else float("inf")

    return FundFit(
        symbol=symbol,
        launch_date=pd.Timestamp(launch),
        floor=float(F),
        initial_premium=float(A),
        decay_rate=float(k),
        half_life_days=float(half_life),
        nav_0=float(F + A),
        current_nav=current_nav,
        current_pct_above_floor=(current_nav - F) / F if F > 0 else 0.0,
        fit_r2=float(r2),
        n_obs=len(p),
    )


# ---------------------------------------------------------------------------
# Plateau / entry-exit zone detection
# ---------------------------------------------------------------------------

@dataclass
class PlateauZone:
    plateau_start_date: pd.Timestamp
    plateau_start_nav: float
    entry_high: float       # buy at-or-below this
    entry_low: float        # below this means model may be breaking
    fair_value_today: float # the model's NAV expectation today
    days_into_plateau: int
    is_in_plateau_now: bool
    expected_weekly_decay_pct: float   # how fast the model says NAV will fall this week
    annualized_yield_at_entry_high: Optional[float] = None
    annualized_yield_at_entry_low: Optional[float] = None


def find_plateau(fit: FundFit, dividends: pd.DataFrame,
                 slope_threshold_weekly_pct: float = 0.5,
                 as_of_date: Optional[pd.Timestamp] = None) -> PlateauZone:
    """Identify the plateau as the moment when the model's predicted weekly
    NAV decline drops below `slope_threshold_weekly_pct` percent.

    Mathematically:
        dNAV/dt = -k * A * exp(-k*t)
        weekly_pct_drop = 7 * k * A * exp(-k*t) / NAV(t) * 100

    Solve weekly_pct_drop <= threshold for t.
    """
    F, A, k = fit.floor, fit.initial_premium, fit.decay_rate
    thr = slope_threshold_weekly_pct / 100.0

    # Solve weekly_pct_drop <= thr for t.
    if 7 * k <= thr or A <= 0:
        t_plateau = 0.0   # always "in plateau" (essentially flat)
    else:
        denom = A * (7 * k - thr)
        if denom <= 0:
            t_plateau = 0.0
        else:
            arg = thr * F / denom
            if arg <= 0 or arg >= 1:
                t_plateau = 0.0
            else:
                t_plateau = -np.log(arg) / k
                t_plateau = max(t_plateau, 0.0)

    plateau_start = fit.launch_date + pd.Timedelta(days=int(t_plateau))
    plateau_start_nav = float(decay_model(t_plateau, F, A, k))

    if as_of_date is None:
        as_of_date = pd.Timestamp.today().normalize()
    days_since_launch = max((as_of_date - fit.launch_date).days, 0)
    days_into_plateau = max(days_since_launch - int(t_plateau), 0)
    fair_value_today = float(decay_model(days_since_launch, F, A, k))
    nav_t = fair_value_today
    expected_weekly_decay_pct = (7 * k * A * np.exp(-k * days_since_launch) /
                                  nav_t * 100) if nav_t > 0 else 0.0

    # Entry band:
    #   entry_high = fair value (willing to pay up to model's expectation)
    #   entry_low  = max(F * 1.05, F + 0.3*remaining_premium_today)
    # Never buy too close to the floor (risk of model breakdown).
    remaining_premium_today = A * np.exp(-k * days_since_launch)
    entry_high = fair_value_today
    entry_low = max(F * 1.05, F + 0.3 * remaining_premium_today)
    if entry_low >= entry_high:
        entry_low = entry_high * 0.95

    is_in_plateau_now = days_since_launch >= int(t_plateau)

    last_year = dividends[dividends["date"] >=
                          (as_of_date - pd.Timedelta(days=365))]
    if len(last_year) > 0:
        ttm_div = float(last_year["dividend_adj"].sum())
        ann_yield_high = ttm_div / entry_high if entry_high > 0 else None
        ann_yield_low = ttm_div / entry_low if entry_low > 0 else None
    else:
        ann_yield_high = ann_yield_low = None

    return PlateauZone(
        plateau_start_date=plateau_start,
        plateau_start_nav=plateau_start_nav,
        entry_high=entry_high,
        entry_low=entry_low,
        fair_value_today=fair_value_today,
        days_into_plateau=days_into_plateau,
        is_in_plateau_now=is_in_plateau_now,
        expected_weekly_decay_pct=float(expected_weekly_decay_pct),
        annualized_yield_at_entry_high=ann_yield_high,
        annualized_yield_at_entry_low=ann_yield_low,
    )


# ---------------------------------------------------------------------------
# Total return reconstruction & backtest
# ---------------------------------------------------------------------------

def compute_total_return(prices: pd.DataFrame, dividends: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct a total-return index assuming distributions are
    reinvested at the close on ex-date.

    Returns a DataFrame with columns:
        date, close_adj, dividend_adj, tr_index, weekly_tr_pct
    where tr_index starts at 100.
    """
    p = prices.sort_values("date").copy().reset_index(drop=True)
    d = dividends[["date", "dividend_adj"]].copy()
    df = p.merge(d, on="date", how="left")
    df["dividend_adj"] = df["dividend_adj"].fillna(0.0)

    tr = [100.0]
    for i in range(1, len(df)):
        prev_close = df.loc[i - 1, "close_adj"]
        this_close = df.loc[i, "close_adj"]
        div = df.loc[i, "dividend_adj"]
        if prev_close <= 0:
            tr.append(tr[-1])
            continue
        # daily total return = (P_t + Div_t) / P_{t-1}
        daily_ret = (this_close + div) / prev_close
        tr.append(tr[-1] * daily_ret)
    df["tr_index"] = tr

    # Weekly resample for plateau analysis
    df_weekly = df.set_index("date").resample("W-FRI").last().reset_index()
    df_weekly["weekly_tr_pct"] = df_weekly["tr_index"].pct_change() * 100
    return df, df_weekly


def backtest(prices: pd.DataFrame, dividends: pd.DataFrame,
             min_days_before_first_trade: int = 90,
             min_r2: float = 0.70,
             breakdown_threshold_pct: float = 8.0,
             reentry_cooldown_weeks: int = 4) -> dict:
    """Walk-forward backtest with a PATIENT-HOLD strategy.

    The whole point of these funds is to collect distributions. Frequent
    trading destroys that. So:

    ENTRY (one-shot, only when not holding and not in cooldown):
        - In plateau AND
        - Model R^2 >= min_r2 AND
        - Price within [entry_low, entry_high] (proper band) AND
        - Current price <= recent 4-week high (no chasing)
    Once in, HOLD.

    EXIT (only on serious breakdown):
        - Price < floor estimate by more than breakdown_threshold_pct
          (this signals the model is wrong — true floor is lower)

    Compared to buy-and-hold over the same window.
    """
    df_daily, df_weekly = compute_total_return(prices, dividends)
    if len(df_weekly) < 20:
        return {"error": "not enough weekly data"}

    holding = False
    entry_idx = None
    entry_date = None
    cash_index = 100.0
    strat_index_at_entry = None
    trades = []
    weeks_since_exit = 1000

    launch_date = df_daily["date"].iloc[0]

    for w_idx in range(1, len(df_weekly)):
        this_date = df_weekly.loc[w_idx, "date"]
        if pd.isna(this_date):
            continue
        days_since_launch = (this_date - launch_date).days
        if days_since_launch < min_days_before_first_trade:
            continue

        history = df_daily[df_daily["date"] <= this_date].copy()
        if len(history) < 30:
            continue
        try:
            fit = fit_decay(history, symbol="")
        except Exception:
            continue

        divs_so_far = dividends[dividends["date"] <= this_date]
        zone = find_plateau(fit, divs_so_far, as_of_date=this_date)

        this_close = df_weekly.loc[w_idx, "close_adj"]
        this_tr = df_weekly.loc[w_idx, "tr_index"]

        if not holding:
            weeks_since_exit += 1
            # 4-week high check
            recent = df_weekly.loc[max(0, w_idx - 4):w_idx, "close_adj"]
            recent_high = float(recent.max())

            in_band = zone.entry_low <= this_close <= zone.entry_high * 1.03
            below_recent_high = this_close <= recent_high * 1.01
            cooldown_ok = weeks_since_exit >= reentry_cooldown_weeks
            entry_ok = (
                zone.is_in_plateau_now and
                fit.fit_r2 >= min_r2 and
                in_band and
                below_recent_high and
                cooldown_ok
            )
            if entry_ok:
                holding = True
                entry_idx = this_tr
                entry_date = this_date
                strat_index_at_entry = cash_index
            continue

        # We are holding - only exit on serious model breakdown
        floor_breakdown = this_close < fit.floor * (1 - breakdown_threshold_pct / 100)
        if floor_breakdown:
            ret = this_tr / entry_idx
            cash_index = strat_index_at_entry * ret
            trades.append({
                "entry_date": entry_date, "exit_date": this_date,
                "entry_tr_idx": entry_idx, "exit_tr_idx": this_tr,
                "return_pct": (ret - 1) * 100, "reason": "floor_breakdown",
            })
            holding = False
            entry_idx = None
            weeks_since_exit = 0

    if holding:
        last_tr = df_weekly["tr_index"].iloc[-1]
        ret = last_tr / entry_idx
        cash_index = strat_index_at_entry * ret
        trades.append({
            "entry_date": entry_date, "exit_date": df_weekly["date"].iloc[-1],
            "entry_tr_idx": entry_idx, "exit_tr_idx": last_tr,
            "return_pct": (ret - 1) * 100, "reason": "end_of_data",
        })

    bh_return = (df_weekly["tr_index"].iloc[-1] / df_weekly["tr_index"].iloc[0] - 1) * 100
    strat_return = (cash_index / 100.0 - 1) * 100

    total_weeks = len(df_weekly)
    weeks_in = sum((pd.Timestamp(t["exit_date"]) - pd.Timestamp(t["entry_date"])).days
                   for t in trades) / 7.0
    tim = weeks_in / total_weeks * 100 if total_weeks > 0 else 0

    if trades:
        wins = [t["return_pct"] for t in trades if t["return_pct"] > 0]
        losses = [t["return_pct"] for t in trades if t["return_pct"] <= 0]
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        win_rate = len(wins) / len(trades) * 100
    else:
        avg_win = avg_loss = win_rate = 0.0

    # ALSO: compute a "buy from plateau onward and hold" benchmark — the
    # natural intuition behind the user's strategy
    plateau_zone = find_plateau(fit_decay(df_daily, ""),
                                 dividends, as_of_date=df_daily["date"].iloc[-1])
    plateau_start = plateau_zone.plateau_start_date
    plateau_df = df_weekly[df_weekly["date"] >= plateau_start]
    if len(plateau_df) >= 2:
        plateau_hold_return = (plateau_df["tr_index"].iloc[-1] /
                                plateau_df["tr_index"].iloc[0] - 1) * 100
    else:
        plateau_hold_return = None

    return {
        "strategy_total_return_pct": strat_return,
        "buy_and_hold_total_return_pct": bh_return,
        "buy_at_plateau_hold_total_return_pct": plateau_hold_return,
        "n_trades": len(trades),
        "time_in_market_pct": tim,
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "trades": trades,
    }


# ---------------------------------------------------------------------------
# Top-level convenience function
# ---------------------------------------------------------------------------

def analyze_fund(symbol: str,
                 prices_raw: pd.DataFrame,
                 dividends_raw: pd.DataFrame) -> dict:
    """End-to-end analysis. prices_raw should have ['date','close'] columns
    in raw UNADJUSTED form; dividends_raw should have ['date','dividend'].

    Key insight: a reverse split for a YieldMax-style fund is effectively a
    "do-over" — the fund admits NAV got too low and resets. So the most
    informative analysis is to fit on data SINCE the most recent reverse
    split (or since launch if none). The same applies to non-split regime
    changes (fund relaunches).
    """
    prices_raw = prices_raw.copy()
    prices_raw["date"] = pd.to_datetime(prices_raw["date"])
    dividends_raw = dividends_raw.copy()
    dividends_raw["date"] = pd.to_datetime(dividends_raw["date"])

    splits = detect_splits(prices_raw)
    regime_changes = detect_regime_changes(prices_raw)

    # Find the most recent "epoch boundary" - either a reverse split or
    # a non-split regime change. Both reset the cycle, so we only analyze
    # post-boundary data.
    boundaries = [d for d, _ in splits] + list(regime_changes)
    truncation_date = max(boundaries) if boundaries else None

    if truncation_date is not None:
        prices_active = prices_raw[prices_raw["date"] >= truncation_date].reset_index(drop=True)
        dividends_active = dividends_raw[dividends_raw["date"] >= truncation_date].reset_index(drop=True)
    else:
        prices_active = prices_raw.copy()
        dividends_active = dividends_raw.copy()

    # In the active window there are by definition no splits/regime changes,
    # so we don't need to adjust prices.
    prices_active["close_adj"] = prices_active["close"].astype(float)
    dividends_active["dividend_adj"] = dividends_active["dividend"].astype(float)

    fit = fit_decay(prices_active, symbol=symbol)
    zone = find_plateau(fit, dividends_active)
    bt = backtest(prices_active, dividends_active)

    return {
        "symbol": symbol,
        "splits_detected": splits,
        "regime_changes": regime_changes,
        "truncation_date": truncation_date,
        "fit": fit,
        "zone": zone,
        "backtest": bt,
        "prices_active": prices_active,
        "dividends_active": dividends_active,
        "prices_full_history": prices_raw,
        "dividends_full_history": dividends_raw,
    }
