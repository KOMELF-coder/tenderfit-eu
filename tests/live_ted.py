"""Opt-in real HTTP smoke test: python -m tests.live_ted (no Apify cloud writes)."""
import asyncio
import json
from pathlib import Path

import httpx

from my_actor.main import TED_FIELDS, match_keywords, parse_notice, search
from my_actor.scoring import score_and_sort


async def main():
    query = '(FT~"cybersecurity" OR FT~"penetration testing") AND buyer-country = FRA AND publication-date >= 20260812'
    async with httpx.AsyncClient(timeout=45) as client:
        notices, total = await search(client, query + " SORT BY publication-date DESC", TED_FIELDS, 20)
        assert notices, "Historical smoke query no longer returns notices; inspect TED data."
        matched = await match_keywords(client, notices, ["cybersecurity", "penetration testing"])
        profile = {"country": "FRA", "services": ["penetration testing", "incident response", "digital forensics"],
                   "cpv_codes": [], "employees": 12, "min_contract_value": 0,
                   "max_contract_value": 500000, "preferred_currencies": ["EUR"]}
        items = score_and_sort([parse_notice(n, matched) for n in notices],
                               ["cybersecurity", "penetration testing"], profile, "FRA")
        assert all("FRA" in item["country"] for item in items)
        assert all(item["publication_date"][:10] >= "2026-08-12" for item in items)
        assert all(item["notice_id"] and item["matched_keywords"] for item in items)
        assert [n["fit_score"] for n in items] == sorted((n["fit_score"] for n in items), reverse=True)
        assert all(0 <= n["fit_score"] <= 100 for n in items)
        assert all(sum(n["score_breakdown"].values()) == n["fit_score"] for n in items)
        empty, count = await search(client, 'FT~"tenderfitzzzznomatchabcdefxyz" AND publication-date >= 20260812', TED_FIELDS, 1)
        assert empty == [] and count == 0
    path = Path("storage/live-test.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"query": query, "total": total, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Live TED smoke passed: total={total}, parsed={len(items)}, empty query=0, scores={[n['fit_score'] for n in items]}")


if __name__ == "__main__":
    asyncio.run(main())
