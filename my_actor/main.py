from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from apify import Actor

from .scoring import score_and_sort, validate_company_profile

TED_API_URL = "https://api.ted.europa.eu/v3/notices/search"
VALUE_SCOPES = ("proc", "lot", "glo", "part")
ELIGIBILITY_FIELDS = [
    "selection-criteria-source", "selection-criterion-lot",
    "selection-criterion-description-lot", "selection-criterion-name-lot",
    "selection-criterion-used-lot", "exclusion-grounds",
    "exclusion-grounds-description", "exclusion-grounds-source-proc",
    "reserved-procurement-lot",
]
EXTRA_TED_FIELDS = [
    *[prefix + scope for prefix in ("title-", "description-") for scope in VALUE_SCOPES],
    "procedure-type", "procedure-identifier", "identifier-lot", "identifier-glo",
    "identifier-part", *ELIGIBILITY_FIELDS, "sme-lot", "sme-glo", "sme-part", "notice-type",
]
TED_FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-country",
    "publication-date", "deadline-receipt-tender-date-lot", "classification-cpv",
    *[prefix + scope for scope in VALUE_SCOPES
      for prefix in ("estimated-value-", "estimated-value-cur-")],
    *EXTRA_TED_FIELDS,
]


def validate_input(value: Any) -> tuple[list[str], str | None, int, int]:
    if not isinstance(value, dict):
        raise ValueError("Input must be a JSON object.")
    keywords = value.get("keywords", ["cybersecurity", "penetration testing"])
    if not isinstance(keywords, list) or not 1 <= len(keywords) <= 20:
        raise ValueError("keywords must contain 1 to 20 strings.")
    cleaned = []
    for keyword in keywords:
        if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 200:
            raise ValueError("Each keyword must be a non-empty string of at most 200 characters.")
        # Only phrases, never silently reinterpret user input as TED query syntax.
        if any(c in keyword for c in '\\"*?') or any(ord(c) < 32 for c in keyword):
            raise ValueError("Keywords cannot contain quotes, backslashes, wildcards or control characters.")
        keyword = keyword.strip()
        if keyword.casefold() not in {k.casefold() for k in cleaned}:
            cleaned.append(keyword)
    country = value.get("country", "FRA")
    if country is not None:
        if not isinstance(country, str):
            raise ValueError("country must be a three-letter country code, empty string or null.")
        country = country.strip().upper() or None
        if country is not None and not re.fullmatch(r"[A-Z]{3}", country):
            raise ValueError("country must use the TED three-letter code, e.g. FRA (not FR).")
    numbers = []
    for name, default, maximum in (("days", 30, 3650), ("max_results", 20, 100)):
        number = value.get(name, default)
        if type(number) is not int or not 1 <= number <= maximum:
            raise ValueError(f"{name} must be an integer between 1 and {maximum}.")
        numbers.append(number)
    validate_company_profile(value.get("company_profile"))
    return cleaned, country, numbers[0], numbers[1]


def build_query(keywords: list[str], country: str | None, days: int) -> str:
    parts = ["(" + " OR ".join(f'FT~"{k}"' for k in keywords) + ")"]
    if country:
        parts.append(f"buyer-country = {country}")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    parts.append(f"publication-date >= {start}")
    return " AND ".join(parts)


def nullable(value: Any) -> Any:
    """Keep TED's types and values; empty containers/strings are missing data."""
    if value is None or value == "" or value == [] or value == {}:
        return None
    return value


