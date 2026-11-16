# WorkHub inbox, assignments and timesheets - 16 November 2026

WorkHub now uses a compact glass submenu with readable theme-aware navigation.
Inbox replaces the separate My Work & Approvals navigation item. Its dropdown
opens My Work, Approvals, Tasks & assignments, or Log hours & timesheets in
the existing team inbox. Dashboard My Work/Approvals actions open the same inbox.
Existing bookmarked work/review URLs remain usable for controlled review.

Inbox work views use the full window width, leaving conversation lists in Chats.
Chat messages, meetings, praise, shared components and history are preserved.

- My Work lists assigned projects, tasks and supporting responsibilities.
- Tasks lists tasks assigned to you or created by you, with search and paging.
  New tasks require a project; creators, project owners and administrators use
  the existing planning authorization. Choose yourself or an active approved
  assignee, provide title/description, due date and planned hours. Existing
  workflow rules and assignment notifications apply. This does not grant every
  contributor permission to change the project plan.
- Timesheets record the current user's work date, project/task, whole hours,
  minutes and work description. Entries use the existing WorkHub update and
  time-review records; authors cannot forge another user ID. Future dates,
  missing work descriptions and invalid durations fail server validation.
- Logged, approved/billing and pending hours are shown separately. Totals are
  the user's own entries in the selected project/date scope. Existing project
  billing still sums approved project/task minutes once; no invoice, currency,
  payment approval or new billing classification is inferred.
- Timesheet CSV includes user, work date, project/task, exact minutes, display
  hours, work description, review status and comments. Export includes all
  filtered pages and protects spreadsheet formula-like text.
- Document/workflow/time reviews open their existing controlled evidence and
  actions. Returned time entries link to the correction/resubmission workflow.
  No document approval or project release gate is bypassed.
- Unfinished task and time forms are retained using account-scoped draft storage.

The additive `/api/team-chat/work-center/` APIs expose options, scoped work,
project task creation, time logging and personal timesheet/CSV retrieval. They
reuse WorkHub create/add_update services and the signed-in account. No database
schema or existing project/document data is rewritten.

Evidence: `.build/inbox-work-center-*`. Browser checks exercise task assignment,
time submission, reviewer-approved totals, CSV, three viewport widths and five
themes. API checks cover assignment permissions, inactive users, module/demo
restrictions, personal timesheet isolation, invalid dates/durations and exports
across multiple pages. Workflow regression checks run in a separate process
because combined legacy fixtures can retain quality-store initialization state.
