# API Reference

<!-- TODO [Steps 2.C2–2.C6]: Populate after API endpoints are designed and
     implemented. The framework choice will be made in Step 2.C1. -->

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
