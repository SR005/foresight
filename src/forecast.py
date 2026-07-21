"""
Project FORESIGHT — D3 Demand Forecast.

Weekly SKU-level demand forecast.

  * Baseline    : seasonal-naive (same week last year; falls back to last week).
  * Model       : LightGBM global regressor on lag / rolling / calendar features.
  * Validation  : rolling-origin cross-validation (1-week-ahead), WAPE vs baseline.
  * Leakage     : every feature uses only information available *before* the week
                  being predicted. Contemporaneous price/promo are never used as
                  features — only their lagged values and the planned calendar.

Run:  python src/forecast.py      (requires pipeline.py to have run first)

Outputs (data/processed/):
    forecast.csv           per-SKU horizon forecast + 80% interval + baseline
    backtest_metrics.json  WAPE / MAPE / bias, model vs baseline
    backtest_points.csv    per (sku,week) backtest predictions (for auditing)
"""
from __future__ import annotations
import json
import warnings

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

import config as C

warnings.filterwarnings("ignore")
np.random.seed(C.SEED)

LAGS = [1, 2, 3, 4, 8, 52]
ROLLS = [4, 8, 12]
FEATURES = (
    [f"lag_{l}" for l in LAGS]
    + [f"rollmean_{r}" for r in ROLLS]
    + [f"rollstd_{r}" for r in ROLLS]
    + ["lag_price_1", "weekofyear", "month", "sin_woy", "cos_woy",
       "weeks_since_launch", "promo_planned", "is_holiday_wk", "cat_code"]
)


