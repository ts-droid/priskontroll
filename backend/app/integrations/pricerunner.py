from typing import Any

import httpx
from pydantic import BaseModel, Field


PRICERUNNER_BASE_URL = "https://api.pricerunner.com"


class PriceRunnerSearchRequest(BaseModel):
    market: str = Field(min_length=2, max_length=2)
    query: str = Field(min_length=1, max_length=100)
    size: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_orders: str | None = None


class PriceRunnerOffersRequest(BaseModel):
    market: str = Field(min_length=2, max_length=2)
    product_identifiers: list[str] = Field(min_length=1, max_length=100)
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    item_condition_filters: list[str] | None = None


class PriceRunnerGtinOffersRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    gtin14: str = Field(min_length=8, max_length=14)
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    item_condition_filters: str | None = "NEW,UNKNOWN"


class PriceRunnerOffer(BaseModel):
    offer_name: str | None = None
    offer_url: str | None = None
    direct_url: str | None = None
    gtin14: str | None = None
    stock_status: str | None = None
    item_condition: str | None = None
    merchant_name: str | None = None
    merchant_product_sku: str | None = None
    merchant_logo_url: str | None = None
    international: bool | None = None
    price_value: str | None = None
    price_currency: str | None = None
    shipping_cost_value: str | None = None
    shipping_cost_currency: str | None = None
    verified: bool | None = None


class PriceRunnerProductSummary(BaseModel):
    product_identifier: str | None = None
    name: str | None = None
    category_name: str | None = None
    subcategory_name: str | None = None
    klarna_product_page_url: str | None = None
    image_url: str | None = None
    brand_name: str | None = None


class PriceRunnerSearchProduct(BaseModel):
    product_identifier: str | None = None
    name: str | None = None
    category_name: str | None = None
    subcategory_name: str | None = None
    klarna_product_page_url: str | None = None
    image_url: str | None = None
    brand_name: str | None = None


class PriceRunnerSearchResponse(BaseModel):
    market: str
    total_number_of_hits: int | None = None
    products: list[PriceRunnerSearchProduct]


class PriceRunnerProductListing(BaseModel):
    product: PriceRunnerProductSummary
    offers: list[PriceRunnerOffer]


class PriceRunnerOffersResponse(BaseModel):
    market: str
    total_product_listings: int
    product_listings: list[PriceRunnerProductListing]


def _headers(token_id: str) -> dict[str, str]:
    return {"tokenId": token_id}


def _map_brand_name(brand: dict[str, Any] | None) -> str | None:
    if not brand:
        return None
    return brand.get("name")


def _map_search_product(item: dict[str, Any]) -> PriceRunnerSearchProduct:
    product_identifier = item.get("productIdentifier")
    if not product_identifier and item.get("id") is not None:
        product_identifier = str(item.get("id"))
    return PriceRunnerSearchProduct(
        product_identifier=product_identifier,
        name=item.get("name"),
        category_name=item.get("categoryName"),
        subcategory_name=item.get("subcategoryName"),
        klarna_product_page_url=item.get("klarnaProductPageUrl") or item.get("url"),
        image_url=item.get("imageUrl"),
        brand_name=_map_brand_name(item.get("brand")) or item.get("brandName"),
    )


def _map_offer(item: dict[str, Any]) -> PriceRunnerOffer:
    merchant = item.get("merchant") or {}
    price = item.get("price") or {}
    shipping = item.get("shippingCost") or {}
    return PriceRunnerOffer(
        offer_name=item.get("offerName"),
        offer_url=item.get("offerUrl"),
        direct_url=item.get("directUrl"),
        gtin14=item.get("gtin14"),
        stock_status=item.get("stockStatus"),
        item_condition=item.get("itemCondition"),
        merchant_name=merchant.get("merchantName") or item.get("merchantName"),
        merchant_product_sku=merchant.get("merchantProductSku") or item.get("merchantProductSku"),
        merchant_logo_url=merchant.get("merchantLogoUrl") or item.get("merchantLogoUrl"),
        international=merchant.get("international") if "international" in merchant else item.get("international"),
        price_value=price.get("value"),
        price_currency=price.get("currency"),
        shipping_cost_value=shipping.get("value"),
        shipping_cost_currency=shipping.get("currency"),
        verified=item.get("verified"),
    )


