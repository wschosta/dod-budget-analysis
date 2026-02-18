# DoD Budget Analysis REST API Specification — TODO 2.C2-a

**Version:** 1.0.0
**Framework:** FastAPI
**Base URL:** `/api/v1`
**Response Format:** JSON

---

## Overview

The API provides programmatic access to DoD budget line items, aggregations, and reference data.
All endpoints support filtering, pagination, and sorting. Responses include metadata about the
query (filters applied, total results, pagination info).

### Common Response Structure

```json
{
  "success": true,
  "data": [],
  "meta": {
    "total": 0,
    "limit": 20,
    "offset": 0,
    "filters_applied": {}
  }
}
```

### Common Error Response

```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAM",
    "message": "Invalid fiscal year: 9999",
    "details": {}
  }
}
```

---

## Endpoints

### 1. Full-Text Search

#### `GET /api/v1/search`

Search across all budget line items and PDF text using full-text search (FTS5).

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | ✓ | - | Search query (e.g., "fighter aircraft procurement") |
| `limit` | integer | | 20 | Results per page (min: 1, max: 100) |
| `offset` | integer | | 0 | Pagination offset |
| `fiscal_year` | string | | - | Filter by fiscal year (comma-separated, e.g. "2024,2025") |
| `service` | string | | - | Filter by service (comma-separated, e.g. "Army,Navy") |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "bl_12345",
      "type": "budget_line",
      "fiscal_year": 2025,
      "service": "Army",
      "account_title": "Ammunition, Army",
      "line_item_title": "5.56mm Ammunition",
      "amount_thousands": 450000,
      "snippet": "...5.56mm <mark>Ammunition</mark> procurement for combat operations..."
    },
    {
      "id": "pdf_67890_p45",
      "type": "pdf_excerpt",
      "source": "DoD_Budget_Documents/Army/P-1_FY2025.pdf",
      "page": 45,
      "excerpt": "...planning for future <mark>ammunition</mark> requirements..."
    }
  ],
  "meta": {
    "query": "fighter aircraft procurement",
    "total": 342,
    "limit": 20,
    "offset": 0
  }
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid query parameter
- `500`: Database or search service error

---

### 2. Budget Lines — Structured Query

#### `GET /api/v1/budget-lines`