# ---------------------------------------------------------------- metrics
def wape(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    denom = np.abs(y).sum()
    return np.abs(y - yhat).sum() / denom if denom else np.nan


def mape(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    m = y > 0
    return np.mean(np.abs((y[m] - yhat[m]) / y[m])) if m.any() else np.nan


def bias(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    return (yhat - y).mean()


# ---------------------------------------------------------------- features
def load_panel():
    panel = pd.read_csv(C.DATA_PROC / "weekly_panel.csv", parse_dates=["week_start"])
    cal = pd.read_csv(C.DATA_PROC / "calendar.csv", parse_dates=["date"])
    # Weekly calendar attributes (holiday / planned promo event) by week_start.
    cal["week_start"] = cal["date"].dt.to_period(C.WEEK_RULE).dt.start_time
    wcal = (cal.groupby("week_start")
              .agg(is_holiday_wk=("is_holiday", "max"),
                   promo_planned=("promo_event", lambda s: int((s != "").any())))
              .reset_index())
    panel = panel.merge(wcal, on="week_start", how="left")
    panel[["is_holiday_wk", "promo_planned"]] = \
        panel[["is_holiday_wk", "promo_planned"]].fillna(0).astype(int)
    panel["cat_code"] = panel["category"].astype("category").cat.codes
    return panel.sort_values(["sku_id", "week_start"]).reset_index(drop=True)


def make_features(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    g = df.groupby("sku_id", group_keys=False)
    df["y"] = df["units_sold"]
    for l in LAGS:
        df[f"lag_{l}"] = g["units_sold"].shift(l)
    for r in ROLLS:
        # shift(1) first => rolling window uses only weeks strictly before t.
        df[f"rollmean_{r}"] = g["units_sold"].apply(lambda s: s.shift(1).rolling(r, min_periods=2).mean())
        df[f"rollstd_{r}"] = g["units_sold"].apply(lambda s: s.shift(1).rolling(r, min_periods=2).std())
    df["lag_price_1"] = g["avg_price"].shift(1)
    df["seasonal_naive"] = df["lag_52"].fillna(df["lag_1"])   # baseline
    woy = df["week_start"].dt.isocalendar().week.astype(int)
    df["weekofyear"] = woy
    df["month"] = df["week_start"].dt.month
    df["sin_woy"] = np.sin(2 * np.pi * woy / 52)
    df["cos_woy"] = np.cos(2 * np.pi * woy / 52)
    df["weeks_since_launch"] = g.cumcount()
    return df


def _fit(train: pd.DataFrame) -> LGBMRegressor:
    m = LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
        random_state=C.SEED, n_jobs=-1, verbose=-1,
    )
    m.fit(train[FEATURES], train["y"])
    return m


# ---------------------------------------------------------------- backtest
def rolling_origin_backtest(feat: pd.DataFrame, n_origins=C.BACKTEST_ORIGINS):
    """1-week-ahead rolling origin over the last `n_origins` weeks."""
    weeks = np.sort(feat["week_start"].unique())
    test_weeks = weeks[-n_origins:]
    rows = []
    for w in test_weeks:
        ESS=["lag_1","lag_4","y"]
        train = feat[(feat["week_start"] < w)].dropna(subset=ESS)
        test = feat[feat["week_start"] == w].dropna(subset=ESS)
        if len(train) < 500 or test.empty:
            continue
        model = _fit(train)
        pred = model.predict(test[FEATURES]).clip(min=0)
        out = test[["sku_id", "week_start", "y", "seasonal_naive"]].copy()
        out["model"] = pred
        rows.append(out)
        print(f"  origin {pd.Timestamp(w).date()}  train={len(train):>6}  "
              f"test={len(test):>4}  WAPE model={wape(out['y'],out['model']):.3f} "
              f"naive={wape(out['y'],out['seasonal_naive']):.3f}")
    pts = pd.concat(rows, ignore_index=True)
    pts["seasonal_naive"] = pts["seasonal_naive"].fillna(0)
    metrics = {
        "n_test_points": int(len(pts)),
        "n_origins": int(pts["week_start"].nunique()),
        "model": {"WAPE": round(wape(pts.y, pts.model), 4),
                  "MAPE": round(mape(pts.y, pts.model), 4),
                  "bias": round(bias(pts.y, pts.model), 3)},
        "seasonal_naive": {"WAPE": round(wape(pts.y, pts.seasonal_naive), 4),
                           "MAPE": round(mape(pts.y, pts.seasonal_naive), 4),
                           "bias": round(bias(pts.y, pts.seasonal_naive), 3)},
    }
    imp = wape(pts.y, pts.seasonal_naive) - wape(pts.y, pts.model)
    metrics["wape_improvement_abs"] = round(imp, 4)
    metrics["wape_improvement_pct"] = round(100 * imp / wape(pts.y, pts.seasonal_naive), 1)
    metrics["model_beats_baseline"] = bool(imp > 0)
    return pts, metrics


# ---------------------------------------------------------------- horizon forecast
def forecast_horizon(feat: pd.DataFrame, panel: pd.DataFrame,
                     horizon=C.HORIZON_WEEKS, resid_sigma=None):
    """Retrain on all data, then roll forward `horizon` weeks recursively."""
    train = feat.dropna(subset=["lag_1","lag_4","y"])
    model = _fit(train)

    # Per-SKU working history of weekly units (for recursive lag updates).
    hist = {s: g.set_index("week_start")["units_sold"].to_dict()
            for s, g in panel.groupby("sku_id")}
    last_week = panel["week_start"].max()
    cat_code = panel.groupby("sku_id")["cat_code"].last().to_dict()
    launch_len = panel.groupby("sku_id").size().to_dict()
    last_price = panel.groupby("sku_id")["avg_price"].last().to_dict()

    future_weeks = [last_week + pd.Timedelta(weeks=i) for i in range(1, horizon + 1)]
    recs = []
    for s in hist:
        series = dict(hist[s])
        for step, fw in enumerate(future_weeks, start=1):
            def lag(k):
                wk = fw - pd.Timedelta(weeks=k)
                return series.get(wk, np.nan)
            vals = [lag(l) for l in LAGS]
            past = [series.get(fw - pd.Timedelta(weeks=k), np.nan) for k in range(1, 13)]
            past = pd.Series(past).dropna()
            row = {f"lag_{l}": v for l, v in zip(LAGS, vals)}
            for r in ROLLS:
                w = pd.Series([series.get(fw - pd.Timedelta(weeks=k), np.nan)
                               for k in range(1, r + 1)]).dropna()
                row[f"rollmean_{r}"] = w.mean() if len(w) else np.nan
                row[f"rollstd_{r}"] = w.std() if len(w) > 1 else 0.0
            woy = fw.isocalendar().week
            row.update({
                "lag_price_1": last_price.get(s, np.nan),
                "weekofyear": woy, "month": fw.month,
                "sin_woy": np.sin(2 * np.pi * woy / 52),
                "cos_woy": np.cos(2 * np.pi * woy / 52),
                "weeks_since_launch": launch_len.get(s, 0) + step,
                "promo_planned": 0, "is_holiday_wk": 1 if (fw.month == 12) else 0,
                "cat_code": cat_code.get(s, -1),
            })
            X = pd.DataFrame([row])[FEATURES]
            yhat = float(model.predict(X)[0])
            yhat = max(0.0, yhat)
            series[fw] = yhat            # feed prediction back in (recursive)
            # seasonal-naive baseline for the same future week
            base = series.get(fw - pd.Timedelta(weeks=52),
                              series.get(fw - pd.Timedelta(weeks=1), yhat))
            recs.append({"sku_id": s, "week_start": fw, "horizon_step": step,
                         "forecast": round(yhat, 2), "baseline": round(float(base), 2)})
    fc = pd.DataFrame(recs)
    # 80% prediction interval from backtest residual scale (grows with horizon step).
    sigma = resid_sigma if resid_sigma else fc["forecast"].std()
    fc["yhat_lower"] = (fc["forecast"] - 1.28 * sigma * np.sqrt(fc["horizon_step"])).clip(lower=0).round(2)
    fc["yhat_upper"] = (fc["forecast"] + 1.28 * sigma * np.sqrt(fc["horizon_step"])).round(2)
    return fc, model


def main():
    print("=" * 70)
    print("PROJECT FORESIGHT — D3 DEMAND FORECAST")
    print("=" * 70)
    panel = load_panel()
    feat = make_features(panel)
    print(f"Panel: {panel['sku_id'].nunique()} SKUs, "
          f"{panel['week_start'].nunique()} weeks, {len(feat):,} rows")

    print("\nRolling-origin backtest (1-week-ahead):")
    pts, metrics = rolling_origin_backtest(feat)
    resid_sigma = float(np.std(pts["y"] - pts["model"]))

    print("\nBacktest result:")
    print(f"  Model  WAPE = {metrics['model']['WAPE']:.3f}")
    print(f"  Naive  WAPE = {metrics['seasonal_naive']['WAPE']:.3f}")
    print(f"  Improvement = {metrics['wape_improvement_pct']}%  "
          f"(model beats baseline: {metrics['model_beats_baseline']})")

    print("\nFitting final model and forecasting horizon "
          f"({C.HORIZON_WEEKS} weeks) ...")
    fc, _ = forecast_horizon(feat, panel, resid_sigma=resid_sigma)

    fc.to_csv(C.DATA_PROC / "forecast.csv", index=False)
    pts.to_csv(C.DATA_PROC / "backtest_points.csv", index=False)
    with open(C.DATA_PROC / "backtest_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nWrote forecast.csv ({len(fc):,} rows), backtest_metrics.json")
    print("Forecast complete.")


if __name__ == "__main__":
    main()
