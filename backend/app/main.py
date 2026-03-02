import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from pydantic import BaseModel, Field

from .db import DATABASE_URL, engine
from .integrations.google_shopping import (
    GoogleShoppingCheckRequest,
    GoogleShoppingCheckMultiRequest,
    GoogleShoppingCheckMultiResponse,
    GoogleShoppingCountryResult,
    GoogleShoppingCheckResponse,
    check_google_shopping_prices,
)

app = FastAPI(title="Priskontroll API", version="0.1.0")

COUNTRY_LABELS = {
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
    "IS": "Iceland",
    "LT": "Lithuania",
    "LV": "Latvia",
    "EE": "Estonia",
    "PL": "Poland",
}


def _env_csv_upper(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def _allowed_markets() -> list[str]:
    return _env_csv_upper(
        "ALLOWED_MARKETS", "SE,NO,DK,FI,IS,LT,LV,EE,PL"
    )


def _default_markets() -> list[str]:
    defaults = _env_csv_upper("DEFAULT_MARKETS", "SE,NO,DK,FI")
    allowed = set(_allowed_markets())
    valid = [market for market in defaults if market in allowed]
    return valid or [next(iter(allowed))]


class InternalSalesRecord(BaseModel):
    external_record_id: str = Field(min_length=1, max_length=200)
    sold_at: datetime
    customer_external_id: str = Field(min_length=1, max_length=200)
    customer_name: str = Field(min_length=1, max_length=300)
    customer_country: str = Field(min_length=2, max_length=2)
    product_sku: str | None = None
    product_ean: str | None = None
    sold_price: float = Field(ge=0)
    currency: str = Field(default="SEK", min_length=3, max_length=3)
    quantity: int = Field(default=1, ge=1)
    destination_market: str | None = None
    invoice_ref: str | None = None
    order_ref: str | None = None


class InternalSalesImportRequest(BaseModel):
    source_system: str = Field(min_length=2, max_length=100)
    records: list[InternalSalesRecord] = Field(min_length=1, max_length=5000)


class InternalSalesImportResponse(BaseModel):
    source_system: str
    imported: int
    skipped_duplicates: int
    unresolved_products: int


class GreyImportFlag(BaseModel):
    product_id: str
    product_sku: str | None = None
    product_ean: str | None = None
    product_name: str
    market: str
    reseller: str | None = None
    observed_price: float
    baseline_min_sold_price: float
    baseline_avg_sold_price: float
    deviation_pct_vs_min: float
    captured_at: datetime


class GreyImportFlagsResponse(BaseModel):
    lookback_days: int
    min_deviation_pct: float
    total_flags: int
    items: list[GreyImportFlag]


def _ensure_internal_sales_tables() -> None:
    stmts = [
        """
        create table if not exists internal_customers (
          id text primary key,
          external_id text not null unique,
          name text not null,
          country_code text not null,
          created_at timestamp not null default current_timestamp,
          updated_at timestamp not null default current_timestamp
        )
        """,
        """
        create table if not exists internal_sales_lines (
          id text primary key,
          source_system text not null,
          external_record_id text not null,
          sold_at timestamp not null,
          customer_id text not null,
          customer_external_id text not null,
          customer_name text not null,
          customer_country text not null,
          product_id text,
          product_sku text,
          product_ean text,
          sold_price real not null,
          currency text not null,
          quantity integer not null default 1,
          destination_market text,
          invoice_ref text,
          order_ref text,
          created_at timestamp not null default current_timestamp
        )
        """,
        "create unique index if not exists idx_internal_sales_source_record on internal_sales_lines (source_system, external_record_id)",
        "create index if not exists idx_internal_sales_product_sold_at on internal_sales_lines (product_id, sold_at desc)",
        "create index if not exists idx_internal_sales_customer on internal_sales_lines (customer_id, sold_at desc)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


def _resolve_product_id(conn, sku: str | None, ean: str | None) -> str | None:
    if sku:
        result = conn.execute(
            text("select id from products where sku = :sku limit 1"),
            {"sku": sku},
        ).scalar()
        if result:
            return str(result)
    if ean:
        result = conn.execute(
            text("select id from products where ean = :ean limit 1"),
            {"ean": ean},
        ).scalar()
        if result:
            return str(result)
    return None


@app.on_event("startup")
def bootstrap():
    _ensure_internal_sales_tables()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    masked_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    return {
        "service": "priskontroll",
        "status": "running",
        "database": masked_url,
    }


@app.get("/db/ping")
def db_ping():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}


@app.get("/ui/ean-check", response_class=HTMLResponse)
def ean_check_ui():
    allowed = _allowed_markets()
    defaults = set(_default_markets())
    checkbox_html = []
    for code in allowed:
        label = COUNTRY_LABELS.get(code, code)
        checked = "checked" if code in defaults else ""
        checkbox_html.append(
            f'<label style="display:inline-block;margin-right:10px;"><input type="checkbox" name="country_codes" value="{code}" {checked}> {code} ({label})</label>'
        )

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>EAN/UPC Price Check</title>
    <style>
      body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }}
      input, button {{ padding: 8px; margin: 4px 0; }}
      .row {{ margin-bottom: 12px; }}
      table {{ border-collapse: collapse; width: 100%; margin-top: 14px; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 14px; }}
      th {{ background: #f6f6f6; text-align: left; }}
      .country {{ margin-top: 28px; }}
      .muted {{ color: #666; font-size: 13px; }}
    </style>
  </head>
  <body>
    <h2>EAN/UPC Price Check</h2>
    <p class="muted">Sök Google Shopping i valda marknader. Verifiering via Scraperdog är valfri.</p>
    <form id="checkForm">
      <div class="row">
        <label>EAN/UPC eller sökfråga</label><br/>
        <input id="query" name="query" type="text" placeholder="ex: 810086361679" style="width:420px;" required />
      </div>
      <div class="row">
        <label>Länder</label><br/>
        {"".join(checkbox_html)}
      </div>
      <div class="row">
        <label><input id="verify" type="checkbox" /> Verifiera länkar med Scraperdog</label>
      </div>
      <button type="submit">Sök priser</button>
    </form>
    <div id="status" class="muted"></div>
    <div id="results"></div>

    <script>
      const form = document.getElementById("checkForm");
      const statusEl = document.getElementById("status");
      const resultsEl = document.getElementById("results");

      form.addEventListener("submit", async (e) => {{
        e.preventDefault();
        resultsEl.innerHTML = "";
        statusEl.textContent = "Kör sökning...";

        const query = document.getElementById("query").value.trim();
        const verify = document.getElementById("verify").checked;
        const country_codes = Array.from(document.querySelectorAll('input[name="country_codes"]:checked')).map(el => el.value.toLowerCase());

        if (!query || country_codes.length === 0) {{
          statusEl.textContent = "Ange query och välj minst ett land.";
          return;
        }}

        const payload = {{
          query,
          country_codes,
          language: "sv",
          max_results: 10,
          verify_with_scraperdog: verify
        }};

        try {{
          const res = await fetch("/integrations/google-shopping/check-multi", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify(payload)
          }});

          const data = await res.json();
          if (!res.ok) {{
            statusEl.textContent = data.detail || "Fel vid anrop.";
            return;
          }}

          statusEl.textContent = `Klart. ${data.results.length} marknader hämtade.`;

          data.results.forEach(countryResult => {{
            const wrapper = document.createElement("div");
            wrapper.className = "country";

            const heading = document.createElement("h3");
            heading.textContent = `${{countryResult.country_code.toUpperCase()}} - träffar: ${{countryResult.result.total_found}}`;
            wrapper.appendChild(heading);

            const table = document.createElement("table");
            table.innerHTML = `
              <thead>
                <tr>
                  <th>Butik</th>
                  <th>Titel</th>
                  <th>Pris</th>
                  <th>Valuta</th>
                  <th>Länk</th>
                  <th>Verifierad</th>
                </tr>
              </thead>
              <tbody>
                ${{
                  (countryResult.result.offers || []).map(o => `
                    <tr>
                      <td>${{o.source || ""}}</td>
                      <td>${{o.title || ""}}</td>
                      <td>${{o.listed_price_text || ""}}</td>
                      <td>${{o.currency || ""}}</td>
                      <td>${{o.product_url ? `<a href="${{o.product_url}}" target="_blank">Öppna</a>` : ""}}</td>
                      <td>${{o.verification_ok === null ? "" : (o.verification_ok ? "Ja" : "Nej")}}</td>
                    </tr>
                  `).join("")
                }}
              </tbody>
            `;
            wrapper.appendChild(table);
            resultsEl.appendChild(wrapper);
          }});
        }} catch (err) {{
          statusEl.textContent = "Nätverksfel: " + err;
        }}
      }});
    </script>
  </body>
</html>
"""


@app.post(
    "/integrations/google-shopping/check",
    response_model=GoogleShoppingCheckResponse,
)
async def google_shopping_check(payload: GoogleShoppingCheckRequest):
    serper_api_key = os.getenv("SERPER_API_KEY")
    scraperdog_api_key = os.getenv("SCRAPERDOG_API_KEY")

    if not serper_api_key:
        raise HTTPException(
            status_code=400,
            detail="SERPER_API_KEY is missing. Add it in backend/.env before calling this endpoint.",
        )

    if payload.verify_with_scraperdog and not scraperdog_api_key:
        raise HTTPException(
            status_code=400,
            detail="SCRAPERDOG_API_KEY is missing but verify_with_scraperdog=true.",
        )

    try:
        return await check_google_shopping_prices(
            payload,
            serper_api_key=serper_api_key,
            scraperdog_api_key=scraperdog_api_key,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream integration error: {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Network error: {exc}") from exc


@app.post(
    "/integrations/google-shopping/check-multi",
    response_model=GoogleShoppingCheckMultiResponse,
)
async def google_shopping_check_multi(payload: GoogleShoppingCheckMultiRequest):
    serper_api_key = os.getenv("SERPER_API_KEY")
    scraperdog_api_key = os.getenv("SCRAPERDOG_API_KEY")
    allowed_markets = set(_allowed_markets())

    if not serper_api_key:
        raise HTTPException(
            status_code=400,
            detail="SERPER_API_KEY is missing. Add it in backend/.env before calling this endpoint.",
        )

    if payload.verify_with_scraperdog and not scraperdog_api_key:
        raise HTTPException(
            status_code=400,
            detail="SCRAPERDOG_API_KEY is missing but verify_with_scraperdog=true.",
        )

    requested = [code.upper() for code in payload.country_codes]
    invalid = [code for code in requested if code not in allowed_markets]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported markets requested: {', '.join(invalid)}. Allowed: {', '.join(sorted(allowed_markets))}",
        )

    tasks = []
    for country_code in requested:
        single = GoogleShoppingCheckRequest(
            query=payload.query,
            country_code=country_code.lower(),
            language=payload.language,
            max_results=payload.max_results,
            verify_with_scraperdog=payload.verify_with_scraperdog,
        )
        tasks.append(
            check_google_shopping_prices(
                single,
                serper_api_key=serper_api_key,
                scraperdog_api_key=scraperdog_api_key,
            )
        )

    try:
        results = await asyncio.gather(*tasks)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream integration error: {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Network error: {exc}") from exc

    return GoogleShoppingCheckMultiResponse(
        query=payload.query,
        country_codes=[code.lower() for code in requested],
        results=[
            GoogleShoppingCountryResult(
                country_code=result.country_code,
                result=result,
            )
            for result in results
        ],
    )


@app.post(
    "/integrations/internal-sales/import",
    response_model=InternalSalesImportResponse,
)
def import_internal_sales(
    payload: InternalSalesImportRequest,
    x_import_token: str | None = Header(default=None),
):
    expected_token = os.getenv("INTERNAL_SALES_IMPORT_TOKEN")
    if expected_token and x_import_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid import token")

    imported = 0
    skipped_duplicates = 0
    unresolved_products = 0

    with engine.begin() as conn:
        for rec in payload.records:
            customer = conn.execute(
                text(
                    "select id from internal_customers where external_id = :external_id limit 1"
                ),
                {"external_id": rec.customer_external_id},
            ).scalar()

            if customer:
                customer_id = str(customer)
                conn.execute(
                    text(
                        """
                        update internal_customers
                        set name = :name, country_code = :country_code, updated_at = current_timestamp
                        where id = :id
                        """
                    ),
                    {
                        "id": customer_id,
                        "name": rec.customer_name,
                        "country_code": rec.customer_country.upper(),
                    },
                )
            else:
                customer_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        """
                        insert into internal_customers (id, external_id, name, country_code)
                        values (:id, :external_id, :name, :country_code)
                        """
                    ),
                    {
                        "id": customer_id,
                        "external_id": rec.customer_external_id,
                        "name": rec.customer_name,
                        "country_code": rec.customer_country.upper(),
                    },
                )

            product_id = _resolve_product_id(conn, rec.product_sku, rec.product_ean)
            if not product_id:
                unresolved_products += 1

            result = conn.execute(
                text(
                    """
                    insert into internal_sales_lines (
                      id, source_system, external_record_id, sold_at, customer_id,
                      customer_external_id, customer_name, customer_country,
                      product_id, product_sku, product_ean, sold_price, currency, quantity,
                      destination_market, invoice_ref, order_ref
                    )
                    values (
                      :id, :source_system, :external_record_id, :sold_at, :customer_id,
                      :customer_external_id, :customer_name, :customer_country,
                      :product_id, :product_sku, :product_ean, :sold_price, :currency, :quantity,
                      :destination_market, :invoice_ref, :order_ref
                    )
                    on conflict(source_system, external_record_id) do nothing
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "source_system": payload.source_system,
                    "external_record_id": rec.external_record_id,
                    "sold_at": rec.sold_at,
                    "customer_id": customer_id,
                    "customer_external_id": rec.customer_external_id,
                    "customer_name": rec.customer_name,
                    "customer_country": rec.customer_country.upper(),
                    "product_id": product_id,
                    "product_sku": rec.product_sku,
                    "product_ean": rec.product_ean,
                    "sold_price": rec.sold_price,
                    "currency": rec.currency.upper(),
                    "quantity": rec.quantity,
                    "destination_market": rec.destination_market.upper() if rec.destination_market else None,
                    "invoice_ref": rec.invoice_ref,
                    "order_ref": rec.order_ref,
                },
            )

            if result.rowcount == 0:
                skipped_duplicates += 1
            else:
                imported += 1

    return InternalSalesImportResponse(
        source_system=payload.source_system,
        imported=imported,
        skipped_duplicates=skipped_duplicates,
        unresolved_products=unresolved_products,
    )


