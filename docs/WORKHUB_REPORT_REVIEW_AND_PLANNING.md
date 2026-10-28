# WorkHub 4.94.0: report review and project planning

## Create a project

Enter the project name and **Customer / Client name**. Select an existing client from the suggestions or enter a name. The client is saved once in the project context and reused in the FRD, validation, FAT and closure documents.

The project number may be left blank for automatic allocation or entered manually. Admin configures **Settings > WorkHub workflows & document control > Company numbering and revisions > Project number prefix**. A configured prefix produces automatic numbers such as `PTPL-PRJ-2026-001`; a custom suffix such as `441` becomes `PTPL-PRJ-441`. With no separate prefix, the existing company project numbering pattern is used. The displayed next number is a preview; actual allocation remains transactional when creating the project.

Expand **Timeline and planning method** to choose Waterfall, Agile, Sprint or Custom. Set the project start and finish, sprint length and initial sprint count. Move or resize the preview periods, or open a period to enter dates. A named workflow creates its configured tasks without duplicating the planning template tasks.

After creation, open **Overview > Plan & milestones**. Agile and Sprint projects show their backlog and sprint board here, including **New sprint**. Managers may change the planning method while retaining existing tasks and sprints.

## Review the reports before quality approval

1. Save and confirm the FRD requirements. Validation, FAT and closure drafts are prepared from that saved revision. Expected results and acceptance criteria are copied from the requirements; actual test results remain empty until recorded.
2. Choose the project quality action and open **View Validation Report / FAT and Quality Review**. The quality workspace provides both reports together, with their document numbers, revisions and statuses.
3. Use **View Validation Report** and **View FAT** to read the saved content and recorded results. PDF previews remain available.
4. Use **Open / edit** to review the structured fields, add attachments and save changes. Use **Continue to Quality Review** to return. Approved reports remain read-only; changes use a controlled successor revision and review.
5. Submit the reviewed report drafts for their assigned approval. Actual execution, test-result and FAT acceptance requirements remain enforced. The quality decision requires viewing the current reports and completing the existing applicable review checks.

If your assigned quality-review tasks remain open, explicitly confirm **I completed my assigned review tasks; finish them with this approval**. The task completion and report decision are saved together, without changing the reviewed engineering content. Another engineer's unfinished quality work must be completed by that engineer first.

**Prepare missing reports from FRD** fills missing reports without overwriting existing engineer edits. If the source FRD changes, the existing baseline checks identify outdated reports; prepare and review a controlled updated revision before approval.

## Attach files to fields

Engineering text fields have **Attach files**. Upload a new file for that field or select an existing project file. Each field retains its own links within the document revision. Removing a link keeps the original file in project storage.

Links cover FRD purpose, scope and requirement fields; correction details; Validation/FAT objectives, procedures, expected results and acceptance criteria; report sections; and recorded-result/observation fields. Related report drafts inherit linked requirement files from the FRD. Internal PDFs include an attachment-by-field reference table.

Changing a procedure or expected-result attachment changes the test specification hash, so its old execution cannot count as a verified result for the changed specification. Files attached to actual-result fields can be included in the recorded execution. Customer copies continue to use explicit authorization and the existing filtered projection.

## Edit the timeline later

Authorized managers and assignees can adjust planned project, phase, sprint and task dates at any stage, including after completion. Milestone dates, valid ranges, permissions and concurrent-edit checks remain enforced. Date changes record the prior and new dates in the activity history.

The original baseline finish and actual start/completion records are retained. Active review baselines may require a fresh quality review when the project deadline changes. Editing planning dates after closure preserves the historical approval context and frozen PDF bytes. Controlled reopening starts a new review cycle against the then-current plan. Adding new work to a completed project still requires reopening it.
