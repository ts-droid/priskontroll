# Technical Spec (v0.1)

## Mål

Bygg en prisbevaknings- och dynamisk prissättningsplattform med:

1. Multi-source inläsning (API/CSV/scraping)
2. Regelstyrda prisbeslut med godkännandeflöde
3. Historik, rapportering och alerts
4. RRP/MAP compliance per återförsäljare och marknad

## Systemkomponenter

1. API service
- Exponerar kontrakt enligt `docs/api/openapi.yaml`.
- Hanterar CRUD, simulering, godkännanden och historik.

2. Sync workers
- Läser `source_connections`.
- Kör connectors enligt `docs/connectors/interface.md`.
- Skriver `source_sync_runs`, `source_records`, `competitor_prices`.

3. Pricing engine
- Läser aktiva `pricing_rules`.
- Beräknar `price_decisions`.
- Applicerar beslut och skriver `price_history`.

4. Alert service
- Evaluerar alert-villkor mot events/data.
- Skapar `alert_events` och skickar via kanal.

5. Compliance service
- Läser `reseller_offers` mot aktiva `rrp_policies`.
- Skapar `compliance_events` med severity/status/evidence.
- Hanterar uppföljningsärenden i `cases`.

6. Targeting service
- Prioriterar återförsäljare via `reseller_targets` (Top-50 + strategi).
- Kör discovery/capture och loggar i `offer_capture_runs`.

## Flöden

1. Ingestionflöde
- Trigger: schemalagt jobb eller `POST /sources/{sourceId}/sync`.
- Output: uppdaterade snapshots i `competitor_prices`.

2. Beslutsflöde
- Trigger: nya competitor-priser eller manuell simulering.
- Output: `price_decisions` med status `proposed`.
- Approve: `POST /price-decisions/{decisionId}/approve` -> uppdaterar `products.current_price` och skriver `price_history`.

3. Alertflöde
- Trigger: sync misslyckad, floor breach, stor prisförändring.
- Output: notifiering + audit i `alert_events`.

4. Complianceflöde
- Trigger: ny `reseller_offer` eller policyändring.
- Output: `compliance_events` vid avvikelse, annars recovery-event.
- Uppföljning: skapa/uppdatera `cases` för kontakt med återförsäljare.

5. Target discovery-flöde
- Trigger: `POST /reseller-targets/{targetId}/discover` eller schema.
- Strategi:
  - `direct_scrape`: crawl kända domäner direkt.
  - `search_then_scrape`: hitta URL via sök, verifiera sedan med crawl.
- Output: körresultat i `offer_capture_runs`.

## NFR (icke-funktionella krav)

1. Auditability: alla prisändringar måste ha reason + actor/system.
2. Idempotens: ingest får inte skapa dubbletter vid retry.
3. Tålighet: retries med exponential backoff.
4. Säkerhet: credentials lagras utanför DB (secret ref).
5. Prestanda: indexerade tidsserier för snabb historik.
6. Spårbarhet: varje compliance-event ska kunna kopplas till evidens (url/hash/snapshot-ref).

## Implementationsordning

1. Skapa DB från `db/schema.sql`.
2. Scaffold API enligt OpenAPI.
3. Implementera `csv` connector först (snabb validering av flöde).
4. Lägg till en API-connector (t.ex. Shopify).
5. Implementera pricing engine med två strategier först:
- `match_lowest`
- `cost_plus`
6. Lägg på approve/apply-flöde och alerts.
