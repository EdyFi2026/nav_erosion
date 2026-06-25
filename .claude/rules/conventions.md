# Rule: Conventions & Usability

Load this when adding code, restructuring files, or producing deliverables.

## Audience

Deliverables span three audiences — keep them distinct:
1. **Technical scripts** — for the engine and pipeline.
2. **Investor-facing plain-English docs** (PDF) — NO formulas, NO proprietary
   model mechanics. Explains *what* and *why*, not *how*.
3. **Setup guides for non-developers** — step-by-step, screenshot-friendly.

## Non-tech-user usability rules

The owner is not a full-time developer and wants this runnable without fighting
the command line. When you add or change anything user-facing:

- Favor a **single entry point** over a multi-command sequence. A non-tech user
  should not have to remember `fetch → build_board → erosion_class` in order.
- Every command a non-developer runs must fail with a **plain-English message**,
  never a raw traceback. Say what went wrong and what to do next.
- Prefer **one config file** (or env var) for the API key over re-typing it.
- Output a **human-readable summary** (and optionally an HTML report) by default;
  keep the JSON/CSV as machine artifacts, not the primary thing the user reads.
- Document any new command in `README.md` with a copy-paste example.

## Code style

- Python 3.10+. Type hints and dataclasses where they aid clarity.
- Standard library where possible. The engine needs pandas/numpy/scipy;
  matplotlib/reportlab only for viz/PDF; keep `fetch_data.py` std-lib only so it
  runs anywhere.
- Pin runtime deps in `requirements.txt` so install is one command.
- Transparent, composable, documented functions over opaque signals. If a scoring
  factor has magic constants, document the knots inline (see `entry_score`).
- Validate math on synthetic data before applying to real data.

## File layout & outputs

- Engine/library modules live under `src/` (and form the `src` package via
  `src/__init__.py`). Root holds only the entry points `run.py` and `main.py`;
  tests live under `tests/`; cached data under `data/`; generated
  boards/charts/PDFs under `output/`.
- Root entry points add `src/` to `sys.path` via a path **relative to the file**
  (`Path(__file__).parent / "src"`), never via the current working directory.
  No hardcoded absolute paths anywhere.
- Boards are **dated** (`ranked_board_YYYY-MM-DD.json`) and regeneratable.
- Workflow should stay **automatable**: self-refreshing fund universe discovery,
  re-run monthly to catch regime drift.

## Guardrail reminders

- Educational research framework, not investment advice — in every output.
- The PDF income scenario uses a deliberately conservative distribution
  assumption (lower than recent actual payments) so it can't be accused of
  cherry-picking a rosy number. Keep it that way.
