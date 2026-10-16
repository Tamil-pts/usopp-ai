# DataInspect personal dashboards and automatic units

## Create your dashboard

1. Open DataInspect and select the PLC and matching metadata.
2. Open **My dashboard**, choose **Live data** or **Report data** in
   **My dashboards**, then **Add widget**. You can also choose an Excel layout
   from **Prepared dashboards** and click **Open layout**.
3. Choose **Direct PLC value** or **Calculated formula**.
4. Select each numeric source by its Group Code, Tag Code and parameter name.
   Give formula inputs short aliases such as `hours` and `minutes`.
5. Enter the display unit and formula, for example `hours * 60 + minutes`.
6. Choose a validation condition: display only, numeric limits, or comparison
   with another PLC parameter using an absolute tolerance.
7. Choose value cards, dial gauges, progress bars, line, area, column, pie,
   doughnut, scatter, heat map or readings table widgets. Set width, minimum
   height and display range where relevant.
8. **Add parameter** adds another named value or formula within the same widget,
   with its own target, inputs, display unit, precision and validation condition.
   Choose **Parameter to configure** to edit each one; up to 12 are supported.
   Charts sharing one scale require matching display units. Scatter charts have
   separate X/Y scales; the first parameter supplies X. Tables support mixed units.
9. Read the required groups through **Packet checks**, decode a complete response
   through **Manual received data**, or enable collection in **Manage targets**.

Every account has its own named dashboards. Create up to 20 dashboards with up
to 32 widgets each. Each value binds to one target and its metadata; formulas
use that target's inputs. Different targets can appear on the same dashboard.
The single **Department** filter uses the configured machine category, such as
Finisher or Carding. Machine type and department are the same classification.
**Target** identifies a specific PLC connection within that department.
Select 1–4 columns. **Arrange** enables drag handles and keyboard move buttons.
Use the widget's bottom-right resize handle in Arrange mode to adjust its width
and minimum height, or set them numerically in the editor. Width snaps to the
dashboard's 1–4 columns; height ranges from 180–1000 pixels. Arrow left/right
changes width and arrow up/down changes height when the handle has keyboard focus.
Source expansion and intrinsic chart content can increase a widget's height.
Widget widths collapse on smaller screens. **Edit dashboard** renames, duplicates
or removes a layout and switches its Live/Report mode. The plus button beside
**My dashboards** creates a new display.

Dashboard selection, department, columns and arranging share one compact control
panel above the widgets. **Report period / Trend period**, **Layouts**, **Results**
and the help icon open their options in that panel. Only one options panel opens
at a time; Escape or clicking outside closes it. Layout import/export and saving
to knowledge are under **Layouts**. Result export format and download are under
**Results**. Returning to My dashboard restores the last opened saved display
for your account, including after an interface reload.

Multi-parameter widgets show the configured parameter names and values / legends.
Widgets normally show their display name and value. **View source** reveals the
machine, formula, GC/Tag identities, capture times and validation condition.
Missing, stale or invalid inputs never become a zero or implicit pass.
Export/import layouts to transfer them; review machine bindings afterward.
Export results retains formulas, input identities, times and outcomes in JSON.
Existing single-dashboard layouts are migrated as a separate named dashboard
when their matching target/metadata is opened; the old saved copy is retained.

### Live collection and optional storage

Open **Manage targets**. Each target has **Enable live collection** and
**Store readings for trends and reports**, both off by default. Select the
group codes explicitly (GC 11 is sent automatically to close a cycle), a
5–3600 second interval, and 1–30 days retention, then **Save & Apply**.
The next cycle starts after the previous one finishes plus this interval.
The server keeps collecting after the browser closes and resumes enabled
targets on startup. Disabling collection prevents further cycles; an exchange
already sent can finish, but its result is not saved after configuration changes.
Use a personal account; demonstration accounts cannot enable collection.

Up to 16 targets per account are configurable, with at most 8 collection cycles
running across the server at once. The same physical endpoint is serialized with
manual packet requests; another machine can be tested while collection continues.
Each cycle uses the existing read/GC 11 protocol, never PLC writes. Select only
the groups needed for your display. Live timeouts are limited to 30 seconds per
exchange; long cycles stop requesting further groups after a 60-second budget.

Without storage, only the latest server sample remains in memory. With storage,
compressed samples and their exact metadata snapshot are saved to the application's
SQLite store under its persistent data root. Expired samples disappear from
reports immediately and are purged at least once a minute. Retention never
exceeds 30 days; reducing retention applies to existing samples too. Stopping
storage does not erase already retained samples before their expiry.

