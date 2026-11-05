# Chopper chat and spreadsheet workspace

Updated on 5 November 2026. The AI Assist Chat page now uses one window layout
for an empty conversation, attached spreadsheets, engineering questions and reports.
This fixes the conflicting welcome/report grids that confined the chat to a narrow
column while leaving the remainder of the workspace empty.

## Interaction

- Attach or drop XLSX, XLS, CSV, reports and existing supported engineering files.
  Spreadsheets support up to 20 MB, 50,000 rows and one million cells per selected
  worksheet, with up to 256 columns. Reading limits produce an explicit error.
- Workbook and sheet selectors appear in the window title bar. A header-row control
  supports rows 1–100, or 0 for data without a header. Recognised mill-report headers
  reuse the report parser's exact row; ambiguous generic headers remain user selected.
- **Chat**, **Split view** and **Results** use the full available width. Engineering
  tools remain available through the title-bar tools button.
- **Dataset Prompts**, **Overview**, **Outliers & Risk**, **Comparisons** and
  **Recommendations** provide common analytical prompts. Prompt buttons prefill the
  composer; sending them calculates from the currently selected saved worksheet.
- Choose group, measure, aggregation and order, then switch instantly between
  **Bar**, **Line**, **Donut** and **Pivot**. Charts have tooltips and source-row
  inspection; pivots can use a separate column dimension. The task tabs support
  arrow keys, Home and End.
- Minimise into a compact dock, expand to the full viewport, restore, or pop out
  into a separate browser window. Conversation, attachments and worksheet choices
  are shared with that window. Closing the pop-out restores the workspace. A blocked
  pop-up produces a visible message. The parent application must remain open.
- Download the selected worksheet as CSV or XLSX, download analysis JSON with its
  source references, or retrieve the unchanged original workbook, including XLS.

The charts are native application components. This change does not connect to or
embed external Tableau or Power BI services.

## Data consistency

Generic worksheet statistics and known mill-report calculations remain distinct.
The optional **Mill report analytics** view retains the existing production,
stoppage, utilization and quality analysis, date/machine controls and exports.
Raw worksheet analysis includes nonempty rows after the chosen header, including
totals/subtotals. Its report-view notice directs users to the report-specific
analysis when those exclusions and engineering units are required.

Generic calculations never execute spreadsheet formulas, macros or uploaded code.
Missing cached formula results remain errors; blanks remain missing; rows are not
silently deduplicated. Numeric interpretation excludes dates, booleans, leading-zero
identifiers, ambiguous locale formats, nonfinite values and integers outside safe
chart precision. Source previews and original downloads retain their actual values.
IQR candidates are statistical review items; no approved limit, defect, cause or
engineering risk classification is invented. Donut charts refuse negative shares.

Changing worksheet or calculation hides results from the previous selection until
the matching response arrives. Chart inspection retrieves actual matching rows,
including rows outside the initial 100-row preview. Large group and pivot previews
state their limits; full worksheet downloads retain all nonempty source rows.

Calculations, prompt summaries and suggested data checks use deterministic source
records, not model-authored numbers. Unrecognised dataset questions ask the user to
select supported controls or prompts. Existing PLC log decoding, Sheet2 checks,
project investigation and model publication boundaries remain in place.

The authenticated `/api/assist/datasets` API provides `uploads`, `analyze`, `rows`,
`{id}/source`, and `export/{csv|xlsx|json}`. It reuses immutable account-owned source
snapshots. Other accounts cannot use a source ID, and changed sources block analysis
and downloads. CSV/XLSX exports escape formula-like text without executing it.

Artifacts and verification logs are under `.build/chat-studio-20261105/`.

## Verification

- Main TypeScript/production build, DataInspect production build and standalone
  MatchView report build passed. The unchanged Virtual PLC build remains present.
- Forty targeted Python tests passed for worksheet calculations, file ownership,
  source changes, safe downloads, attachments, existing prompts, required Sheet2
  mappings and document comparison. Nine existing TypeScript decoder tests passed.
- Thirteen browser scenarios passed for real XLSX, BIFF8 XLS and CSV upload,
  drag/drop, workbook/sheet switching, deterministic prompt answers, all four
  result views, source rows, downloads, dock/full-screen/pop-out and the existing
  mill-report view. Layout checks covered 320, 390, 800, 1024 and 1600 pixel widths
  and both themes, with no browser page errors.
- Five additional browser scenarios passed for missing Sheet2 tag 653, unchanged
  source on rejected metadata save, chat metadata rejection, chat decoder CSVs and
  DataInspect offline decoding/export. Existing metadata validation was retained.
- Checked the supplied Comber XLS and Production Report XLSX without modifying
  them. The report's exact header row 10 and specialised report analytics remained
  available alongside raw worksheet exploration.
- Restarted the local installation on port 8200 at UI/API version 4.99.3. Main,
  DataInspect, report and Virtual PLC assets returned HTTP 200; the new dataset
  routes rejected anonymous access. The 53 projects and 34 accounts were retained.
  The model was idle with its existing 8192-token context after restart.

These are targeted regression checks for this change, not a claim that every
application function or external service was tested.
