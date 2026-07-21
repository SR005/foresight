# Project FORESIGHT — Submission Sheet

**Intern:** SR005 · **Program:** Zidio Internship — Data Science & Analytics
**Project:** FORESIGHT — Demand & Inventory Intelligence (client: NorthBay Living)

---

## Links to submit

| # | Item | Link |
|---|------|------|
| 1 | GitHub repository | https://github.com/SR005/foresight |
| 2 | Live dashboard (Streamlit) | https://foresight-zg7d8ovsapp3lgq5czrvab6.streamlit.app |
| 3 | Executive readout (deck) | in repo → `reports/executive_readout.pptx` (+ `.pdf`) |
| 4 | Data-quality & EDA memo | in repo → `reports/eda_memo.md` |
| 5 | README (setup + results) | in repo → `README.md` |
| 6 | Demo video (3–5 min, unlisted) | ⬜ PASTE YOUR YOUTUBE/DRIVE LINK HERE |
| 7 | Scoring service URL (optional) | ⬜ optional — dashboard already exposes scoring |

---

## Headline result (for the form / readout)

- **Forecast accuracy:** WAPE **0.56** vs seasonal-naive baseline **0.89** → **~37% better**,
  validated with rolling-origin cross-validation (leakage-free).
- **Business impact (modelled 197-SKU assortment):**
  - Rs **372,519** capital locked in overstock — 88 SKUs to clear.
  - Rs **17,931** sales at risk from stockouts — 16 SKUs to reorder.
- **Reproducible:** whole pipeline re-runs from raw data with `python src/run_all.py`.

## Deliverables map (D1–D7)

| # | Deliverable | Where |
|---|-------------|-------|
| D1 | Data pipeline | `src/pipeline.py` |
| D2 | EDA & DQ memo | `reports/eda_memo.md`, `reports/figures/` |
| D3 | Forecast model | `src/forecast.py`, `data/processed/backtest_metrics.json` |
| D4 | Risk scoring | `src/risk.py`, `data/processed/risk_scores.csv` |
| D5 | Planning dashboard | `app/streamlit_app.py` (live URL above) |
| D6 | Scoring service | `service/main.py` |
| D7 | Executive readout | `reports/executive_readout.pptx` |

## Still to do before submitting

1. Record the demo video → upload unlisted → paste link in row 6 above.
2. (Optional) deploy `service/main.py` for row 7.
3. Fill the Zidio cohort submission form with rows 1–6.
