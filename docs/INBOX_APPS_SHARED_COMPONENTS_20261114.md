# Inbox approvals, workflows, updates and shared components

Implemented and checked on 14 November 2026 (Asia/Calcutta).

The team inbox now has **Chats**, **Meetings**, **Workflows**, **Approvals** and
**Updates** apps across its top. Live meeting deployment remains deferred as
requested; this update does not start a meeting server or connect a cloud service.

## WorkHub integration

- **Approvals:** shows reviews assigned to the current user, including controlled
  documents, workflow stages and submitted time entries. Document cards identify
  the current saved revision; workflow cards identify the saved work version.
  **Review saved evidence** opens the existing WorkHub review screen. Decisions
  remain there, with its document revision, independent reviewer, sign-off,
  permission and release/closure gates. Chat does not add an alternate approval
  status or a generic approval button that skips reviewing the evidence.
- **Workflows:** shows the user's active project/task responsibilities, saved
  stages, due dates and versions, with links to their normal workflow workspace.
- **Updates:** displays the user's WorkHub notifications and allows factual text
  updates on an authorized saved project/task through the existing WorkHub update
  API. It creates no invented hours, test execution or completion results.

The projections are paged and recheck access. The approval list uses the existing
portfolio calculation and filters to assigned actionable reviews. A link does
not bypass permissions when its destination opens. The notifications bell and
existing My Work & Approvals remain available.

## Praise

Use **Praise / Shared** next to the chat attachment and emoji controls. Select
Praise, another current conversation member, a badge, title and optional message.
Available badges: Thank you, Teamwork, Quality champion, Problem solver and
Leadership. Recognition is visible to that conversation's current participants.
Posted praise is retained rather than edited into a different recognition record.
Praise does not approve a project, validate an engineering result or change a
competency/performance score.

## Local Loop-style components

The same composer creates shared notes, checklists and small tables:

- Notes support a title and editable text.
- Checklists support shared completion ticks, editable item text and adding or
  removing items. These ticks are independent of WorkHub task completion.
- Tables support named columns, editable cells and adding rows. Creation uses
  comma-separated column names and `|` between cells, with one row per line.

Current participants can edit. Saved edits appear through the chat's existing
polling, rather than keystroke-level live cursors. Notes and tables use explicit
**Save component**; checklist ticks save immediately with pending UI feedback.
Each save has a version and editor/time audit entry. **Version history** retains
earlier content. A stale save returns a conflict instead of overwriting a newer
edit; the user's draft stays in the editor until they choose to load the latest
version or cancel. History is paged. Participant access is checked for reading,
editing and history, including after team membership changes.

Components are stored locally in the existing chat database. These are native
uSOPp components; Microsoft Loop / Microsoft 365 synchronization, `.loop` file
support, collaborative Word/Excel embedding and Teams tenant integration are
not implemented. Shared content is not promoted into approved engineering
knowledge or controlled WorkHub documents automatically.

Limits: titles 160 characters; praise 2,000 characters; note body 16,000
characters; 100 checklist items; tables up to 8 columns and 100 rows; each
component up to 64 KB. Creation is idempotent for retries. Existing message
limits and a shared-edit rate limit apply.

## Verification

- 25 inbox/chat/collaboration API tests passed: existing messaging and meetings,
  praise recipient scope, recognition immutability, notes/checklists/tables,
  identity/revoked access, persistent history, stale-edit rejection, validation,
  WorkHub module access, assigned approval scope and saved-revision projection.
- 30 existing WorkHub portfolio/workflow regression tests passed.
- Two-account browser checks passed for praise delivery, shared checkbox save,
  simultaneous note edits and draft preservation, loading the current version,
  revision history, shared table display, assigned review links, workflow cards,
  saving a real WorkHub update, nested-dialog Escape and 390–1440px layouts.
- TypeScript and production Vite build passed.

Artifacts: `.build/inbox-apps-tests.log`, `.build/inbox-apps-workflow-tests.log`,
`.build/inbox-apps-browser.log`, `.build/inbox-apps-build.log` and
`.build/inbox-apps-20261114/`. Test users, messages and work records were created
in isolated temporary storage, not in the live project database.
