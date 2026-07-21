# Project FORESIGHT — Data-Quality & EDA Insight Memo (D2)

**Client:** NorthBay Living · **Prepared by:** Data Science, Zidio engagement
**Source extract:** transactional sales, 01 Dec 2009 – 09 Dec 2011 (two yearly files)

---

## 1. What the data is

The client extract is a line-level transaction log (one row per product per
invoice): invoice id, product code (SKU), description, quantity, timestamp,
unit price, customer id and country. From it the pipeline builds the four-table
star schema the engagement runs on — `sales_daily`, `sku_master`, `calendar`,
`inventory_snapshots` — and an analysis-ready weekly demand panel.

## 2. Data-quality issues found and how they were handled

Every fix below is **coded in `src/pipeline.py`** (never manual) and logged with
a rationale to `data/processed/data_quality_report.json`.

| Issue | Rows | How it was handled |
|---|---:|---|
| Cancellations / returns (invoice prefix `C`) | 19,494 | Removed — they are reversals, not demand. |
| Non-product codes (postage `POST`, `DOT`, fees, `BANK CHARGES`, manual adjustments, non-numeric codes) | 4,676 | Removed — not sellable SKUs. |
| Non-positive quantity or price (returns not flagged `C`, zero-price give-aways) | 6,166 | Removed — not genuine sales. |
| Exact duplicate transaction lines | 33,666 | De-duplicated on invoice+SKU+time+qty+price. |
| Missing critical fields | 0 | None after the above (checked and logged). |

**Result:** ~1.07M raw rows → **1.00M clean rows (94% retained)**, 4,730
sellable SKUs. Cleaning is transparent and reproducible.

Two documented modelling conventions (stated so the client can audit them):

- **Promo flag** — the raw feed has no promotion column, so a SKU-day is treated
  as *on promo* when its price is ≥10% below that SKU's list price (a standard
  discount-detection proxy).
- **Inventory snapshot** — the raw feed contains sales only, no stock table. To
  exercise the risk layer we synthesise a **deterministic, seeded** stock
  position per SKU from its recent demand (lead time by category, reorder point,
  on-hand cover, in-transit orders). This is clearly flagged as a modelled
  stand-in; on a real engagement it would be replaced by NorthBay's actual
  `inventory_snapshots`.

## 3. Demand patterns

- **Trend & seasonality** (`fig_weekly_demand.png`): weekly demand is stable
  through the year and **spikes sharply in Nov–Dec**, the classic gifting peak.
- **Top movers** (`fig_top_movers.png`): a small set of SKUs dominates volume.
- **Category mix** (`fig_category_mix.png`): revenue concentrates in a few
  categories (home décor, kitchen & dining, seasonal).
- **Dead stock** (`fig_dead_stock.png`): a long tail of SKUs sells ~0 units in
  the most recent 8 weeks.

## 4. Three business-relevant insights (plain language)

1. **Sales are highly concentrated — the top 20% of SKUs drive ~78% of all units.**
   The forecast and reorder effort should be focused here first; getting these
   right protects most of the revenue.

2. **Demand is strongly seasonal — ~23% of the year's volume lands in Nov–Dec.**
   Reorder timing must lead this peak by the replenishment lead time, or the
   best-sellers stock out exactly when they sell most.

3. **There is a real dead-stock tail — ~12 modelled SKUs sold ≈0 units in the
   last 8 weeks** while still occupying warehouse space and cash. These are
   markdown / clearance candidates today.

## 5. Modelling scope

Forecasting focuses on the **top 197 SKUs by volume** with ≥30 weeks of history
(the active assortment the brief describes as "~200 SKUs"). Long-tail and
brand-new SKUs are out of scope for the point forecast and fall back to
category-level treatment — flagged as low-confidence rather than silently
forecast.

*Figures referenced above are in `reports/figures/`. Headline statistics are in
`data/processed/eda_insights.json`.*
