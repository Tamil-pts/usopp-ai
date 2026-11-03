# WorkHub calendar filters and default Overview — 3 November 2026

Overview opens with the existing **Portfolio & delivery** layout: total, active,
completed, delayed and at-risk projects; delivery stages; and portfolio health.
Figures use the authorized portfolio API and existing calculation rules. The
**Custom dashboards** tab opens saved editable dashboards. This display change
does not replace saved dashboard configurations.

The shared calendar picker appears in Overview, Projects and project export:

- **Day** selects a single date.
- **Week** selects Sunday–Saturday, matching the supplied reference.
- **Month** selects the entire calendar month.
- **Range** shows two months and supports selecting an inclusive start/end pair.
- **OK** applies the draft selection. **Cancel**, Escape or clicking outside
  discards it. **All dates** removes the date restriction.

Month/year controls support historical records; range mode also supports typed
dates and open-ended ranges. Reversed typed ranges cannot be applied. The current
day is marked, and week numbers provide shortcuts for selecting whole weeks.
The dialog fits smaller viewports and supports keyboard tab navigation, arrow-key
day navigation, focus return and dark mode.

Projects offers **Due date**, **Planned start date**, **Actual start date**,
**Closure date**, **Created date**, **Last updated date**, and typed custom date
fields. The selected dates filter table, cards and timeline before pagination.
Export inherits the date field and range; saved export views retain them.
Overview's picker filters its existing API by project due date.

Both range endpoints are included. Missing dates are excluded while a date range
is active and included under All dates. Closure-date filtering requires a closed
project. Reset filters clears the date selection with the other project filters.
Dates and project records are not edited by filtering.

Verification: 29 targeted backend tests passed, including inclusive/open-ended
ranges, date-field selection, custom historical dates, saved export settings,
permission checks and invalid input. Sixteen browser checks passed, including
JSON export agreement, all selection modes, month boundaries, Cancel/Escape,
default Overview and preservation of saved custom dashboards. Calendar bounds
were checked at widths 1600, 1067, 800 and 390. All four frontend production builds
passed; subsequent main-interface changes also passed TypeScript/Vite checks.
Artifacts are under `.build/workhub-dates-20261103/`.