def parse_response(data: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(data, dict) or data.get("timedOut") is not False:
        raise RuntimeError("TED search timed out or returned an unexpected response envelope.")
    notices, total = data.get("notices"), data.get("totalNoticeCount")
    if (not isinstance(notices, list) or not all(isinstance(n, dict) for n in notices)
            or type(total) is not int or total < len(notices)):
        raise RuntimeError("TED response must contain notices[] and totalNoticeCount.")
    return notices, total


async def search(client: httpx.AsyncClient, query: str, fields: list[str], limit: int) -> tuple[list[dict[str, Any]], int]:
    Actor.log.info(f"TED query: {query}")
    for attempt in range(3):
        try:
            response = await client.post(TED_API_URL, json={
                "query": query, "fields": fields, "page": 1,
                "limit": limit, "scope": "ALL",
            })
        except httpx.TransportError:
            if attempt == 2:
                raise
            Actor.log.warning("TED transport error; retrying.")
        else:
            Actor.log.info(f"TED HTTP status: {response.status_code}")
            if response.status_code == 200:
                notices, total = parse_response(response.json())
                Actor.log.info(f"TED total results: {total}; returned: {len(notices)}")
                return notices, total
            if response.status_code != 429 and response.status_code < 500:
                raise RuntimeError(f"TED HTTP {response.status_code}: {response.text[:1000]}")
            if attempt == 2:
                raise RuntimeError(f"TED HTTP {response.status_code} after 3 attempts.")
            Actor.log.warning("TED temporarily unavailable; retrying.")
        await asyncio.sleep(2 ** (attempt + 1))
    raise RuntimeError("TED request failed.")


async def match_keywords(client: httpx.AsyncClient, notices: list[dict[str, Any]], keywords: list[str]) -> dict[str, list[str]]:
    ids = [n.get("publication-number") for n in notices]
    ids = list(dict.fromkeys(i for i in ids if isinstance(i, str) and re.fullmatch(r"\d+-\d{4}", i)))
    matched: dict[str, list[str]] = {i: [] for i in ids}
    if not ids:
        return matched
    if len(keywords) == 1:
        return {i: keywords.copy() for i in ids}
    for keyword in keywords:
        await asyncio.sleep(0.5)
        query = f'FT~"{keyword}" AND publication-number IN ({" ".join(ids)})'
        hits, total = await search(client, query, ["publication-number"], len(ids))
        if total != len(hits):
            raise RuntimeError("Incomplete TED keyword verification response.")
        for hit in hits:
            notice_id = hit.get("publication-number")
            if notice_id in matched:
                matched[notice_id].append(keyword)
    return matched


def parse_notice(notice: dict[str, Any], matched: dict[str, list[str]]) -> dict[str, Any]:
    notice_id = nullable(notice.get("publication-number"))
    # Never sum lots or pair currencies across scopes.
    estimated_value = currency = estimate_scope = None
    for scope in VALUE_SCOPES:
        estimated_value = nullable(notice.get(f"estimated-value-{scope}"))
        if estimated_value is not None:
            estimate_scope = scope
            currency = nullable(notice.get(f"estimated-value-cur-{scope}"))
            break
    if estimated_value is None:
        for scope in VALUE_SCOPES:
            currency = nullable(notice.get(f"estimated-value-cur-{scope}"))
            if currency is not None:
                break
    links = notice.get("links") or {}
    html = links.get("html") or {}
    url = next((html[k] for k in ("ENG", "FRA", *sorted(html)) if html.get(k)), None)
    return {
        "notice_id": notice_id,
        "title": nullable(notice.get("notice-title")),
        "buyer": nullable(notice.get("buyer-name")),
        "country": nullable(notice.get("buyer-country")),
        "publication_date": nullable(notice.get("publication-date")),
        "deadline": nullable(notice.get("deadline-receipt-tender-date-lot")),
        "estimated_value": estimated_value,
        "currency": currency,
        "cpv": nullable(notice.get("classification-cpv")),
        "ted_url": url,
        "matched_keywords": nullable(matched.get(notice_id)) if isinstance(notice_id, str) else None,
        "estimated_value_scope": estimate_scope,
        "scope_titles": nullable({scope: notice[f"title-{scope}"] for scope in VALUE_SCOPES
                                  if nullable(notice.get(f"title-{scope}")) is not None}),
        "description": nullable({scope: notice[f"description-{scope}"] for scope in VALUE_SCOPES
                                 if nullable(notice.get(f"description-{scope}")) is not None}),
        "procedure_type": nullable(notice.get("procedure-type")),
        "procedure_id": nullable(notice.get("procedure-identifier")),
        "lot_ids": nullable(notice.get("identifier-lot")),
        "group_ids": nullable(notice.get("identifier-glo")),
        "part_ids": nullable(notice.get("identifier-part")),
        "eligibility": nullable({field: notice[field] for field in ELIGIBILITY_FIELDS
                                 if nullable(notice.get(field)) is not None}),
        "sme_suitability": nullable({scope: notice[f"sme-{scope}"] for scope in ("lot", "glo", "part")
                                     if nullable(notice.get(f"sme-{scope}")) is not None}),
        "notice_type": nullable(notice.get("notice-type")),
    }


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input()
        keywords, country, days, max_results = validate_input({} if actor_input is None else actor_input)
        profile = validate_company_profile((actor_input or {}).get("company_profile"))
        query = build_query(keywords, country, days) + " SORT BY publication-date DESC"
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0), headers={"Accept": "application/json"}) as client:
            notices, total = await search(client, query, TED_FIELDS, max_results)
            notices = notices[:max_results]
            if total > len(notices):
                Actor.log.info(f"Output limited to {len(notices)} of {total} matching notices.")
            matched = await match_keywords(client, notices, keywords)
        items = score_and_sort([parse_notice(n, matched) for n in notices], keywords, profile, country)
        Actor.log.info(f"Scored {len(items)} notices; dataset sorted by fit_score descending.")
        if items:
            await Actor.push_data(items)
        Actor.log.info(f"Dataset results written: {len(items)}")