Live charts keep up to 300 recent points in browser memory (up to one hour) while
the dashboard is open, even without server storage. Those points disappear on
reload or dashboard switch. Live charts extend the loaded stored period with
new captures; Report mode uses only its selected stored period. Stored report
data remains separate. Charts break at
invalid inputs. Tables and scatter plots pair different captures only within the
configured input time gap; missing readings stay unavailable.

Manual received data appears in Live dashboards for the selected machine.
It remains available across machine switches while the DataInspect workspace
stays open. It does not automatically enter the live collector's history; the
existing manual test history remains separate. View source identifies manual
captures. Synthetic virtual PLC targets and Automation Studio simulation are
identified by their target mode in source details. See **DATA_SIMULATOR.md**.

### Reports and trends

Choose a report dashboard, open **Report period** and select a past period of up
to 30 days. Values show the
last sample in that period. Trend/table widgets can also display stored history
on a Live dashboard through **Trend period**. **Load report / Load trend period** or **Last 24 hours**
refreshes that history; live values refresh automatically.

Reports return at most 300 representative captures per machine (fewer for large
metadata), selected across the whole range. Sampling is identified in the UI;
charts are not totals or complete event logs. Invalid captures break trend lines.
No stored data produces an empty report. Historical formulas use the metadata
stored with each sample and do not change the original test verdicts.

### Formula examples

| Purpose | Input aliases | Formula | Output unit |
| --- | --- | --- | --- |
| Total minutes | `hours`, `minutes` | `hours * 60 + minutes` | Mins |
| Total seconds | `minutes`, `seconds` | `minutes * 60 + seconds` | Sec |
| Run share | `run`, `idle` | `100 * run / (run + idle)` | % |

Both sides of comparisons must use compatible units. Inputs use decoded PLC
numbers; express scaling and unit conversions in the formula. Display rounding
does not alter the numbers used by comparisons.

The formula language supports numbers, input aliases, arithmetic operators
`+ - * / % ^`, parentheses and `min`, `max`, `abs`, `round`, `floor`, `ceil`,
`sqrt`, plus numeric comparisons `gt`, `gte`, `lt`, `lte`, `eq` and `neq` (0 or 1). A constant formula needs no PLC inputs and is labeled Configured constant. It does not execute JavaScript or arbitrary instructions from a reference.

### Read the result

- **Value available:** a value was calculated, with no validation condition.
- **Pass / Outside configured condition:** comparison against the condition
  you explicitly configured, using valid captured inputs.
- **Waiting for valid inputs:** missing or invalid responses, stale inputs,
  different capture sources, or captures outside the configured time gap.
- **Calculation error:** division by zero or another nonfinite calculation.

Source details identify PLC, manual offline or saved captures. Sample-number
previews are separate from PLC validation. Controller requests start only after
explicit collection enablement or a packet-test action. Saved captures use your
current dashboard formulas and do not change the original test verdicts.

Data model formulas in the packet table are reference definitions. Configure
their source inputs in My dashboard before validating their numeric results.

## Configure automatic metadata units

Open **AI Assistant → KnowHub → Automatic units**. Admin can add, edit, disable,
reorder and preview shared unit rules. Other users can view the configuration.

Defaults map the whole words `minute` / `minutes` to `Mins` and `second` /
`seconds` to `Sec`. Matching ignores capitalization and recognizes separated
words in underscore and camel-case parameter names. Choose whole word/phrase,
contains text, or entire parameter name matching.

Department-specific rules take priority over All; within a scope, the first
enabled matching row wins. Existing explicit units in Parameter mappings take
priority. Disable the feature or add more specific rules when a name has a
different meaning in your project.

Save the rules and **generate a new metadata workbook**. Existing selected
workbooks are not modified. Only empty units are filled; this does not convert
PLC values or change offsets, datatypes, scale factors, HMI limits or Sheet2.
Generated JSON records identify the unit rule and its configuration revision.

The rules are included in Admin knowledge export/import for production transfer.

## Excel starters and reusable layouts

All 124 prepared sheet layouts are available directly in
**DataInspect → My dashboard → Prepared dashboards**, grouped by PMS/QMS/CMS
and department. The Department filter narrows both widgets and prepared layouts.
Choose a sheet and **Open layout** to create an editable personal copy using a
target in that department. With multiple targets, choose the target beside the
layout. Reopening the same layout for that target returns to an existing saved
copy, preserving edits. Departments without a configured target remain browsable;
add a matching target before using their layouts. Opening a layout does not
enable collection or storage.

