# Chopper answer workspace and local worksheet BI

Implemented in the current 4.99.3 checkout on 18 November 2026.

## One chat, evidence first

The main AI Assist navigation is Chat, Rule configuration, KnowHub, Document
Compare and Presentation Studio. Agent controls/evaluation, answer feedback and
reviewed training live inside KnowHub. Existing agent/training direct URLs still
open those controls inside KnowHub.

Project replies use one card with Summary, Flow, Sequence, I/O & axes, Alarms and
Sources. Empty tabs are omitted. The first available tab opens immediately; a
later summary preserves the user's selected tab. Advanced source analysis and
coverage remain available in an expandable Engineer section, including writer
traces, routines, timers, library limitations and the complete graph loader.

The backend publishes compact parsed source records before the optional checked
explanation. This is staged polling, not token-by-token model streaming. Progress
shows stages and elapsed time without a model remaining-time promise. Stop keeps
available findings and prevents late reply publication. It does not promise to
interrupt an already running model kernel; that call may finish in the background.
Stopped workers still count toward concurrency limits until they finish.

Operator / Simple hides source navigation, I/O details, code paths and citations
in the summary. Engineer / Detail retains evidence and raw source records. Neither
mode changes the evidence or validation verdict. Model-assisted text is labelled
inferred; unsupported broad machine-purpose claims remain withheld by the existing
engineering publication gate. An inference badge is not permission to invent one.

Mermaid is bundled locally and loaded only when Flow opens. It receives generated
state-transition descriptions, uses strict rendering and encodes labels. It does
not execute source-supplied scripts, Mermaid directives or click callbacks. The
application binds displayed nodes to authenticated, read-only source inspection.
The view provides zoom (20%-300%), pan, fit, PNG/SVG downloads and Mermaid copy.
Views are bounded to 25 nodes, with branch expansion/paging and an explicit notice
when connections outside the current branch are omitted. Green/solid means a
configured active task assignment, never live motor state. Grey/dashed means a
non-active or unresolved assignment. Parsed CASE branches do not prove an entire
machine timeline.

Question chips, follow-ups, copy controls, Enter/Shift+Enter and slash shortcuts
are available. Late replies do not force the user back to the bottom. The microphone
remains alongside the composer; attachment, text, microphone and Send have separate
layout columns.

## History and corrections

`/api/assist/conversations/{project}` stores up to 50 messages / 2 MiB per account
and project. It verifies project access on read and write. Records include the
account creation identity to avoid reuse by a subsequently recreated account.
Restored replies are historical snapshots; source inspection reports current
index freshness. Starting a new chat clears that project's saved conversation.

Thumbs up/down and Correct this answer create private pending feedback records.
KnowHub > Answer feedback shows them for review. They never alter approved
knowledge, validation outcomes or weights. Existing project-answer training still
requires its separate evidence, approval and held-out evaluation checks. Feedback
is not automatically promoted into that approved training dataset.

## Worksheet analysis

CSV, XLS and XLSX reuse the existing account-owned reader and worksheet switcher.
Saved cells are read without executing formulas or macros. The background profiler
calculates exact Decimal KPI inputs, column types, missing/error cells, duplicates,
category counts and IQR review candidates. Ambiguous dates and mixed numeric/text
columns remain text. Identifiers with leading zeroes are not coerced to numbers.

Rules propose date trends, category bars, two-measure scatter plots, histograms
and category-count donuts (six categories or fewer). The existing grouped/pivot,
outlier, source-table and recommendation views remain available. Questions can
produce a compact dashboard card in chat as well as the larger results panel.

DuckDB 2.0.0 evaluates generated SELECT templates against an in-memory table.
The model cannot supply executable SQL or Python. Strict typed specifications
validate chart kind, existing column indices, numeric measures, date buckets and
optional equality filters. Filter values are bound parameters. File/network
access and automatic extension loading/installation are disabled. Each connection
has one thread, 128 MiB memory and no temporary disk spill. There is no connection
to application databases. Result previews are capped at 5,000 points; correlation
uses all complete pairs. Charts use floating-point aggregation; KPI calculations
use Decimal before conversion to displayable finite values. No unit conversion or
CRC/PLC meaning is inferred from these statistics.

Supported examples include "show monthly Production by Line" and "total Hours by
Team". Unclear filters and measures request clarification; explicit controls can
select columns, aggregation, date bucket and equality filter. Local model proposals
are validated before execution. An optional second-stage model selects existing
computed insight IDs only; code renders their exact words/numbers. Unknown IDs,
free-text additions and malformed selections fall back to calculated insights.
Only ready local/loopback inference is used for this optional worksheet summary;
no spreadsheet source rows or category samples are sent to that planner.

Profiles/charts cache by account, file SHA256, sheet, header row and algorithm
revision. Switching sheets rejects late results from the previous selection.
Custom charts can be pinned, and dashboard snapshots saved under the current
account. HTML/PDF exports regenerate validated pinned chart specifications or
open an explicitly saved snapshot. PNG is available per chart. Portable exports
show at most 100 plotted points per chart and label that limit; PDF tables contain
12-row excerpts. Existing worksheet CSV/XLSX and original-file downloads retain
the complete uploaded data. Saved snapshots retain their original source hash.

## Verification

- TypeScript and the main Vite production build passed.
- Targeted Python regression: 147 passed. Includes genuine authenticated HTTP
  uploads, calculations, pin/save/export, ownership, cancellation and source tests.
- Browser checks use actual account, worksheet, source and feedback APIs with
  temporary storage. A controlled delayed project reply verifies early tabs,
  Stop and late-summary behavior. CSV/XLSX, sheets, PDF/HTML/PNG, Mermaid source
  clicks/exports, KnowHub navigation, light/dark and 1440/760/390 widths are covered.
- Separate pure frontend checks cover empty-tab omission, mode visibility,
  bounded branches, source references and hostile label isolation.
- Optional model selection has strict-output regression fixtures and deterministic
  fallback coverage. No new live-model inference or model training is claimed.
- The Windows packager includes DuckDB's native import. Dependency and Docker
  inputs were updated; no new Windows executable or Docker image was built here.

Artifacts: `.build/chopper-answer-browser/`, `.build/chopper-agent-browser/`,
`.build/chopper-workspace-regression.log`, `.build/chopper-bi-build.log`.

The packet validation engine, saved projects, account permissions and document
approval logic were not changed. This update does not establish complete PLC
semantics, physical safety or runtime execution.