Query budget line items with optional filtering, sorting, and pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fiscal_year` | string | | Comma-separated FY (e.g., "2024,2025") |
| `service` | string | | Comma-separated services (Army, Navy, Air Force, Space Force, Marine Corps, Defense-Wide) |
| `appropriation` | string | | Comma-separated appropriation codes |
| `program_element` | string | | Program Element number (7 digits + letter, e.g. "0602702E") |
| `exhibit_type` | string | | Comma-separated exhibit types (P-1, P-5, R-1, R-2, O-1, M-1, C-1, RF-1) |
| `account_title` | string | | Filter account title (substring match, case-insensitive) |
| `min_amount` | number | | Minimum amount in thousands (e.g., "1000" for $1B+) |
| `max_amount` | number | | Maximum amount in thousands |
| `sort` | string | | Sort key: `amount_thousands`, `fiscal_year`, `service`, `account_title` (prefix with `-` for descending, e.g., `-amount_thousands`) |
| `limit` | integer | | Results per page (default: 20, max: 500) |
| `offset` | integer | | Pagination offset (default: 0) |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": "bl_98765",
      "fiscal_year": 2025,
      "service": "Navy",
      "appropriation_code": "1319",
      "appropriation_title": "Other Procurement, Navy",
      "program_element": "0604754N",
      "program_title": "Littoral Combat Ship - Combat System",
      "account_title": "Littoral Combat Ship (LCS) - Unmanned Systems",
      "line_item_title": "LCS Mission Modules - Unmanned",
      "budget_activity": "02",
      "exhibit_type": "P-1",
      "amount_thousands": 125000,
      "prior_year_enacted": 100000,
      "current_year_enacted": 100000,
      "quantity": 2,
      "unit_cost_thousands": 62500,
      "source_file": "DoD_Budget_Documents/Navy/P-1_FY2025.xlsx",
      "source_sheet": "P-1"
    }
  ],
  "meta": {
    "total": 4527,
    "limit": 20,
    "offset": 0,
    "filters_applied": {
      "service": ["Navy"],
      "min_amount": 100000
    }
  }
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid filter or sort parameter
- `404`: No results found (but success=true with empty data)

---

### 3. Aggregations

#### `GET /api/v1/aggregations`

Get aggregated budget totals grouped by a dimension (service, fiscal year, appropriation).

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `group_by` | string | ✓ | Grouping dimension: `service`, `fiscal_year`, `appropriation`, `exhibit_type` |
| `fiscal_year` | string | | Filter by fiscal year(s) before aggregating |
| `service` | string | | Filter by service(s) before aggregating |
| `exhibit_type` | string | | Filter by exhibit type(s) before aggregating |
| `sort_by` | string | | Sort order: `amount_descending` (default), `amount_ascending`, `label_ascending` |
| `limit` | integer | | Limit result count (default: no limit) |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "group": "Army",
      "total_thousands": 154320000,
      "item_count": 2347,
      "percentage_of_total": 22.5
    },
    {
      "group": "Navy",
      "total_thousands": 187450000,
      "item_count": 2891,
      "percentage_of_total": 27.3
    },
    {
      "group": "Air Force",
      "total_thousands": 205100000,
      "item_count": 2156,
      "percentage_of_total": 29.9
    },
    {
      "group": "Space Force",
      "total_thousands": 28300000,
      "item_count": 456,
      "percentage_of_total": 4.1
    },
    {
      "group": "Marine Corps",
      "total_thousands": 15800000,
      "item_count": 234,
      "percentage_of_total": 2.3
    },
    {
      "group": "Defense-Wide",
      "total_thousands": 75200000,
      "item_count": 1342,
      "percentage_of_total": 10.9
    }
  ],
  "meta": {
    "group_by": "service",
    "grand_total_thousands": 666170000,
    "filters_applied": {
      "fiscal_year": ["2025"]
    }
  }
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid group_by or filter parameter
- `422`: Missing required parameter

---

### 4. Single Line Item Detail

#### `GET /api/v1/budget-lines/{id}`

Retrieve the complete record for a single budget line item.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Budget line item ID |

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "bl_98765",
    "fiscal_year": 2025,
    "service": "Navy",
    "appropriation_code": "1319",
    "appropriation_title": "Other Procurement, Navy",
    "program_element": "0604754N",
    "program_title": "Littoral Combat Ship - Combat System",
    "account_title": "Littoral Combat Ship (LCS) - Unmanned Systems",
    "line_item_title": "LCS Mission Modules - Unmanned",
    "budget_activity": "02",
    "exhibit_type": "P-1",
    "amount_thousands": 125000,
    "prior_year_enacted": 100000,
    "current_year_enacted": 100000,
    "budget_estimate": 125000,
    "quantity": 2,
    "unit_cost_thousands": 62500,
    "notes": "Includes hardware and software development",
    "source": {
      "file": "DoD_Budget_Documents/Navy/P-1_FY2025.xlsx",
      "sheet": "P-1",
      "row": 42,
      "url": "https://comptroller.defense.gov/..."
    },
    "related_items": [
      {
        "id": "bl_98764",
        "fiscal_year": 2024,
        "amount_thousands": 100000,
        "relationship": "same_program_prior_year"
      },
      {
        "id": "bl_98766",
        "fiscal_year": 2026,
        "amount_thousands": 138000,
        "relationship": "same_program_next_year"
      }
    ]
  }
}
```

**Status Codes:**
- `200`: Success
- `404`: Line item not found

---

### 5. Download/Export

#### `GET /api/v1/download`

Export filtered budget line items in CSV or JSON format. Supports streaming for large result sets.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `format` | string | ✓ | - | Export format: `csv` or `json` |
| `fiscal_year` | string | | - | Comma-separated fiscal years (same filter as /budget-lines) |
| `service` | string | | - | Comma-separated services |
| `appropriation` | string | | - | Comma-separated appropriation codes |
| `exhibit_type` | string | | - | Comma-separated exhibit types |

**Response:**

For `format=csv`:
```
Content-Type: text/csv
Content-Disposition: attachment; filename="budget-export_2025-02-18.csv"

fiscal_year,service,appropriation_code,program_element,amount_thousands
2025,Army,2105,0602788A,450000
2025,Navy,1319,0604754N,125000
...
```

