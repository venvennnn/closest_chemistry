from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.services.ssrf import FetchError, fetch_public_https

PRICE_RE = re.compile(r'"price"\s*:\s*"?(?P<price>[0-9]+(?:\.[0-9]+)?)"?')


def _from_jsonld(document: str) -> dict[str, Any] | None:
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        document,
        flags=re.I | re.S,
    )
    for raw in matches:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            type_list = types if isinstance(types, list) else [types]
            if "Product" not in type_list and "Offer" not in type_list:
                graph = item.get("@graph")
                if isinstance(graph, list):
                    items.extend(graph)
                continue
            offers = item.get("offers")
            offer = offers[0] if isinstance(offers, list) and offers else offers if isinstance(offers, dict) else item
            price = None
            currency = None
            if isinstance(offer, dict):
                price = offer.get("price")
                currency = offer.get("priceCurrency")
            image = item.get("image")
            if isinstance(image, list):
                image = image[0]
            if isinstance(image, dict):
                image = image.get("url")
            if price is None:
                continue
            return {
                "title": item.get("name") or "Untitled product",
                "price": str(price),
                "currency": currency,
                "image_url": image,
                "origin": "jsonld",
            }
    return None


def parse_price_minor(value: str | float | int, currency: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Price must be a number in major units or an integer minor-unit amount.") from exc
    if number < 0:
        raise ValueError("Price cannot be negative.")
    return int(round(number * 100))


async def ingest_product_url(url: str) -> dict[str, Any]:
    try:
        body, content_type, final_url = await fetch_public_https(url)
    except FetchError as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "requires_manual": True,
            "message": "URL fetch failed. Upload the product image and enter the price manually. Prices are never inferred by an LLM.",
        }
    text = body.decode("utf-8", errors="ignore") if "html" in content_type or text_looks_html(body) else ""
    parsed = _from_jsonld(text) if text else None
    if parsed and parsed.get("price") and parsed.get("currency"):
        return {
            "ok": True,
            "title": parsed["title"],
            "price_minor": parse_price_minor(parsed["price"], parsed["currency"]),
            "currency": parsed["currency"],
            "image_url": parsed.get("image_url"),
            "source_url": final_url,
            "metadata_origin": "fetched_jsonld",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "shipping_tax_included": False,
        }
    return {
        "ok": False,
        "requires_manual": True,
        "source_url": final_url,
        "message": (
            "No Product/Offer JSON-LD with price and currency was found. "
            "Upload the actual image and enter the price. Login walls and anti-bot pages are not bypassed."
        ),
    }


def text_looks_html(body: bytes) -> bool:
    start = body[:200].lstrip().lower()
    return start.startswith(b"<!doctype html") or start.startswith(b"<html")
