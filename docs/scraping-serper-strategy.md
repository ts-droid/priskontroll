# Scraping + Serper Strategy for Top-50 Resellers

## Kort svar

Ja, det gar att automatisera prisinsamling utan Prisjakt/Pricerunner-API om ni kor en hybrid:

1. Direkt scraping mot kanda reseller-domaner (primar kanal)
2. Serper-driven discovery nar URL-strukturer andras (fallback)
3. Manuell review-ko for osakra matcher

## Teknisk tweak (redan inford i spec)

Nya byggblock i schema/API:

1. `reseller_targets` for prioritering, strategi och crawlfrekvens
2. `offer_capture_runs` for korhistorik och kvalitet per reseller
3. API for att styra/overvaka:
   - `GET/POST /reseller-targets`
   - `PATCH /reseller-targets/{targetId}`
   - `POST /reseller-targets/{targetId}/discover`
   - `GET /reseller-targets/{targetId}/capture-runs`

## Rekommenderad strategi per target

1. `direct_scrape`
- Anvand nar reseller har stabil PDP/PLP-struktur.
- Hog precision, lagre latency.

2. `search_then_scrape`
- Serper hittar aktuell produkt-URL med query: `site:domain.tld <ean or sku>`.
- Crawler verifierar URL och extraherar prisfalten.
- Bra nar sajten byter URL-monstrer ofta.

3. `feed`
- For partners som kan ge CSV/SFTP/egen endpoint.
- Minst underhall, hog tillforlitlighet.

4. `manual`
- For B2B/portal-kunder dar offentlig prisyta saknas.
- Eventuellt semiautomatisk inlasning via exporter.

## Forslag for Top-50 rollout

1. Batch A (prio 1-15): 15 viktigaste kunderna, crawl var 2-4 timme.
2. Batch B (prio 16-35): crawl var 6-12 timme.
3. Batch C (prio 36-50): crawl 1 gang per dygn.

## Datakvalitet och bevis

For varje observerat pris spara:

1. `effective_price` (sale/base + shipping)
2. `in_stock`, `promo_type`, `promo_text`
3. `offer_url`, `captured_at`
4. Evidence (`html_hash`, `selector_version`, valfri screenshot-ref)

## Risker att hantera

1. Anti-bot/blockering: rate-limit + jitter + rotating user-agent.
2. Felmatchning av produkt: krav pa EAN/GTIN-match eller manuell review.
3. Juridik/TOS: per-domain policy innan aktivering.

## KPI att folja (for att se att Top-50 fungerar)

1. Coverage: andel av Top-50 med minst ett giltigt pris senaste 24h.
2. Freshness: median alder pa senaste observation per reseller.
3. Accuracy: andel observationer med korrekt EAN/SKU-match.
4. Stability: misslyckade korningar per 100 capture-runs.

