import re
from typing import Any

import httpx
from pydantic import BaseModel, Field


class GoogleShoppingCheckRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    country_code: str = Field(default="se", min_length=2, max_length=2)
    language: str = Field(default="sv", min_length=2, max_length=5)
    max_results: int = Field(default=10, ge=1, le=50)
    verify_with_scraperdog: bool = False


class GoogleShoppingOffer(BaseModel):
    title: str
    source: str | None = None
    product_url: str | None = None
    currency: str | None = None
    listed_price_text: str | None = None
    listed_price_value: float | None = None
    verification_ok: bool | None = None
    verification_title: str | None = None


class GoogleShoppingCheckResponse(BaseModel):
    query: str
    country_code: str
    language: str
    total_found: int
    verified_count: int
    offers: list[GoogleShoppingOffer]


class GoogleShoppingCheckMultiRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    country_codes: list[str] = Field(min_length=1, max_length=20)
    language: str = Field(default="sv", min_length=2, max_length=5)
    max_results: int = Field(default=10, ge=1, le=50)
    verify_with_scraperdog: bool = False


class GoogleShoppingCountryResult(BaseModel):
    country_code: str
    result: GoogleShoppingCheckResponse


class GoogleShoppingCheckMultiResponse(BaseModel):
    query: str
    country_codes: list[str]
    results: list[GoogleShoppingCountryResult]


def _extract_price_value(raw: str | None) -> float | None:
    if not raw:
        return None
    normalized = raw.replace("\u00a0", " ")
    # Keep digits and decimal separators only, then normalize comma to dot.
    normalized = re.sub(r"[^0-9,.\-]", "", normalized).replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _extract_title_from_html(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:300]


async def _verify_link_with_scraperdog(
    client: httpx.AsyncClient, scraperdog_api_key: str, url: str
) -> tuple[bool, str | None]:
    params = {"api_key": scraperdog_api_key, "url": url, "dynamic": "false"}
    resp = await client.get("https://api.scraperdog.com/scrape", params=params)
    if resp.status_code >= 400:
        return False, None
    title = _extract_title_from_html(resp.text)
    return True, title


async def check_google_shopping_prices(
    request: GoogleShoppingCheckRequest,
    *,
    serper_api_key: str,
    scraperdog_api_key: str | None,
) -> GoogleShoppingCheckResponse:
    headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}
    payload = {
        "q": request.query,
        "gl": request.country_code.lower(),
        "hl": request.language.lower(),
        "num": request.max_results,
    }

    async with httpx.AsyncClient(timeout=25) as client:
        serper_resp = await client.post("https://google.serper.dev/shopping", headers=headers, json=payload)
        serper_resp.raise_for_status()
        data: dict[str, Any] = serper_resp.json()

        shopping_results = data.get("shopping", []) or []
        offers: list[GoogleShoppingOffer] = []
        verified_count = 0

        for item in shopping_results[: request.max_results]:
            listed_text = item.get("price")
            offer = GoogleShoppingOffer(
                title=item.get("title") or "Unknown title",
                source=item.get("source"),
                product_url=item.get("link"),
                currency=item.get("currency"),
                listed_price_text=listed_text,
                listed_price_value=_extract_price_value(listed_text),
            )

            if (
                request.verify_with_scraperdog
                and scraperdog_api_key
                and offer.product_url
            ):
                ok, page_title = await _verify_link_with_scraperdog(
                    client, scraperdog_api_key, offer.product_url
                )
                offer.verification_ok = ok
                offer.verification_title = page_title
                if ok:
                    verified_count += 1

            offers.append(offer)

    return GoogleShoppingCheckResponse(
        query=request.query,
        country_code=request.country_code.lower(),
        language=request.language.lower(),
        total_found=len(offers),
        verified_count=verified_count,
        offers=offers,
    )
