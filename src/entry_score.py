"""
entry_score.py
==============
A transparent "best entry candidate right now" marker for the NAV-erosion
screener board.

Why this file exists
--------------------
The original ``signal_score`` blended two different ideas — *how attractively
priced* a fund is and *how much we trust the model* — into one opaque number.
That blend is why TSLY (strong fit, but trading ABOVE its band) could outrank
NVDY (sitting INSIDE its band, but with a fit too weak to believe). The detail
report told one story; the ranked board told another.

This module fixes that WITHOUT touching ``signal_score``. The legacy number is
left exactly as it was (rename/retire it on your own schedule). Instead we add
a new, well-defined marker, ``entry_score``, built by composing the clean
per-axis quantities your board already computes:

    entry_score = band_attractiveness          # valuation: where price sits in the band
                  * fit_weight                  # trust:     can we believe the band at all
                  * plateau_gate                # regime:    is the fund past early erosion
                  * breakdown_gate              # safety:    is price below the floor-break line

Every factor is in [0, 1], so ``entry_score`` is in [0, 1]. A factor of 0 in
any term hard-zeros the score — i.e. an untrustworthy fit, a pre-plateau fund,
or a floor breakdown each disqualify a fund on their own, which is exactly the
behaviour the walk-forward backtest already uses for its ENTRY rule.

Read ``entry_score`` as "where this fund sits relative to the model's entry
logic," NOT as "how good a buy this is." It is a research signal, not advice.

Drop-in usage
-------------
This module is pure standard library (no pandas/numpy needed), so it imports
anywhere. In whatever script builds ``ranked_board_<date>.json``, after you've
assembled the per-fund records, do:

    from entry_score import compute_board
    board = compute_board(board)          # adds entry_score + band_attractiveness,
                                          # then re-sorts funds by entry_score desc

Or score a single record:

    from entry_score import score_record
    rec = score_record(rec)               # mutates/returns rec with the new fields

Run it directly to see a worked example on your real funds plus a few
illustrative rows:

    python entry_score.py
"""

