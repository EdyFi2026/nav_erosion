# NAV-Erosion Screener — Project Memory

> Read this at the start of every session. It is the index. Deep detail lives in
> `.claude/rules/` — load those files only when the task touches them.

## What this project is

A research framework that analyzes covered-call / option-income ETFs (YieldMax
single-stock funds like TSLY, NVDY, MSTY, CONY; Defiance/Roundhill weeklies like
QQQY, WDTE). These funds launch at a high NAV, erode toward a floor, then plateau.
The tool fits an exponential-decay-to-floor model per fund, classifies where each
fund sits in that life cycle, and surfaces a suggested entry/exit price band.

The single most valuable output is often a *negative* signal: "don't buy yet."

## Non-negotiable guardrails (these always apply)

- **This is an educational research framework, NOT investment advice.** Every
  report, number, and scenario is illustrative. Keep this framing in all output
  (code comments, docs, generated reports).
- **Fit on RAW, NON-split-adjusted prices.** Split/dividend-adjusted series hide
  the erosion and the reverse splits the model exists to measure. See
  `.claude/rules/data-pipeline.md`.
- **A reverse split resets the cycle.** Only fit on data since the most recent
  epoch boundary (reverse split or non-split regime change).
- **Never hardcode an API key in committed files.** The FMP key comes from the
  `FMP_API_KEY` environment variable or a `--api-key` flag only.
- **Don't claim a fund is a buy.** The tool describes model state; it does not
  recommend trades.

## The pipeline (current working flow)

The whole pipeline runs from one root command (preferred):

    python run.py              # fetch -> build board -> classify erosion
    python run.py --no-fetch   # skip the download, use data already cached

Under the hood that chains the three engine scripts (now under `src/`), in order.
Confirm exact filenames against the repo — the codebase may have moved past
what's described here.

1. `python src/fetch_data.py --all` — pull raw price + dividend CSVs (~105 tickers)
2. `python src/build_board.py --data-dir data` — fit the model on every cached
   ticker, compute `entry_score`, write a dated ranked JSON board
3. `python src/erosion_class.py ranked_board_<date>.json --write` — backfill the
   erosion bucket onto every fund record

Single-fund report: `python src/screener.py TSLY -v`

## Key files

Engine/library modules live under `src/`; root holds the entry points (`run.py`,
`main.py`); the synthetic-data test lives under `tests/`; generated boards,
charts, and PDFs go under `output/`.

| File | Role |
|------|------|
| `run.py` | Single root entry point: chains fetch → build_board → erosion_class. |
| `src/nav_erosion_model.py` | Core engine: decay fit, split/regime detection, plateau, total return, backtest, `analyze_fund()`. Don't run directly. |
| `src/screener.py` | CLI for one ticker → formatted text report. |
| `src/fetch_data.py` | Pulls raw FMP data → two CSVs per ticker. Std-lib only. |
| `src/build_board.py` | Fits every cached ticker → ranked JSON board. |
| `src/erosion_class.py` | Adds an erosion bucket to each fund on the board. |
| `src/entry_score.py` | The transparent composite score (replaced legacy `signal_score`). |
| `src/build_viz_data.py` | Builds visualization data (writes `output/viz_data.json`). |
| `tests/test_synthetic.py` | Validates parameter recovery on synthetic data. |

## Deep-detail rule files (load on demand)

- **`.claude/rules/model-mechanics.md`** — the decay model, `entry_score`
  formula, `band_pos`, the five erosion buckets, plateau math. Read this before
  touching scoring or classification.
- **`.claude/rules/data-pipeline.md`** — FMP endpoints, the `adjClose` quirk,
  split detection, the fetch workflow. Read this before touching data fetching.
- **`.claude/rules/conventions.md`** — coding style, output formats, where files
  go, non-tech-user usability rules. Read this before adding/restructuring code.

## Coding conventions (summary — full version in conventions.md)

- Python 3.10+, standard library where possible. Engine needs pandas/numpy/scipy;
  matplotlib/reportlab only for viz/PDF; `fetch_data.py` is std-lib only.
- Prefer transparent, composable, documented functions over opaque signals.
- Validate model math on synthetic data before trusting it on real data.
- Human-readable errors, never raw stack traces, for anything a non-developer runs.

## Things NOT to put here

Execution plans, running checklists, and "what we did last session" belong in a
task tracker or a scratch file — not in memory. This file is for stable facts
Claude should hold in every session.
