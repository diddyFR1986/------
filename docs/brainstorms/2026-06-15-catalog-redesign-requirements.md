---
date: 2026-06-15
topic: catalog-redesign
---

## Summary

Redesign the product catalog as a card grid with a custom color theme and a
price-change indicator driven by existing price history. Change the scraper
so it only writes a new price snapshot when the price or availability
actually changes. Add a product comparison view as a stretch addition if time
allows.

## Problem Frame

The service currently renders as a stock Bootstrap site: a plain table for
the product catalog, default colors, and a separate analytics dashboard. The
underlying data already supports richer presentation — `PriceSnapshot`
records a price history per offer, and a price-history chart already exists
on the product detail page — but the catalog itself gives no visual signal
of how prices are moving. The project needs to look and feel more
distinctive for today's defense, and the redesign should lean on data the
system already collects rather than introduce new models.

## Key Decisions

- **Cards over table for the catalog** — a card grid is the highest-visibility
  change for a defense demo and lets each item show an image, key specs, and
  a price-change indicator together.
- **Custom color theme** — replace the default Bootstrap palette across
  `base.html` and templates that extend it, rather than swapping frameworks.
  Light, minimal palette: page background `#f8fafc`, cards `#ffffff` with a
  soft shadow, body text `#1e293b`, accent (links/buttons/badges) `#6366f1`,
  price-down indicator `#16a34a`, price-up indicator `#dc2626`.
- **Price-change indicator compares to the previous snapshot**, not a fixed
  time window (e.g. "last 7 days"). This matches how snapshots are now
  recorded (only on change) and avoids an extra date-range query.
- **Snapshot deduplication** — the scraper writes a new `PriceSnapshot` only
  when price or availability differs from the offer's most recent snapshot.
  This keeps price history meaningful and keeps the price-change indicator
  from flagging false "changes" between identical consecutive snapshots.
- **Cards + theme + indicator is the must-ship core**; the comparison view is
  a stretch addition attempted only once the core is working.

## Requirements

**Catalog redesign**

- R1. The product list renders as a responsive card grid (image, name, brand,
  capacity/type/frequency, best price) instead of a table.
- R2. A custom color theme replaces the default Bootstrap styling in
  `base.html` and the pages that extend it (catalog, product detail,
  analytics dashboard).
- R3. Existing search and filter controls remain available and apply to the
  card grid.

**Price history**

- R4. The scraper writes a new `PriceSnapshot` for an offer only when the
  price or availability differs from that offer's most recent snapshot;
  otherwise no new row is created.
- R5. Each product card and the product detail page show a price-change
  indicator (direction and percentage) comparing the latest snapshot to the
  previous one for that offer's best price.

**Comparison (stretch)**

- R6. From the card grid, a user can select 2–4 RAM modules via checkboxes.
- R7. Selected modules open a comparison view showing specs and
  per-marketplace prices for each module side by side.

## Acceptance Examples

- AE1. **Covers R5.** Latest snapshot price is lower than the previous
  snapshot → card shows a downward indicator with the percentage decrease.
  Price is higher → upward indicator with percentage increase. Price
  unchanged or only one snapshot exists → no indicator shown.
- AE2. **Covers R4.** A scrape run finds the same price and availability as
  the offer's last snapshot → no new `PriceSnapshot` row. A scrape run finds
  a different price or availability → a new row is created as before.
- AE3. **Covers R6, R7.** Fewer than 2 modules selected → comparison view is
  not reachable (or shows a prompt to select more). More than 4 selected →
  additional selections are disabled until one is deselected.

## Scope Boundaries

**Deferred for later**

- Analytics dashboard redesign with KPI cards (overview-panel approach) —
  only revisit if the core catalog redesign and comparison view are both
  done with time to spare.

**Out of scope**

- Favorites/watchlists, price-drop alerts, data export.

## Dependencies / Assumptions

- Reuses the existing `PriceSnapshot` model and `analytics/charts.py`
  price-history chart — no new models or migrations beyond the scraper
  save-logic change in R4.
- Assumes `RAMModule.image_url` is populated for enough products that the
  card grid doesn't look empty; products without an image fall back to a
  placeholder.
