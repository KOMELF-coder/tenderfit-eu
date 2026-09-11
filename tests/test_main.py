import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from my_actor.main import (
    TED_FIELDS, build_query, match_keywords, nullable,
    parse_notice, parse_response, search, validate_input,
)


class InputTests(unittest.TestCase):
    def test_defaults_and_normalization(self):
        self.assertEqual(validate_input({}), (["cybersecurity", "penetration testing"], "FRA", 30, 20))
        self.assertEqual(validate_input({"keywords": [" cloud ", "CLOUD"], "country": " deu "})[:2], (["cloud"], "DEU"))
        self.assertIsNone(validate_input({"country": None})[1])
        self.assertIsNone(validate_input({"country": ""})[1])

    def test_invalid_inputs(self):
        for value in ([], "input", False, {"keywords": []}, {"keywords": "cloud"},
                      {"keywords": [None]}, {"keywords": [" "]}, {"keywords": ["x" * 201]},
                      {"keywords": ["a"] * 21}, {"keywords": ['cloud" OR FT~"x']},
                      {"keywords": ["cloud*"]}, {"keywords": ["x\\y"]},
                      {"keywords": ["x\ny"]}, {"country": 123}, {"country": "FR"},
                      {"country": "FRA OR TRUE"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_input(value)
        for key, maximum in (("days", 3650), ("max_results", 100)):
            for invalid in (True, "20", 1.5, None, 0, -1, maximum + 1):
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    validate_input({key: invalid})

    def test_query_date_and_phrase(self):
        with patch("my_actor.main.datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 11, tzinfo=timezone.utc)
            self.assertEqual(build_query(["cybersecurity", "penetration testing"], "FRA", 30),
                             '(FT~"cybersecurity" OR FT~"penetration testing") AND buyer-country = FRA AND publication-date >= 20260812')
            self.assertNotIn("buyer-country", build_query(["cloud"], None, 30))


class ParsingTests(unittest.TestCase):
    def test_real_response(self):
        data = json.loads((Path(__file__).parent / "fixtures/ted_response.json").read_text(encoding="utf-8"))
        notices, total = parse_response(data)
        self.assertEqual(total, 3)
        items = [parse_notice(n, {n["publication-number"]: ["cybersecurity"]}) for n in notices]
        self.assertEqual(items[1]["estimated_value"], "265000000")
        self.assertEqual(items[1]["currency"], "EUR")
        self.assertIsNone(items[0]["estimated_value"])
        self.assertEqual(items[0]["title"], notices[0]["notice-title"])
        self.assertEqual(items[0]["buyer"], notices[0]["buyer-name"])
        self.assertIn("FRA", items[0]["country"])
        self.assertEqual(items[0]["deadline"], ["2026-10-15+02:00"] * 2)
        self.assertEqual(items[0]["ted_url"], notices[0]["links"]["html"]["ENG"])

    def test_missing_and_zero(self):
        self.assertTrue(all(v is None for v in parse_notice({}, {}).values()))
        self.assertEqual(nullable(0), 0)
        item = parse_notice({"estimated-value-proc": 0, "estimated-value-cur-lot": ["EUR"]}, {})
        self.assertEqual(item["estimated_value"], 0)
        self.assertIsNone(item["currency"])

    def test_lot_fallback_without_summing_or_cross_scope_currency(self):
        item = parse_notice({"estimated-value-lot": ["10", "20"], "estimated-value-cur-lot": ["EUR", "USD"]}, {})
        self.assertEqual(item["estimated_value"], ["10", "20"])
        self.assertEqual(item["currency"], ["EUR", "USD"])

    def test_invalid_envelopes_are_not_empty_success(self):
        for data in ({}, {"results": []}, {"notices": [], "totalNoticeCount": 0, "timedOut": True},
                     {"notices": "bad", "totalNoticeCount": 0, "timedOut": False}):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                parse_response(data)
        self.assertEqual(parse_response({"notices": [], "totalNoticeCount": 0, "timedOut": False}), ([], 0))


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyword_verification(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["fields"], ["publication-number"])
            self.assertIn("publication-number IN (123-2026)", body["query"])
            hits = [{"publication-number": "123-2026"}] if 'FT~"cloud"' in body["query"] else []
            return httpx.Response(200, json={"notices": hits, "totalNoticeCount": len(hits), "timedOut": False})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("my_actor.main.asyncio.sleep", new_callable=AsyncMock):
                result = await match_keywords(client, [{"publication-number": "123-2026"}], ["cloud", "security"])
            self.assertEqual(result, {"123-2026": ["cloud"]})

    async def test_retry_and_fail_fast(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429)
            return httpx.Response(200, json={"notices": [], "totalNoticeCount": 0, "timedOut": False})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("my_actor.main.asyncio.sleep", new_callable=AsyncMock):
                self.assertEqual(await search(client, "test", TED_FIELDS, 20), ([], 0))
            self.assertEqual(len(calls), 2)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad field"))) as client:
            with patch("my_actor.main.asyncio.sleep", new_callable=AsyncMock) as sleep:
                with self.assertRaisesRegex(RuntimeError, "400"):
                    await search(client, "test", TED_FIELDS, 20)
                sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
