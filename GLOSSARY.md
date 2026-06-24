# NAV-Erosion Screener — Glossary of Output Terms

A plain-English definition of **every term** that appears in the screener
report and the ranked board, each with a worked example using the real
TSLY and NVDY numbers you've already seen on screen.

Read this alongside a report: each section below matches a section of the
`python screener.py SYM -v` output, in the same order.

> All examples are illustrative. This is a research framework, not investment
> advice. Every dollar figure is a model estimate from cached data, not a live
> quote or a recommendation.

---

## 1. Identity & data scope

**symbol** — The fund's ticker (e.g. `TSLY`, `NVDY`). One report or one board
row per symbol.

**as_of** — The date the board/report was generated. Everything ("current
price," "today's fair value") is relative to this date.
*Example:* `as_of = 2026-06-22`.

**trading days analyzed / n_obs** — How many daily price observations the model
was fitted on, **within the current epoch only** (see *epoch* below). More
observations = a more reliable fit.
*Example:* NVDY shows `756 trading days analyzed`; TSLY shows only `115`,
because TSLY's history was truncated at its most recent reverse split.

**epoch / epoch_start / analysis window starts** — An *epoch* is one cycle of
the fund's life. A reverse split or a fund relaunch ends one epoch and starts a
new one, because the share units change. The model only fits the **most recent**
epoch; `epoch_start` is the date that window begins.
*Example:* NVDY (no splits) has one epoch starting `2023-05-11`. TSLY's epoch
starts `2025-12-01` — the date of its 1:5 reverse split — so everything before
that is excluded from the fit.

**History truncated / truncation_date** — A warning line that appears when older
data was dropped because of a split or regime change. It tells you the fit is
based on a shortened window.
*Example:* TSLY's report flags truncation to `2025-12-01`; NVDY's does not.

**splits (Total Epochs − 1)** — The count of reverse splits detected in the full
price history. These funds reverse-split when NAV falls too low, which resets
the cycle. The number of epochs is `splits + 1`.
*Example:* TSLY `splits = 2` (a 1:2 in Feb 2024 and a 1:5 in Dec 2025) → 3
epochs total, of which only the latest is analyzed. NVDY `splits = 0` → 1 epoch.

**regime_changes** — Sharp upward jumps that are *not* clean reverse splits
(e.g. a fund relaunch or NAV reset). They also end an epoch. Listed separately
from splits.
*Example:* none detected for TSLY or NVDY.

**Starting NAV (this epoch) / nav_0** — The fund's price at the start of the
current epoch — the model's `NAV_0`. Equals `floor + initial_premium`.
*Example:* NVDY `nav_0 = $27.00` (its 2023-05-11 launch price).

**Current NAV / current_nav** — The most recent **cached** closing price the
model sees. (In a live board you'd refresh this daily; in the report it's the
last close in your CSV.)
*Example:* NVDY `current_nav = $14.34`, which the report notes is `-46.9% from
epoch start` (down from the $27.00 starting NAV).

---

## 2. Decay model

The model fits the curve `NAV(t) = floor + premium · exp(−k · t)` to the epoch.

**Estimated floor / floor (F)** — The asymptotic price the decay curve flattens
toward — the long-run equilibrium NAV. Found by curve-fitting, **not** observed
directly. It is *not* a guaranteed price bottom; it's the level around which the
fund is expected to plateau.
*Example:* NVDY `floor = $6.88`; TSLY `floor = $25.07`.

**Initial NAV premium / initial_premium (A)** — How far above the floor the fund
launched: `A = nav_0 − floor`. The decay is the fund "paying down" this premium.
*Example:* NVDY `initial_premium = $20.12` ( = $27.00 − $6.88 ).

**launch was X% above floor** — The premium expressed as a percentage of the
floor: `A / F`. A quick read on how inflated the launch price was.
*Example:* NVDY `launch was 293% above floor` ( = 20.12 / 6.88 ).

**Decay rate (per day) / decay_rate (k)** — How fast NAV erodes toward the floor,
per day. Bigger `k` = faster erosion.
*Example:* NVDY `k = 0.00073` (very slow); a fast-eroding fund might be 0.005+.

**Half-life / half_life_days** — How many days for the *remaining* premium above
the floor to halve: `ln(2) / k ≈ 0.693 / k`. An intuitive restatement of the
decay rate.
*Example:* NVDY `half_life = 956 days` ( ≈ 0.693 / 0.00073 ), about 31.9 months.
TSLY's is `82 days` — it sheds its premium far faster.

**Fit quality (R²) / fit_r2** — How well the decay curve matches the actual price
history, from 0 (useless) to 1 (perfect). **The most important trust signal in
the whole report.** The screener labels it:
- `> 0.85` → **strong**
- `0.60 – 0.85` → **moderate**
- `< 0.60` → **weak — model may not apply**

*Example:* TSLY `R² = 0.892` (strong); NVDY `R² = 0.484` (weak) — because NVDA
trended too hard for the simple decay shape to fit. A weak R² means the floor
and band below it are unreliable.

**Current % above floor / pct_above_floor** — How far today's price sits above
the estimated floor: `(current_nav − floor) / floor`. High = lots of premium
left to erode; near zero = close to the floor.
*Example:* NVDY `pct_above_floor = +108.5%` ( = (14.34 − 6.88) / 6.88 ).

---

## 3. Plateau detection

**Plateau** — The stage where the model's predicted *weekly* NAV decline drops
below 0.5%. From here on, distribution income is expected to outweigh capital
erosion, so total return turns positive on average. This is the "productive
zone" the tool is hunting for.

**In plateau now? / in_plateau** — Whether today's date is past the plateau
start. A fund still in early, steep erosion reads `NOT YET`.
*Example:* NVDY `YES`; TSLY `NOT YET` (it's still eroding quickly).

**Plateau started / plateau_start_date** and **plateau_start_nav** — The date the
model says the plateau began, and the modeled NAV on that date.
*Example:* NVDY `Plateau started: 2023-05-11 (at NAV $27.00)`.

**Days into plateau / days_into_plateau** — How many days the fund has been in
its plateau as of today. Longer = more settled.
*Example:* NVDY `1138` days into plateau.

**Expected weekly NAV decay / expected_weekly_decay_pct (wk_decay_pct)** — The
model's estimate of how much NAV will erode over the next week, in percent.
Below ~0.5% is the plateau condition.
*Example:* NVDY `0.29%/wk` now.

---

## 4. Suggested entry / exit range

**Fair value today / fair_value_today** — The model's NAV expectation for today
(the decay curve evaluated at today's `t`). This is also the **top** of the buy
band — the most you'd pay without overpaying versus the model.
*Example:* NVDY `fair_value_today = $15.69`.

**BUY zone / entry_low – entry_high** — The price band the tool considers a
sensible entry.
- `entry_high` = fair value today (pay up to, but not above, the model's value).
- `entry_low` = `max(floor × 1.05, floor + 0.3 × remaining_premium)` — a floor on
  how low you'd buy, so you never enter right on top of the floor where
  breakdown risk is highest.

*Example:* NVDY buy zone `$9.52 – $15.69`. Above $15.69 = paying a premium;
below $9.52 = floor-breakdown risk.

**EXIT trigger** — The price that signals the floor estimate was wrong and the
fund is weakening: `floor × 0.92` (8% below the estimated floor).
*Example:* NVDY `EXIT trigger: below $6.33` ( = 6.88 × 0.92 ).

**TTM yield at entry_high / entry_low (ttm_yield_pct)** — The trailing-twelve-
month distributions divided by that entry price — i.e. the yield you'd lock in
buying at the top vs. bottom of the band. **Pre-tax and pre-erosion**; the real
after-tax, after-decay number is materially lower.
*Example:* NVDY `47%` at entry_high, `78%` at entry_low. (`ttm_yield_pct` on the
board uses the entry_high figure, 47%.)

**Where is it now? / status** — A one-line verdict comparing today's price to the
band:
- `ABOVE` — price is above the band → "wait for a pullback."
- `IN_BAND` — price is inside the band → "conditions look favorable" (subject to
  fit quality).
- `BELOW` — price is below the band → "model may be breaking; wait for a new
  equilibrium."

*Example:* NVDY `IN_BAND` at $14.34; TSLY `ABOVE` at $30.36.

**band_pos** — Where price sits **within** the band, normalized:
`band_pos = (price − entry_low) / (entry_high − entry_low)`.
- `0.0` = at entry_low (bottom of band)
- `1.0` = at entry_high (fair value, top of band)
- `< 0` = below the band   ·   `> 1` = above the band

*Example:* NVDY `band_pos = 0.78` ( = (14.34 − 9.52) / (15.69 − 9.52) ) → inside,
upper part of the band. TSLY `+2.51` (well above the band); MSTY `−4.35` (well
below it).

---

## 5. Walk-forward backtest (patient-hold strategy)

Tests a "buy once when conditions are right, then hold" rule, walking forward
through history so it only ever uses data it would have had at the time.

**Strategy total return / strategy_total_return_pct** — Total return of the
patient-hold strategy over the backtest window, distributions reinvested.
*Example:* NVDY `+0.0%` — because the strategy **never entered** (its R² never
cleared the trust gate), so it held cash and earned nothing. Not a loss, a
non-participation.

**Buy-and-hold total return / buy_and_hold_total_return_pct** — Total return if
you'd simply bought at the start of the window and held, distributions
reinvested. The benchmark.
*Example:* NVDY `+358.2%`.

**Buy-at-plateau-and-hold / buy_at_plateau_hold_total_return_pct** — A second
benchmark: buy when the plateau begins and hold from there. Matches the
intuition behind the strategy.
*Example:* NVDY `+358.2%` (same as buy-and-hold here, since NVDY's plateau
starts at its launch).

**Edge over buy-and-hold** — `strategy − buy_and_hold`. Positive = the strategy
beat holding; negative = it trailed.
*Example:* NVDY `−358.2%` — the strategy sat out a fund that rallied, so it
"lost" the entire run-up *on paper*. This large negative number is a known
artifact of zero trades; **don't surface it raw on a 100-fund board** — it reads
as broken. Show it only when `n_trades > 0`.

**# trades / n_trades** — How many complete entry→exit round trips the strategy
made in the window. Zero is common and usually correct (the fund never met the
strict entry conditions).
*Example:* NVDY `0`.

**Win rate / win_rate_pct** — Share of trades that ended positive. Only
meaningful when `n_trades > 0`.

**Avg win / Avg loss (avg_win_pct / avg_loss_pct)** — Mean return of winning vs.
losing trades. Only meaningful when there are trades.

**Time in market / time_in_market_pct** — Fraction of the backtest window the
strategy was actually holding (vs. in cash). Low values mean a very selective,
patient strategy.
*Example:* NVDY `0%` (never entered).

**Trade log (verbose `-v` only)** — One line per trade: `entry_date → exit_date:
return% (reason)`. The **reason** is either:
- `floor_breakdown` — exited because price fell more than 8% below the floor.
- `end_of_data` — still holding when the backtest ran out of data (an open
  position marked to the last price).

---

## 6. Ranked-board markers (the master table)

These appear in `ranked_board_<date>.json`, the multi-fund triage table — the
fields that let you sort 100+ funds before opening any single report.

**signal_score (legacy)** — The original composite ranking number. It blended
valuation and fit quality into one value, which is why it could rank an
above-band fund (TSLY) above an in-band one (NVDY). Kept for backward
compatibility; **prefer `entry_score` below** for "best entry candidate now."

**fit_weight** — The trust axis, isolated: how much to believe the model's band,
from a linear ramp on R² — `clamp((R² − 0.50) / 0.40, 0, 1)`. 0 at R² 0.50, 1 at
R² 0.90.
*Example:* TSLY `0.98` (R² 0.892), MSTY `0.447` (0.679), NVDY `0.00` (0.484).

**band_attractiveness** *(new)* — The valuation axis, isolated: a 0–1 score for
how attractively priced the fund is, derived from `band_pos`. Peaks at the lower
quarter of the band (band_pos ≈ 0.25), and rolls off to 0 both below the band
(breakdown risk) and above it (overpaying).
*Example:* NVDY `band_pos 0.78 → band_attractiveness ≈ 0.61` (inside, but in the
upper half, so a moderate score). A fund sitting at band_pos 0.25 would score
`1.00`.

**plateau_gate** *(new)* — A 0/1 regime gate: 1 if the fund is in its plateau,
else 0 (matching the backtest's entry rule). Can be softened to a partial credit
if desired.
*Example:* NVDY `1.0`, TSLY `0.0`.

**breakdown_gate** *(new)* — A 0/1 safety gate: 0 if price is more than 8% below
the estimated floor (the EXIT condition), else 1.
*Example:* NVDY `1.0`; MSTY `0.0` (its price is far below its floor).

**entry_score** *(new — the recommended default sort)* — The "best entry
candidate right now" composite:

```
entry_score = band_attractiveness × fit_weight × plateau_gate × breakdown_gate
```

All factors are 0–1, so `entry_score` is 0–1. Any single 0 hard-zeros the score
— an untrustworthy fit, a pre-plateau fund, or a floor breakdown each
disqualifies a fund on its own. Read it as "where this fund sits relative to the
model's entry logic," **not** as "how good a buy this is."
*Example:* All three real funds score `0.00` today — TSLY (above band → valuation
0), MSTY (below band + breakdown gate 0), NVDY (fit_weight 0). An illustrative
fund that's low in its band, in plateau, with a strong fit would score ≈ `0.95`.

**errors** — A list (usually empty) of funds that couldn't be processed — e.g.
missing data or a failed fit — so a single bad ticker never silently drops out
of the board.

---

## 7. Two concepts behind all the numbers

**Total return** — Everywhere the report says "return," it means **price change
plus distributions, with distributions reinvested.** That's the right measure
for income funds: the price *falling* while big distributions pay out can still
be a positive total return. If you **spend** the distributions instead of
reinvesting, your real return is lower than the figures shown.

**Pre-tax, pre-erosion yield** — Headline distribution yields (the 47% / 78%
above) are gross. These distributions are typically taxed as ordinary income,
and the yield is quoted before the NAV erosion that partly funds it. The
after-tax, after-erosion total return is usually **30–50% lower** than the
headline yield implies — which is why these products are generally best held in
tax-advantaged accounts.
