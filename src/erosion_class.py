"""
erosion_class.py
================
Erosion-stage classifier for the NAV-erosion board.

Tags each fund with an `erosion_class` (and human-readable `erosion_label`) so
the low-erosion index-like funds — which trivially fit the decay curve and
otherwise float to the top of the ranking — can be filtered out from the
high-erosion funds the tool is actually built to surface.

Classes
-------
    LOW_EROSION         index-like / risk-managed: modest yield AND barely
                        decaying. Not the target.
    BELOW_FLOOR         high-erosion fund trading below its own model floor —
                        the model may be breaking.
    MATURE_NEAR_FLOOR   high-erosion fund that has reached its floor and is
                        income-dominant. This is the zone the tool was built to
                        find.
    MID_EROSION         high-erosion fund in the heart of its decay.
    EARLY_HIGH_PREMIUM  high-erosion fund still far above its floor — lots of
                        decay still ahead, highest NAV risk. The income has to
                        outrun a steep grind.

Thresholds are module-level constants so they're easy to tune; each is
explained where it's defined.

Usage (wiring into build_board.py — two lines):
    from erosion_class import classify_record
    ...
    rec = build_record(sym, data_dir)
    classify_record(rec)              # adds rec["erosion_class"]

Or classify an existing board file in place:
    python erosion_class.py ranked_board_2026-06-23.json --write
"""

import sys
import json
import argparse
from typing import Optional, Dict, Any


# --- Tunable thresholds ----------------------------------------------------

# A fund is "low-erosion" only if it pays a modest yield AND is barely decaying.
# Both conditions are required so a *high-yield* fund that happens to be near
# its floor now (low current decay) is NOT mislabeled as an index fund.
LOW_EROSION_MAX_YIELD = 20.0     # % TTM. Index/risk-managed payers sit ~5-15%.
LOW_EROSION_MAX_WK_DECAY = 0.10  # %/week. Index funds barely move (~0.01-0.05).

# Lifecycle-stage cutoffs on pct_above_floor (only applied to high-erosion funds):
BELOW_FLOOR_PCT = -8.0   # below floor by >8% ≈ the breakdown line: model breaking
NEAR_FLOOR_PCT = 12.0    # within +12% of floor: mature, income-dominant
MID_EROSION_PCT = 45.0   # +12% to +45%: in the heart of the decay; above => early


EROSION_LABELS = {
    "LOW_EROSION":        "Low-erosion / index-like",
    "BELOW_FLOOR":        "Below floor - model may be breaking",
    "MATURE_NEAR_FLOOR":  "Mature - near floor (target zone)",
    "MID_EROSION":        "Mid-erosion",
    "EARLY_HIGH_PREMIUM": "Early - high premium (most NAV risk)",
}

# The class the tool is primarily built to surface.
TARGET_CLASS = "MATURE_NEAR_FLOOR"


def classify_erosion(ttm_yield_pct: Optional[float],
                     pct_above_floor: Optional[float],
                     wk_decay_pct: Optional[float]) -> str:
    """Return the erosion class for one fund from three board fields.

    See the module docstring for what each class means.
    """
    y = ttm_yield_pct if ttm_yield_pct is not None else 0.0
    paf = pct_above_floor if pct_above_floor is not None else 0.0
    wk = wk_decay_pct if wk_decay_pct is not None else 0.0

    # 1. Low-erosion / index-like: modest yield AND barely decaying.
    if y < LOW_EROSION_MAX_YIELD and wk < LOW_EROSION_MAX_WK_DECAY:
        return "LOW_EROSION"

    # 2. High-erosion funds: classify by lifecycle stage (distance above floor).
    if paf < BELOW_FLOOR_PCT:
        return "BELOW_FLOOR"
    if paf <= NEAR_FLOOR_PCT:
        return "MATURE_NEAR_FLOOR"
    if paf <= MID_EROSION_PCT:
        return "MID_EROSION"
    return "EARLY_HIGH_PREMIUM"


def classify_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Add `erosion_class` and `erosion_label` to a single fund record in place.

    Reads only fields the board already has: `ttm_yield_pct`, `pct_above_floor`,
    and `wk_decay_pct`.
    """
    cls = classify_erosion(
        rec.get("ttm_yield_pct"),
        rec.get("pct_above_floor"),
        rec.get("wk_decay_pct"),
    )
    rec["erosion_class"] = cls
    rec["erosion_label"] = EROSION_LABELS[cls]
    return rec


def classify_board(board: Dict[str, Any]) -> Dict[str, Any]:
    """Apply classify_record to every fund in a loaded board dict."""
    for rec in board.get("funds", []):
        classify_record(rec)
    return board


def _summarize(board: Dict[str, Any]) -> None:
    """Print a count per erosion class, target zone last for visibility."""
    counts: Dict[str, int] = {}
    for rec in board.get("funds", []):
        counts[rec.get("erosion_class", "?")] = counts.get(rec.get("erosion_class", "?"), 0) + 1
    order = ["EARLY_HIGH_PREMIUM", "MID_EROSION", "LOW_EROSION",
             "BELOW_FLOOR", "MATURE_NEAR_FLOOR"]
    print("\nErosion-class breakdown:")
    for cls in order:
        if cls in counts:
            star = "  <-- target zone" if cls == TARGET_CLASS else ""
            print(f"  {counts[cls]:>3}  {cls:<20} {EROSION_LABELS[cls]}{star}")
    # Name the target-zone funds explicitly.
    targets = [r["symbol"] for r in board.get("funds", [])
               if r.get("erosion_class") == TARGET_CLASS]
    if targets:
        print(f"\n{TARGET_CLASS} funds: {', '.join(sorted(targets))}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify erosion stage on a board JSON.")
    parser.add_argument("board", help="Path to a ranked_board_<date>.json file")
    parser.add_argument("--write", action="store_true",
                        help="Backfill erosion_class/erosion_label into the file in place")
    args = parser.parse_args()

    try:
        with open(args.board) as f:
            board = json.load(f)
    except FileNotFoundError:
        print(f"Board file not found: {args.board}")
        sys.exit(1)

    classify_board(board)
    _summarize(board)

    if args.write:
        with open(args.board, "w") as f:
            json.dump(board, f, indent=2)
        print(f"\nWrote erosion classes back into {args.board}")
    else:
        print("\n(dry run - pass --write to backfill the classes into the file)")


if __name__ == "__main__":
    main()
