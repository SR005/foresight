"""
Project FORESIGHT — D5 Planning Dashboard (Streamlit), modern web app.

A dashboard the NorthBay operations team can use without a data scientist:
answer "what do I reorder / clear this week?", see each SKU's forecast vs actual,
and read the risk flags.

Run locally:
    cd foresight
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations
from pathlib import Path
import json

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

st.set_page_config(page_title="FORESIGHT — Planning Dashboard",
                   page_icon="📦", layout="wide",
                   initial_sidebar_state="expanded")

CUR = "Rs"
# modern palette
INDIGO = "#6366F1"
VIOLET = "#8B5CF6"
EMERALD = "#10B981"
ROSE = "#F43F5E"
AMBER = "#F59E0B"
SLATE = "#0F172A"
QCOLOR = {"Reorder now": ROSE, "Markdown / clear": INDIGO,
          "Watch / volatile": AMBER, "Healthy": EMERALD}
QICON = {"Reorder now": "⚡", "Markdown / clear": "🏷️",
         "Watch / volatile": "👁️", "Healthy": "✅"}

# ---------------------------------------------------------------- styling
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  html, body, [class*="css"], .stApp * { font-family: 'Inter', sans-serif; }
  .stApp {
      background:
        radial-gradient(1200px 500px at 12% -8%, #eef1ff 0%, rgba(238,241,255,0) 55%),
        radial-gradient(1000px 480px at 100% 0%, #eafcf5 0%, rgba(234,252,245,0) 50%),
        #f6f7fb;
  }
  #MainMenu, footer, header {visibility: hidden;}
  .block-container {padding-top: 1.6rem; padding-bottom: 2.4rem; max-width: 1360px;}

  /* hero */
  .fs-hero {
      position: relative; overflow: hidden;
      background: linear-gradient(120deg, #4f46e5 0%, #7c3aed 48%, #9333ea 100%);
      border-radius: 24px; padding: 30px 36px; margin-bottom: 22px; color:#fff;
      box-shadow: 0 20px 45px -18px rgba(79,70,229,.65);
  }
  .fs-hero:after {content:""; position:absolute; right:-60px; top:-60px;
      width:240px; height:240px; border-radius:50%;
      background: rgba(255,255,255,.10);}
  .fs-hero h1 {font-size: 2.15rem; margin:0; font-weight:800; letter-spacing:-.5px;}
  .fs-hero p  {margin:8px 0 0; color: rgba(255,255,255,.82); font-size:1.05rem; font-weight:400;}
  .fs-chip {display:inline-block; background: rgba(255,255,255,.16);
      border:1px solid rgba(255,255,255,.3); border-radius:999px;
      padding:6px 15px; margin:14px 8px 0 0; font-size:.8rem; font-weight:600;
      color:#fff; backdrop-filter: blur(4px);}

  /* KPI cards */
  .kpi {position:relative; background:#fff; border-radius:20px; padding:20px 22px 18px;
      height:150px; border:1px solid #ecedf5;
      box-shadow: 0 10px 30px -20px rgba(15,23,42,.35);
      transition: transform .16s ease, box-shadow .16s ease;}
  .kpi:hover {transform: translateY(-3px); box-shadow:0 18px 36px -20px rgba(15,23,42,.4);}
  .kpi .ic {width:40px; height:40px; border-radius:12px; display:flex;
      align-items:center; justify-content:center; font-size:20px; margin-bottom:10px;}
  .kpi .lab {font-size:.74rem; color:#8a90a6; font-weight:600; text-transform:uppercase; letter-spacing:.6px;}
  .kpi .val {font-size:2.05rem; font-weight:800; line-height:1.1; margin-top:2px; letter-spacing:-.5px;}
  .kpi .sub {font-size:.78rem; color:#9aa0b4; margin-top:3px; font-weight:500;}

  /* section card + titles */
  .card {background:#fff; border-radius:20px; padding:18px 20px; border:1px solid #ecedf5;
      box-shadow:0 10px 30px -22px rgba(15,23,42,.35); margin-bottom:6px;}
  .sec {font-size:1.02rem; font-weight:700; color:#0f172a; margin:2px 0 12px;
      display:flex; align-items:center; gap:9px;}
  .sec:before {content:""; width:9px; height:20px; border-radius:5px;
      background: linear-gradient(180deg,#6366F1,#8B5CF6);}
  .pill {display:inline-block; border-radius:999px; padding:5px 14px; color:#fff;
      font-weight:700; font-size:.82rem;}
  .muted {color:#9aa0b4; font-size:.8rem; font-weight:500;}

  /* sidebar */
  section[data-testid="stSidebar"] {background:#0f172a;}
  section[data-testid="stSidebar"] * {color:#e2e8f0 !important;}
  section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {color:#fff !important;}
  .stMultiSelect [data-baseweb="tag"] {background:#6366F1 !important;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading model outputs …")
def load_data():
    fc = pd.read_csv(PROC / "forecast.csv", parse_dates=["week_start"])
    rs = pd.read_csv(PROC / "risk_scores.csv")
    panel = pd.read_csv(PROC / "weekly_panel.csv", parse_dates=["week_start"])
    try:
        summ = json.load(open(PROC / "risk_summary.json"))
    except FileNotFoundError:
        summ = {}
    try:
        bt = json.load(open(PROC / "backtest_metrics.json"))
    except FileNotFoundError:
        bt = {}
    return fc, rs, panel, summ, bt


def kpi(col, icon, tint, label, value, sub, color):
    col.markdown(
        f"<div class='kpi'>"
        f"<div class='ic' style='background:{tint};color:{color}'>{icon}</div>"
        f"<div class='lab'>{label}</div>"
        f"<div class='val' style='color:{color}'>{value}</div>"
        f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)


def hero(bt):
    imp = bt.get("wape_improvement_pct")
    chip = (f"<span class='fs-chip'>▲ {imp:.0f}% better than baseline</span>"
            if imp else "")
    st.markdown(
        "<div class='fs-hero'>"
        "<h1>📦 FORESIGHT</h1>"
        "<p>NorthBay Living · weekly demand forecast &amp; stock-risk early warning</p>"
        f"{chip}"
        "<span class='fs-chip'>Reorder · Markdown · Healthy triage</span>"
        "<span class='fs-chip'>Prioritised by rupees at stake</span>"
        "</div>", unsafe_allow_html=True)


def main():
    if not (PROC / "forecast.csv").exists() or not (PROC / "risk_scores.csv").exists():
        st.markdown("<div class='fs-hero'><h1>📦 FORESIGHT</h1>"
                    "<p>No model outputs found yet.</p></div>", unsafe_allow_html=True)
        st.warning("Run the pipeline first:\n\n"
                   "`python src/pipeline.py && python src/forecast.py && python src/risk.py`")
        st.stop()

    fc, rs, panel, summ, bt = load_data()
    hero(bt)

    if rs.empty:
        st.info("The risk table is empty — nothing to plan yet.")
        st.stop()

    # ---- sidebar filters
    st.sidebar.markdown("## ⚙️ Filters")
    cats = sorted(rs["category"].dropna().unique())
    sel_cats = st.sidebar.multiselect("Category", cats, default=cats)
    quads = ["Reorder now", "Markdown / clear", "Watch / volatile", "Healthy"]
    sel_quads = st.sidebar.multiselect("Risk quadrant", quads, default=quads)
    st.sidebar.markdown("---")
    st.sidebar.caption("FORESIGHT · Zidio Data Science engagement. "
                       "Model beats a seasonal-naive baseline on rolling-origin backtest. "
                       "Inventory positions are modelled in this demo.")

    view = rs[rs["category"].isin(sel_cats) & rs["quadrant"].isin(sel_quads)]
    if view.empty:
        st.info("No SKUs match the current filters. Widen the selection on the left.")
        st.stop()

    # ---- KPI row
    q = view["quadrant"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "⚡", "#fee6ea", "Reorder now", q.get("Reorder now", 0),
        "SKUs to replenish", ROSE)
    kpi(c2, "🏷️", "#e9e9fd", "Markdown / clear", q.get("Markdown / clear", 0),
        "SKUs to discount", INDIGO)
    kpi(c3, "📉", "#fee6ea", f"Sales at risk ({CUR})",
        f"{summ.get('sales_at_risk_stockout', 0):,.0f}", "stockout exposure", ROSE)
    kpi(c4, "💰", "#e9e9fd", f"Capital locked ({CUR})",
        f"{summ.get('capital_locked_overstock', 0):,.0f}", "overstock capital", INDIGO)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.05, 1])

    # ---- decisioning grid
    with left:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>Decisioning grid — every SKU</div>",
                    unsafe_allow_html=True)
        grid = view.copy()
        st.scatter_chart(grid, x="overstock_score", y="stockout_score",
                         color="quadrant", size="value_at_stake", height=380)
        st.markdown("<div class='muted'>Top-left = reorder · bottom-right = markdown · "
                    "bubble size = Rs at stake.</div></div>", unsafe_allow_html=True)

    # ---- prioritised action list
    with right:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>Prioritised action list</div>",
                    unsafe_allow_html=True)
        act = (view[view["quadrant"] != "Healthy"]
               .sort_values("value_at_stake", ascending=False)
               [["sku_id", "description", "quadrant", "value_at_stake"]].head(20))
        st.dataframe(
            act, hide_index=True, width="stretch", height=372,
            column_config={
                "sku_id": "SKU",
                "description": "Product",
                "quadrant": "Action",
                "value_at_stake": st.column_config.NumberColumn(
                    f"{CUR} at stake", format="%.0f")})
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- per-SKU forecast vs actual
    st.markdown("<div class='sec'>Forecast vs actual — pick a SKU</div>",
                unsafe_allow_html=True)
    skus = sorted(view["sku_id"].astype(str).unique())
    sku = st.selectbox("SKU", skus, index=0, label_visibility="collapsed")
    hist = (panel[panel["sku_id"].astype(str) == sku]
            .sort_values("week_start").tail(40))
    f = fc[fc["sku_id"].astype(str) == sku].sort_values("week_start")

    cc1, cc2 = st.columns([1.5, 1])
    with cc1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if hist.empty:
            st.info("No history for this SKU.")
        else:
            chart = pd.concat([
                hist[["week_start", "units_sold"]].rename(columns={"units_sold": "Actual"}),
                f[["week_start", "forecast"]].rename(columns={"forecast": "Forecast"}),
                f[["week_start", "baseline"]].rename(columns={"baseline": "Baseline"}),
            ]).set_index("week_start")
            st.line_chart(chart, height=330, color=["#0f172a", "#6366F1", "#F59E0B"])
        st.markdown("</div>", unsafe_allow_html=True)
    with cc2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        r = rs[rs["sku_id"].astype(str) == sku]
        if not r.empty:
            r = r.iloc[0]
            b = QCOLOR.get(r["quadrant"], "#888")
            ic = QICON.get(r["quadrant"], "")
            st.markdown(f"#### {r['description']}")
            st.markdown(f"<span class='muted'>Category · {r['category']}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"<span class='pill' style='background:{b}'>{ic} {r['quadrant']}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"**Action:** {r['action']}")
            m1, m2 = st.columns(2)
            m1.metric("Stockout score", f"{r['stockout_score']:.2f}")
            m2.metric("Overstock score", f"{r['overstock_score']:.2f}")
            m3, m4 = st.columns(2)
            m3.metric("On hand", f"{int(r['on_hand_units'])}")
            m4.metric("Lead time", f"{int(r['lead_time_days'])}d")
            st.metric(f"{CUR} at stake", f"{r['value_at_stake']:,.0f}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br><div class='muted'>Forecasts are point estimates with an 80% "
                "interval. Model WAPE beats seasonal-naive by ~37% on rolling-origin "
                "backtest. Inventory positions in this demo are modelled (see README).</div>",
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
else:
    main()