@app.get(
    "/analytics/internal-sales/by-ean/{ean}",
)
def internal_sales_by_ean(ean: str, days: int = 180):
    from_ts = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 3650)))
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                select
                  isl.sold_at,
                  isl.customer_external_id,
                  isl.customer_name,
                  isl.customer_country,
                  isl.destination_market,
                  isl.sold_price,
                  isl.currency,
                  isl.quantity,
                  isl.source_system,
                  isl.invoice_ref,
                  isl.order_ref,
                  p.id as product_id,
                  p.sku as product_sku,
                  p.ean as product_ean,
                  p.name as product_name
                from internal_sales_lines isl
                left join products p on p.id = isl.product_id
                where (isl.product_ean = :ean or p.ean = :ean)
                  and isl.sold_at >= :from_ts
                order by isl.sold_at desc
                limit 1000
                """
            ),
            {"ean": ean, "from_ts": from_ts},
        ).mappings().all()

    return {"ean": ean, "days": days, "count": len(rows), "items": [dict(row) for row in rows]}


@app.get(
    "/analytics/grey-import/flags",
    response_model=GreyImportFlagsResponse,
)
def grey_import_flags(lookback_days: int = 120, min_deviation_pct: float = 15):
    safe_days = max(7, min(lookback_days, 3650))
    safe_dev = max(1, min(min_deviation_pct, 95))
    from_ts = datetime.now(timezone.utc) - timedelta(days=safe_days)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                with latest_offers as (
                  select ro.product_id, ro.competitor_id, ro.market, ro.effective_price, ro.captured_at
                  from reseller_offers ro
                  join (
                    select product_id, competitor_id, market, max(captured_at) as max_captured_at
                    from reseller_offers
                    group by product_id, competitor_id, market
                  ) m
                    on ro.product_id = m.product_id
                   and ro.competitor_id = m.competitor_id
                   and ro.market = m.market
                   and ro.captured_at = m.max_captured_at
                ),
                sales_stats as (
                  select
                    product_id,
                    avg(sold_price) as avg_sold_price,
                    min(sold_price) as min_sold_price
                  from internal_sales_lines
                  where product_id is not null
                    and sold_at >= :from_ts
                  group by product_id
                )
                select
                  p.id as product_id,
                  p.sku as product_sku,
                  p.ean as product_ean,
                  p.name as product_name,
                  lo.market,
                  c.name as reseller,
                  lo.effective_price as observed_price,
                  ss.min_sold_price as baseline_min_sold_price,
                  ss.avg_sold_price as baseline_avg_sold_price,
                  round(((ss.min_sold_price - lo.effective_price) / nullif(ss.min_sold_price, 0)) * 100.0, 2) as deviation_pct_vs_min,
                  lo.captured_at
                from latest_offers lo
                join sales_stats ss on ss.product_id = lo.product_id
                join products p on p.id = lo.product_id
                left join competitors c on c.id = lo.competitor_id
                where lo.effective_price < ss.min_sold_price * (1 - :min_dev / 100.0)
                order by deviation_pct_vs_min desc, lo.captured_at desc
                limit 500
                """
            ),
            {"from_ts": from_ts, "min_dev": safe_dev},
        ).mappings().all()

    items = [
        GreyImportFlag(
            product_id=str(row["product_id"]),
            product_sku=row["product_sku"],
            product_ean=row["product_ean"],
            product_name=row["product_name"],
            market=row["market"],
            reseller=row["reseller"],
            observed_price=float(row["observed_price"]),
            baseline_min_sold_price=float(row["baseline_min_sold_price"]),
            baseline_avg_sold_price=float(row["baseline_avg_sold_price"]),
            deviation_pct_vs_min=float(row["deviation_pct_vs_min"]),
            captured_at=row["captured_at"],
        )
        for row in rows
    ]

    return GreyImportFlagsResponse(
        lookback_days=safe_days,
        min_deviation_pct=safe_dev,
        total_flags=len(items),
        items=items,
    )
