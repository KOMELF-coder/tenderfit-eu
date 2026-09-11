from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from apify import Actor


TED_API_URL = "https://api.ted.europa.eu/v3/notices/search"


def build_query(keywords: list[str], country: str | None, days: int) -> str:
    parts: list[str] = []

    if keywords:
        keyword_query = " OR ".join(
            f'FT~"{keyword.strip()}"'
            for keyword in keywords
            if keyword.strip()
        )
        if keyword_query:
            parts.append(f"({keyword_query})")

    if country:
        parts.append(f"buyer-country = {country.upper()}")

    if days > 0:
        start_date = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y%m%d")

        parts.append(f"publication-date >= {start_date}")

    if not parts:
        return "*"

    return " AND ".join(parts)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}

        keywords = actor_input.get(
            "keywords",
            ["cybersecurity", "penetration testing"],
        )

        country = actor_input.get("country", "FRA")
        days = int(actor_input.get("days", 30))
        max_results = int(actor_input.get("max_results", 20))

        max_results = max(1, min(max_results, 100))
        days = max(1, min(days, 3650))

        if not isinstance(keywords, list):
            raise ValueError('"keywords" must be an array of strings.')

        query = build_query(
            keywords=keywords,
            country=country,
            days=days,
        )

        Actor.log.info(f"TED query: {query}")

        request_body = {
            "query": query,
            "page": 1,
            "limit": max_results,
            "fields": [
                "publication-number",
                "notice-title",
                "buyer-name",
                "buyer-country",
                "publication-date",
                "deadline-receipt-tender-date",
                "estimated-value",
                "estimated-value-cur",
                "classification-cpv",
            ],
        }

        timeout = httpx.Timeout(30.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                TED_API_URL,
                json=request_body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            Actor.log.error(
                f"TED API error {response.status_code}: {response.text}"
            )
            raise RuntimeError(
                f"TED API returned HTTP {response.status_code}"
            )

        data = response.json()

        notices = (
            data.get("notices")
            or data.get("results")
            or data.get("items")
            or []
        )

        if not notices:
            Actor.log.info("No notices found.")
            return

        output_items = []

        for notice in notices[:max_results]:
            notice_id = (
                notice.get("publication-number")
                or notice.get("notice-id")
                or notice.get("id")
            )

            output_items.append(
                {
                    "notice_id": notice_id,
                    "title": notice.get("notice-title"),
                    "buyer": notice.get("buyer-name"),
                    "country": notice.get("buyer-country"),
                    "publication_date": notice.get("publication-date"),
                    "deadline": notice.get(
                        "deadline-receipt-tender-date"
                    ),
                    "estimated_value": notice.get("estimated-value"),
                    "currency": notice.get("estimated-value-cur"),
                    "cpv": notice.get("classification-cpv"),
                    "ted_url": (
                        f"https://ted.europa.eu/en/notice/-/detail/{notice_id}"
                        if notice_id
                        else None
                    ),
                    "matched_keywords": keywords,
                }
            )

        await Actor.push_data(output_items)

        Actor.log.info(
            f"Successfully saved {len(output_items)} TED notices."
        )