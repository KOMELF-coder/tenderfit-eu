# TenderFit EU

Stop manually reviewing TED notices. TenderFit EU finds recent EU public tenders and ranks them against your company profile so you can focus on the opportunities most worth reviewing.

## What TenderFit EU does

Turn recent tender notices into a ranked shortlist for your team to review. TenderFit EU:

- Searches official [TED public procurement data](https://ted.europa.eu/).
- Filters notices by keywords, buyer country and publication period.
- Compares tenders with your optional company profile.
- Calculates an explainable fit score from 0 to 100.
- Gives reasons for each match.
- Flags missing information, short deadlines and other points to check.
- Sorts the retrieved results from highest to lowest fit score.

## What you get

- Explainable 0-100 fit score
- Strong / medium / weak ranking
- Matched services
- Matched keywords
- Matched CPV codes
- Buyer country
- Estimated contract value
- Tender deadline
- Match reasons
- Warnings
- Direct TED source link

Source values are included when TED provides them. Missing data stays `null`.

## Example result

The JSON below is a simplified illustrative example, not a real TED notice or a complete scoring calculation.

```json
{
  "notice_id": "EXAMPLE-2026",
  "title": {
    "eng": "Cybersecurity penetration testing services"
  },
  "buyer": {
    "eng": ["Example Public Authority"]
  },
  "country": ["FRA"],
  "estimated_value": "180000",
  "currency": "EUR",
  "days_until_deadline": 21,
  "fit_score": 87,
  "fit_level": "strong",
  "matched_services": [
    "penetration testing",
    "incident response"
  ],
  "matched_keywords": [
    "cybersecurity"
  ],
  "match_reasons": [
    "Matched service in market title/description: penetration testing",
    "Buyer country matches company profile: FRA",
    "Estimated value is within the preferred range"
  ],
  "warnings": [],
  "ted_url": "https://ted.europa.eu/..."
}
```

This is an illustrative example. TenderFit never invents missing TED data.

## Who is this for?

- SMEs looking for relevant public contracts
- Consulting firms monitoring opportunities for their services
- IT companies and cybersecurity companies building a tender shortlist
- Business development teams prioritizing opportunities to review
- Procurement consultants researching opportunities for clients
- Developers, AI agents and automation workflows that need structured, ranked TED data

## How it works

```text
TED public procurement data
↓
TenderFit search
↓
company-profile matching
↓
deterministic scoring
↓
ranked dataset
```

## How to use

1. Click "Try for free".
2. Enter keywords and filters.
3. Optionally add your company profile.
4. Run the Actor.
5. Review ranked results.

Use this input as a starting point and replace the services and preferences with your own.

Exact example in `examples/company-profile.json`:

```json
{
  "keywords": ["penetration testing", "incident response", "digital forensics"],
  "country": "FRA",
  "days": 30,
  "max_results": 20,
  "company_profile": {
    "country": "FRA",
    "services": ["penetration testing", "incident response", "digital forensics"],
    "cpv_codes": [],
    "employees": 12,
    "min_contract_value": 0,
    "max_contract_value": 500000,
    "preferred_currencies": ["EUR"]
  }
}
```

## Pricing

TenderFit EU uses pay-per-result pricing.

- $0.01 per result returned
- $0.00005 Actor start fee
- Apify platform usage is included

Examples:

- 20 results ≈ $0.20
- 100 results ≈ $1.00
- 1,000 results ≈ $10.00

These examples show result charges; the Actor start fee applies per run. Each run returns up to 100 results, so 1,000 results requires multiple runs.

## Input

| Field | Default | Validation and meaning |
| --- | --- | --- |
| keywords | cybersecurity, penetration testing | 1–20 non-empty strings, maximum 200 characters each; trimmed and deduplicated case-insensitively. Quotes, backslashes, wildcards and control characters are rejected. |
| country | FRA | Three-letter TED country code; trimmed and uppercased. Empty string or null disables filtering. Format is checked, not membership in TED's country vocabulary. Use FRA, not FR. |
| days | 30 | Integer 1–3650. Inclusive lower bound: UTC today minus this many days. |
| max_results | 20 | Integer 1–100. Candidate cap: retrieve newest publication dates first, then sort these candidates by fit score. |
| company_profile | {} | Optional object; all seven nested fields optional, including null values. See below. |

Booleans, numeric strings, fractional numbers and out-of-range values are rejected for integer inputs, rather than silently converted or clamped.

### Company profile

`country` is a three-letter preferred buyer country. `services` contains up to 50 non-empty phrases of up to 200 characters. `cpv_codes` contains up to 50 eight-digit strings (an optional `-checkdigit` suffix is stripped, not verified). `employees` is a non-negative integer used only for an informational warning. `min_contract_value` and `max_contract_value` are finite non-negative numbers, with minimum <= maximum when both are present. `preferred_currencies` contains up to 50 three-letter codes. Country/currency vocabulary membership is not checked. Unknown profile keys fail validation to catch typos.

Lists are deduplicated and empty lists are accepted. Omitted/null fields are not inferred. Services and CPV codes affect scoring only; they do not expand the TED keyword search or bypass its country filter. Use `country: ""` at top level to search all buyer countries while scoring against the profile country.

## Output

Each item retains the eleven original fields and adds source context and scoring fields. Missing or empty source values become `null`; zero and explicit false are retained. TED's multilingual objects, arrays, decimal strings and date strings are preserved. No translation, monetary aggregation or currency conversion is performed. Computed match/reason/warning arrays use `[]` when empty; an uncalculable `days_until_deadline` is null.

You can download the dataset in various formats such as JSON, HTML, CSV, or Excel. JSON retains nested multilingual data most clearly.

For a compact **projection of a real API result** observed on 2026-09-11 (other dataset fields omitted here):

```json
{
  "notice_id": "609844-2026",
  "publication_date": "2026-09-04+02:00",
  "deadline": ["2026-10-26+01:00"],
  "estimated_value": "265000000",
  "currency": "EUR",
  "matched_keywords": ["cybersecurity"]
}
```

## Important

TenderFit measures documented relevance, not legal eligibility, bidding feasibility, or probability of winning. Always review the official TED notice and procurement documents before making a bid decision.

## Data table

| Dataset field | Source and representation |
| --- | --- |
| notice_id | `publication-number`: string |
| title | `notice-title`: language code → title string |
| buyer | `buyer-name`: language code → list of buyer names |
| country | `buyer-country`: list of codes; may include multiple countries |
| publication_date | `publication-date`: raw date string, including TED timezone suffix |
| deadline | `deadline-receipt-tender-date-lot`: list of tender submission dates |
| estimated_value | First populated `estimated-value-{proc,lot,glo,part}` in that order; procedure scalar or scoped array |
| currency | Same scope as the selected estimate. If every estimate is absent, first populated currency in the same scope order. |
| cpv | `classification-cpv`: list, including any source duplicates |
| ted_url | Actual `links.html` URL, preferring ENG, then FRA, then another available language |
| matched_keywords | Keywords confirmed by TED full-text searches restricted to returned publication numbers; [] when unconfirmed |

For multiple keywords, one small additional API search per keyword confirms matches across the entire notice, including languages and fields not returned in the dataset. A single-keyword query already proves that match. Multi-lot amounts are never summed and currency is never borrowed from another scope. Arrays are not treated as guaranteed lot-to-currency or buyer-to-country joins.

## V2 source fields

These **26 additional field names were accepted together by the live API**, for 41 requested fields total (4,100 field slots at the 100-notice cap). A field being supported does not guarantee it appears in a given notice.

| Dataset context | Additional TED fields |
| --- | --- |
| scope_titles, description | `title-proc`, `title-lot`, `title-glo`, `title-part`; `description-proc`, `description-lot`, `description-glo`, `description-part` |
| procedure_type, procedure_id | `procedure-type`, `procedure-identifier` |
| lot_ids, group_ids, part_ids | `identifier-lot`, `identifier-glo`, `identifier-part` |
| eligibility (raw source keys) | `selection-criteria-source`, `selection-criterion-lot`, `selection-criterion-description-lot`, `selection-criterion-name-lot`, `selection-criterion-used-lot`, `exclusion-grounds`, `exclusion-grounds-description`, `exclusion-grounds-source-proc`, `reserved-procurement-lot` |
| sme_suitability (by scope) | `sme-lot`, `sme-glo`, `sme-part` |
| notice_type | `notice-type` |

`estimated_value_scope` identifies the chosen existing estimate source (`proc`, `lot`, `glo`, `part`), not a guessed contract hierarchy. Descriptions/titles are dictionaries by scope containing the unmodified multilingual TED values. The API exposes procedure/lot identifiers and criteria, but this Actor does not assume that parallel arrays can be joined by position.

## Exact deterministic scoring formula

The score is the sum of seven integer components, bounded to 0–100. **Weights are fixed: missing profile or notice data earns zero; weights are never redistributed.** `score_breakdown` exposes every component. `match_reasons` gives evidence and `warnings` identifies uncertainty, missing information and urgency.

| Component | Exact points |
| --- | --- |
| Services | `floor(35 × matched services / supplied services)`, or 0 with no services. |
| Keywords | `floor(20 × TED-confirmed requested keywords / requested keywords)`, or 0 with none. |
| CPV | 15 if at least one supplied eight-digit CPV exactly matches a returned CPV; otherwise 0. No prefix matching. |
| Country | 10 if the profile country occurs in buyer countries; use top-level search country only if profile country is absent. Otherwise 0. |
| Budget | 10 if at least one bound is supplied and one valid non-negative estimate is within the inclusive range, in the single preferred currency; otherwise 0. Missing minimum means 0; missing maximum means unbounded. |
| Currency | 5 if all reported non-empty currency entries are valid codes and belong to preferred currencies; otherwise 0. |
| Deadline | 5 if earliest tender date is at least 7 days away; 2 if 1–6 days away; 0 if today, past, missing or unparseable. |

Services match whole normalized phrases in individual market title/description strings across returned languages and scopes. Matching ignores case, accents, markup and punctuation; it does not translate, infer synonyms, stem words or join separate fields into a phrase. Buyer names and eligibility text are excluded from service scoring. Service/profile lists are deduplicated before computing coverage.

Budget comparisons require **exactly one preferred currency**, with every reported currency matching it. The estimate must be a scalar or a one-element array. Multiple amounts, unknown currencies or multiple preferred currencies receive no budget points. There is no exchange-rate lookup or summation of lot values. Currency points are independent from budget points.

Deadline calculations use the earliest published **calendar date** minus UTC today, retaining the date written by TED without timezone conversion. Missing/invalid entries make the calculation unknown. Mixed past/future lot deadlines use the earliest, even if another lot is still open. Submission times are not checked. Dates in 1–6 days, today and the past generate warnings.

Levels: **strong >= 70**, **medium 40–69**, **weak 0–39**. This is relevance, not an availability verdict: an expired notice can still score highly on other components, with an explicit warning. SME indicators, employee count, procedure type and eligibility data contribute no points and never establish legal eligibility.

Without a profile, the maximum is 35 (20 keyword + 10 search-country + 5 deadline), or 25 with no country filter. This deliberately makes scores for incomplete profiles conservative. Results are stably sorted by decreasing score; ties preserve TED's returned publication-date order. Only the retrieved candidate set is ranked, not every matching notice on TED.

## TED API verification and development

Official references consulted on 2026-09-11:

- [TED Search API v3](https://docs.ted.europa.eu/api/latest/search.html)
- [Official field list](https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html)
- [OpenAPI specification linked by Swagger](https://api.ted.europa.eu/api-v3.yaml)
- [Expert query syntax](https://ted.europa.eu/en/help/search-browse)

The original HTTP 400 was reproduced and every original field was tested individually:

| Original field | Real HTTP result | Correction |
| --- | --- | --- |
| publication-number | 200 | unchanged |
| notice-title | 200 | unchanged |
| buyer-name | 200 | unchanged |
| buyer-country | 200 | unchanged |
| publication-date | 200 | unchanged |
| deadline-receipt-tender-date | 400 UNSUPPORTED_VALUE | deadline-receipt-tender-date-lot |
| estimated-value | 400 UNSUPPORTED_VALUE | estimated-value-proc, with lot/glo/part fallbacks |
| estimated-value-cur | 400 UNSUPPORTED_VALUE | estimated-value-cur-proc, with matching scoped fallbacks |
| classification-cpv | 200 | unchanged |

The 15 V1 fields were tested together; V2 adds the 26 fields listed above. The original query syntax remains valid:

```text
(FT~"cybersecurity" OR FT~"penetration testing") AND buyer-country = FRA AND publication-date >= 20260812
```

`FT~` applies TED full-text matching; quoted multiword terms are phrases. Country equality uses the three-letter code. Dates use YYYYMMDD; `>=` is inclusive. The Actor adds `SORT BY publication-date DESC` and explicitly uses scope `ALL`.

Observed JSON envelope: `notices` (array), `totalNoticeCount` (integer), `iterationNextToken` (null in page mode), and `timedOut` (boolean). Unexpected envelopes and timed-out searches fail instead of being reported as empty success.

Real V2 tests on 2026-09-11: HTTP 200, total 3 for the cybersecurity/penetration-testing query, publications `598420-2026`, `609844-2026`, `612350-2026`. Each matched cybersecurity; none matched penetration testing. Using the company profile above with those two search keywords produced sorted scores **30, 30, 25**. A full local SDK run wrote those 3 scored items and exited 0; the output passed the dataset schema. The exact three-keyword input example returned HTTP 200, **zero notices** on that date and exited 0. That is a valid empty search, not a scoring error; broaden the date range or keywords if needed.

The no-match smoke query also returned HTTP 200 and zero results. The unmodified V1 response is saved in `tests/fixtures/ted_response.json`. A real V2 notice with populated descriptions, selection criteria and lot identifiers is saved in `tests/fixtures/ted_v2_notice.json`. Synthetic scoring fixtures in unit tests are explicitly test data, never production output.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q my_actor tests
python -m tests.live_ted
python -m my_actor
```

The live test is opt-in and calls TED over HTTP; it writes its report under ignored local `storage/`. Set local input in `storage/key_value_stores/default/INPUT.json`. If a local corporate TLS setup needs extra trusted certificates, configure HTTPX's `SSL_CERT_FILE` with the approved CA bundle; never disable TLS verification.

The Actor uses Python, Apify SDK and HTTPX only. It requires no TED credentials, browser, LLM, database or proxy configuration. Apify provides scheduling, API access, monitoring and integrations for the results.

## Limitations and support

The country filter matches buyer country, not place of performance. Scope ALL can include award notices and expired opportunities. Missing tender deadlines remain null; request-to-participate dates are not substituted. TED may omit estimated amounts or other fields. Procedure estimates take precedence over lot, group and part estimates; use the source notice for a full lot breakdown. Publication versions can appear separately. This Actor deliberately limits output to 100 recent candidates and does not paginate beyond that cap; relevant older candidates can be missed.

Selection criteria can be located in procurement documents or the ESPD instead of the notice, according to the [eForms procedure/lot documentation](https://docs.ted.europa.eu/eforms/latest/schema/procedure-lot-part-information.html). When such information is not returned, the Actor does not reconstruct it. It does not download documents, parse complete XML, verify certifications, infer financial capacity, assess exclusion grounds, resolve criteria to individual lots, or determine legal eligibility. Raw SME suitability indicates the buyer's statement only. Employee count alone is never used to classify SME status. Missing flags remain null, and explicit false flags remain false.

Literal service matching can miss translated, inflected or synonymous descriptions and cannot interpret negation or contractual intent. TED keyword matching can occur outside the title/description. A fixed 0–100 score has no calibrated success probability and should be reviewed alongside its reasons, warnings and source fields.

Local SDK storage does not publish data to Apify Cloud. Rebuild from the pushed commit and run in Apify to verify the cloud environment; the development tests do not claim a cloud run. API results and supported fields can change over time. Report reproducible issues at [GitHub Issues](https://github.com/KOMELF-coder/tenderfit-eu/issues).
