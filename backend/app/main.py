import os

import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from .db import DATABASE_URL, engine
from .integrations.google_shopping import (
    GoogleShoppingCheckRequest,
    GoogleShoppingCheckResponse,
    check_google_shopping_prices,
)

app = FastAPI(title="Priskontroll API", version="0.1.0")


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
