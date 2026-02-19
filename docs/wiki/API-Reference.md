# API Reference

<!--
──────────────────────────────────────────────────────────────────────────────
Documentation TODOs (Step 3.C — Documentation & Help)
──────────────────────────────────────────────────────────────────────────────

TODO 3.C4-a / DOC-001 [Group: BEAR] [Complexity: MEDIUM] [Tokens: ~4000] [User: NO]
    Populate API Reference wiki page with complete endpoint documentation.
    The API is fully implemented but this wiki page has only placeholder
    comments. Steps:
      1. Document each endpoint with: method, path, parameters, response schema
      2. For /api/v1/search: document q, type, limit, offset params;
         show example request and response JSON
      3. For /api/v1/budget-lines: document all filter params, sorting, pagination;
         show example request and response
      4. For /api/v1/aggregations: document group_by options, filter params
      5. For /api/v1/download: document fmt (csv/json), filter params, streaming
      6. For /api/v1/reference/*: document all three sub-endpoints
      7. For /health: document response format and status codes
      8. Include curl examples for each endpoint
      9. Document error response format (400, 404, 429, 500)
     10. Document rate limits per endpoint
     Note: FastAPI auto-generates OpenAPI docs at /docs, but this wiki page
     should be a human-readable narrative reference.
    Acceptance: Wiki page fully documents all endpoints with examples.
-->

REST API documentation for the DoD Budget Analysis database.

---

## Base URL

<!-- To be determined after deployment (Step 4.A1, 4.A4). -->

## Authentication

<!-- To be determined. Initial plan: open/unauthenticated for read access,
     with rate limiting to prevent abuse (Step 2.C5). -->

## Endpoints

### `GET /search`

<!-- Full-text search across budget lines and PDF pages.
     Parameters: q, type (excel|pdf|both), org, exhibit, top, offset -->

### `GET /budget-lines`

<!-- Filtered query for structured budget data.
     Parameters: org, fiscal_year, exhibit_type, account, line_item, sort, limit, offset -->

### `GET /aggregations`

<!-- Aggregate budget totals by various dimensions.
     Parameters: group_by (org|year|exhibit|account), filters -->

### `GET /download`

<!-- Export filtered results as CSV or JSON.
     Parameters: same as /budget-lines + format (csv|json) -->

---

## Error Handling

<!-- Standard error response format:
     { "error": "message", "code": 400, "detail": "..." } -->

## Rate Limits

<!-- To be determined based on deployment infrastructure. -->

## Examples

<!-- Sample curl commands and responses for each endpoint. -->
