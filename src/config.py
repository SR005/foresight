"""
Project FORESIGHT — central configuration.

Every tunable lives here so the pipeline is reproducible and auditable.
Change a value in one place and the whole engagement re-runs consistently.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]           # .../foresight
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

for _p in (DATA_RAW, DATA_PROC, REPORTS, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# Raw source workbook (UCI Online Retail II — the NorthBay client extract).
# The pipeline copies it into data/raw on first run; if absent it falls back
# to the sibling dataset folder shipped with the brief.
RAW_XLSX = DATA_RAW / "online_retail_II.xlsx"
RAW_FALLBACKS = [
    ROOT.parents[1] / "online+retail+ii" / "online_retail_II.xlsx",
    ROOT.parents[1] / "archive" / "online_retail_II.xlsx",
]

# ---------------------------------------------------------------- currency
# The brief asks for business impact in rupees. The source prices are in the
# dataset's native currency; we treat one price unit as one rupee (INR) for the
# purpose of quantifying impact, and label everything in Rs. This is a stated,
# documented convention — not a live FX conversion (out of scope).
CURRENCY = "Rs"

# ---------------------------------------------------------------- modelling
SEED = 42
TOP_N_SKUS = 200          # focus on the ~200 active SKUs the brief describes
HORIZON_WEEKS = 8         # forecast horizon (weeks)
MIN_ACTIVE_WEEKS = 30     # a SKU needs this much history to be modelled
WEEK_RULE = "W-SUN"       # weeks end on Sunday (ISO-ish, deterministic)

# Rolling-origin backtest: number of successive 1-week-ahead origins to score.
BACKTEST_ORIGINS = 8

# Assumed cost structure when the raw extract has no cost column.
UNIT_COST_RATIO = 0.60    # unit_cost = 0.60 * list_price (typical D2C margin)

# ---------------------------------------------------------------- risk layer
SERVICE_LEVEL_Z = 1.28    # ~90% service level (z-score) for safety stock
OVERSTOCK_WEEKS = 8       # holding > this many weeks of cover = overstock signal
RISK_THRESHOLD = 0.5      # grid split point for stockout / overstock quadrants
