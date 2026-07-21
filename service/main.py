"""
Project FORESIGHT — D6 Scoring Service (FastAPI).

A small, documented API that returns the demand forecast + stock risk for a SKU
(or a batch of SKUs). Reads the artefacts produced by the pipeline / forecast /
risk modules — it does not retrain on the fly, so responses are fast and stable.

Run locally:
    cd foresight
    uvicorn service.main:app --reload --port 8000
Then open  http://localhost:8000/docs  for interactive, documented I/O.

Deploy (Render / Hugging Face Spaces / Railway): run the same uvicorn command;
point the platform at this module. See README section "Deploying".
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

app = FastAPI(
    title="Project FORESIGHT — Scoring Service",
    version="1.0",
    description="Returns weekly demand forecast + stockout/overstock risk for a "
                "NorthBay Living SKU. Data is refreshed by re-running the pipeline.",
)

# ------------------------------------------------------------------ data load
_STATE: dict = {}


def _load():
    try:
        fc = pd.read_csv(PROC / "forecast.csv", parse_dates=["week_start"])
        rs = pd.read_csv(PROC / "risk_scores.csv")
        _STATE["fc"] = fc
        _STATE["rs"] = rs
        _STATE["skus"] = sorted(set(fc["sku_id"].astype(str)))
        _STATE["loaded"] = True
    except FileNotFoundError:
        _STATE["loaded"] = False


@app.on_event("startup")
def startup():
    _load()


# ------------------------------------------------------------------ schemas
class ForecastWeek(BaseModel):
    week_start: str
    horizon_step: int
    forecast: float
    baseline: float
    yhat_lower: float
    yhat_upper: float


class SkuScore(BaseModel):
    sku_id: str
    description: Optional[str] = None
    category: Optional[str] = None
    quadrant: Optional[str] = Field(None, description="Reorder now / Markdown-clear / Watch / Healthy")
    action: Optional[str] = None
    stockout_score: Optional[float] = None
    overstock_score: Optional[float] = None
    value_at_stake: Optional[float] = None
    forecast_horizon: List[ForecastWeek] = []


class BatchRequest(BaseModel):
    sku_ids: List[str] = Field(..., min_items=1, description="One or more SKU ids.")


class BatchResponse(BaseModel):
    results: List[SkuScore]
    not_found: List[str]


# ------------------------------------------------------------------ helpers
def _score_one(sku_id: str) -> Optional[SkuScore]:
    sku_id = str(sku_id).strip().upper()
    fc, rs = _STATE["fc"], _STATE["rs"]
    fsku = fc[fc["sku_id"].astype(str).str.upper() == sku_id]
    if fsku.empty:
        return None
    rrow = rs[rs["sku_id"].astype(str).str.upper() == sku_id]
    weeks = [ForecastWeek(
        week_start=str(r.week_start.date()), horizon_step=int(r.horizon_step),
        forecast=float(r.forecast), baseline=float(r.baseline),
        yhat_lower=float(r.yhat_lower), yhat_upper=float(r.yhat_upper))
        for r in fsku.itertuples()]
    out = SkuScore(sku_id=sku_id, forecast_horizon=weeks)
    if not rrow.empty:
        r = rrow.iloc[0]
        out.description = str(r["description"])
        out.category = str(r["category"])
        out.quadrant = str(r["quadrant"])
        out.action = str(r["action"])
        out.stockout_score = float(r["stockout_score"])
        out.overstock_score = float(r["overstock_score"])
        out.value_at_stake = float(r["value_at_stake"])
    return out


# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    return {"status": "ok" if _STATE.get("loaded") else "no_data",
            "skus_available": len(_STATE.get("skus", []))}


@app.get("/skus", response_model=List[str])
def list_skus():
    if not _STATE.get("loaded"):
        raise HTTPException(503, "Model artefacts not found — run the pipeline first.")
    return _STATE["skus"]


@app.get("/score/{sku_id}", response_model=SkuScore)
def score(sku_id: str):
    if not _STATE.get("loaded"):
        raise HTTPException(503, "Model artefacts not found — run the pipeline first.")
    res = _score_one(sku_id)
    if res is None:
        raise HTTPException(404, f"SKU '{sku_id}' not found in the modelled assortment.")
    return res


@app.post("/score/batch", response_model=BatchResponse)
def score_batch(req: BatchRequest):
    if not _STATE.get("loaded"):
        raise HTTPException(503, "Model artefacts not found — run the pipeline first.")
    results, not_found = [], []
    for s in req.sku_ids:
        r = _score_one(s)
        (results.append(r) if r else not_found.append(str(s)))
    return BatchResponse(results=results, not_found=not_found)


@app.get("/")
def root():
    return {"service": "Project FORESIGHT scoring API", "docs": "/docs",
            "endpoints": ["/health", "/skus", "/score/{sku_id}", "/score/batch"]}
