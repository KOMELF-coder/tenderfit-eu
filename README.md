## What does TenderFit EU do?

**TenderFit EU searches public procurement notices from [TED](https://ted.europa.eu/)** using its public Search API v3. It filters by keyword phrases, buyer country and publication date, then writes up to 100 notices to an Apify dataset. Apify provides scheduling, API access, monitoring and integrations for these results.

The Actor uses Python, Apify SDK and HTTPX only. It requires no TED credentials, browser, LLM, database or proxy configuration.

## Why use TenderFit EU?

Use it for procurement monitoring and collecting source data for manual opportunity review. Results are full-text matches, not a qualification or relevance score. For example, “cybersecurity” can match an organisation's name in a furniture tender. Always inspect the source notice before deciding whether a tender is relevant.

## How to use TenderFit EU

1. Build the Actor from this repository's `main` branch.
2. Enter the JSON below in the Apify Input tab.
3. Run the Actor and inspect the Output dataset and run logs.

```json
{
  "keywords": ["cybersecurity", "penetration testing"],
  "country": "FRA",
  "days": 30,
  "max_results": 20
}
```

## Input

| Field | Default | Validation and meaning |
| --- | --- | --- |
| keywords | cybersecurity, penetration testing | 1–20 non-empty strings, maximum 200 characters each; trimmed and deduplicated case-insensitively. Quotes, backslashes, wildcards and control characters are rejected. |
| country | FRA | Three-letter TED country code; trimmed and uppercased. Empty string or null disables filtering. Format is checked, not membership in TED's country vocabulary. Use FRA, not FR. |
| days | 30 | Integer 1–3650. Inclusive lower bound: UTC today minus this many days. |
| max_results | 20 | Integer 1–100. Newest publication dates first; no particular order guaranteed for equal dates. |

Booleans, numeric strings, fractional numbers and out-of-range values are rejected for integer inputs, rather than silently converted or clamped.

## Output

Each item contains all eleven fields below. Missing or empty source values become `null`; zero is retained. TED's multilingual objects, arrays, decimal strings and date strings are preserved. No translation, monetary aggregation or date/time conversion is performed.

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
| matched_keywords | Keywords confirmed by TED full-text searches restricted to returned publication numbers; null when unconfirmed |

For multiple keywords, one small additional API search per keyword confirms matches across the entire notice, including languages and fields not returned in the dataset. A single-keyword query already proves that match. Multi-lot amounts are never summed and currency is never borrowed from another scope. Arrays are not treated as guaranteed lot-to-currency or buyer-to-country joins.

## Pricing / cost estimation

Apify usage depends on your account and run resources. The Actor makes one main request, then up to 20 verification requests, with bounded retries for transport errors, HTTP 429 and server errors. Smaller inputs reduce network traffic and run time. No external AI service is used.

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

All 15 final fields were tested together. The original query syntax is valid:

```text
(FT~"cybersecurity" OR FT~"penetration testing") AND buyer-country = FRA AND publication-date >= 20260812
```

`FT~` applies TED full-text matching; quoted multiword terms are phrases. Country equality uses the three-letter code. Dates use YYYYMMDD; `>=` is inclusive. The Actor adds `SORT BY publication-date DESC` and explicitly uses scope `ALL`.

Observed JSON envelope: `notices` (array), `totalNoticeCount` (integer), `iterationNextToken` (null in page mode), and `timedOut` (boolean). Unexpected envelopes and timed-out searches fail instead of being reported as empty success.

Real tests on 2026-09-11: HTTP 200, total 3, publications `598420-2026`, `609844-2026`, `612350-2026`. Each matched cybersecurity; none matched penetration testing. A full local SDK run wrote 3 items and exited 0. A no-match query returned HTTP 200 and zero results. The unmodified response for the nine corrected fields is saved in `tests/fixtures/ted_response.json` for regression tests.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q my_actor tests
python -m tests.live_ted
python -m my_actor
```

The live test is opt-in and calls TED over HTTP; it writes its report under ignored local `storage/`. Set local input in `storage/key_value_stores/default/INPUT.json`. If a local corporate TLS setup needs extra trusted certificates, configure HTTPX's `SSL_CERT_FILE` with the approved CA bundle; never disable TLS verification.

## Limitations and support

The country filter matches buyer country, not place of performance. Scope ALL can include award notices and expired opportunities. Missing tender deadlines remain null; request-to-participate dates are not substituted. TED may omit estimated amounts or other fields. Procedure estimates take precedence over lot, group and part estimates; use the source notice for a full lot breakdown. Publication versions can appear separately. This Actor deliberately limits output to 100 notices and does not paginate beyond that cap.

Local SDK storage does not publish data to Apify Cloud. Rebuild from the pushed commit and run in Apify to verify the cloud environment; the development tests do not claim a cloud run. API results and supported fields can change over time. Report reproducible issues at [GitHub Issues](https://github.com/KOMELF-coder/tenderfit-eu/issues).
