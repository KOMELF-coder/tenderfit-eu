"""Deterministic notice-level relevance; never an eligibility assessment."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

WEIGHTS = {"services": 35, "keywords": 20, "cpv": 15, "country": 10,
           "budget": 10, "currency": 5, "deadline": 5}


def normalize_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]*>", " ", value))
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def cpv_code(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{8}(?:-[0-9])?", value.strip()):
        return value.strip()[:8]
    return None


def validate_company_profile(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("company_profile must be an object or null.")
    allowed = {"country", "services", "cpv_codes", "employees", "min_contract_value",
               "max_contract_value", "preferred_currencies"}
    if set(value) - allowed:
        raise ValueError(f"Unknown company_profile fields: {', '.join(sorted(set(value) - allowed))}")
    result = {}
    for key, item in value.items():
        if item is None:
            continue
        if key == "country":
            if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z]{3}", item.strip()):
                raise ValueError("company_profile.country must be a three-letter TED code.")
            result[key] = item.strip().upper()
        elif key in ("services", "cpv_codes", "preferred_currencies"):
            if not isinstance(item, list) or len(item) > 50:
                raise ValueError(f"company_profile.{key} must be an array of at most 50 strings.")
            cleaned, seen = [], set()
            for entry in item:
                if not isinstance(entry, str) or not 1 <= len(entry.strip()) <= 200:
                    raise ValueError(f"company_profile.{key} contains an invalid string.")
                if any(ord(c) < 32 for c in entry):
                    raise ValueError(f"company_profile.{key} cannot contain control characters.")
                entry = entry.strip()
                if key == "cpv_codes":
                    entry = cpv_code(entry)
                    if entry is None:
                        raise ValueError("CPV codes must have eight digits, optionally followed by -checkdigit.")
                elif key == "preferred_currencies":
                    if not re.fullmatch(r"[A-Za-z]{3}", entry):
                        raise ValueError("Currencies must be three-letter codes, e.g. EUR.")
                    entry = entry.upper()
                canonical = normalize_text(entry) if key == "services" else entry
                if not canonical:
                    raise ValueError("Services must contain letters or digits.")
                if canonical not in seen:
                    cleaned.append(entry)
                    seen.add(canonical)
            result[key] = cleaned
        elif key == "employees":
            if type(item) is not int or item < 0:
                raise ValueError("company_profile.employees must be a non-negative integer.")
            result[key] = item
        else:
            if type(item) not in (int, float) or not Decimal(str(item)).is_finite() or item < 0:
                raise ValueError(f"company_profile.{key} must be a finite non-negative number.")
            result[key] = item
    if ("min_contract_value" in result and "max_contract_value" in result
            and result["min_contract_value"] > result["max_contract_value"]):
        raise ValueError("min_contract_value cannot exceed max_contract_value.")
    return result


def deadline_days(value: Any, today: date) -> int | None:
    """Earliest published calendar date; do not infer submission time or lot joins."""
    values = value if isinstance(value, list) else [value]
    if not values:
        return None
    dates = []
    for raw in values:
        if not isinstance(raw, str):
            return None
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})?", raw):
                parsed = datetime.fromisoformat(raw[:10] + "T00:00:00" + raw[10:])
            elif "T" in raw:
                parsed = datetime.fromisoformat(raw)
            else:
                return None
        except ValueError:
            return None
        dates.append(parsed.date())
    return (min(dates) - today).days


def single_amount(value: Any) -> Decimal | None:
    if isinstance(value, list):
        if len(value) != 1:
            return None
        value = value[0]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() and result >= 0 else None


def score_notice(item: dict[str, Any], keywords: list[str], profile: dict[str, Any] | None = None,
                 country: str | None = None, today: date | None = None) -> dict[str, Any]:
    profile = validate_company_profile(profile)
    today = today or datetime.now(timezone.utc).date()
    points = dict.fromkeys(WEIGHTS, 0)
    reasons, warnings = [], []

    # Keep fields/languages/lots separate to avoid creating phrases across boundaries.
    texts = [normalize_text(s) for field in ("title", "scope_titles", "description")
             for s in strings(item.get(field))]
    services = profile.get("services", [])
    matched_services = [s for s in services if any(
        f" {normalize_text(s)} " in f" {text} " for text in texts)]
    if services:
        points["services"] = 35 * len(matched_services) // len(services)
        reasons.extend(f"Matched service in market title/description: {s}" for s in matched_services)
        if not matched_services:
            warnings.append("No service phrase found in available market titles/descriptions.")
    else:
        warnings.append("No company services supplied; service points unavailable.")

    requested = list(dict.fromkeys(k.casefold() for k in keywords))
    confirmed = {k.casefold() for k in strings(item.get("matched_keywords"))}
    matched_keywords = list(dict.fromkeys(k for k in keywords if k.casefold() in confirmed))
    if requested:
        points["keywords"] = 20 * len(set(requested) & confirmed) // len(requested)
    reasons.extend(f"TED full-text keyword match: {k}" for k in matched_keywords)
    if matched_keywords and not any(f" {normalize_text(k)} " in f" {t} "
                                    for k in matched_keywords for t in texts):
        warnings.append("Keyword matches are outside available market text or use TED stemming; relevance needs review.")

    cpvs = {c for raw in strings(item.get("cpv")) if (c := cpv_code(raw))}
    matched_cpv = [c for c in profile.get("cpv_codes", []) if c in cpvs]
    if matched_cpv:
        points["cpv"] = 15
        reasons.append(f"Exact CPV match: {', '.join(matched_cpv)}")
    elif not cpvs:
        warnings.append("TED CPV data missing or invalid.")
    elif profile.get("cpv_codes"):
        warnings.append("No exact company CPV match.")

    target_country = profile.get("country") or country
    countries = {c.upper() for c in strings(item.get("country"))}
    if target_country and target_country in countries:
        points["country"] = 10
        reasons.append(f"Buyer country matches {'company profile' if profile.get('country') else 'search preference'}: {target_country}")
    elif target_country:
        warnings.append("Buyer country missing or different from preferred country.")

    raw_currencies = item.get("currency")
    currency_list = raw_currencies if isinstance(raw_currencies, list) else [raw_currencies]
    currencies = ({c.strip().upper() for c in currency_list}
                  if currency_list and all(isinstance(c, str) and re.fullmatch(r"[A-Za-z]{3}", c.strip())
                                           for c in currency_list) else set())
    preferred = profile.get("preferred_currencies", [])
    if currencies and preferred and currencies.issubset(set(preferred)):
        points["currency"] = 5
        reasons.append(f"Reported currency matches preference: {', '.join(sorted(currencies))}")
    elif preferred:
        warnings.append("Currency missing or outside preferred currencies.")
    budget_set = any(k in profile for k in ("min_contract_value", "max_contract_value"))
    if budget_set:
        amount = single_amount(item.get("estimated_value"))
        if amount is None:
            warnings.append("Budget not scored: estimate missing, invalid or contains multiple amounts.")
        elif len(preferred) != 1 or currencies != set(preferred):
            warnings.append("Budget not scored: requires one preferred currency matching the estimate; no currency conversion.")
        elif (amount >= Decimal(str(profile.get("min_contract_value", 0)))
              and ("max_contract_value" not in profile or amount <= Decimal(str(profile["max_contract_value"])))):
            points["budget"] = 10
            reasons.append("Estimated value is within the inclusive preferred range in the same currency.")
        else:
            warnings.append("Estimated value is outside the preferred budget range.")
        if item.get("estimated_value_scope") not in (None, "proc"):
            warnings.append("Estimate is scoped below the procedure; it is not the whole contract value.")

    days = deadline_days(item.get("deadline"), today)
    if days is None:
        warnings.append("Tender deadline missing or unparseable; deadline points unavailable.")
    elif days >= 7:
        points["deadline"] = 5
        reasons.append(f"Earliest tender deadline is in {days} calendar days.")
    elif days > 0:
        points["deadline"] = 2
        reasons.append("Tender deadline is still ahead (less than 7 days).")
        warnings.append(f"Deadline is in {days} days.")
    elif days == 0:
        warnings.append("Deadline is today; submission time has not been checked.")
    else:
        warnings.append(f"Earliest tender deadline passed {-days} days ago.")
    if len(set(strings(item.get("deadline")))) > 1:
        warnings.append("Multiple deadlines: earliest date used, without matching dates to lots.")

    if profile.get("employees") is not None:
        warnings.append("Employee count does not establish SME status or eligibility; no employee points awarded.")
    sme = item.get("sme_suitability")
    if sme is not None:
        warnings.append("TED SME suitability flags are informational and do not prove company eligibility.")
    eligibility = item.get("eligibility")
    warnings.append("Selection/exclusion requirements require manual review; eligibility is not verified."
                    if eligibility else "Eligibility requirements unavailable in returned fields; consult procurement documents.")
    if item.get("notice_type") and item["notice_type"] != "cn-standard":
        warnings.append(f"Notice type is {item['notice_type']}; verify whether it is an actionable opportunity.")

    score = max(0, min(100, sum(points.values())))
    return {**item, "fit_score": score,
            "fit_level": "strong" if score >= 70 else "medium" if score >= 40 else "weak",
            "score_breakdown": points, "match_reasons": reasons, "warnings": warnings,
            "matched_services": matched_services, "matched_keywords": matched_keywords,
            "matched_cpv": matched_cpv, "days_until_deadline": days}


def score_and_sort(items: list[dict[str, Any]], keywords: list[str],
                   profile: dict[str, Any] | None = None, country: str | None = None,
                   today: date | None = None) -> list[dict[str, Any]]:
    today = today or datetime.now(timezone.utc).date()
    # Stable sorting preserves TED publication-date order for equal scores.
    return sorted((score_notice(item, keywords, profile, country, today) for item in items),
                  key=lambda item: item["fit_score"], reverse=True)
