"""
Project FORESIGHT — D1 Data Pipeline.

Reproducible ingestion + cleaning. Turns the raw NorthBay client extract
(UCI Online Retail II, two yearly sheets of messy transactions) into a clean
star schema and an analysis-ready weekly panel.

Run:  python src/pipeline.py

Produces (in data/processed/):
    sales_daily.csv          one row per SKU per day
    sku_master.csv           one row per SKU (category, cost, price, launch)
    calendar.csv             one row per date (week, month, season, holiday, promo)
    inventory_snapshots.csv  latest stock position per SKU (modelled — see notes)
    weekly_panel.csv         analysis-ready SKU x week demand panel (for modelling)
    data_quality_report.json machine-readable log of every cleaning decision

Every cleaning decision is coded (never manual) and logged with a rationale.
"""
from __future__ import annotations
import json
import shutil
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd

import config as C

warnings.filterwarnings("ignore")
np.random.seed(C.SEED)

# Stock codes in Online Retail II that are NOT sellable products (fees, postage,
# manual adjustments, etc.). Removing them is a documented cleaning decision.
NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "C2", "BANK CHARGES", "BANK CHARGE", "AMAZONFEE",
    "CRUK", "PADS", "S", "D", "B", "TEST001", "TEST002", "GIFT", "ADJUST",
    "ADJUST2", "SP1002", "m",
}

# Keyword -> category map used to give each SKU a business category from its
# free-text description (the raw extract has no category column).
CATEGORY_RULES = [
    ("Kitchen & Dining", ["MUG", "CUP", "PLATE", "BOWL", "JUG", "TEAPOT", "CUTLERY",
                          "BAKING", "CAKE", "JAR", "BOTTLE", "GLASS", "SPOON", "KITCHEN"]),
    ("Lighting",         ["LIGHT", "LAMP", "CANDLE", "T-LIGHT", "TEA LIGHT", "LANTERN",
                          "HOLDER", "NIGHT LIGHT"]),
    ("Home Decor",       ["HEART", "FRAME", "MIRROR", "CLOCK", "SIGN", "HANGING",
                          "DECORATION", "ORNAMENT", "CUSHION", "DOORMAT", "WALL"]),
    ("Bags & Storage",   ["BAG", "BOX", "TIN", "BASKET", "STORAGE", "CASE", "TRUNK"]),
    ("Stationery & Gift",["CARD", "PAPER", "NAPKIN", "GIFT WRAP", "NOTEBOOK", "PEN",
                          "PENCIL", "CHALK", "STICKER", "WRAP"]),
    ("Garden & Outdoor", ["GARDEN", "PLANT", "WATERING", "BIRD", "OUTDOOR", "PARASOL"]),
    ("Seasonal",         ["CHRISTMAS", "EASTER", "HALLOWEEN", "ADVENT", "XMAS",
                          "VALENTINE", "SANTA", "SNOW"]),
    ("Toys & Games",     ["TOY", "GAME", "PLAY", "DOLL", "SKITTLES", "PUZZLE",
                          "BINGO", "SPACEBOY", "SOLDIER"]),
]


def _log(dq: dict, key: str, value, note: str):
    dq[key] = {"value": value, "note": note}
    print(f"  · {key}: {value}  — {note}")


def ingest() -> pd.DataFrame:
    """
    Load both yearly sheets from the raw workbook.

    Reading the 45MB workbook is slow, so on first run we cache it to a fast
    parquet next to the raw file; every subsequent run reads the cache in
    seconds. Delete the parquet to force a fresh read from the xlsx.
    """
    cache = C.DATA_RAW / "online_retail_II_raw.parquet"
    if cache.exists():
        print(f"Ingesting cached parquet {cache.name} ...")
        raw = pd.read_parquet(cache)
        print(f"  raw rows: {len(raw):,}")
        return raw

    if not C.RAW_XLSX.exists():
        for fb in C.RAW_FALLBACKS:
            if fb.exists():
                print(f"Copying raw extract into repo: {fb.name}")
                shutil.copy(fb, C.RAW_XLSX)
                break
    if not C.RAW_XLSX.exists():
        raise FileNotFoundError(
            f"Raw workbook not found at {C.RAW_XLSX} or fallbacks {C.RAW_FALLBACKS}"
        )
    print(f"Ingesting {C.RAW_XLSX.name} (calamine engine) ...")
    try:
        xls = pd.ExcelFile(C.RAW_XLSX, engine="calamine")
        frames = [pd.read_excel(xls, sheet_name=s, engine="calamine")
                  for s in xls.sheet_names]
    except Exception:                       # calamine not installed -> openpyxl
        xls = pd.ExcelFile(C.RAW_XLSX)
        frames = [pd.read_excel(xls, sheet_name=s) for s in xls.sheet_names]
    raw = pd.concat(frames, ignore_index=True)
    for col in ("Invoice", "StockCode", "Description", "Country"):
        raw[col] = raw[col].astype(str)
    try:
        raw.to_parquet(cache)               # cache for fast re-runs
        print(f"  cached raw -> {cache.name}")
    except Exception as e:
        print(f"  (cache skipped: {e})")
    print(f"  raw rows: {len(raw):,} across sheets {xls.sheet_names}")
    return raw