def _map_product_summary(item: dict[str, Any]) -> PriceRunnerProductSummary:
    product_identifier = item.get("productIdentifier")
    if not product_identifier and item.get("id") is not None:
        product_identifier = str(item.get("id"))
    return PriceRunnerProductSummary(
        product_identifier=product_identifier,
        name=item.get("name"),
        category_name=item.get("categoryName"),
        subcategory_name=item.get("subcategoryName"),
        klarna_product_page_url=item.get("klarnaProductPageUrl") or item.get("productPage"),
        image_url=item.get("imageUrl"),
        brand_name=_map_brand_name(item.get("brand")) or item.get("brandName"),
    )


async def pricerunner_search(
    request: PriceRunnerSearchRequest,
    *,
    token_id: str,
) -> PriceRunnerSearchResponse:
    params = {
        "q": request.query,
        "size": request.size,
        "offset": request.offset,
    }
    if request.sort_orders:
        params["sortOrders"] = request.sort_orders

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            f"{PRICERUNNER_BASE_URL}/public/v0/product/search/{request.market.upper()}",
            headers=_headers(token_id),
            params=params,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    products = [_map_search_product(item) for item in (data.get("searchProducts") or [])]
    return PriceRunnerSearchResponse(
        market=request.market.lower(),
        total_number_of_hits=data.get("totalNumberOfHits"),
        products=products,
    )


async def pricerunner_offers(
    request: PriceRunnerOffersRequest,
    *,
    token_id: str,
) -> PriceRunnerOffersResponse:
    params: dict[str, str | int] = {
        "ids": ",".join(request.product_identifiers),
    }
    if request.min_price is not None:
        params["minPrice"] = request.min_price
    if request.max_price is not None:
        params["maxPrice"] = request.max_price
    if request.item_condition_filters:
        params["itemConditionFilters"] = ",".join(request.item_condition_filters)

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            f"{PRICERUNNER_BASE_URL}/public/v2/product/offers/{request.market.upper()}/ids",
            headers=_headers(token_id),
            params=params,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    listings = []
    for item in data.get("productListings") or []:
        listings.append(
            PriceRunnerProductListing(
                product=_map_product_summary(
                    item.get("product") or item.get("productListingProduct") or {}
                ),
                offers=[_map_offer(offer) for offer in (item.get("offers") or [])],
            )
        )

    return PriceRunnerOffersResponse(
        market=request.market.lower(),
        total_product_listings=len(listings),
        product_listings=listings,
    )


async def pricerunner_offers_by_gtin(
    request: PriceRunnerGtinOffersRequest,
    *,
    token_id: str,
) -> PriceRunnerOffersResponse:
    params: dict[str, str | int] = {"gtin14": request.gtin14}
    if request.min_price is not None:
        params["minPrice"] = request.min_price
    if request.max_price is not None:
        params["maxPrice"] = request.max_price
    if request.item_condition_filters:
        params["itemConditionFilters"] = request.item_condition_filters

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            f"{PRICERUNNER_BASE_URL}/public/v2/product/offers/{request.country_code.upper()}/gtin14",
            headers=_headers(token_id),
            params=params,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    listing = PriceRunnerProductListing(
        product=_map_product_summary(data.get("productListingProduct") or {}),
        offers=[_map_offer(offer) for offer in (data.get("offers") or [])],
    )
    return PriceRunnerOffersResponse(
        market=request.country_code.lower(),
        total_product_listings=1,
        product_listings=[listing],
    )