For `format=json` (newline-delimited JSON):
```
Content-Type: application/x-ndjson
Content-Disposition: attachment; filename="budget-export_2025-02-18.json"

{"fiscal_year": 2025, "service": "Army", "appropriation_code": "2105", ...}
{"fiscal_year": 2025, "service": "Navy", "appropriation_code": "1319", ...}
...
```

**Status Codes:**
- `200`: Success, streaming export
- `400`: Invalid format or filter
- `413`: Result set too large (apply filters to reduce)

---

### 6. Reference Data Endpoints

#### `GET /api/v1/reference/services`

List all services in the database.

**Response:**

```json
{
  "success": true,
  "data": [
    {"code": "Army", "name": "Department of the Army"},
    {"code": "Navy", "name": "Department of the Navy"},
    {"code": "Air Force", "name": "Department of the Air Force"},
    {"code": "Space Force", "name": "United States Space Force"},
    {"code": "Marine Corps", "name": "Marine Corps"},
    {"code": "Defense-Wide", "name": "Defense-Wide"}
  ]
}
```

#### `GET /api/v1/reference/exhibit-types`

List all exhibit types in the database.

**Response:**

```json
{
  "success": true,
  "data": [
    {"code": "P-1", "name": "Procurement (P-1)", "description": "Summary procurement budget"},
    {"code": "P-5", "name": "Procurement Detail (P-5)", "description": "Detailed procurement line items"},
    {"code": "R-1", "name": "RDT&E (R-1)", "description": "Research, Development, Test & Evaluation"},
    ...
  ]
}
```

#### `GET /api/v1/reference/fiscal-years`

List all fiscal years in the database.

**Response:**

```json
{
  "success": true,
  "data": [
    {"year": 2025, "available": true},
    {"year": 2024, "available": true},
    {"year": 2023, "available": true},
    ...
  ]
}
```

---

## Request/Response Models (Pydantic)

```python
# Request Models
class SearchParams(BaseModel):
    q: str
    limit: int = 20
    offset: int = 0
    fiscal_year: Optional[str] = None
    service: Optional[str] = None

class BudgetLineFilters(BaseModel):
    fiscal_year: Optional[str] = None
    service: Optional[str] = None
    appropriation: Optional[str] = None
    program_element: Optional[str] = None
    exhibit_type: Optional[str] = None
    account_title: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    sort: str = "account_title"
    limit: int = 20
    offset: int = 0

class AggregationParams(BaseModel):
    group_by: Literal["service", "fiscal_year", "appropriation", "exhibit_type"]
    fiscal_year: Optional[str] = None
    service: Optional[str] = None
    exhibit_type: Optional[str] = None
    limit: Optional[int] = None

# Response Models
class BudgetLineResponse(BaseModel):
    id: str
    fiscal_year: int
    service: str
    appropriation_code: str
    amount_thousands: float
    ...

class AggregationResult(BaseModel):
    group: str
    total_thousands: float
    item_count: int
    percentage_of_total: float
```

---

## Error Handling

All endpoints return structured error responses with appropriate HTTP status codes:

| Status | Meaning | Example |
|--------|---------|---------|
| `200` | Success | Query executed, results returned |
| `400` | Bad Request | Invalid filter parameter, malformed query |
| `404` | Not Found | Budget line item ID does not exist |
| `422` | Validation Error | Required parameter missing or type mismatch |
| `429` | Too Many Requests | Rate limiting (if implemented) |
| `500` | Internal Server Error | Database connection failure |

**Error Response Format:**

```json
{
  "success": false,
  "error": {
    "code": "INVALID_FISCAL_YEAR",
    "message": "Fiscal year must be between 2015 and 2030",
    "details": {
      "provided": "9999",
      "valid_range": "2015-2030"
    }
  }
}
```

---

## Authentication & Rate Limiting

- **Current Phase:** No authentication required (internal use, open government data)
- **Future Phases:** Consider API key authentication if public access needs rate limiting

---

## Implementation Notes

1. All endpoints support CORS (Cross-Origin Resource Sharing) for browser-based access
2. Pagination defaults to 20 items/page, maximum 500 items/page
3. Large exports (>100k rows) should use streaming to avoid memory issues
4. Database queries should timeout after 30 seconds
5. Response times should be cached where appropriate (reference data endpoints especially)
