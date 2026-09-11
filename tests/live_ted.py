"""Opt-in real HTTP smoke test: python -m tests.live_ted (no Apify cloud writes)."""
import asyncio
import json
from pathlib import Path

import httpx

from my_actor.main import TED_FIELDS, match_keywords, parse_notice, search


async def main():
    query = '(FT~"cybersecurity" OR FT~"penetration testing") AND buyer-country = FRA AND publication-date >= 20260812'
    async with httpx.AsyncClient(timeout=45) as client:
        notices, total = await search(client, query + " SORT BY publication-date DESC", TED_FIELDS, 20)
        assert notices, "Historical smoke query no longer returns notices; inspect TED data."
        matched = await match_keywords(client, notices, ["cybersecurity", "penetration testing"])
        items = [parse_notice(n, matched) for n in notices]
        assert all("FRA" in item["country"] for item in items)
        assert all(item["publication_date"][:10] >= "2026-08-12" for item in items)
        assert all(item["notice_id"] and item["matched_keywords"] for item in items)
        empty, count = await search(client, 'FT~"tenderfitzzzznomatchabcdefxyz" AND publication-date >= 20260812', TED_FIELDS, 1)
        assert empty == [] and count == 0
    path = Path("storage/live-test.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"query": query, "total": total, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Live TED smoke passed: total={total}, parsed={len(items)}, empty query=0")


if __name__ == "__main__":
    asyncio.run(main())
