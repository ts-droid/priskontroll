# Backend scaffold

Detta är en minimal körbar API-bas återanvänd från `priser`-projektet,
anpassad som startpunkt för implementation enligt `docs/api/openapi.yaml` och `db/schema.sql`.

## Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fyll i SERPER_API_KEY och SCRAPERDOG_API_KEY i .env
uvicorn app.main:app --reload
```

Endpoints:
- `GET /health`
- `GET /`
- `GET /db/ping`
- `GET /ui/ean-check`
- `POST /integrations/google-shopping/check`
- `POST /integrations/google-shopping/check-multi`
- `POST /integrations/internal-sales/import`
- `GET /analytics/internal-sales/by-ean/{ean}`
- `GET /analytics/grey-import/flags`
- `GET /analytics/grey-import/by-ean/{ean}`

Notera: `DATABASE_URL` fallbackar till lokal sqlite (`sqlite:///./priskontroll.db`) om variabeln saknas.

## Exempel: Google Shopping-check

```bash
curl -sS -X POST "http://127.0.0.1:8000/integrations/google-shopping/check" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"Satechi USB-C Hub",
    "country_code":"se",
    "language":"sv",
    "max_results":10,
    "verify_with_scraperdog":true
  }'
```

Endpointen använder:

- `SERPER_API_KEY` för Google Shopping-resultat
- `SCRAPERDOG_API_KEY` för frivillig verifiering av länkar/resultat

## Multi-country check (för tickbox-UI)

```bash
curl -sS -X POST "http://127.0.0.1:8000/integrations/google-shopping/check-multi" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"810086361679",
    "country_codes":["se","no","dk","fi"],
    "language":"sv",
    "max_results":10,
    "verify_with_scraperdog":false
  }'
```

Öppna enkelt gränssnitt:

- `http://127.0.0.1:8000/ui/ean-check`

Marknadsstyrning via env:

- `ALLOWED_MARKETS=SE,NO,DK,FI,IS,LT,LV,EE,PL`
- `DEFAULT_MARKETS=SE,NO,DK,FI`

## Intern försäljningsdata (backend-system)

Sätt gärna en skyddstoken:

- `INTERNAL_SALES_IMPORT_TOKEN=<hemlig-token>`

Exempelimport:

```bash
curl -sS -X POST "http://127.0.0.1:8000/integrations/internal-sales/import" \
  -H "Content-Type: application/json" \
  -H "X-Import-Token: <hemlig-token>" \
  -d '{
    "source_system":"erp",
    "records":[
      {
        "external_record_id":"INV-1001-1",
        "sold_at":"2026-03-01T12:00:00Z",
        "customer_external_id":"CUST-001",
        "customer_name":"Example Retailer AB",
        "customer_country":"SE",
        "product_sku":"SAT-USB4-HUB",
        "product_ean":"810086361679",
        "sold_price":699.0,
        "currency":"SEK",
        "quantity":2,
        "destination_market":"SE",
        "invoice_ref":"INV-1001"
      }
    ]
  }'
```

Analys:

- `GET /analytics/internal-sales/by-ean/810086361679?days=180`
- `GET /analytics/grey-import/flags?lookback_days=120&min_deviation_pct=15`
- `GET /analytics/grey-import/by-ean/810086361679?lookback_days=120&min_deviation_pct=15&country_codes=se,no,dk,fi`
