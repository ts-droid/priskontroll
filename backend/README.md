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
