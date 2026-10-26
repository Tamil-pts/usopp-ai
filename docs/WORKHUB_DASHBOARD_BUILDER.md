# WorkHub Dashboard Builder — 4.84.0

## Where to find it

Open **WorkHub → Overview → My Dashboard** using an enabled personal account.
The project portfolio remains below the builder. Existing project workflows, planning,
approvals, engineering tools, capability calculations and validation engines retain their behavior.

1. Select **New** to name a dashboard, then **Edit dashboard**.
2. Click a widget in the library or drag it onto the canvas.
3. Drag its header to move it. Resize from any edge or corner. The grid moves colliding
   widgets without overlapping them; free positions remain available.
4. Select a widget to configure its source, dimensions, metrics, aggregation, filters,
   columns, colors, axes, legend, number format and size. Coordinates also support keyboard entry.
5. Use the desktop, tablet and mobile controls to edit each responsive layout.
6. **Save** persists all layouts. **View mode** uses the layout for the available width.

Undo and redo cover unsaved configuration and layout changes. Duplicating a widget copies
its settings and dimensions. Dashboards can be renamed, copied, switched and deleted.
A dashboard copy starts private and includes the current unsaved design. Switching dashboards
warns before discarding unsaved edits. Moving to other WorkHub views keeps the builder mounted
so its unsaved editor state remains available. Closing/reloading the application warns about
unsaved editable changes. Save before signing out.

## Widget library

The 25 widget types are:

| Family | Widgets |
|---|---|
| Indicators | KPI, scorecard, gauge, progress |
| Charts | Bar, stacked bar, line, area, pie, donut, scatter, combo, heatmap, histogram, treemap, funnel, radar |
| Tables | Table, pivot, matrix |
| Planning | Gantt, roadmap, calendar |
| Content | Plain text, internal document links |

Charts use Apache ECharts 6.1.0. The editor uses React Grid Layout 2.3.0, including
two-dimensional resizing and independent 12/8/4-column responsive layouts. Tables, pivots,
matrices, calendars and dated Gantt/roadmap bars are React components. No external chart CDN is needed.

Cartesian charts and scorecards can display multiple metrics. Combo charts allow bar/line
selection for each metric and an optional right axis. Pie/donut, gauge, heatmap, funnel,
treemap, pivot and matrix use the first metric. Raw-record tables use selected semantic columns.
Scatter uses its first two numeric fields. Histogram bins use all matching numeric records
on the server, rather than only the displayed rows. Gantt/roadmap need saved start and due dates.
Calendars use the saved due date or recorded date; dates are never invented.

Color palettes, light/dark/inherited theme, canvas pattern, density, titles and formatting
are configurable. Dashboard filters apply together with widget filters; date ranges intersect.
Loading, no-record, missing-value, incompatible-field and request-error states are explicit.

## Sources and meaning

`GET /api/workhub/dashboards/registry` supplies the semantic field registry, supported
aggregation methods, widget types, layouts and limits. Registry/provider extensions belong
in `backend/core/workhub_dashboards/schema.py` and `data.py`; SQL access is never exposed in the editor.

| Source | Meaning and access |
|---|---|
| Projects | Existing WorkHub project calculations, including independent development/quality/release progress; visible to enabled personal accounts |
| Tasks | Saved workflow steps and their recorded phase/stage; completion uses the existing stage meanings |
| Assignments | One record per work item and assigned workflow role, not a unique-person count |
| Milestones | Explicit milestone task records |
| Approvals | Current pending quality/release decisions and recorded decision history; filter status to distinguish them |
| Engineering activity | Own activity or managed-project activity; Admin can view all |
| Validation results | The same authorized native run ledger; unlinked private archives remain private |
| Reviewed contributions | Existing independently reviewed, de-duplicated contributions from authorized 365-day performance profiles |
| Capability information | Existing five capability profiles over 365 days; supporting record counts are not skill scores |
| Knowledge articles | Published revisions only; drafts and submitted revisions are excluded |
| Project documents | WorkHub attachments and approved Project Intelligence revisions; no draft document content |

The source registry explains what “engineer” means for each source: owner, assignee,
reviewer, author or uploader. Projects retain their existing completion calculation;
development completion is not changed into project completion.

