# WorkHub 4.93.0

## Layout and navigation

WorkHub fills the available content area. Header controls, navigation, cards and document forms wrap at narrower widths. Wide tables and the dashboard editing canvas scroll within their panels. The saved custom dashboard and its editor remain available.

The main sections are Overview, Projects and Knowledge. Projects retains its Team Activity board; Knowledge retains Team Overview. The large portfolio filter panel and separate Team workload section have been removed from the main navigation. Existing API filters and access restrictions remain enforced.

## Delete a project

Admin opens the project and selects **Delete project**, enters its exact name and confirms. The server checks Admin access and the current project version. Active processing or uploads must finish or be cancelled first.

The project and its related tasks, reports, processing records and notifications leave the active register. Before removal, their database rows are written and flushed to `.usopp_workhub/deleted-projects/`. Original file bytes remain in storage. Numbering and audit history remain. Independent documents and knowledge contributions are detached from the project and retained. Recovery is an administrator maintenance operation; there is no restore button in this release.

## Testing rules in Settings

Open **Settings > Testing-tool validation rules > Manage testing rules**. The library and Chopper configuration editor use the same saved rules and pipeline selections as the testing tools. The current testing project is available for draft checks. Existing review and test requirements still apply before enabling a rule. ByteMap's metadata contract remains in the BOOL metadata settings below.

Project workflow checks are configured separately under **WorkHub workflows & document control**.

## Requested sample projects

| Sample | Stage |
| --- | --- |
| 01 Ring Frame PLC Upgrade | Completed |
| 02 Conveyor Interlock Upgrade | In progress |
| 03 Pump HMI Alarm Update | In progress |
| 04 Packaging Line Validation | Quality review; Admin decision pending |
| 05 Winder Control Handover | Closure; Admin decision pending |
| 06 Utility Panel Integration | Assigned |

Each has five assigned tasks, MOM, FRD, a functional flowchart, Correction Notes, Validation Test Report, FAT, Quality Review and Project Closure Report. Tamil prepares the reports and development work; Admin reviews documents and handles quality/handover, with Tamil assigned release approval. The completed sample has approved reports and a completed release workflow. Earlier-stage reports remain drafts or pending review where appropriate.

All sample reports, attachments, results, acceptance entries and approval comments explicitly identify fictional demonstration data. They do not represent equipment testing, customer acceptance or actual engineering sign-off. No new user accounts are created in the live workspace.

`scripts/seed_workhub_samples.py` defaults to an isolated temporary workspace. Its explicit `--live` mode backs up the existing project and account databases, creates exactly the requested six samples and records an idempotency manifest in `.build/workhub-navigation/six-samples-live.json`. A partial manifest stops automatic reseeding to prevent duplicates.