For batch creation, open **Layout library → Excel starters**.
Choose PMS, QMS or CMS, select a department, then select the workbook sheets you
want. LIVE, shift, doff, hourly and minute sheets remain separate dashboards.
The preview lists exact metadata matches and fields needing configuration.
Create the selected dashboards, then use **Arrange** or **View source → Edit
widget** to change names, sources, formulas, size and presentation.

The knowledge folder contains 124 sheet templates from the 22 key definition
workbooks, under `knowledge/dashboard_layouts/{service}/{department}/`.
Every named non-server row is retained in each template's `parameters`, with its
workbook, sheet and row. Text/date fields and unnamed/server rows are listed in
the audit instead of being passed to numeric widgets. Original source workbooks
are retained under `knowledge/data_models/reference_sources/`. The extra CMS
threshold workbook and RingFrame frozen database key workbook have no PLC
datatype/Group Code schema and remain source references.

Starters bind unique numeric names and configured aliases within their Group
Codes. Letter case and configured space/underscore formatting are accepted.
Named workbook formulas are linked to concrete equations in the matching
service, department and reporting period of the supplied JSON. Database keys
resolve nested equations, with Mongo output keys distinguished from raw
TDEngine input keys. Original JSON definitions take priority over workbook
supplements. Actual input wire types come from machine metadata; FLOAT/REAL
output types can use integer PLC sources. Explicit wire requirements stay
strict. Missing machine inputs, ambiguous definitions and textual instructions
are reported for configuration; they are never replaced with fabricated data.
Report dashboards
show stored sample values and trends; they do not build shift aggregates or doff
event records automatically.

**Export layout** downloads the current dashboard or all your dashboards as JSON.
**Import layout** adds copies and optionally binds all widgets to one target;
unmatched identities remain pending. **Save to knowledge** writes a named JSON
copy under `knowledge/dashboard_layouts/users/{account-hash}/`. These copies
contain layouts and source identities, without captured readings or connection
settings. They remain private to the account in the application. Shared Admin
knowledge transfer includes workbook starters and excludes personal layout
copies; use layout export/import to transfer your own copies.

**Export results** exports the widgets currently in view as Excel or JSON. Excel
contains Results, Trend samples, Input evidence and Report context sheets.
Exports include all configured series, timestamps, units, current formula
results and pending/failure explanations. Stored trends are representative
samples (up to 300 per machine), not complete event logs or calculated totals.

## Workbook coverage in the data model knowledge

The knowledge builder supplements older database JSON with omitted Excel
requirements. Existing JSON keys and conflicting definitions are retained.
`knowledge/data_models/workbook_coverage.json` records every added requirement;
fixed JSON files in PMS/QMS/CMS and `catalog.json` include the supplement.
All 5,487 named rows in the 22 key definition workbooks are represented by a
name, Group Code and field-kind requirement. Repeated requirements across
worksheets share a check; their source workbook evidence remains available.
Letter case is accepted. Different names and PLC datatypes are reported
separately, including simultaneous name and datatype differences.

Rebuild development knowledge with:

```powershell
.\.venv\Scripts\python.exe scripts/build_data_model_knowledge.py --source knowledge/data_models/reference_sources
.\.venv\Scripts\python.exe scripts/build_dashboard_layouts.py
```

## Review formulas and reference mappings during validation

Open **DataInspect → Data model requirements → Review and edit reference
configuration**. Admin can edit the shared JSON, including scoped parameter
names, numeric database value types and explicit `plcDataType` requirements.
Changes are saved with a revision check in
`knowledge/master/data_model_rules.json`. Other users can view the configuration.
Reference checks refresh after saving. Create a fresh starter copy to apply new
formula definitions; existing widgets retain their personal configuration.

`formulaOverrides` accepts service, machine, view, parameter and expression.
Use database keys from that department/sheet, or a constant for a configured
target. Widget formulas can also be edited individually using their input
aliases. The Finisher and Carding equations are kept separate; a formula is not
substituted merely because its display name resembles another department's KPI.

Data model results distinguish **Mapped numeric value** from strict wire-type
requirements. This mapping checks numeric compatibility, not independent
verification of a PLC declaration. Payload decoding, offsets and widths continue
to use the selected machine metadata. QMS CV/U formatting aliases are explicit
and scoped; they do not infer missing A%, spectrogram or unrelated sensor fields.

A consistent numeric Excel definition can clarify an older JSON datatype error,
such as TIMESTAMP on production weight. Corrections and both source locations
are recorded in `knowledge/data_models/reference_corrections.json`; original
archived sources remain unchanged. Exports include reference value types, actual
PLC input types and the equation source. No default acceptance limits are added.
