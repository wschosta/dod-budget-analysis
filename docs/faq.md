# Frequently Asked Questions

---

## How current is the data?

The database is updated when new President's Budget submissions are published by the
Department of Defense, which typically occurs in early February each year. The most
recent fiscal year available reflects the latest PB submission that has been downloaded,
parsed, and loaded into the database.

Data for a newly released budget year may lag the official release date by days or weeks
depending on how quickly the automated parsing pipeline processes new documents. The
source documents themselves are published by the DoD Comptroller and individual military
service budget offices.

---

## Why are some years missing?

Coverage varies for several reasons:

- **Format changes:** DoD periodically changes the format of budget exhibits (switching
  from PDF to Excel, restructuring columns, or renaming fields). When the format changes,
  the parser may not extract data correctly until it is updated.
- **Availability:** Not all historical documents are posted on current service websites.
  Older documents may have been removed or archived in ways that automated collection
  cannot reach.
- **Parsing failures:** Some documents — particularly older PDFs — could not be parsed
  reliably enough to include in the database. See the [Methodology](methodology.md) for
  more on parsing accuracy.
- **Coverage scope:** The project began with recent fiscal years and is expanding backward
  over time. Some earlier years may not yet be included.

If a specific fiscal year or service you need is missing, check the
[Methodology](methodology.md) for known gaps, or report it as a data gap.

---

## What does "$K" mean?

**$K means thousands of dollars.** All dollar amounts in DoD budget exhibits are
denominated in thousands, and this database preserves that convention.

So a figure of `$1,200,000` in the database means $1.2 billion (1,200,000 × $1,000),
not $1.2 million. A figure of `$450,000` means $450 million.

This is standard practice across all DoD budget documents and is not an error. When
reading or citing specific amounts, always multiply the displayed figure by 1,000 to
get the actual dollar value.

---

## What's the difference between PB, enacted, and CR amounts?

- **PB (President's Budget):** The formal budget request submitted by the President to
  Congress, usually in February. This is what the executive branch is asking to receive.
  PB figures represent intent and priorities, but Congress is not required to approve them.

- **Enacted:** The amount Congress actually appropriated, as signed into law through
  an appropriations act. Enacted figures may be higher or lower than the PB request,
  and Congress sometimes funds programs the executive did not request, or cuts programs
  the executive prioritized.

- **CR (Continuing Resolution):** When Congress does not pass full-year appropriations
  by October 1, it passes a CR that temporarily funds the government, usually at the
  prior year's rate. CR figures are not the same as PB or enacted figures and do not
  reflect new program requests.

Most documents in this database represent PB submissions. Enacted amounts, where
available, are noted in separate columns and sourced from enacted appropriations exhibits.

---

## Why don't service totals add up?

There are several legitimate reasons why totals you compute from this database may not
match figures published by DoD:

1. **Coverage gaps:** Not every line item from every exhibit has been successfully
   parsed and loaded. Missing rows will cause totals to be lower than official figures.
2. **Rounding:** Exhibit documents sometimes round individual line items in ways that
   do not sum exactly to their own reported totals.
3. **Double-counting risk:** Some programs appear in both summary exhibits (e.g., P-1)
   and detail exhibits (e.g., P-5), representing the same funding. Summing across
   exhibit types without filtering can double-count amounts.
4. **Parsing errors:** Automated parsing of PDF and Excel files occasionally misreads
   values, particularly for complex multi-column layouts or merged cells.
5. **Scope differences:** DoD's published topline figures sometimes include items not
   broken out at the line-item level in justification exhibits (e.g., classified programs,
   legislative rescissions, or adjustments).

For authoritative totals, always refer to the official DoD Comptroller published documents.

---

## How do I cite this data?

When citing specific budget figures for reporting or research, we recommend citing both
this database and the underlying source document. Example citation format:

> [Program Name], [Service], FY[Year] President's Budget, [Exhibit Type],
> [Amount] (in thousands). Source document: [source_file field]. Data via
> DoD Budget Explorer, accessed [date].

The `source_file` field on each record identifies the original document filename.
The source documents themselves are public records published by the Department of Defense
and available on the DoD Comptroller website (comptroller.defense.gov) and individual
service budget office websites.

For journalistic use, confirm key figures against the primary source document before
publication.

---

## What are PE numbers?

**PE stands for Program Element.** A program element number is a standardized identifier
used across DoD budget documents to track a specific research, development, or acquisition
program across fiscal years and exhibit types.

PE numbers are typically 7 digits followed by a letter that identifies the component:

| Suffix | Component |
|--------|-----------|
| `A` | Army |
| `N` | Navy / Marine Corps |
| `F` | Air Force / Space Force |
| `D` | Defense-Wide |
| `E` | Defense Agencies (some) |

**Example:** PE `0604229F` is the F-35 Lightning II program element for the Air Force.

PE numbers are useful for tracking a single program across multiple years or across
different exhibit types (e.g., finding both the R-2 research justification and the P-5
procurement detail for the same program).

---

## What is an exhibit type (R-2, P-5, etc.)?

Exhibit types are the standardized form numbers used in DoD budget justification
documents. Each type corresponds to a different appropriation category and level of detail:

| Exhibit | Full Name | What It Contains |
|---------|-----------|------------------|
| **P-1** | Procurement Summary | Summary-level list of all procurement line items |
| **P-5** | Procurement Detail | Cost and quantity breakdowns, unit costs, production quantities |
| **R-1** | RDT&E Summary | Summary list of all research and development programs |
| **R-2** | RDT&E Program Detail | Narrative descriptions, technical goals, and funding profiles for individual R&D programs |
| **O-1** | Operation & Maintenance Summary | O&M budget by activity group |
| **M-1** | Military Personnel | Military pay, allowances, and authorized end-strength |
| **C-1** | Military Construction | Individual construction projects with location and cost |
| **RF-1** | Revolving Fund | Working capital fund activity |

The exhibit type determines what fields are available for a given record. Procurement
exhibits (P-1, P-5) include quantity and unit cost fields. RDT&E exhibits (R-1, R-2)
include technology readiness levels and development phase information where available.

---

## How do I report errors?

If you find data that appears incorrect — a wrong amount, a mislabeled service, a
program attributed to the wrong fiscal year, or a line item that is clearly garbled —
please report it.

**To report an error:**

1. Note the record ID (the `id` field shown in the detail view, e.g., `bl_12345`)
2. Note the specific field that appears wrong and what the correct value should be
3. If possible, identify the source document page or row where the correct value appears
4. Submit a report via the project's GitHub issue tracker

Including the source document reference makes it much easier to diagnose whether the
error is a parsing bug, a data entry issue in the original document, or a known
limitation of automated extraction.

See also the [Methodology](methodology.md) document for a description of known parsing
limitations that may explain some apparent errors.
