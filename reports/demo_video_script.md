# Demo video script (3–5 minutes)

A tight walkthrough to record (screen capture) for the cohort submission.

**0:00 – 0:30 · Problem.** "NorthBay Living plans ~200 SKUs on gut feel — they
stock out of best-sellers and sit on dead stock. FORESIGHT forecasts weekly
demand and flags what to reorder vs clear, with rupees at stake."

**0:30 – 1:15 · Pipeline & data (terminal).** Run `python src/run_all.py`. Point
out: 1.07M raw rows → 1.00M clean (94%), cleaning decisions logged to
`data_quality_report.json`, four-table schema + weekly panel built, all seeded.

**1:15 – 2:15 · Forecast honesty (terminal + figure).** Show the rolling-origin
backtest output and `backtest_metrics.json`: model WAPE 0.56 vs seasonal-naive
0.89 — **37% better**, no leakage. Open `fig_forecast_example.png` (actual +
baseline + forecast + 80% interval).

**2:15 – 3:15 · Risk & decisioning (dashboard).** `streamlit run
app/streamlit_app.py`. Filter to "Reorder now", read the prioritised list; show
the decisioning grid; pick a SKU and show forecast vs actual + its action and
rupees at stake.

**3:15 – 4:00 · Service (browser).** Hit `http://localhost:8000/docs`, run
`GET /score/{sku_id}` live, show a 404 on a bad SKU to prove graceful handling.

**4:00 – 4:45 · Executive readout.** Flip through `executive_readout.pptx`:
Rs 372k locked / Rs 18k at risk, top actions, honest limitations.

**4:45 – 5:00 · Close.** "Reproducible from raw data in one command, usable by
the ops team without me. Deliver it like a consultant, defend it like a
scientist."