def clean(raw: pd.DataFrame, dq: dict) -> pd.DataFrame:
    """Coded cleaning steps; each logged to the data-quality report."""
    df = raw.rename(columns={
        "Invoice": "invoice", "StockCode": "sku_id", "Description": "description",
        "Quantity": "units", "InvoiceDate": "datetime", "Price": "unit_price",
        "Customer ID": "customer_id", "Country": "country",
    })
    n0 = len(df)
    _log(dq, "rows_raw", n0, "Combined transaction rows before cleaning.")

    # Types
    df["sku_id"] = df["sku_id"].astype(str).str.strip().str.upper()
    df["description"] = df["description"].astype(str).str.strip()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df["units"] = pd.to_numeric(df["units"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

    # 1. Cancellations: invoices starting with 'C' are returns/cancellations.
    canc = df["invoice"].astype(str).str.upper().str.startswith("C")
    _log(dq, "cancellations_removed", int(canc.sum()),
         "Invoices prefixed 'C' are cancellations/returns — excluded from demand.")
    df = df[~canc]

    # 2. Non-product stock codes (postage, fees, manual adjustments).
    nonprod = df["sku_id"].isin({c.upper() for c in NON_PRODUCT_CODES}) | \
              (~df["sku_id"].str.contains(r"\d", regex=True))  # real SKUs contain digits
    _log(dq, "non_product_rows_removed", int(nonprod.sum()),
         "Fees/postage/adjustment codes and non-numeric codes are not sellable SKUs.")
    df = df[~nonprod]

    # 3. Missing critical fields.
    miss = df["datetime"].isna() | df["units"].isna() | df["unit_price"].isna() | \
           (df["sku_id"].isin(["", "NAN", "NONE"]))
    _log(dq, "missing_field_rows_removed", int(miss.sum()),
         "Rows missing date, quantity, price or SKU cannot be used and are dropped.")
    df = df[~miss]

    # 4. Non-positive quantity or price (returns not flagged as C, zero-price giveaways).
    nonpos = (df["units"] <= 0) | (df["unit_price"] <= 0)
    _log(dq, "non_positive_rows_removed", int(nonpos.sum()),
         "Quantity<=0 or price<=0 are returns/adjustments/freebies, not demand.")
    df = df[~nonpos]

    # 5. Exact duplicate transaction lines.
    dup = df.duplicated(subset=["invoice", "sku_id", "datetime", "units", "unit_price"])
    _log(dq, "duplicate_rows_removed", int(dup.sum()),
         "Identical invoice/SKU/time/qty/price lines are double-scans — de-duplicated.")
    df = df[~dup]

    df["date"] = df["datetime"].dt.normalize()
    df["revenue"] = df["units"] * df["unit_price"]

    _log(dq, "rows_clean", len(df), f"Retained {len(df)/n0:.1%} of raw rows after cleaning.")
    _log(dq, "date_min", str(df["date"].min().date()), "Earliest transaction date.")
    _log(dq, "date_max", str(df["date"].max().date()), "Latest transaction date.")
    _log(dq, "distinct_skus", int(df["sku_id"].nunique()), "Distinct sellable SKUs.")
    return df


def categorise(desc: str) -> str:
    d = (desc or "").upper()
    for cat, kws in CATEGORY_RULES:
        if any(k in d for k in kws):
            return cat
    return "Other"


def build_sku_master(df: pd.DataFrame) -> pd.DataFrame:
    # Most frequent description per SKU = the canonical product name.
    desc = (df.groupby("sku_id")["description"]
              .agg(lambda s: s.value_counts().index[0]).rename("description"))
    launch = df.groupby("sku_id")["date"].min().rename("launch_date")
    # list_price = 90th percentile of observed price (robust to promo dips).
    list_price = df.groupby("sku_id")["unit_price"].quantile(0.90).rename("list_price")
    master = pd.concat([desc, launch, list_price], axis=1).reset_index()
    master["category"] = master["description"].map(categorise)
    master["subcategory"] = master["description"].str.split().str[0].str.title()
    master["unit_cost"] = (master["list_price"] * C.UNIT_COST_RATIO).round(2)
    return master[["sku_id", "description", "category", "subcategory",
                   "launch_date", "unit_cost", "list_price"]]


def build_sales_daily(df: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    g = (df.groupby(["sku_id", "date"])
           .agg(units_sold=("units", "sum"),
                revenue=("revenue", "sum"),
                unit_price=("unit_price", "mean"))
           .reset_index())
    # Promo flag (raw extract has no promo column): a SKU-day is 'on promo' when
    # its mean price is >=10% below the SKU's list price. Documented proxy.
    g = g.merge(master[["sku_id", "list_price"]], on="sku_id", how="left")
    g["promo_flag"] = (g["unit_price"] < 0.90 * g["list_price"]).astype(int)
    return g.drop(columns="list_price")


def build_calendar(df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    cal = pd.DataFrame({"date": dates})
    iso = cal["date"].dt.isocalendar()
    cal["week"] = iso["week"].astype(int)
    cal["year"] = iso["year"].astype(int)
    cal["month"] = cal["date"].dt.month
    cal["season"] = cal["month"].map(
        {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
         6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"})
    # Simple UK-style holiday flag + named promo events (deterministic by date).
    md = cal["date"].dt.strftime("%m-%d")
    cal["is_holiday"] = md.isin(["01-01", "12-25", "12-26"]).astype(int)
    def promo_event(d):
        if d.month == 12 and d.day <= 24: return "Christmas Run-up"
        if d.month == 11 and d.day >= 22: return "Black Friday / Cyber"
        if d.month == 1: return "January Clearance"
        if d.month == 7: return "Summer Sale"
        return ""
    cal["promo_event"] = cal["date"].map(promo_event)
    return cal


def build_inventory(master: pd.DataFrame, weekly: pd.DataFrame, dq: dict) -> pd.DataFrame:
    """
    MODELLED inventory position. The raw client extract contains sales only —
    no stock table. To exercise the risk layer we synthesise a defensible,
    deterministic (seeded) snapshot per SKU from its recent demand, exactly as
    NorthBay's real inventory_snapshots would look. This is clearly flagged as a
    modelled stand-in in the data-quality report and the README.
    """
    rng = np.random.default_rng(C.SEED)
    last_week = weekly["week_start"].max()
    recent = (weekly[weekly["week_start"] > last_week - pd.Timedelta(weeks=12)]
              .groupby("sku_id")["units_sold"].mean().rename("avg_wk"))
    m = master.merge(recent, on="sku_id", how="left").fillna({"avg_wk": 0})
    # Lead time by category (days) — plausible D2C replenishment windows.
    lt_map = {"Kitchen & Dining": 21, "Lighting": 28, "Home Decor": 30,
              "Bags & Storage": 35, "Stationery & Gift": 14, "Garden & Outdoor": 42,
              "Seasonal": 45, "Toys & Games": 30, "Other": 25}
    m["lead_time_days"] = m["category"].map(lt_map).fillna(25).astype(int)
    lt_weeks = m["lead_time_days"] / 7.0
    # Reorder point = demand over lead time + safety stock.
    m["reorder_point"] = np.ceil(m["avg_wk"] * lt_weeks * 1.3).astype(int)
    # On-hand: weeks-of-cover drawn from a wide spread so all four risk quadrants
    # appear (some near-empty, some heavily overstocked). Deterministic (seeded).
    cover = rng.uniform(0.2, 18.0, size=len(m))          # 0.2 to 18 weeks of cover
    m["on_hand_units"] = np.ceil(m["avg_wk"] * cover).astype(int)
    # Only ~45% of below-reorder-point SKUs already have replenishment in transit,
    # leaving the rest genuinely exposed to stockout.
    below = m["on_hand_units"] < m["reorder_point"]
    in_transit = below & (rng.random(len(m)) < 0.45)
    m["on_order_units"] = np.where(
        in_transit, np.ceil(m["avg_wk"] * lt_weeks).astype(int), 0)
    m["date"] = last_week
    inv = m[["date", "sku_id", "on_hand_units", "on_order_units",
             "lead_time_days", "reorder_point"]]
    _log(dq, "inventory_snapshots_modelled", int(len(inv)),
         "Raw extract has no stock table; inventory snapshot synthesised from demand (seeded).")
    return inv


def build_weekly_panel(sales: pd.DataFrame, master: pd.DataFrame, dq: dict) -> pd.DataFrame:
    """Analysis-ready SKU x week panel with zero-filled inactive weeks."""
    s = sales.copy()
    s["week_start"] = s["date"].dt.to_period(C.WEEK_RULE).dt.start_time
    wk = (s.groupby(["sku_id", "week_start"])
            .agg(units_sold=("units_sold", "sum"),
                 revenue=("revenue", "sum"),
                 avg_price=("unit_price", "mean"),
                 promo_days=("promo_flag", "sum"))
            .reset_index())

    # Focus on the top-N SKUs by total units (mirrors "~200 active SKUs").
    top = (wk.groupby("sku_id")["units_sold"].sum()
             .sort_values(ascending=False).head(C.TOP_N_SKUS).index)
    wk = wk[wk["sku_id"].isin(top)]
    _log(dq, "skus_modelled", int(len(top)),
         f"Forecast scope = top {C.TOP_N_SKUS} SKUs by volume (the active assortment).")

    # Zero-fill each SKU's inactive weeks between its first and last observed week.
    panels = []
    all_weeks = pd.DatetimeIndex(sorted(wk["week_start"].unique()))
    for sku, g in wk.groupby("sku_id"):
        first = g["week_start"].min()
        grid = pd.DataFrame({"week_start": all_weeks[all_weeks >= first]})
        gg = grid.merge(g, on="week_start", how="left")
        gg["sku_id"] = sku
        gg["units_sold"] = gg["units_sold"].fillna(0)
        gg["revenue"] = gg["revenue"].fillna(0)
        gg["promo_days"] = gg["promo_days"].fillna(0)
        gg["avg_price"] = gg["avg_price"].ffill().bfill()
        panels.append(gg)
    panel = pd.concat(panels, ignore_index=True)
    panel = panel.merge(master[["sku_id", "category", "list_price", "unit_cost"]],
                        on="sku_id", how="left")
    active = panel.groupby("sku_id")["week_start"].transform("count")
    kept = panel[active >= C.MIN_ACTIVE_WEEKS].copy()
    _log(dq, "skus_after_min_history",
         int(kept["sku_id"].nunique()),
         f"SKUs with >= {C.MIN_ACTIVE_WEEKS} weeks of history kept for modelling.")
    return kept.sort_values(["sku_id", "week_start"]).reset_index(drop=True)


def main():
    print("=" * 70)
    print("PROJECT FORESIGHT — D1 DATA PIPELINE")
    print("=" * 70)
    dq: dict = {}
    raw = ingest()
    clean_df = clean(raw, dq)
    master = build_sku_master(clean_df)
    sales = build_sales_daily(clean_df, master)
    calendar = build_calendar(clean_df)
    weekly = build_weekly_panel(sales, master, dq)
    inventory = build_inventory(master, weekly, dq)

    sales.to_csv(C.DATA_PROC / "sales_daily.csv", index=False)
    master.to_csv(C.DATA_PROC / "sku_master.csv", index=False)
    calendar.to_csv(C.DATA_PROC / "calendar.csv", index=False)
    inventory.to_csv(C.DATA_PROC / "inventory_snapshots.csv", index=False)
    weekly.to_csv(C.DATA_PROC / "weekly_panel.csv", index=False)
    with open(C.DATA_PROC / "data_quality_report.json", "w") as f:
        json.dump(dq, f, indent=2, default=str)

    print("-" * 70)
    print("Wrote processed tables to", C.DATA_PROC)
    print(f"  sales_daily        {len(sales):>8,} rows")
    print(f"  sku_master         {len(master):>8,} rows")
    print(f"  calendar           {len(calendar):>8,} rows")
    print(f"  inventory_snapshots{len(inventory):>8,} rows")
    print(f"  weekly_panel       {len(weekly):>8,} rows  "
          f"({weekly['sku_id'].nunique()} SKUs)")
    print("Pipeline complete.")


if __name__ == "__main__":
    main()
