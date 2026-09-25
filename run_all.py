"""
run_all.py — runs the whole pipeline (stages 1 -> 5) in order.

Usage (from the project root):
    python run_all.py

Each stage is a standalone script in src/. We run each one as a separate
Python process so every stage starts fresh, exactly as if you ran it by hand.
If any stage fails, we stop immediately (fail loudly) instead of running the
later stages on broken data.
"""

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

STAGES = [
    ("Stage 1: Ingest & clean raw CSVs -> staging", "src/01_ingest_clean.py"),
    ("Stage 2: Build star schema", "src/02_build_warehouse.py"),
    ("Stage 3: Build marts", "src/03_build_marts.py"),
    ("Stage 4: Run analysis queries", "src/04_analysis.py"),
    ("Stage 5: Generate charts", "src/05_visualize.py"),
]


def main():
    total_start = time.time()

    for title, script in STAGES:
        print("\n" + "=" * 70)
        print(f"  {title}")
        # flush=True: print the banner NOW, before the child process writes
        # its own output (otherwise buffering can print them out of order).
        print("=" * 70, flush=True)

        start = time.time()
        # sys.executable = the same Python interpreter running this file,
        # so the stages use the same installed packages.
        result = subprocess.run([sys.executable, script], cwd=PROJECT_ROOT)
        elapsed = time.time() - start

        if result.returncode != 0:
            print(f"\nFAILED: {script} exited with code {result.returncode}. Stopping.")
            sys.exit(result.returncode)

        print(f"\n  -> {script} finished in {elapsed:.1f}s", flush=True)

    print("\n" + "=" * 70)
    print(f"  ALL STAGES COMPLETE in {time.time() - total_start:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
