import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from my_actor.main import main, parse_notice, validate_input
from my_actor.scoring import deadline_days, score_and_sort, score_notice, validate_company_profile

TODAY = date(2026, 9, 11)
PROFILE = {
    "country": "FRA", "services": ["penetration testing", "incident response"],
    "cpv_codes": ["72225000"], "employees": 12,
    "min_contract_value": 0, "max_contract_value": 500000,
    "preferred_currencies": ["EUR"],
}
ITEM = {
    "notice_id": "1-2026", "title": {"eng": "Penetration testing"},
    "description": {"proc": {"eng": "Incident response services"}},
    "buyer": {"eng": ["Example buyer (synthetic unit-test data)"]},
    "country": ["FRA"], "cpv": ["72225000"], "estimated_value": "400000",
    "estimated_value_scope": "proc", "currency": "EUR",
    "deadline": ["2026-10-01+02:00"], "matched_keywords": ["cybersecurity"],
}


class ScoringTests(unittest.TestCase):
    def score(self, item=None, profile=PROFILE):
        return score_notice(ITEM if item is None else item, ["cybersecurity"], profile, today=TODAY)

    def test_complete_profile(self):
        result = self.score()
        self.assertEqual(result["fit_score"], 100)
        self.assertEqual(result["fit_level"], "strong")
        self.assertEqual(result["days_until_deadline"], 20)
        self.assertEqual(result["matched_services"], PROFILE["services"])
        self.assertEqual(result["matched_cpv"], ["72225000"])
        self.assertEqual(sum(result["score_breakdown"].values()), result["fit_score"])

    def test_partial_profile(self):
        result = self.score(profile={"services": ["penetration testing"]})
        self.assertEqual(result["fit_score"], 60)  # services 35 + keyword 20 + deadline 5
        self.assertEqual(result["fit_level"], "medium")

    def test_no_profile(self):
        self.assertEqual(self.score(profile=None)["fit_score"], 25)
        self.assertEqual(self.score(profile={})["fit_score"], 25)
        self.assertEqual(score_notice(ITEM, ["cybersecurity"], country="FRA", today=TODAY)["fit_score"], 35)

    def test_missing_budget_deadline_cpv(self):
        for field, weight in (("estimated_value", 10), ("deadline", 5), ("cpv", 15)):
            item = {**ITEM, field: None}
            with self.subTest(field=field):
                result = self.score(item)
                self.assertEqual(result["fit_score"], 100 - weight)
                self.assertTrue(result["warnings"])
        self.assertIsNone(self.score({**ITEM, "deadline": None})["days_until_deadline"])
        self.assertEqual(self.score({**ITEM, "cpv": None})["matched_cpv"], [])

    def test_missing_everything(self):
        result = self.score({})
        self.assertEqual(result["fit_score"], 0)
        self.assertEqual(result["fit_level"], "weak")
        self.assertEqual(result["matched_services"], [])
        self.assertEqual(result["matched_keywords"], [])

    def test_fractional_matches_floor_each_component(self):
        profile = {"services": ["penetration testing", "digital forensics", "cloud" ]}
        result = score_notice(ITEM, ["cybersecurity", "cloud", "forensics"], profile, today=TODAY)
        self.assertEqual(result["score_breakdown"]["services"], 11)
        self.assertEqual(result["score_breakdown"]["keywords"], 6)
        self.assertEqual(result["fit_score"], 22)

    def test_service_matching_excludes_buyers_and_field_boundaries(self):
        item = {**ITEM, "title": {"eng": "Furniture"}, "description": None,
                "buyer": {"eng": ["Penetration testing incident response agency"]}}
        self.assertEqual(self.score(item)["matched_services"], [])
        item.update(title={"eng": "penetration"}, description={"proc": {"eng": "testing"}})
        self.assertEqual(self.score(item)["matched_services"], [])
        item.update(title={"eng": "Penetration-testing <b>service</b>"})
        self.assertEqual(self.score(item)["matched_services"], ["penetration testing"])
        self.assertEqual(self.score(profile={"services": ["test"]})["matched_services"], [])

    def test_cpv_exact_not_prefix_and_checksum_normalization(self):
        self.assertEqual(self.score(profile={"cpv_codes": ["72225000-8"]})["matched_cpv"], ["72225000"])
        self.assertEqual(self.score(profile={"cpv_codes": ["72000000"]})["matched_cpv"], [])

    def test_budget_currency_safety_and_zero(self):
        cases = [({"estimated_value": "0"}, 10), ({"estimated_value": "500000"}, 10),
                 ({"estimated_value": "500001"}, 0), ({"estimated_value": ["1", "2"]}, 0),
                 ({"estimated_value": "NaN"}, 0), ({"estimated_value": "Infinity"}, 0),
                 ({"currency": "USD"}, 0), ({"currency": None}, 0),
                 ({"currency": ["EUR", None]}, 0)]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.score({**ITEM, **changes})["score_breakdown"]["budget"], expected)
        for currencies in ([], ["EUR", "USD"]):
            self.assertEqual(self.score(profile={**PROFILE, "preferred_currencies": currencies})["score_breakdown"]["budget"], 0)

    def test_deadline_boundaries_and_multiple_lots(self):
        for days, points in ((-1, 0), (0, 0), (1, 2), (6, 2), (7, 5)):
            result = self.score({**ITEM, "deadline": [(TODAY + timedelta(days=days)).isoformat()]})
            self.assertEqual(result["days_until_deadline"], days)
            self.assertEqual(result["score_breakdown"]["deadline"], points)
        self.assertEqual(deadline_days(["2026-09-10+02:00", "2026-10-01+02:00"], TODAY), -1)
        for value in (None, [], ["2026-02-30"], ["2026-10-01", "bad"], [None]):
            self.assertIsNone(deadline_days(value, TODAY))

    def test_no_sme_or_employee_bonus(self):
        result = self.score({**ITEM, "sme_suitability": {"lot": [False, True]}, "eligibility": {"selection-criterion-lot": ["x"]}})
        self.assertEqual(result["fit_score"], self.score()["fit_score"])
        self.assertTrue(any("not establish SME" in w for w in result["warnings"]))
        self.assertFalse(any("eligible" in r for r in result["match_reasons"]))

    def test_score_bounds_and_stable_descending_sort(self):
        source = [{**ITEM, "notice_id": "first", "matched_keywords": []},
                  {"notice_id": "empty"}, {**ITEM, "notice_id": "best"},
                  {**ITEM, "notice_id": "tie"}]
        before = copy.deepcopy(source)
        result = score_and_sort(source, ["cybersecurity"], PROFILE, today=TODAY)
        self.assertEqual([r["notice_id"] for r in result], ["best", "tie", "first", "empty"])
        self.assertEqual(source, before)
        for profile in (None, {}, PROFILE, {"services": ["x"] * 50}):
            for item in source:
                result = self.score(item, profile)
                self.assertIs(type(result["fit_score"]), int)
                self.assertTrue(0 <= result["fit_score"] <= 100)

    def test_real_extra_fields_preserved(self):
        raw = json.loads((Path(__file__).parent / "fixtures/ted_v2_notice.json").read_text(encoding="utf-8"))
        item = parse_notice(raw, {})
        self.assertEqual(item["procedure_type"], "open")
        self.assertEqual(item["description"]["proc"], raw["description-proc"])
        self.assertEqual(item["lot_ids"], raw["identifier-lot"])
        self.assertEqual(item["eligibility"]["selection-criterion-description-lot"], raw["selection-criterion-description-lot"])
        self.assertIsNone(item["sme_suitability"])
        self.assertEqual(parse_notice({"sme-lot": [False]}, {})["sme_suitability"], {"lot": [False]})


