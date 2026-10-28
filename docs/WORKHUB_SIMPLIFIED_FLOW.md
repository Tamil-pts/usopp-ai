# WorkHub 4.91.1 - simplified workflow acceptance

Verified and published locally on 2026-10-27 (Asia/Calcutta).

## Using the workspace

- **Overview:** the saved, customizable dashboard opens first. Use Edit dashboard to change it. Project Portfolio, Recent uSOPp.ai Activity, Approval Details and Reports remain accessible alongside it.
- **Projects:** Project Portfolio, My Work, Team Activity and Documents. My Work includes assigned, in progress and completed work. The team Kanban uses Assigned, To do, In progress and Completed columns; transitions still follow existing workflow permissions.
- **Team:** existing workload and assignments.
- **Knowledge:** My Performance, Team Overview and Knowledge, using the existing calculations and contribution records.

New project requires a name; a brief, assignment and target date are optional. The default action opens an FRD immediately. Existing projects retain their detailed planning and assignment controls.

FRD requirement entry starts with title, description and acceptance criterion. Purpose, scope, PLC signals and additional conditions are collapsed. Project and document information are reused. Saved drafts retain the existing autosave behavior.

Use **Prepare related reports** on the saved FRD to prepare editable validation, FAT and closure drafts. The same preparation occurs after human confirmation of the FRD. Preparation reuses requirements, source revision and source hash. Existing reports are retained; repeated preparation does not overwrite an edited or approved document. Test execution remains Not Tested until someone records actual results. Source FRD changes invalidate the derived draft's readiness for confirmation.

## Chopper document creation

Use **Create Document > Create New > Prepare with Chopper**, enter one requirement brief and select **Create with Chopper**. The background worker retains the original brief, extracts source-linked requirements and opens an editable FRD. A saved project brief is also reused. Choosing Chopper on an existing blank template now runs the requested preparation. Missing sources produce a clear error rather than a successful empty draft. Saved edits are preserved; use the embedded FRD assistant for proposed changes or create a controlled successor revision.

Generation cache checks include project brief changes. Short model prompt references are restored to the exact saved source identities. For a functional flowchart document, the creation request includes the existing flowchart preparation option; diagrams still require review against the requirements.

Custom dashboard count cards display zero for no matching records. Missing numerical assessments remain unavailable. Continue Work removes links to deleted projects or scopes the user can no longer access.

## Independent documents and MOM

**Create Document** outside a project defaults to an independent document. A project link is optional and reuses available project information. The eight document types remain available. Independent scopes are stored separately from project items in the same WorkHub database, and do not increase the project count.

Private documents are accessible to their author, assigned reviewer and administrators. Approved library previews expose the approved snapshot, while drafts, revision history and original attachments retain their private permissions. Reuse creates an editable draft with source identity; previous approvals and test executions are not copied. Linking a project does not grant permission to it.

The MOM editor has Meeting Details, Discussion & Decisions, Action Items, Clarifications and Review. It supports a saved preview, attachments and access to the existing meeting recorder and transcript tools. MOM numbers use the configured organization prefix and transaction-safe sequence. Saved titles and sections appear in the shared PDF engine.

Testing remains in ByteMap, metadata generation, DataInspect, MatchView and LogicScan. Unassigned runs no longer create WorkHub projects automatically. Engineers can explicitly link saved results through an assigned work update; existing source associations continue only for authorized assigned projects. Engine results and scores are retained.

Visible WorkHub labels use work updates, attachments and test results. Optional controls and repeated document headings have been reduced. Internal API identifiers remain compatible.

## Verification

