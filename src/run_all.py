"""
Project FORESIGHT — one-command reproducible run.

Runs the full engagement pipeline end-to-end from the raw extract:
    pipeline  ->  forecast  ->  risk  ->  eda (figures + insights)

Run:  python src/run_all.py
"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

STEPS = ["pipeline", "forecast", "risk", "eda"]

if __name__ == "__main__":
    for step in STEPS:
        print(f"\n{'#' * 70}\n# RUNNING: {step}\n{'#' * 70}")
        runpy.run_module(step, run_name="__main__")
    print("\nAll steps complete. Outputs in data/processed/ and reports/figures/.")