from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp x into [lo, hi]."""
    return max(lo, min(hi, x))


def _interp(x: float, knots: List[tuple]) -> float:
    """Piecewise-linear interpolation over a list of (x, y) knots sorted by x.

    Below the first knot returns the first y; above the last returns the last y
    (flat extrapolation). Used to give ``band_attractiveness`` an explicit,
    auditable shape instead of a hard-to-explain closed form.
    """
    if x <= knots[0][0]:
        return knots[0][1]
    if x >= knots[-1][0]:
        return knots[-1][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            frac = (x - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return knots[-1][1]  # unreachable, defensive


# ---------------------------------------------------------------------------
# 1. band_attractiveness — the valuation axis
# ---------------------------------------------------------------------------
#
# Input is ``band_pos``, the price's normalized position inside the entry band:
#
#       band_pos = (price - entry_low) / (entry_high - entry_low)
#
#   band_pos = 0.0  -> price is AT entry_low  (bottom of the buy band)
#   band_pos = 1.0  -> price is AT entry_high (= fair value, top of the band)
#   band_pos < 0    -> price is BELOW the band (floor-breakdown territory)
#   band_pos > 1    -> price is ABOVE the band (paying a premium; "wait")
#
# What "attractive" means for these funds: you collect distributions, so total
# return = income + price change. Buying lower means more shares per dollar
# (more income) and more room to revert up toward fair value — UNTIL "lower"
# stops meaning "cheap" and starts meaning "the model's floor is wrong and the
# fund is still falling." That failure mode lives just below entry_low. So the
# ideal entry is "as low as possible while still safely inside the band," and
# attractiveness must roll off on BOTH sides of the band, not just the top.
#
# The shape below encodes exactly that, via five control points each with a
# plain-English justification:
#
#   band_pos   attractiveness   rationale
#   --------   --------------   ------------------------------------------------
#    -1.00          0.00        a full bandwidth below entry_low: model is
#                               clearly broken — no credit, don't catch the knife
#     0.00          0.85        AT entry_low: cheap, but right on the breakdown
#                               edge, so shave a little off the top
#     0.25          1.00        lower quarter of the band: the sweet spot —
#                               discounted yet safely inside the zone
#     1.00          0.45        AT fair value: a legitimate entry, but you're
#                               paying full model value with no discount
#     2.00          0.00        a full bandwidth above fair value: clearly
#                               overpaying — no credit, "wait for a pullback"
#
# The curve is continuous (no cliffs) and peaks at band_pos = 0.25. Tune the
# knots here if you want a more or less aggressive preference for buying low.

_ATTRACTIVENESS_KNOTS = [
    (-1.00, 0.00),
    (0.00, 0.85),
    (0.25, 1.00),
    (1.00, 0.45),
    (2.00, 0.00),
]


def band_attractiveness(band_pos: float) -> float:
    """Valuation score in [0, 1] from the price's position within the entry band.

    Peaks at the lower quarter of the band (band_pos = 0.25) and rolls off to 0
    both below the band (model-breakdown risk) and above it (overpaying).
    See the knot table above for the full, documented shape.
    """
    return _clamp(_interp(band_pos, _ATTRACTIVENESS_KNOTS))


# ---------------------------------------------------------------------------
# 2. fit_weight — the trust axis
# ---------------------------------------------------------------------------
#
# This reproduces the convention already baked into your ranked_board:
# a linear ramp on R^2 from 0.50 (no trust) to 0.90 (full trust).
#
#       fit_weight = clamp( (r2 - 0.50) / (0.90 - 0.50), 0, 1 )
#
# Verified against the live board: TSLY R^2 0.892 -> 0.98, MSTY 0.679 -> 0.447,
# NVDY 0.484 -> 0.00. Below R^2 0.50 the model is doing no better than a flat
# line, so its band is meaningless and the fund is disqualified from entry.

R2_NO_TRUST = 0.50
R2_FULL_TRUST = 0.90


def fit_weight_from_r2(r2: float) -> float:
    """Map a fit R^2 to a trust weight in [0, 1] (linear 0.50 -> 0.90 ramp)."""
    return _clamp((r2 - R2_NO_TRUST) / (R2_FULL_TRUST - R2_NO_TRUST))


# ---------------------------------------------------------------------------
# 3. plateau_gate — the regime axis
# ---------------------------------------------------------------------------
#
# The strategy never enters a fund still in its early, steep erosion phase.
# By default this is a hard gate (1.0 in plateau, 0.0 before) to match the
# backtest's ENTRY rule exactly. Set ``soft=True`` to instead apply a fixed
# partial credit before the plateau, if you'd rather a near-plateau fund still
# appears (faintly) on the board instead of being fully hidden.

PLATEAU_SOFT_CREDIT = 0.25


def plateau_gate(in_plateau: bool, soft: bool = False) -> float:
    """Regime gate in [0, 1]. Hard by default (matches the backtest entry rule)."""
    if in_plateau:
        return 1.0
    return PLATEAU_SOFT_CREDIT if soft else 0.0


# ---------------------------------------------------------------------------
# 4. breakdown_gate — the safety axis
# ---------------------------------------------------------------------------
#
# Mirrors the report's EXIT trigger: if price has fallen more than
# ``buffer_pct`` below the estimated floor, the floor estimate is presumed
# wrong and the fund is disqualified from entry. Default 8% matches
# ``breakdown_threshold_pct`` in the backtest.

BREAKDOWN_BUFFER_PCT = 8.0


def breakdown_gate(current_nav: Optional[float], floor: Optional[float],
                   buffer_pct: float = BREAKDOWN_BUFFER_PCT) -> float:
    """Safety gate in {0, 1}. Returns 0 if price is below floor*(1 - buffer)."""
    if current_nav is None or floor is None or floor <= 0:
        return 1.0  # not enough info to disqualify; let other gates decide
    breakdown_line = floor * (1.0 - buffer_pct / 100.0)
    return 0.0 if current_nav < breakdown_line else 1.0


# ---------------------------------------------------------------------------
# 5. entry_score — the composite
# ---------------------------------------------------------------------------

def entry_score(*,
                band_pos: float,
                in_plateau: bool,
                r2: Optional[float] = None,
                fit_weight: Optional[float] = None,
                current_nav: Optional[float] = None,
                floor: Optional[float] = None,
                breakdown_buffer_pct: float = BREAKDOWN_BUFFER_PCT,
                plateau_soft: bool = False) -> Dict[str, float]:
    """Compute the entry_score and return all of its component factors.

    entry_score = band_attractiveness * fit_weight * plateau_gate * breakdown_gate

    Provide ``fit_weight`` directly if your board already has it; otherwise pass
    ``r2`` and it will be derived via ``fit_weight_from_r2``. ``current_nav`` and
    ``floor`` are optional and only used by the breakdown safety gate.

    Returns a dict with the final ``entry_score`` plus every intermediate
    factor, so the board can display *why* a fund scored the way it did.
    """
    ba = band_attractiveness(band_pos)

    if fit_weight is None:
        if r2 is None:
            raise ValueError("entry_score needs either fit_weight or r2")
        fw = fit_weight_from_r2(r2)
    else:
        fw = _clamp(fit_weight)

    pg = plateau_gate(in_plateau, soft=plateau_soft)
    bg = breakdown_gate(current_nav, floor, buffer_pct=breakdown_buffer_pct)

    score = ba * fw * pg * bg

    return {
        "entry_score": round(score, 4),
        "band_attractiveness": round(ba, 4),
        "fit_weight": round(fw, 4),
        "plateau_gate": round(pg, 4),
        "breakdown_gate": round(bg, 4),
    }


# ---------------------------------------------------------------------------
# 6. Board integration
# ---------------------------------------------------------------------------

def score_record(rec: Dict[str, Any],
                 breakdown_buffer_pct: float = BREAKDOWN_BUFFER_PCT,
                 plateau_soft: bool = False) -> Dict[str, Any]:
    """Add entry_score (+ component fields) to one ranked_board fund record.

    Expects the keys your board already produces: ``band_pos``, ``in_plateau``,
    and either ``fit_weight`` or ``r2`` (plus optional ``current_nav`` /
    ``floor`` for the safety gate). Returns the same dict, mutated.
    """
    result = entry_score(
        band_pos=rec["band_pos"],
        in_plateau=rec.get("in_plateau", False),
        r2=rec.get("r2"),
        fit_weight=rec.get("fit_weight"),
        current_nav=rec.get("current_nav"),
        floor=rec.get("floor"),
        breakdown_buffer_pct=breakdown_buffer_pct,
        plateau_soft=plateau_soft,
    )
    rec.update(result)
    return rec


def compute_board(board: Dict[str, Any],
                  breakdown_buffer_pct: float = BREAKDOWN_BUFFER_PCT,
                  plateau_soft: bool = False,
                  sort: bool = True) -> Dict[str, Any]:
    """Score every fund in a ranked_board dict and (by default) re-sort.

    ``board`` is the structure you already write to ranked_board_<date>.json:
    ``{"as_of": ..., "funds": [ {...}, ... ], "errors": [...]}``.

    Funds are sorted by entry_score descending, with band_attractiveness then
    fit_weight as tie-breakers (so among equally-disqualified 0.0 funds, the
    ones closest to qualifying surface first).
    """
    for rec in board.get("funds", []):
        try:
            score_record(rec, breakdown_buffer_pct=breakdown_buffer_pct,
                         plateau_soft=plateau_soft)
        except (KeyError, ValueError):
            rec["entry_score"] = None  # leave unscored rather than crash the board

    if sort:
        board["funds"].sort(
            key=lambda r: (
                r.get("entry_score") if r.get("entry_score") is not None else -1.0,
                r.get("band_attractiveness", 0.0),
                r.get("fit_weight", 0.0),
            ),
            reverse=True,
        )
    return board


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Your three real funds (as of 2026-06-22), plus two illustrative rows that
    # show what a qualifying, nonzero-scoring fund looks like.
    demo = {
        "as_of": "2026-06-22",
        "funds": [
            {"symbol": "TSLY", "band_pos": 2.51, "in_plateau": False,
             "r2": 0.892, "fit_weight": 0.98, "current_nav": 30.36, "floor": 25.07},
            {"symbol": "MSTY", "band_pos": -4.35, "in_plateau": True,
             "r2": 0.679, "fit_weight": 0.447, "current_nav": 15.70, "floor": 20.83},
            {"symbol": "NVDY", "band_pos": 0.78, "in_plateau": True,
             "r2": 0.484, "fit_weight": 0.0, "current_nav": 14.34, "floor": 6.88},
            # --- illustrative (not real) rows to show the curve in action ---
            {"symbol": "AAAY*", "band_pos": 0.25, "in_plateau": True,
             "r2": 0.88, "current_nav": 18.0, "floor": 14.0},   # ideal: low in band, strong fit
            {"symbol": "BBBY*", "band_pos": 0.90, "in_plateau": True,
             "r2": 0.72, "current_nav": 11.0, "floor": 8.0},    # fair-valued, ok fit
        ],
        "errors": [],
    }

    compute_board(demo)

    hdr = f"{'Sym':<7}{'entry':>7}{'band_attr':>11}{'fit_w':>8}{'plat':>6}{'brk':>6}"
    print(hdr)
    print("-" * len(hdr))
    for r in demo["funds"]:
        print(f"{r['symbol']:<7}"
              f"{r['entry_score']:>7.3f}"
              f"{r['band_attractiveness']:>11.3f}"
              f"{r['fit_weight']:>8.3f}"
              f"{r['plateau_gate']:>6.1f}"
              f"{r['breakdown_gate']:>6.1f}")

    print("\n* AAAY / BBBY are illustrative rows, not real funds.")
    print("Note: all three REAL funds score 0.00 today — TSLY is above its band,")
    print("MSTY is below it (model breaking), and NVDY's fit is too weak to trust.")
    print("That is the correct, honest result, not a bug.")
