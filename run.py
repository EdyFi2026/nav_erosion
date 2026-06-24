"""
run.py
======
Single entry point for the NAV-Erosion pipeline.

Instead of remembering three commands in the right order — and pasting a dated
board filename between the second and third — just run:

    python run.py                 # fetch -> build board -> classify erosion
    python run.py --no-fetch      # skip the download, use the data already cached

What it does, in order:
    1. fetch_data.py   --all              (download raw prices + distributions)
    2. build_board.py  --data-dir data    (fit the model, write the ranked board)
    3. erosion_class.py <that board> --write  (backfill erosion buckets)

It auto-detects the board file build_board.py just wrote and passes it into the
erosion step for you, so there is no date to type. If any step fails it stops
and prints a plain-English explanation of which step failed and what to do —
never a raw traceback.

This is a thin orchestrator: it shells out to the three scripts exactly as you
would by hand, so each one keeps working on its own. It changes nothing about
how they behave.

Educational research framework, not investment advice.
"""

import sys
import time
import glob
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable or "python"


def _run(cmd, capture: bool):
    """Run a child script from the project root.

    capture=False streams the child's output live (good for the long fetch).
    capture=True collects stdout/stderr so we can parse it (build_board) and
    still echo it afterwards. Returns (returncode, stdout, stderr).
    """
    if capture:
        proc = subprocess.run(cmd, cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.returncode, proc.stdout, proc.stderr
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode, "", ""


def _fail(step_name: str, advice: str, stderr: str = "") -> None:
    """Print a plain-English failure message (no traceback) and exit non-zero."""
    print(f"\n{'=' * 64}")
    print(f"  X  {step_name} failed - stopping here.")
    print(f"{'=' * 64}")
    print(advice.rstrip())
    # Surface a single hint line from the child's stderr, never the whole dump.
    hint = ""
    for line in (stderr or "").splitlines():
        if line.strip():
            hint = line.strip()
    if hint and "Traceback" not in hint:
        print(f"\n  (technical detail: {hint})")
    print()
    sys.exit(1)


def _find_board(stdout: str, cutoff: float) -> Path | None:
    """Figure out which ranked_board_*.json build_board just wrote.

    Primary: parse build_board's own '... ->  <path>' summary line.
    Fallback: the newest ranked_board_*.json modified during this run.
    """
    # Primary: the line build_board prints is "Board as of <date>  ->  <path>".
    for line in stdout.splitlines():
        if "->" in line:
            candidate = ROOT / line.split("->", 1)[1].strip()
            if candidate.exists():
                return candidate

    # Fallback: newest board file touched since we started this step.
    boards = [Path(p) for p in glob.glob(str(ROOT / "ranked_board_*.json"))]
    fresh = [b for b in boards if b.stat().st_mtime >= cutoff - 1]
    if fresh:
        return max(fresh, key=lambda b: b.stat().st_mtime)
    return None


def step_fetch(data_dir: str) -> None:
    print("\n>>> Step 1 of 3 - Fetching raw prices & distributions (fetch_data.py)")
    print("    (this hits FMP for ~105 tickers and can take a couple of minutes)\n")
    rc, _, _ = _run([PY, "fetch_data.py", "--all", "--data-dir", data_dir],
                    capture=False)
    if rc != 0:
        _fail(
            "Step 1 (fetch data)",
            "The data download didn't finish. The usual cause is a missing or\n"
            "rejected FMP API key.\n\n"
            "What to do:\n"
            "  - Set your key, then re-run:\n"
            "        PowerShell:  $env:FMP_API_KEY = \"your_key_here\"\n"
            "        CMD:         set FMP_API_KEY=your_key_here\n"
            "  - Or, if you already have data cached in the data/ folder, skip the\n"
            "    download entirely:\n"
            "        python run.py --no-fetch",
        )


def step_build(data_dir: str) -> Path:
    print("\n>>> Step 2 of 3 - Fitting the model & building the ranked board "
          "(build_board.py)\n")
    cutoff = time.time()
    rc, out, err = _run([PY, "build_board.py", "--data-dir", data_dir],
                        capture=True)
    if out:
        print(out.rstrip())
    if rc != 0:
        _fail(
            "Step 2 (build board)",
            "The model couldn't build the ranked board from the data in "
            f"'{data_dir}/'.\n\n"
            "What to do:\n"
            f"  - Make sure '{data_dir}/' has <SYM>_prices.csv files. The repo ships\n"
            "    TSLY and NVDY samples so it runs without an API key.\n"
            "  - If a fetch just failed, fix the API key and run again, or use\n"
            "    --no-fetch to work from the cached samples.",
            stderr=err,
        )

    board = _find_board(out, cutoff)
    if board is None:
        _fail(
            "Step 2 (build board)",
            "build_board.py finished but I couldn't find the board file it wrote.\n"
            f"I expected a ranked_board_<date>.json in:\n    {ROOT}\n\n"
            "What to do: re-run, and check the folder is writable.",
            stderr=err,
        )
    print(f"\n    Detected board file: {board.name}")
    return board


def step_classify(board: Path) -> None:
    print("\n>>> Step 3 of 3 - Classifying erosion buckets (erosion_class.py)\n")
    rc, out, err = _run([PY, "erosion_class.py", str(board.name), "--write"],
                        capture=True)
    if out:
        print(out.rstrip())
    if rc != 0:
        _fail(
            "Step 3 (classify erosion)",
            f"Couldn't tag erosion buckets onto '{board.name}'.\n\n"
            "What to do: the board file may be incomplete - re-run step 2 by\n"
            "running the pipeline again (add --no-fetch to reuse cached data).",
            stderr=err,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the whole NAV-erosion pipeline with one command.")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip the download step and use data already cached "
                             "in the data/ folder.")
    parser.add_argument("--data-dir", default="data",
                        help="Folder with cached <SYM>_prices.csv (default: data)")
    args = parser.parse_args()

    print("NAV-Erosion pipeline  -  educational research, not investment advice.")

    if args.no_fetch:
        print("\n(Skipping Step 1: --no-fetch set, using cached data.)")
    else:
        step_fetch(args.data_dir)

    board = step_build(args.data_dir)
    step_classify(board)

    print(f"\n{'=' * 64}")
    print("  Pipeline complete.")
    print(f"{'=' * 64}")
    print(f"  Ranked, erosion-classified board:  {board.name}")
    print("  Single-fund report:  python screener.py TSLY -v")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was left half-written by run.py itself.")
        sys.exit(130)
