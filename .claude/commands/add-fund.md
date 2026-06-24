---
description: Add a new fund to the cached universe and screen it
argument-hint: [TICKER]
---

Add and screen the fund: $ARGUMENTS

1. Run `python fetch_data.py $ARGUMENTS` to cache its raw price + dividend CSVs.
2. Run `python screener.py $ARGUMENTS -v` to produce the full report.

Then give me a plain-English readout: where it sits in its life cycle (erosion
bucket), whether today's price is inside / above / below the suggested band, the
fit quality (and whether the fit is trustworthy), and the main caveat.

If the fit R² is weak, say so prominently and treat the band as a soft signal,
not a confident read. Educational research only — not investment advice.
