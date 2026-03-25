# Priskontroll Technical Specification

Detta repo innehåller en konkret grundspec för en prisbevaknings- och prissättningsplattform:

- API-kontrakt: `docs/api/openapi.yaml`
- Databas-DDL: `db/schema.sql`
- Connector-interface: `docs/connectors/interface.md`
- Google Shopping-check i backend via Serper + valfri Scraperdog-verifiering
- Multi-country EAN/UPC-check och enkel UI: `GET /ui/ean-check`
- Intern sales-import API för kund/produkt/inpris + gråimportflaggor
- Authorized reseller domain-register + `GET /api/check-market/{ean}` (is_authorized + marginal)

## Körbar backend-bas

Projektet har nu en minimal backend-skeleton i `backend/` (återanvända delar från projektet `priser`):

- FastAPI app (`backend/app/main.py`)
- DB bootstrap + session (`backend/app/db.py`)
- Dependencies (`backend/requirements.txt`)

Starta:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Målet är att fortsätta bygga API-endpoints och datamodeller enligt OpenAPI/DDL-specen.

- PriceRunner Product API och Agentic Product API integration i backend