Metrics use actual records. Count means count of non-null field values; distinct count,
sum, average, minimum and maximum are allowlisted by field type. Missing numeric values stay
null, with **Not enough information** in indicators. Run/iteration counts are activity,
and a completed run does not imply it passed. A validation score is projected only when the
source records exactly one unambiguous score field; its original field name is retained.
Zero-valued pie charts do not show invented equal shares. Missing radar measurements are
not replaced with zero. Empty matrix cells show a dash.

Capability snapshots cannot be honestly narrowed by arbitrary project/date filters.
Their widget explains this and asks the user to clear those filters or select Reviewed
contributions instead. Contribution date filters narrow the existing 365-day profile window.

Aggregations include every matching authorized source record before limiting displayed
groups. Raw-record views are bounded and explicitly disclose partial displays. Source
projections have a 100,000-record safety limit and reject larger sources rather than silently
calculating incomplete totals. A dashboard supports 60 widgets; each query supports 2 dimensions,
4 metrics, 20 filters and 500 displayed groups/records. Each account can own 100 dashboards.
Visible Overview dashboards refresh data every 60 seconds and offer a manual refresh.

## Chopper

The existing header Chopper and full Chat route WorkHub dashboard creation/modification
requests to the builder. Existing report-analysis and engineering conversations keep their paths.
The builder also has **Build with Chopper** with examples:

- Create a project progress dashboard.
- Add a bar chart of completed tasks by engineer.
- Show validation activity as a heatmap.
- Change this widget to a line chart. (Select the widget first.)
- Make this widget larger.

Chopper returns a **draft configuration**, with live previews for up to six added/changed
widgets. **Apply to editor** is separate from **Save**. Layout-only changes are described
in the draft, then shown on the editable canvas after applying. Every generated widget is
editable using the same manual controls.

Common actions work through local structured interpretation without a model. Other requests
can use the existing private local model when `USOPP_PI_LLM_URL` is already configured.
The existing private-network URL guard applies; there is no cloud fallback. Only the registry,
request and dashboard settings are supplied to this model, not query result rows or company files.
No new server/model activation is required for the structured examples.

Manual saves, data queries and model proposals share the same server allowlist validation.
Generated JavaScript, HTML, SQL, arbitrary ECharts options and external data URLs are never executed.
Model availability does not affect manual editing or existing engineering calculations.

## Storage and permissions

Additive tables in the existing `.usopp_workhub/projects.sqlite3` database:

- `wh_dashboards`: owner, version, name and complete validated configuration, including
  widget queries, filters, appearance and all grid coordinates/dimensions.
- `wh_dashboard_access`: named enabled accounts with viewer/editor permission.
- `wh_dashboard_changes`: actor/action/version audit metadata.

Creation is private. Only the owner can share or delete; editors can save the design.
Concurrent updates use version checks and return a conflict rather than overwriting changes.
Admin status alone does not take over another account’s personal dashboard.
Sharing a design grants **no source-data permissions**. Every query is scoped afresh to
the requesting account, so two viewers can legitimately see different counts.
All dashboard API responses request private, noncached handling.

Endpoints under `/api/workhub/dashboards`:

| Operation | Route |
|---|---|
| List / create | `GET /`, `POST /` |
| Registry / validate / query | `GET /registry`, `POST /validate`, `POST /query` |
| Chopper draft | `POST /propose` |
| Open / update / delete | `GET /{id}`, `PUT /{id}`, `DELETE /{id}?version=N` |
| Copy / sharing | `POST /{id}/duplicate`, `PUT /{id}/sharing` |

Use the existing Docker/Linux persistent WorkHub volume. No additional service, database,
external AI provider or company file upload destination is introduced.

## Implementation checks

TypeScript checking, Python compilation and the WorkHub/Nami/Virtual PLC production builds
were run during implementation. An online SQLite backup was created under
`.build/dashboard-builder/` before activating the additive dashboard schema.
No automated tests or browser interaction tests were run for this change.

Dependency references: [React Grid Layout](https://github.com/react-grid-layout/react-grid-layout),
[ECharts integration](https://echarts.apache.org/handbook/en/basics/import/),
[ECharts resizing](https://echarts.apache.org/handbook/en/concepts/chart-size/).
