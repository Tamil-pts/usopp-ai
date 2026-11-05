# Document Compare — 3 November 2026

Open **AI Assist → Document Compare** in the top submenu, alongside Chat, Rule
configuration and KnowHub. The comparison workspace belongs to AI Assist and
does not require a WorkHub project. Document Management retains its existing
register, approved library and document workflows.

1. Upload the **Base** and **Compared** files. Supported formats are CSV, XLS,
   XLSX, PDF, Word DOCX and TXT, up to 25 MB per file. Legacy DOC files must be
   saved as DOCX first.
2. For spreadsheets, choose the worksheet and header row on each side. Header
   row 0 means no header. Select the column pairs to compare; different column
   names can be paired manually. Columns omitted from the selection do not
   create differences.
3. Choose row order, or select one or more mapped columns as a composite row key.
   Key mode matches reordered records. Blank or duplicate keys require a more
   complete selection; the engine does not guess which record was intended.
4. Compare the files. Inspect added, removed, modified, unchanged and Needs
   review results side by side, with original cell/page/paragraph references.
   Filter the result and download the selected view as an Excel-compatible CSV.
5. For CSV/XLS/XLSX results, choose **Detailed view** or **Table view** under
   **Result view**. Detailed view remains the default. Table view groups the
   selected columns under **File 1** and **File 2**, keeps matched rows aligned,
   and highlights individual changed cells. Choose **All** to include unchanged
   rows. Both layouts retain the active filter, row matching, paging and export
   selection. The view preference is saved separately for each account.
6. Optionally tick **Enable header filters**. Each selected column heading then
   has an Excel-style dropdown for value search, selection checkboxes and sorting.
   Apply a selection or clear that column's filter. Ascending/descending sorting
   keeps the two files' matched rows together. Enabling filters opens Table view;
   unticking the checkbox clears the column filters and sorting.

Table view uses one scroll area with sticky headers and a compact source-row
column. Full cell references and value types are available on hover. Missing
rows stay visibly absent on the appropriate side, and unavailable values remain
Needs review. Word and mixed-format text comparisons retain the text layout. For two PDFs,
the original-page review is described below.

Header filtering operates on the complete saved comparison, before paging.
Filters on File 1 and File 2 combine, and value lists respect the current
difference filter and other column selections. Blank cells and absent rows are
separate options. Search narrows the values list; Select all applies across all
pages. New comparisons clear existing column criteria. The summary cards remain
comparison totals, while pagination shows the matching row count. CSV export
includes the current filters, sort order and matching rows.

Spreadsheet comparison reads stored cell values. XLSX can also compare formula
text. Formulas and macros are never executed. Missing XLSX formula results are
marked Needs review. CSV values remain text; cell-type comparison is optional.
Leading zeroes remain significant. Letter case and repeated whitespace can be
ignored explicitly. Empty selected rows are omitted.

PDF, DOCX and TXT can be compared with one another as extracted text. Word table
rows retain their position between paragraphs. PDF references retain page
numbers. The Differences filter includes five surrounding text lines. This view
does not compare images, page geometry, typography or tracked-change history.
Scanned PDFs need an OCR/text copy; unreadable pages in a partially readable PDF
remain Needs review. Use e-design MatchView for visual electrical drawing review.

## Original PDF review ? 4 November 2026

When both uploads are PDFs, **Original PDF pages** opens paired source pages
with text changes highlighted in place. Choose a page pair, fit to width or
zoom, toggle highlights and use linked scrolling. The page panes can be resized
vertically. Click a highlight or a Before/After note to locate the change.
**Text differences** remains available with five surrounding text lines.

**Ignore printed page numbers** is on by default. Only complete counter labels
in the outer page margins are excluded, for example `1 / 181`, `Page 1 of 181`
or `Page 1`, checked against the actual page index/total. Bare numbers remain
compared. Routine names, program headers, timestamps, tags and PLC operands
remain evidence. Ignored labels and counts are retained with the result.

Text aligns across page boundaries. Page pairing uses shared text in source
order; an inserted page remains accessible without an invented counterpart.
Content may continue onto an adjacent page. The engine compares extracted text;
ladder connections, symbols drawn as graphics and program execution are outside
this comparison. Image-only pages in a partially readable PDF stay Needs review.

