# TODO: Reseller Price Tracking Improvements

## P0 (build first)

1. Product matching v2 (EAN/GTIN first, SKU+title fallback, manual review queue)
2. Track effective total price (sale/base + shipping + promo impact)
3. Compliance engine (RRP/MAP status per reseller/market)
4. Evidence logging for each breach (timestamp, URL, captured values, hash/snapshot ref)
5. Alerts with severity (P1/P2) and daily digest

## P1

1. Campaign detection (temporary promo vs normal price)
2. Stock-aware compliance logic (in-stock vs out-of-stock)
3. Case workflow (owner, status, contacted_at, notes)
4. Reseller scorecard (compliance %, avg deviation, breach count)

## P2

1. Smart crawl frequency by SKU importance
2. Data quality score per source/reseller
3. Monthly reporting export (CSV/PDF)

## Required schema additions

1. `rrp_policies`
2. `reseller_offers`
3. `compliance_events`
4. `cases`

