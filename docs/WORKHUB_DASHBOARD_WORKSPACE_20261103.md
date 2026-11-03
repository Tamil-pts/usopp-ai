# WorkHub dashboard navigation and Projects presentation — 3 November 2026

Overview now starts with compact dashboard tabs and **Create dashboard** and
**Arrange dashboards** controls. The large WorkHub introduction banner has been
removed. **Portfolio & delivery** remains the first-use default. Saved custom
dashboards appear as named tabs without changing their existing designs.

Use **Arrange dashboards** to drag rows or use their arrow buttons, show/hide
tabs, and choose the default view. At least one view must remain visible. These
preferences belong to the signed-in account and use existing revision-checked
server settings, so they also apply in another browser. Hiding a dashboard keeps
its saved design. Project and document creation remain under **Project actions**.

**Create dashboard** opens the existing designer with a name and template choice.
Templates include WorkHub shortcuts, the engineering overview, editable project
cards and graphs, and a blank canvas. Saving adds the dashboard to the tabs.
Cards, charts, titles, metrics, colors and desktop/tablet/mobile layouts remain
editable. Unsaved changes prompt before switching dashboard tabs.

Projects now has **Customize cards & graphs** and **Display options**. Users can
create a presentation, edit it, select another saved dashboard, return to the
standard project cards, or hide the summary. The project starter includes total,
active, completed and awaiting-review cards plus delivery-group and owner charts.
Project dashboards are also available in Overview, where users can choose whether
to display their tabs.

Projects data widgets follow the register's search, stage, type, owner, summary
and date filters before pagination. Widget-specific and saved dashboard filters
further restrict the selection. An empty project selection produces zero counts.
Opening the same dashboard in Overview uses that dashboard's saved filters;
temporary Projects register filters are not written into its saved design.
WorkHub shortcuts/lists retain their existing account context; capability
snapshots explicitly reject project scoping instead of displaying misleading
filtered assessments.

The project custom-fields chooser is now a compact **Edit project fields** button
with a searchable dialog. Date-field selection, the Day/Week/Month/Range calendar
and reset controls share a compact wrapping row. Table, Cards, Timeline, columns
and export controls remain available.

An unfinished Projects dashboard edit stays mounted when navigating to another
WorkHub section. Returning to Projects restores that editor; save the design
before reloading the application.

Dashboard ownership, sharing, stale-version rejection and backend data permissions
use the existing APIs. No project workflow, approval record or assignment is
rewritten by these presentation changes. UI and API remain at version 4.99.3.

Verification artifacts are under `.build/workhub-dashboards-20261103/`.

- 34 targeted backend tests passed, including project scoping, empty selections,
  private time-entry permissions, saved layouts, shared dashboards and conflicts.
- 18 browser checks passed for creation/cancellation, tab ordering/visibility,
  default selection, unsaved-edit guards, filtered totals, persistence, account
  isolation, retaining unfinished Projects edits between sections, and recovery
  when a selected dashboard is deleted.
- Overview and Projects fit viewport widths of 1600, 1067, 800 and 390 pixels;
  dark-theme rendering and the arrangement dialog were checked.
- All four production interface builds passed. The final main interface build
  and TypeScript check passed after the interaction fixes.
- The local server was restarted through the supported launcher after idle checks.
  Live UI/API versions match at 4.99.3; served entry hashes, authenticated dashboard
  inspection, project templates, and empty/single-project scoped queries passed.
  The existing 53 projects and 34 accounts were retained.