**PDF exports** provides an all-changes comparison PDF, highlighted Base and
Compared PDFs, and HTML change notes. The comparison PDF contains Before/After
notes followed by paired original pages with transparent highlights. Highlighted
originals retain their page counts and include annotation notes. CSV continues
to export the selected text filter. All exports include source references;
HTML/PDF reports retain source hashes. Owner checks and source-hash validation
also apply to previews, cached downloads and exports.

New PDF endpoints under `/results/{id}` are `GET /pdf-pairs/{pair_id}`,
`GET /pdf-pages/{base|compared}/{page}.png`, `GET /highlighted-{base|compared}.pdf`,
`GET /report.pdf`, and `GET /report.html`. They require the same signed-in owner.
No new dependencies were added.

Verification of the supplied `TSV9444.pdf` / `TSV9445.pdf` samples: 181 / 183
original pages, 364 ignored printed counters, 183 review pairs, 188 modified
text lines, 29 added, 1 removed and 3,653 unchanged. These totals include changed
project headers and timestamps; they are not counts of changed PLC functions.
Sources were unchanged after comparison and export. The highlighted originals
retain 181 / 183 pages; the comparison report contains 213 pages including notes.
Artifacts: `.build/document-pdf-20261104/`.

The update passed 30 focused comparison/API tests, nine integrated browser
checks, five responsive layouts (320?1,600 px), TypeScript checks and the main
production build. The local UI/API remains 4.99.3; startup, served assets and
unchanged account/project counts were checked after the supported restart.

Uploaded copies and results are private to the signed-in account under
`.usopp_workspaces/document-comparisons/`. Source SHA256 snapshots are checked
before publication and included in the export. The latest result is saved in
existing account settings. Switching Assist tabs retains the open workspace.
Source files, project assignments and controlled-document approvals are not
changed by running a comparison.

The API is under `/api/assist/document-comparisons`:

- `POST /uploads` accepts one multipart file.
- `GET /uploads/{id}/columns` returns columns and a bounded preview for the
  selected `sheet` and `header_row`.
- `POST /run` compares the selected sources and column pairs.
- `GET /results/{id}` provides filtered, paged results.
- `GET /results/{id}/export.csv` exports the selected result view.
- `POST /results/{id}/query` applies optional column filters and sorting before
  paging; `POST /results/{id}/values` searches/pages a header's available values.
- `POST /results/{id}/export.csv` exports the current column-filtered/sorted view.

Limits are explicit: 100 worksheets per workbook, columns A through IV, 50,000
rows and one million read cells per selected sheet, 300,000 compared cells per
result, and 250 PDF pages / 10,000 extracted text lines per file. Oversized
selections return an error rather than silently comparing a truncated document.

Verification includes 25 comparison/document/competency regression tests,
15 integrated browser checks and 12 desktop/mobile light/dark layout checks. All four
production interfaces built successfully. Actual XLSX and XLS uploads were
checked using the two supplied workbooks. Their worksheets were selectable;
`TAG_CODE + GROUP_CODE` correctly identified duplicate keys at Comber rows 878
and 879 and requested another key column. This is an ambiguity check, not an
approved mapping between those different workbook versions.

The local server was restarted with the supported launcher. Authenticated live
upload, column inspection, comparison and CSV export returned HTTP 200. UI/API
versions match at **4.99.3**. The live smoke-test files were removed; existing
53 projects and 34 accounts were retained. Artifacts are under
`.build/document-comparison-20261103/`.

The optional spreadsheet Table view passed 12 focused browser checks, including
the supplied XLSX/XLS files, layout switching without another comparison run,
selected columns, reordered/added/removed rows, filters/export, missing formula
results, paging beyond 100 rows, and account-specific preferences. Twelve
light/dark layouts covered 1600, 1067, 800, 760, 390 and 320 pixels. Main production
build and TypeScript checks passed. Artifacts:
`.build/document-table-view-20261103/`.

The optional header filters passed 32 comparison/document/competency regression
tests, 14 focused browser checks and 12 light/dark viewport checks. The table-view
regression also passed its 12 browser checks and 12 layouts. Checks covered value
search, selection beyond the first 100 rows, combined filters, numeric sorting,
Cancel/Escape, blank versus absent cells and filtered CSV export. TypeScript and
the main production build passed. After restarting the local server, the new
query, value-list and filtered-export APIs returned HTTP 200; UI/API versions
remain **4.99.3**. Temporary live smoke-test files were removed, with the existing
53 projects and 34 accounts retained. Artifacts:
`.build/document-header-filters-20261103/`.
