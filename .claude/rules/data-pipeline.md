# Rule: Data Pipeline (FMP)

Load this when working on data fetching, parsing, or anything touching FMP.
These are reproducibility-critical details discovered the hard way.

## Correct endpoints

REST base for local scripts: `https://financialmodelingprep.com/stable`

- **Prices:** `historical-price-eod/non-split-adjusted?symbol=SYM`
  → raw unadjusted closes. The right choice for NAV-erosion analysis.
- **Dividends:** `dividends?symbol=SYM` → use the raw `dividend` field.
- **Split verification:** `splits-company`.
- **Batch market cap/price:** `batch-quote` (NOT `batch-quote-short`, which omits
  `marketCap`; and avoid `batch-market-cap`, which returns approval errors).

In-chat (FMP MCP) equivalents: `chart` with
`endpoint='historical-price-eod-non-split-adjusted'`; `calendar` with
`endpoint='dividends-company'` and `endpoint='splits-company'`.

## Gotchas (do not regress these)

- **The `adjClose` quirk:** the non-split-adjusted price endpoint labels the close
  field `adjClose` even though the value is unadjusted. Parser fallback: try
  `close` first, then `adjClose`.
- **Dividends:** use raw `dividend`, never `adjDividend`.
- **AVOID `historical-price-eod-light`** — returns split+dividend-adjusted prices,
  which is wrong for this use case.
- **Retain ~60 pre-split rows** when fetching so the split-detection algorithm has
  its inputs. Epoch truncation discards pre-split rows automatically after
  detection.
- Output CSV rows sorted **oldest-first**, columns `date,close` and `date,dividend`.
- **Empty dividend history is valid, not an error** (some new ETFs haven't paid).

## Split detection logic

A reverse split is flagged only when BOTH hold:
1. Clean near-integer ratio (2/3/4/5/6/8/10 within 5%).
2. Pre-jump NAV in the bottom 30% of the trailing 60-day range (the typical
   reverse-split trigger).

Non-split positive discontinuities (fund relaunches / NAV resets) are flagged
separately as regime changes. Both reset the epoch.

Confirmed example: TSLY reverse-split 1:2 on 2024-02-26 and 1:5 on 2025-12-01.

## Error handling for fetch

Human-readable, never raw stack traces: 401 → key rejected; 403 → not on plan /
quota; 429 → rate-limited, wait; network failure → check connection. A ~0.3s
sleep between calls keeps the free tier from rate-limiting large batches.

## API key resolution

`--api-key` flag overrides `FMP_API_KEY` env var. If neither is present, exit
with a clear message and instructions. Never commit a key.
