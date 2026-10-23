# Chopper mill report analysis

## Prompt-based comparisons (4.70.0)

Type your own report question. The comparison is built from the attached column
catalog rather than a selected example prompt. Recognized column names resolve
directly; unfamiliar wording uses the configured model to propose a structured
plan. The server validates sources, fields, operations, filters and requested
column coverage, then calculates from the owned worksheet rows. Model-generated
numbers or executable code are never used as report results.

Examples:

- Compare RF 01 and RF 02 total production, average spindle RPM and delivery speed.
- Which machine has the highest total production? Which has the lowest average delivery speed?
- Compare RF 12 production from 2026-10-11 to 2026-10-15 versus 2026-10-16 to 2026-10-20.
- Compare production and energy consumption by machine.
- Which machines used the most electricity? Show the top 3 with their output.
- Show machine-wise median spindle speed, filtered to a named lot.

Each measure has its own total/mean/min/max/median/standard-deviation/count
operation. Filters can select original records or calculated group values.
Comparisons can group by available identity columns. Differences and percent
changes preserve units and identify the baseline. Report families are aggregated
before alignment, avoiding multiplication of detail rows. Cross-report derived
ratios/differences require matching machine/date/shift coverage and complete
paired values; subtraction also requires compatible units.

The current plan is carried with dashboard filters and downloads, validated
again on the server, and recalculated from records. No model generation is
repeated for a filter/export using that plan. Expand **Measures and filters used**
to inspect the interpretation. Changing attached column schemas invalidates a
saved plan; ask the question again. Dates outside uploaded coverage return no
matching values. Missing fields and unsupported calculations need clarification.

Bounds: six related queries per message, twelve measures per query, four grouping
columns, four compared date periods, and 500 displayed groups. The optional model
uses its configured context and a 120-second interpretation budget. A missing,
busy or unavailable model leaves exact-column requests available and reports
that other wording could not be interpreted. These limits do not imply that
every possible natural-language request or statistical method is supported.

## Production scope and multiple fields (4.69.2)

Production is the default dashboard report type when production data is attached.
Use **Report data** to choose stoppage, quality, breakage, air, power, or all
attached report types. A specific question selects the families containing its
requested columns. Date/machine/shift filters and exports retain that selection.
Unrelated KPI cards, navigation, charts, findings and download columns are omitted.

Questions such as "Show machine-wise lot names and average spindel speed" and
"Compare machine-wise average spindle speed and average delivery speed" return
all named measures. Common spindle/delivery spelling mistakes are normalized.
Lot/speed averages are grouped by machine and lot, preserving their relationship.
Each numeric chart keeps its own source units and scale. Records counts are not
selected as a replacement chart measure. Additional unsupported requests are
identified in a result note.

The optional local model can be checked in Settings / AI models using the model
connection check. A Ready indicator confirms loading; the connection check asks
the configured model to generate a short reply. Report arithmetic uses the full
uploaded records directly, so a model connection is optional for these operations.

## Question resolution (4.69.1)

Typed questions are matched to the actual report headers. Examples include
"Show machine-wise TPI and yarn count", "What are the lots run?", "Show mean
voltage and current by machine", and "List available report columns". TPI,
count and lot settings stay as distinct combinations unless an average is
explicitly requested. Lot lists include the first/last recorded dates.

An unsupported column request returns an explanation and available columns,
without substituting a default report metric or waiting for a language model.
Explicit PLC/application questions retain their engineering assistant route.
A new machine-wise/comparative machine request clears a prior single-machine
focus unless the new question names a machine or explicitly refers to that
selected machine. Date and shift filters remain visible.

The dashboard opens Your question after a specific report question. It shows
the matched tables and charts of those displayed values. Filters and PDF/CSV
exports preserve the current question. Executive summary and the existing
performance sections remain selectable. The chart uses at most 20 displayed
rows; the result tables show at most 500 grouped rows with a truncation note.

## Performance workspace (4.69.0)

Recognized uploads open Chat / Split / Dashboard views. Use the expand button
for a full workspace, and Escape to restore it. Attachments stay compact; PLC
project and model details can be expanded separately.

