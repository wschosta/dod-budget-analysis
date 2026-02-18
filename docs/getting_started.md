# Getting Started with DoD Budget Explorer

This guide is written for Congressional staffers, journalists, researchers, and anyone
who wants to explore Department of Defense budget data without needing a background in
defense finance. No prior experience with government budget documents is required.

---

## What is DoD Budget Explorer?

DoD Budget Explorer is a searchable, publicly accessible database of Department of Defense
budget justification documents. It aggregates budget line items submitted by the military
services and defense agencies to Congress and makes them queryable in a single interface.

Every year, the President submits a budget request to Congress. The Department of Defense
publishes detailed supporting documents — called budget justification exhibits — that
explain exactly what they are asking to fund and why. These documents are public, but
they are spread across multiple military service websites, published in dozens of PDFs
and Excel spreadsheets, and use specialized terminology that can be difficult to navigate.

DoD Budget Explorer collects all of those documents, parses them into structured data,
and presents them in a searchable table with plain-language labels.

---

## Data Included

### Fiscal Years

The database covers multiple fiscal years of President's Budget submissions. The U.S.
government fiscal year runs from October 1 through September 30. For example, Fiscal Year
2026 (FY2026) began on October 1, 2025.

Data availability varies by year and service. Not every exhibit type is available for
every year. See the [FAQ](faq.md) for more information on coverage gaps.

### Military Services and Agencies

The database includes budget data from the following components:

- **Department of the Army** — includes Army-specific procurement, R&D, operations, and personnel budgets
- **Department of the Navy** — covers both the Navy and Marine Corps budgets
- **Department of the Air Force** — includes Air Force and, separately, Space Force budgets
- **Marine Corps** — sometimes reported as a subset of Navy, sometimes standalone
- **Space Force** — stood up as a separate service in December 2019; data available from FY2021 onward
- **Defense-Wide** — covers defense agencies, joint programs, and activities that serve all services (e.g., DARPA, DIA, MDA)

### Exhibit Types

DoD budget justification documents are organized into standardized "exhibit" types.
Each exhibit type covers a different appropriation category:

| Exhibit | Appropriation Category | What It Covers |
|---------|------------------------|----------------|
| **P-1** | Procurement (summary) | Top-level procurement line items by account |
| **P-5** | Procurement (detail) | Cost and quantity breakdowns for procurement programs |
| **R-1** | RDT&E (summary) | Research, Development, Test & Evaluation summary |
| **R-2** | RDT&E (detail) | Program-level descriptions and justifications for R&D |
| **O-1** | Operation & Maintenance | Operating costs, readiness, training |
| **M-1** | Military Personnel | Pay, allowances, and end-strength |
| **C-1** | Construction | Military construction projects |
| **RF-1** | Revolving Fund | Working capital and revolving fund accounts |

---

## How to Search

The search bar on the main page performs full-text search across all budget line items
and parsed document text. You can search for:

- **Program names** — for example, `F-35`, `Stryker`, `HIMARS`, `Littoral Combat Ship`
- **Topics** — for example, `cybersecurity`, `artificial intelligence`, `hypersonics`
- **Appropriation accounts** — for example, `Aircraft Procurement`, `Missile Procurement`
- **Program Element numbers** — for example, `0604229F` (see the FAQ for an explanation of PE numbers)
- **Contractor names or technologies** — if mentioned in the document text

Search results are ranked by relevance. Each result shows the program name, service,
fiscal year, appropriation account, and the dollar amount requested.

**Tips for better searches:**

- Use specific terms rather than broad ones — `M109 howitzer` will return more targeted
  results than just `artillery`
- If your search returns no results, try removing qualifiers or checking for alternate
  spellings (e.g., `F-15EX` vs. `F15EX`)
- PE numbers are exact — search the full number including the trailing letter if known

---

## How to Filter

After running a search (or viewing all results), the filter sidebar on the left lets you
narrow results without re-typing a query. Available filters include:

### Fiscal Year
Check one or more fiscal years to limit results to those budget cycles. This is useful
when you want to compare the same program across multiple years.

### Service
Check one or more services to see only their budget requests. For example, checking
only "Air Force" and "Space Force" will hide Army, Navy, and Defense-Wide entries.

### Exhibit Type
Filter to a specific exhibit type. For example, selecting only `R-2` will show you
program-level research and development justifications and hide procurement line items.

### Amount Range
Enter a minimum and/or maximum dollar amount (in thousands of dollars — see the section
below on reading amounts). For example, entering `1000000` as a minimum will show only
programs requesting $1 billion or more.

After setting filters, click **Apply Filters**. To reset, click **Clear All**.

---

## How to Download

You can download the results of any search or filter in two formats:

- **CSV** — compatible with Excel, Google Sheets, and any data analysis tool
- **JSON** — structured data suitable for pipelines, scripts, or further processing

To download:

1. Run a search or apply filters to the results you want.
2. Click the **Download Results** button below the results table.
3. Select your preferred format (CSV or JSON).
4. The file will download immediately with your current filters applied.

The downloaded file includes all fields visible in the table plus additional metadata
fields (such as source file name and appropriation code) that are not shown by default
in the interface.

There is no row limit on downloads, but very large result sets (tens of thousands of
rows) may take a moment to generate.

---

## How to Read the Data

### Dollar Amounts Are in Thousands

**All dollar amounts in this database are in thousands of dollars ($K).** This is the
standard used in DoD budget documents themselves and is preserved here to match source
data exactly.

To convert to familiar dollar figures:

| What you see | Actual amount |
|---|---|
| `1,000` | $1 million |
| `10,000` | $10 million |
| `100,000` | $100 million |
| `1,000,000` | $1 billion |
| `10,000,000` | $10 billion |

**Example:** A line item showing `amount_thousands: 450,000` means a request for
$450 million — not $450 thousand.

### PB = President's Budget

**PB** stands for President's Budget. This is the formal budget request that the
President submits to Congress, typically in early February each year. The figures
labeled as PB or "budget estimate" reflect what the executive branch asked for.

Congress then reviews the request, holds hearings, and passes its own funding levels,
which may differ significantly from the request.

### Enacted vs. Request Amounts

Many line items include multiple dollar columns:

- **Request (or Budget Estimate):** The amount the President asked Congress to appropriate.
  This is what you see in the PB documents.
- **Enacted (or Appropriated):** The amount Congress actually approved, as signed into law.
  This may be higher or lower than the request, or may reflect a continuing resolution.
- **Prior Year Enacted:** The enacted amount from the previous fiscal year, shown for
  comparison purposes.

When the database shows only one amount column, it is generally the President's Budget
request figure from the source exhibit.

### Continuing Resolutions (CR)

If Congress does not pass a full appropriations bill before the start of the fiscal year
(October 1), the government operates under a **Continuing Resolution (CR)**. CR funding
is typically set at the prior year's enacted level (sometimes with a slight reduction)
and does not reflect the new year's President's Budget request. Some line items in the
database may note CR amounts separately.

### A Note on Totals

Service and program totals in this database are computed from the parsed line items
and may not match officially published totals exactly. Rounding, coverage gaps, and
parsing limitations can cause small discrepancies. See the [Methodology](methodology.md)
and [FAQ](faq.md) for more detail.

---

## Getting Help

If you encounter data that looks wrong, a program that appears to be missing, or an
amount that does not match a source document, please report it. See the
[FAQ](faq.md) for instructions on how to report errors.