| Check | Result |
| --- | --- |
| Targeted portfolio/workspace backend tests | 41 passed |
| Growth, reliability and FRD regression tests | 43 passed |
| Isolated Chromium checks | 45 passed; no frontend runtime errors |
| Checks of the published saved Admin workspace | 9 passed; no project/document revisions created |
| TypeScript and Vite production build | Passed |
| Live health | HTTP 200; UI/API 4.91.1; entry integrity verified |
| Local Chopper model | Configured Qwen model running and ready |
| Real local-model workflow | 13 isolated checks passed: worker generation, source retention, editing, confirmation, submission, independent approval, related drafts and PDF |
| Actual records after authorized removal | 0 projects; 2 independent document scopes, 2 knowledge articles and 1 saved dashboard retained |
| Protected engine/planning/performance source hashes | 81 matched the initial snapshot |

Fixtures and browser work now run in separate temporary data roots. FRD tests also explicitly replace account and WorkHub stores, protecting combined test discovery from cached imports.

Machine-readable verification outputs and screenshots are under `.build/workhub-navigation/`, including `unit.log`, `regression.log`, `browser-results.json`, `live-browser-results.json`, `live-health.json` and `actual-record-verification.json`. The latest Chopper check is in `real-chopper-results.json`, the generated source-linked FRD in `real-chopper-generated-frd.json`, and the published custom dashboard screenshot in `live-custom-dashboard.png`. The real model created two requirements in 30.19 seconds for the isolated verification; this is one observed example, not a latency guarantee.

An isolated store-query benchmark with 100 projects and 1,000 tasks measured median project-list query time of 63.54 ms before the grouped-query change and 32.28 ms after it. Python peak allocation was similar (about 2.73 MB). Four concurrent readers measured medians of 852.59 ms and 672.42 ms respectively. These are synthetic store-query measurements, not production HTTP or many-user capacity guarantees.

## Authorized test-fixture recovery

An earlier combined test invocation incorrectly used the local database after an import had already fixed its data root. Eight clearly named fictional acceptance projects were created. The original branding was restored and the three test accounts were disabled. With the user's authorization, the eight projects and their dependent test records were removed from the active workspace. Original file contents, approved test PDF bytes, numbering high-water marks and audit history were retained.

The retained archive is `.build/workhub-navigation/authorized-fixture-removal-20261027-000234/`. It contains the database and removed-row archive. The removal transaction verified that every unselected row remained unchanged. The result manifest is `fixture-removal-results.json`. Later verification found zero remaining acceptance fixture projects. Actual user additions and edits made during development were retained; a whole-database-unchanged claim would be incorrect.

The previous frontend entry and build metadata were retained under `published-backup-20261027-003406/`. A fresh database backup was retained under `pre-release-4.91.0-20261027-003455/`. Existing hashed assets, Nami assets and Virtual PLC files were preserved during publication.

## Removal of the selected old projects

After the user explicitly selected all eight remaining old projects, their project rows and dependent tasks, WorkHub run links, source bindings, drafts, notifications and activity were removed from the active register. The transaction verified every unselected database row remained unchanged. Two independent document scopes and two knowledge articles created by the user were retained, together with the saved dashboard, original files, numbering high-water marks and audit history. Native testing history outside WorkHub was retained.

The recovery archive is `.build/workhub-navigation/authorized-old-project-removal-20261027-005603/`, containing `projects.sqlite3`, `removed-rows.json` and `removal-results.json`. This authorized removal is separate from the earlier accidental acceptance-fixture recovery.

Release 4.91.1 also retains a frontend backup and a consistent pre-release database backup under `.build/workhub-navigation/`.

## Environment limits

The local speech model is not installed/configured. Recording, retaining attachments and importing text transcripts are available, while actual speech recognition needs that model. Clear/noisy audio, speaker separation and Tamil-English technical accuracy remain unverified without recordings and an installed speech service.

OCR and external Office conversion are not configured on this machine. Originals remain retained and the job system reports unavailable services. Application-generated PDFs use the working Chromium renderer; these do not require external Office conversion.

Prepared engineering documents remain drafts. Actual testing, independent review and authorized approval continue to be required for approved reports and project closure.
