# NAV-Erosion Screener

A research tool for analyzing high-yield covered-call / option-income ETFs — the
YieldMax single-stock funds (TSLY, NVDY, MSTY, CONY…) and Defiance/Roundhill
weeklies (QQQY, WDTE…).

These funds tend to launch high, erode toward a floor, then plateau. This tool
fits a model to each fund's price history, works out where it sits in that life
cycle, and shows you a suggested entry/exit price band. Its most useful answer is
often "not yet — wait for a pullback."

> **Educational and research use only. Not investment advice.** All figures in
> reports are illustrative.

---

## Quick start (in Claude Code)

If you've opened this folder in Claude Code, you don't need to memorize commands.
Just type:

- `/refresh-board` — pulls fresh data, rebuilds the ranked board, and gives you a
  plain-English summary of which funds are worth a look.
- `/add-fund MSTY` — caches a new fund's data and screens it.

Or ask in plain language, e.g. *"screen TSLY and tell me if it's in its buy zone."*

## Quick start (command line)

You need Python 3.10+ and an [FMP](https://financialmodelingprep.com) API key
(the free tier is enough). Set the key once:

```bash
# macOS / Linux
export FMP_API_KEY=your_key_here
# Windows PowerShell
$env:FMP_API_KEY = "your_key_here"
```

Install dependencies, then run the pipeline:

```bash
pip install -r requirements.txt

python fetch_data.py --all                       # 1. get the data
python build_board.py --data-dir data            # 2. rank every fund
python erosion_class.py ranked_board_<date>.json --write   # 3. classify

python screener.py TSLY -v                        # report on one fund
python screener.py --list                         # see cached funds
```

---

## What you get back

For each fund the tool reports:

- **Erosion bucket** — where it is in its life cycle (early/high-premium,
  mid-erosion, mature-near-floor, low-erosion, or below-floor). The
  *mature-near-floor* funds are the ones the model is built to find.
- **Suggested buy band** — a price range, plus whether today's price is below,
  inside, or above it.
- **Fit quality (R²)** — how well the model actually describes the fund. A low R²
  is the tool honestly telling you not to trust the band for that fund.
- **A backtest** — how a patient buy-and-hold (distributions reinvested) would
  have done versus the model's entry rules.

## A worked example: TSLY vs NVDY

Same tool, same day, very different signals. TSLY fits the decay model cleanly
(strong R²) and may sit above its band, so the tool says wait. NVDY rallied hard
with NVDA in 2024, so the simple model fits poorly (low R²) — the buy band exists
but should be treated as a soft signal. Checking fit quality before acting on the
band is the whole discipline.

---

## How it works (high level)

NAV is modeled as exponential decay toward a floor. A fund's "floor" isn't a true
floor — it's the level at which management tends to reverse-split and restart the
cycle, so the tool only analyzes data since the most recent split or relaunch.
The model recovers known parameters to within ~1% on synthetic data, so for funds
in a stable regime the half-life and floor estimates are reliable; when the
underlying trends hard, the fit (and those estimates) degrade — which the R² score
flags for you.
Distribution yields shown are pre-tax and pre-erosion; after-tax total return is
usually 30–50% lower than the headline yield suggests, so these are best held in
tax-advantaged accounts.

Full mechanics live in `.claude/rules/` (for contributors and for Claude Code):
`model-mechanics.md`, `data-pipeline.md`, and `conventions.md`.

## Caveats

- The model assumes a stable underlying. Sharp moves invalidate the floor estimate.
- Past decay behavior doesn't guarantee future behavior. Re-run monthly.
- Reverse splits reset the cycle.
- Not investment advice. This is a research framework.
