# Inbox daily work and shared submenu redesign

Implemented and checked on 16 November 2026.

The inbox now uses Chats, Meetings, My Work, Assigned Work, Approvals & Actions, and Daily Updates & Hours. The separate Tasks, Workflows, Updates and Timesheets tabs are consolidated. Older inbox navigation events open the appropriate new view.

- My Work lists personal project/task assignments and supporting responsibilities. An Update work action preselects that project or task. Tasks can still be created for an approved user through existing project planning permissions.
- Assigned Work lists work created by the current user or within a project they own, including other assignees. Each entry opens its existing workflow with its saved stage, dates and approval gates.
- Approvals & Actions retains assigned document, time and workflow reviews, and adds explicit guidance, support and review requests. Recipients can reply in private chat or mark their own request handled. Handling a request marks its notification read; it never approves a document or changes workflow stage.
- Daily Updates & Hours records a work date, reported status, work description, optional hours/minutes, purpose and selected mentions in one entry. Project work can be split into multiple tasks owned by different engineers. Task entries retain their parent project for existing time review and billing rollups. Zero-minute updates contribute no billing time. Only approved time contributes approved project hours.
- The feed defaults to the current user's entries. Selecting an authorized project enables its shared contributor feed. Date/project filters and CSV export cover both daily notes and hours, including status, purpose and mentions.
- Mentions notify enabled approved users. Guidance, technical support and review purposes require a recipient and create individual in-app action requests. Mentions do not grant access to linked project content. Existing typed username mentions continue working.
- Chats now has a direct Create internal group button. The existing membership-controlled groups, team groups, messages, files and history are retained.

The compact glass submenu style now applies to WorkHub, PLC, e-design, AI Assist and Virtual, with theme-aware backgrounds, active states, focus outlines and contrasting submenu panels. Existing module actions and project selectors are preserved. Appearance-rule specificity was corrected so the global theme cannot restore the older ribbon over this style.

Storage changes are additive: update_context retains reported daily context, and update_requests retains per-recipient action completion. Existing projects, task stages, document approvals and historical time records are not rewritten.

Validation: 34 account/inbox/chat/collaboration/billing tests passed, plus 13 workflow tests in a separate isolated suite. TypeScript and the production frontend build passed. Browser checks cover creation and assignment, persistent drafts, status/support mentions, saved hours, reviewer-approved totals, CSV export, internal group creation, 390/760/1440 layouts and five themes. Cross-module submenu checks are included in tests/inbox_work_center_browser.py. Artifacts are under .build/inbox-restructure-*.
