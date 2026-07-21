"""
Project FORESIGHT — D4 Risk Scoring & Decisioning.

Converts the demand forecast + the current inventory position into a decision
for every SKU. The logic is deliberately transparent (simple, auditable
formulas — no black box) and reconciles with the stockout-vs-overstock grid in
Section 08 of the brief.

  stockout_score  in [0,1]  — how exposed the SKU is to running out over its
                              replenishment lead time.
  overstock_score in [0,1]  — how much dead cover the SKU is sitting on relative
                              to forecast demand.
  quadrant                  — Reorder now / Markdown-clear / Watch-volatile / Healthy
  action                    — the recommended next step
  value_at_stake (Rs)       — sales at risk (stockout) or capital locked (overstock)

Run:  python src/risk.py     (requires pipeline.py + forecast.py to have run)

Output: data/processed/risk_scores.csv , risk_summary.json
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

import config as C


def load_inputs():
    fc = pd.read_csv(C.DATA_PROC / "forecast.csv", parse_dates=["week_start"])
    inv = pd.read_csv(C.DATA_PROC / "inventory_snapshots.csv")
    master = pd.read_csv(C.DATA_PROC / "sku_master.csv")
    panel = pd.read_csv(C.DATA_PROC / "weekly_panel.csv", parse_dates=["week_start"])
    return fc, inv, master, panel


def recent_weekly_sigma(panel: pd.DataFrame, weeks: int = 12) -> pd.Series:
    last = panel["week_start"].max()
    recent = panel[panel["week_start"] > last - pd.Timedelta(weeks=weeks)]
    return recent.groupby("sku_id")["units_sold"].std().fillna(0)


def score(fc, inv, master, panel):
    sigma = recent_weekly_sigma(panel)

    # Forecast demand over the horizon and over each SKU's lead time.
    horizon_demand = fc.groupby("sku_id")["forecast"].sum().rename("demand_horizon")
    weekly_avg = fc.groupby("sku_id")["forecast"].mean().rename("weekly_forecast")

    df = master.merge(inv, on="sku_id", how="inner")
    df = df[df["sku_id"].isin(fc["sku_id"].unique())].copy()   # modelled SKUs only
    df = df.merge(horizon_demand, on="sku_id").merge(weekly_avg, on="sku_id")
    df["sigma_wk"] = df["sku_id"].map(sigma).fillna(0)

    df["lead_weeks"] = np.ceil(df["lead_time_days"] / 7).astype(int)
    # Demand over the lead time (first `lead_weeks` forecast weeks per SKU).
    lt_rows = []
    for s, g in fc.sort_values("horizon_step").groupby("sku_id"):
        lw = int(np.ceil(df.loc[df.sku_id == s, "lead_time_days"].iloc[0] / 7))
        lt_rows.append((s, g.head(lw)["forecast"].sum()))
    df = df.merge(pd.DataFrame(lt_rows, columns=["sku_id", "demand_leadtime"]),
                  on="sku_id")

    df["available"] = df["on_hand_units"] + df["on_order_units"]
    df["safety_stock"] = (C.SERVICE_LEVEL_Z * df["sigma_wk"]
                          * np.sqrt(df["lead_weeks"].clip(lower=1))).round(1)
    df["need_leadtime"] = df["demand_leadtime"] + df["safety_stock"]

    # ---- Stockout score: 1 - coverage of lead-time need (clipped to [0,1]).
    df["stockout_score"] = (1 - df["available"] / df["need_leadtime"].replace(0, np.nan)
                            ).clip(0, 1).fillna(0).round(3)

    # ---- Overstock score: excess weeks of cover beyond OVERSTOCK_WEEKS.
    df["weeks_of_cover"] = (df["on_hand_units"]
                            / df["weekly_forecast"].replace(0, np.nan)).fillna(99)
    df["overstock_score"] = ((df["weeks_of_cover"] - C.OVERSTOCK_WEEKS)
                             / (2 * C.OVERSTOCK_WEEKS)).clip(0, 1).round(3)

    # ---- Quadrant & action (reconciles with Section 08 grid).
    t = C.RISK_THRESHOLD
    def quadrant(r):
        hi_so, hi_os = r.stockout_score >= t, r.overstock_score >= t
        if hi_so and not hi_os: return "Reorder now"
        if hi_os and not hi_so: return "Markdown / clear"
        if hi_so and hi_os:     return "Watch / volatile"
        return "Healthy"
    df["quadrant"] = df.apply(quadrant, axis=1)

    action_map = {
        "Reorder now": "Raise replenishment order before stock runs out",
        "Markdown / clear": "Promote or discount to free up capital",
        "Watch / volatile": "Investigate — erratic demand; review manually",
        "Healthy": "No action needed",
    }
    df["action"] = df["quadrant"].map(action_map)

    # ---- Rupee value at stake.
    # Stockout: expected unmet demand over lead time x list_price (lost sales).
    df["unmet_units"] = (df["demand_leadtime"] - df["available"]).clip(lower=0)
    df["stockout_value"] = (df["unmet_units"] * df["list_price"]).round(0)
    # Overstock: excess units beyond horizon demand x unit_cost (locked capital).
    df["excess_units"] = (df["on_hand_units"] - df["demand_horizon"]).clip(lower=0)
    df["overstock_value"] = (df["excess_units"] * df["unit_cost"]).round(0)
    df["value_at_stake"] = np.where(
        df["quadrant"].isin(["Reorder now", "Watch / volatile"]),
        df["stockout_value"], df["overstock_value"])

    cols = ["sku_id", "description", "category", "quadrant", "action",
            "stockout_score", "overstock_score", "value_at_stake",
            "on_hand_units", "on_order_units", "reorder_point", "lead_time_days",
            "demand_leadtime", "demand_horizon", "weeks_of_cover",
            "safety_stock", "stockout_value", "overstock_value",
            "list_price", "unit_cost"]
    return df[cols].sort_values("value_at_stake", ascending=False).reset_index(drop=True)


def summarise(rs: pd.DataFrame) -> dict:
    q = rs["quadrant"].value_counts().to_dict()
    return {
        "currency": C.CURRENCY,
        "skus_scored": int(len(rs)),
        "quadrant_counts": q,
        "sales_at_risk_stockout": float(
            rs.loc[rs.quadrant.isin(["Reorder now", "Watch / volatile"]),
                   "stockout_value"].sum()),
        "capital_locked_overstock": float(
            rs.loc[rs.quadrant.isin(["Markdown / clear", "Watch / volatile"]),
                   "overstock_value"].sum()),
        "top_reorder": rs[rs.quadrant == "Reorder now"]
            .head(5)[["sku_id", "description", "value_at_stake"]].to_dict("records"),
        "top_markdown": rs[rs.quadrant == "Markdown / clear"]
            .head(5)[["sku_id", "description", "value_at_stake"]].to_dict("records"),
    }


def main():
    print("=" * 70)
    print("PROJECT FORESIGHT — D4 RISK SCORING & DECISIONING")
    print("=" * 70)
    fc, inv, master, panel = load_inputs()
    rs = score(fc, inv, master, panel)
    summ = summarise(rs)

    rs.to_csv(C.DATA_PROC / "risk_scores.csv", index=False)
    with open(C.DATA_PROC / "risk_summary.json", "w") as f:
        json.dump(summ, f, indent=2)

    print(f"Scored {summ['skus_scored']} SKUs")
    for k, v in summ["quadrant_counts"].items():
        print(f"  {k:<18} {v:>4} SKUs")
    print(f"\n  Sales at risk (stockout)   : {C.CURRENCY} {summ['sales_at_risk_stockout']:,.0f}")
    print(f"  Capital locked (overstock) : {C.CURRENCY} {summ['capital_locked_overstock']:,.0f}")
    print("\nWrote risk_scores.csv, risk_summary.json")
    print("Risk scoring complete.")


if __name__ == "__main__":
    main()
