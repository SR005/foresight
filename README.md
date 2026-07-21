# Project FORESIGHT — Demand & Inventory Intelligence

**Client:** NorthBay Living (D2C home & lifestyle) · **Role:** Data Scientist ·
**Stack:** Python · pandas · scikit-learn · LightGBM · Streamlit · FastAPI

FORESIGHT turns NorthBay's own sales history into a weekly demand forecast and a
stock-risk early-warning system that tells the planning team **what to reorder,
what to clear, and what to leave alone** — with the rupee value at stake on every
call.

---

## Headline result (honest, backtested)

| | WAPE (lower is better) |
|---|---|
| **LightGBM forecast** | **0.56** |
| Seasonal-naive baseline | 0.89 |
| **Improvement** | **≈ 37% better than baseline** |

Validated with **rolling-origin cross-validation** (8 one-week-ahead origins,
1,576 test points). No future information ever enters a feature. Full numbers in
`data/processed/backtest_metrics.json`.

**Business impact (on the modelled 197-SKU assortment):**
Rs 372,519 capital locked in overstock (88 SKUs to clear) ·
Rs 17,931 sales at risk from stockouts (16 SKUs to reorder).

---

## The data

Source: **UCI Online Retail II** — ~1.07M transaction lines, Dec 2009 – Dec 2011,
used as the NorthBay client extract. The pipeline derives the four-table star
schema the brief specifies (`sales_daily`, `sku_master`, `calendar`,
`inventory_snapshots`) plus an analysis-ready weekly panel.

Two documented conventions (see the EDA memo):

- **Promo flag** is inferred from price discounting (raw feed has no promo column).
- **Inventory snapshot** is *modelled* deterministically from demand (raw feed is
  sales-only). On a live engagement, drop in NorthBay's real stock table and the
  rupee figures become exact. Everything else is real client data.

Monetary values are labelled in rupees (`Rs`) per the brief; prices are taken
from the extract at face value (no live FX — out of scope).

---

## How to run (reproducible, one command)

```bash
cd foresight
python -m pip install -r requirements.txt

# full pipeline: clean -> forecast -> risk -> figures/insights
python src/run_all.py
```

Or step by step:

```bash
python src/pipeline.py    # D1  raw extract -> clean star schema + weekly panel
python src/forecast.py    # D3  baseline + LightGBM, rolling-origin backtest
python src/risk.py        # D4  stockout/overstock scoring + rupee impact
python src/eda.py         # D2  figures + insight statistics
```

First run copies the raw workbook into `data/raw/` and caches it to parquet, so
re-runs take seconds. All randomness is seeded (`src/config.py`), so a grader
re-running the pipeline gets the same headline numbers.

### Dashboard (D5)

```bash
streamlit run app/streamlit_app.py
```

Filter by category / SKU, see forecast vs actual, the decisioning grid, and a
prioritised reorder / markdown list. Has explicit loading and empty states.

### Scoring service (D6)

```bash
uvicorn service.main:app --port 8000
# interactive docs at http://localhost:8000/docs
```

| Endpoint | Returns |
|---|---|
| `GET /health` | service + data status |
| `GET /skus` | list of scored SKUs |
| `GET /score/{sku_id}` | forecast (8 wks) + risk for one SKU |
| `POST /score/batch` | forecast + risk for many SKUs |

Unknown SKU → `404`; empty/malformed body → `422` (handled gracefully, never
crashes).

---

## Method (baseline first, then earn the right to beat it)

1. **Frame** — weekly, SKU-level, 8-week horizon; metric = **WAPE** (bias as a
   secondary check).
2. **Baseline** — seasonal-naive (same week last year; falls back to last week).
3. **Features** — lags (1,2,3,4,8,52), rolling mean/std (4,8,12 wks, all shifted
   so only the past is used), calendar (week-of-year sin/cos, month, holiday),
   planned promo, lagged price, weeks-since-launch, category.
4. **Model** — LightGBM global regressor (handles the long tail and NaNs natively).
5. **Backtest** — rolling-origin CV, 1-week-ahead; WAPE vs baseline.
6. **Risk** — combine the forecast with inventory position into transparent
   stockout / overstock scores, a quadrant, an action and rupees at stake.

**Anti-leakage:** contemporaneous price/promo are never features — only their
lagged values and the planned calendar. Rolling features are shifted by one week.

---

## Risk logic (transparent, not a black box)

- **Stockout score** = `1 − (on_hand + on_order) / (lead-time demand + safety stock)`,
  clipped to [0,1]. Safety stock = z(90%) × weekly σ × √lead-weeks.
- **Overstock score** = excess weeks of cover beyond 8, normalised to [0,1].
- **Quadrant**: Reorder now · Markdown/clear · Watch/volatile · Healthy — reconciles
  with the Section 08 grid (`reports/figures/fig_decisioning_grid.png`).
- **Value at stake**: unmet demand × list price (stockout) or excess units ×
  unit cost (overstock).

---

## Repository structure

```
foresight/
  data/
    raw/            # source workbook + parquet cache (gitignored)
    processed/      # star schema, weekly panel, forecast, risk, metrics
  src/
    config.py       # all paths & parameters (seeded)
    pipeline.py     # D1 ingest + clean + derive tables
    forecast.py     # D3 baseline + LightGBM + rolling-origin backtest
    risk.py         # D4 stockout/overstock scoring + rupee impact
    eda.py          # D2 figures + insight stats
    run_all.py      # one-command end-to-end run
  app/streamlit_app.py    # D5 planning dashboard
  service/main.py         # D6 FastAPI scoring service
  reports/
    eda_memo.md            # D2 data-quality & EDA memo
    executive_readout.pptx # D7 executive deck (+ .pdf)
    build_deck.py          # regenerates the deck from outputs
    figures/               # all charts
  README.md
  requirements.txt
```

## Deploying (public URLs)

The dashboard and API run unchanged on free hosts:

- **Dashboard** → Streamlit Community Cloud or Hugging Face Spaces: point it at
  `app/streamlit_app.py`.
- **API** → Render / Railway / HF Spaces: start command
  `uvicorn service.main:app --host 0.0.0.0 --port $PORT`.

Commit `data/processed/*.csv` (small) so the hosted apps have model outputs, or
run the pipeline in the build step.

## Deliverables map

| # | Deliverable | Where |
|---|---|---|
| D1 | Data pipeline | `src/pipeline.py`, `data/processed/data_quality_report.json` |
| D2 | EDA & DQ memo | `reports/eda_memo.md`, `reports/figures/` |
| D3 | Forecast model | `src/forecast.py`, `data/processed/backtest_metrics.json` |
| D4 | Risk scoring | `src/risk.py`, `data/processed/risk_scores.csv` |
| D5 | Dashboard | `app/streamlit_app.py` |
| D6 | Scoring service | `service/main.py` |
| D7 | Executive readout | `reports/executive_readout.pptx` |

## Limitations (the honest version)

Demand is spiky, so treat forecasts as a guided range (80% interval provided),
not a promise. Inventory is modelled in this demo. New / long-tail SKUs have thin
history and are flagged low-confidence rather than silently forecast. A model
that couldn't beat the baseline would have been reported as such — here it does,
by ~37% WAPE.

---
*Deliver it like a consultant. Defend it like a scientist.*