class ProfileValidationTests(unittest.TestCase):
    def test_optional_and_normalized(self):
        self.assertEqual(validate_company_profile(None), {})
        for field in PROFILE:
            validate_company_profile({field: PROFILE[field]})
        self.assertEqual(validate_company_profile({"country": " fra ", "services": ["Sécurité", "securite"]}),
                         {"country": "FRA", "services": ["Sécurité"]})
        validate_input({"company_profile": {"employees": 0, "services": [], "cpv_codes": []}})

    def test_invalid_profiles(self):
        for profile in ([], False, {"employees": True}, {"employees": -1}, {"employees": 1.5},
                        {"country": "FR"}, {"services": "cloud"}, {"services": [None]},
                        {"services": [" "]}, {"services": ["!!!"]}, {"cpv_codes": ["72"]},
                        {"preferred_currencies": ["EURO"]}, {"max_contract_value": "10"},
                        {"max_contract_value": float("nan")}, {"min_contract_value": -1},
                        {"min_contract_value": 10, "max_contract_value": 9}, {"typo": 1}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                validate_input({"company_profile": profile})


class ActorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_pushes_scored_data_in_order(self):
        actor = AsyncMock()
        actor.get_input.return_value = {"keywords": ["testing"], "company_profile": {"services": ["testing"]}}
        notices = [{"publication-number": "1-2026", "notice-title": {"eng": "Furniture"}},
                   {"publication-number": "2-2026", "notice-title": {"eng": "Testing services"}}]
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"notices": notices, "totalNoticeCount": 2, "timedOut": False})))
        with patch("my_actor.main.Actor", actor), patch("my_actor.main.httpx.AsyncClient", return_value=client):
            # The SDK logger is synchronous, unlike its storage methods.
            from unittest.mock import Mock
            actor.log = Mock()
            await main()
        items = actor.push_data.await_args.args[0]
        self.assertEqual([n["notice_id"] for n in items], ["2-2026", "1-2026"])
        self.assertGreater(items[0]["fit_score"], items[1]["fit_score"])


if __name__ == "__main__":
    unittest.main()
