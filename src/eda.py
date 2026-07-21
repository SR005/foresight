"""
Project FORESIGHT — D2 EDA figures + insight statistics.

Generates the labelled charts used in the EDA memo, the executive readout and
the dashboard, and prints the headline statistics behind the written insights.

Run:  python src/eda.py    (requires pipeline.py + forecast.py + risk.py)

Figures written to reports/figures/:
    fig_weekly_demand.png       total weekly demand (trend + seasonality)
    fig_top_movers.png          top 15 SKUs by units
    fig_category_mix.png        revenue by category
    fig_dead_stock.png          slow-mover / dead-stock distribution
    fig_forecast_example.png    actual + baseline + model forecast (one SKU)
    fig_decisioning_grid.png    stockout vs overstock grid (bubble = value)
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as C

plt.rcParams.update({"figure.dpi": 110, "axes.grid": True,
                     "grid.alpha": 0.3, "font.size": 10})
INK = "#3b3b6d"
ACCENT = "#6b6bd6"


def load():
    sales = pd.read_csv(C.DATA_PROC / "sales_daily.csv", parse_dates=["date"])
    master = pd.read_csv(C.DATA_PROC / "sku_master.csv")
    panel = pd.read_csv(C.DATA_PROC / "weekly_panel.csv", parse_dates=["week_start"])
    fc = pd.read_csv(C.DATA_PROC / "forecast.csv", parse_dates=["week_start"])
    rs = pd.read_csv(C.DATA_PROC / "risk_scores.csv")
    return sales, master, panel, fc, rs


def fig_weekly_demand(sales):
    w = (sales.assign(week=sales["date"].dt.to_period("W-SUN").dt.start_time)
              .groupby("week")["units_sold"].sum())
    w = w.iloc[1:-1]  # drop partial first/last weeks
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(w.index, w.values, color=INK, lw=1.6)
    ax.fill_between(w.index, w.values, color=ACCENT, alpha=0.12)
    ax.set_title("Total weekly demand — trend & seasonality (all SKUs)")
    ax.set_xlabel("Week"); ax.set_ylabel("Units sold / week")
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_weekly_demand.png"); plt.close(fig)


def fig_top_movers(sales, master):
    top = (sales.groupby("sku_id")["units_sold"].sum()
                .sort_values(ascending=False).head(15).iloc[::-1])
    names = master.set_index("sku_id")["description"].to_dict()
    labels = [f"{s} · {str(names.get(s,''))[:26]}" for s in top.index]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.barh(labels, top.values, color=ACCENT)
    ax.set_title("Top 15 SKUs by total units sold")
    ax.set_xlabel("Units sold (full history)")
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_top_movers.png"); plt.close(fig)


def fig_category_mix(sales, master):
    m = sales.merge(master[["sku_id", "category"]], on="sku_id", how="left")
    rev = m.groupby("category")["revenue"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(rev.index, rev.values, color=INK)
    ax.set_title(f"Revenue by category ({C.CURRENCY})")
    ax.set_xlabel(f"Revenue ({C.CURRENCY})")
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_category_mix.png"); plt.close(fig)


def fig_dead_stock(panel):
    last = panel["week_start"].max()
    recent = panel[panel["week_start"] > last - pd.Timedelta(weeks=8)]
    sold = recent.groupby("sku_id")["units_sold"].sum()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.hist(np.log1p(sold.values), bins=30, color=ACCENT, edgecolor="white")
    ax.axvline(np.log1p(1), color="crimson", ls="--", lw=1.2,
               label="near-zero (dead stock)")
    ax.set_title("Distribution of last-8-week sales (log scale) — dead-stock tail")
    ax.set_xlabel("log(1 + units sold, last 8 weeks)"); ax.set_ylabel("# SKUs")
    ax.legend()
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_dead_stock.png"); plt.close(fig)


def fig_forecast_example(panel, fc):
    # Pick the highest-volume SKU for an illustrative forecast chart.
    top_sku = panel.groupby("sku_id")["units_sold"].sum().idxmax()
    h = panel[panel["sku_id"] == top_sku].sort_values("week_start").tail(40)
    f = fc[fc["sku_id"] == top_sku].sort_values("week_start")
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(h["week_start"], h["units_sold"], color=INK, lw=1.6, label="Actual demand")
    ax.plot(f["week_start"], f["forecast"], color=ACCENT, lw=2, label="Model forecast")
    ax.plot(f["week_start"], f["baseline"], color="darkorange", ls="--",
            lw=1.4, label="Seasonal-naive baseline")
    ax.fill_between(f["week_start"], f["yhat_lower"], f["yhat_upper"],
                    color=ACCENT, alpha=0.18, label="80% interval")
    ax.axvline(h["week_start"].max(), color="grey", ls=":", lw=1)
    ax.set_title(f"Forecast vs actual — SKU {top_sku} (8-week horizon)")
    ax.set_xlabel("Week"); ax.set_ylabel("Units / week"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_forecast_example.png"); plt.close(fig)


def fig_decisioning_grid(rs):
    colours = {"Reorder now": "#d1495b", "Markdown / clear": "#6b6bd6",
               "Watch / volatile": "#e0a41a", "Healthy": "#3a9679"}
    fig, ax = plt.subplots(figsize=(6.4, 6))
    for q, c in colours.items():
        d = rs[rs["quadrant"] == q]
        if d.empty:
            continue
        ax.scatter(d["overstock_score"], d["stockout_score"], s=np.sqrt(
            d["value_at_stake"].clip(lower=1)) * 3, c=c, alpha=0.6,
            edgecolors="white", linewidths=0.5, label=f"{q} ({len(d)})")
    ax.axhline(C.RISK_THRESHOLD, color="grey", lw=1); ax.axvline(C.RISK_THRESHOLD, color="grey", lw=1)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Overstock risk  →"); ax.set_ylabel("Stockout risk  →")
    ax.set_title("Decisioning view — every SKU (bubble = Rs at stake)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=8)
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig_decisioning_grid.png",
                                    bbox_inches="tight"); plt.close(fig)


def insights(sales, master, panel, rs):
    last = panel["week_start"].max()
    recent = panel[panel["week_start"] > last - pd.Timedelta(weeks=8)]
    dead = recent.groupby("sku_id")["units_sold"].sum()
    dead_ct = int((dead <= 1).sum())
    total_units = int(sales["units_sold"].sum())
    top20 = (sales.groupby("sku_id")["units_sold"].sum()
                  .sort_values(ascending=False))
    top20_share = top20.head(int(0.2 * len(top20))).sum() / top20.sum()
    q4 = sales[sales["date"].dt.month.isin([11, 12])]["units_sold"].sum()
    q4_share = q4 / total_units
    stats = {
        "total_units": total_units,
        "distinct_skus_all": int(sales["sku_id"].nunique()),
        "modelled_skus": int(panel["sku_id"].nunique()),
        "top20pct_volume_share": round(float(top20_share), 3),
        "nov_dec_volume_share": round(float(q4_share), 3),
        "dead_stock_skus_last8w": dead_ct,
        "quadrant_counts": rs["quadrant"].value_counts().to_dict(),
    }
    with open(C.DATA_PROC / "eda_insights.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))
    return stats


def main():
    print("=" * 70)
    print("PROJECT FORESIGHT — D2 EDA FIGURES & INSIGHTS")
    print("=" * 70)
    sales, master, panel, fc, rs = load()
    fig_weekly_demand(sales)
    fig_top_movers(sales, master)
    fig_category_mix(sales, master)
    fig_dead_stock(panel)
    fig_forecast_example(panel, fc)
    fig_decisioning_grid(rs)
    print("Figures written to", C.FIGURES)
    insights(sales, master, panel, rs)
    print("EDA complete.")


if __name__ == "__main__":
    main()
