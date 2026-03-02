import asyncio
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text

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