Dashboard sections include executive summary, daily production, utilization,
stoppages, sortable machine performance, top/bottom machines, KPI compliance,
quality/resources, findings and suggested actions. Clicking a chart date filters
that date; machine rows open their recorded values and follow-up questions.
All records resets filters. Date, shift and machine selections also apply to
subsequent chat questions. Latest 7 days uses the latest uploaded date.

Comparison defaults to the immediately preceding equally long calendar period.
Choose custom comparison dates in the comparison panel. Percent changes are
withheld unless both periods cover every selected day and have matching
machine/shift coverage. Means are unweighted record means; missing days do not
become zero and holidays are not inferred. Partial shifts and absent comparison
data are disclosed. Charts display at most 60 dates; full KPI calculations use
every selected record. The daily series is limited to the latest 366 dates.

Set your mill's KPI targets in the displayed units. No competitor limits are
installed automatically. Targets are saved in this browser for the signed-in
account. Daily compliance checks daily aggregates; machine flags check machine
aggregates. Idle/slip/rogue spindle columns contain counts per machine record,
which remain distinct from the number of machines outside a user target.
Waste kg is not converted into waste percent without a source percentage.

PDF exports include KPI comparisons, daily charts/tables, stoppage reasons,
machine performance, compliance, findings, suggested priorities and provenance.
Machine CSV and complete evidence JSON are also available. All exports reload
the authenticated owner's original report records and recalculate the result.
Suggested priorities and owner/due placeholders are planning aids; no external
maintenance ticket is created. Source text is escaped in PDF/CSV output.

If several tables of one report family are attached, the dashboard uses the
first table and names the alternatives in coverage notes. Remove the first
attachment to select a different source. Separate report-family machine sets
are not combined into fabricated quality/production correlations.

Attach XLSX, XLS or CSV report files in Chopper. Production, quality, stoppage,
breakage, air-consumption and power tables are recognized from their column
headers. A selected PLC project and an AI model are optional for these questions.

Examples:

- Which machine has the highest production kg for the entire report?
- Show today's production overview.
- Which machine has the highest stoppage duration and what are its reasons?
- Which machine has the most stoppage events?
- Show all reasons for that machine.
- Compare RF 01 and RF 02 on 2026-10-21, shift 1.
- Show the daily production trend.
- Rank quality by lowest mean CVM.
- Which machine has the highest energy per production kg?

## Calculation rules

- Read machine detail rows from the complete recognized tables. Exclude unit,
  group-heading, shift-summary, daily-summary and overall-summary rows.
- Sum production kg, energy kWh, air volume, break counts and durations.
  Report arithmetic means for measured percentages/rates. Reported rates such
  as CFM are not added across shifts. Do not infer quality acceptance thresholds.
- Keep Production and Actual Production separate. Calculate target achievement
  only when every selected record has a positive target.
- Aggregate energy intensity as total recorded kWh divided by total production
  kg, using records containing both values and disclosing missing pairs. Keep
  it distinct from the arithmetic mean of the source UKG column.
- Rank stoppages by duration by default. Event-count prompts count event rows.
  For the leading machine, show its own reason breakdown with counts and total
  duration. Recorded reason text is source evidence, not a verified physical
  diagnosis. Historical reports do not prove the current running/stopped state.
- Dates and shifts filter the records. Today's date comes from the browser's
  local calendar. Date/shift filters carry into follow-up questions; request
  the entire report to reset them.
- Compare the complete unfiltered detail total with an available overall
  summary. Display discrepancies explicitly and retain the detail calculation.

## Source and privacy

Each upload is stored in its owner's temporary workspace under an opaque
report ID. Answers reload those server-owned records rather than trusting a
browser-supplied numeric summary or a truncated text preview. Worksheet
evidence lists the source workbook, sheet, header row and selected cells.
Downloading the original workbook enforces the existing workspace access rules.
The user's temporary-cache action also clears their report attachments.

Workbook text is untrusted data. Neither macros nor formulas are executed.
Calculations use stored/cached Excel values; missing numeric cells are excluded
and reported. The source workbooks are not modified.

Bounds: 20 MB uploaded file; 60 MB expanded XLSX; 16 visible sheets;
100,000 rows per sheet; 128 columns; 2,000,000 cells per attachment. A reading
limit produces an explicit partial-coverage notice. An unrecognized spreadsheet
keeps the document preview route; existing PLC-metadata and log decoding remain
available. Reattach reports uploaded before this feature was installed.
