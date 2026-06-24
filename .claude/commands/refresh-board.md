---
description: Fetch fresh data, rebuild the ranked board, and classify erosion buckets in one step
---

Run the full NAV-erosion refresh pipeline end to end, then summarize for me in
plain English. Steps:

1. Run `python fetch_data.py --all` to pull fresh price + dividend data.
2. Run `python build_board.py --data-dir data` to fit every ticker and produce
   today's dated ranked board.
3. Run `python erosion_class.py ranked_board_<today>.json --write` to add erosion
   buckets.

Then tell me, in plain language (no jargon dump):
- How many funds are in each erosion bucket.
- The top MATURE_NEAR_FLOOR candidates currently inside their buy band.
- Anything that errored or looks like a model breakdown (BELOW_FLOOR).

If any step fails, stop and explain what went wrong in plain English and what I
should do — do not continue the pipeline on bad data.

Reminder: this is an educational research summary, not investment advice.
