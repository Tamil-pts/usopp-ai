# uSOPp.ai WorkHub – Performance & Capability

Reviewed: 24 October 2026 · Application: 4.81.0

> This is the historical application-capability review for 4.81.0. The engineer performance and Contribution Passport features added in 4.83.0 are documented in [the current feature guide](PERFORMANCE_CONTRIBUTION_PASSPORT.md).

## Overview

WorkHub connects engineering checks, project planning, daily updates, quality review and release decisions. It supports shared project visibility and decisions by the assigned users, with recorded evidence and approval history.

The current application uses **React, TypeScript and Vite** for the interface, **Python/FastAPI** for the backend, and **SQLite** for WorkHub records. It does not use PHP. The local health endpoint reported `ok` and version `4.81.0` during this review.

## Implemented capabilities

| Area | Current capability |
| --- | --- |
| Project delivery | Assign development, quality, release approval and release ownership to enabled personal accounts. Record requested corrections and return work to development. Development completion remains separate from project release. |
| Planning | Editable work types; Waterfall, Agile, Sprint and Custom templates; draggable and resizable Gantt periods; phase owners, workflow steps, dependencies and milestones. |
| Engineering traceability | New supported ByteMap, DataInspect, MatchView and LogicScan runs create or associate a project and record numbered iterations, results and available evidence. Later exports enrich the same saved run. |
| Daily updates | Short manual notes, attachments, screenshot OCR and document text extraction. Optional Chopper drafting requires the user to review and save the update. |
| File review | Store and download native PLC, CAD and document files; preserve submitted revisions and their approval references. Binary file storage does not establish technical validation of that file format. |
| Team visibility | Portfolio, My work, Team activity, Recent work, approvals, issues and PDF/CSV/JSON reports. Overall completion includes Development, Quality and Release. |
| Notifications | In-app assignment, review, mention, issue and due notifications. Teams group-link sharing prepares a message for manual sending. Optional automatic email/Teams connections require configuration and authorization. |
| Administration | User management and notification configuration under Settings. Demo accounts cannot access shared company projects. |

## Performance design and default limits

| Item | Implementation or default limit |
| --- | --- |
| WorkHub file size | 4 GiB per file, configurable on the server |
| Shared file storage | 100 GiB, configurable on the server |
| Upload requests | Resumable 8 MiB chunks |
| Duplicate storage | Identical file bytes share a SHA-256 content blob; separate references and history remain |
| Revision downloads | Multiple files stream as ZIP64 without retaining another permanent ZIP |
| Evidence extraction | Up to 12 selected files, 25 MiB per document and 40,000 extracted characters per preparation |
| Team activity | Latest 300 updates |
| Project detail | Latest 500 updates, events and engineering iterations |
| Time entries | Latest 1,000 entries in the time view/export |
| Database | SQLite WAL mode with indexes for project items, files, engineering iterations and notifications |

A changed 2 GiB archive can consume another full archive's storage. Uploading individual project files allows unchanged files to share existing blobs. Deduplication occurs after upload; it does not eliminate the initial file transfer.

## Performance findings

- **Current availability:** the local health check succeeded. This confirms application availability, not workflow latency or throughput.
- **Portfolio scaling:** the overview loads all project/task rows, scans that collection for each project's tasks and queries the latest engineering run for each item. More projects and tasks will increase this work. Server pagination and grouped database queries are the first optimization targets.
- **Project detail size:** a project response can include up to 50,000 file records. Lazy loading or pagination would reduce large-project response sizes.
- **Large-file completion:** finalizing an upload hashes the entire file before recording its permanent blob. Available disk throughput and simultaneous uploads affect completion time.
- **OCR and AI latency:** extraction depends on installed OCR support and document contents; Chopper drafting depends on the configured assistant. Manual entry remains available.

No concurrent-user capacity, response-time percentile, actual 2 GiB transfer rate or production SLA was established in this review. Those require representative measurements on the intended server and office network.

## Engineering workspace scope

WorkHub links the existing engineering tools and Virtual PLC. Virtual PLC 0.11.0 includes source-driven HMI layer inspection, password-level handling, dynamic button captions, configured page switching and supported virtual key actions. It executes a supported PLC subset, rather than the native B&R runtime.

The current Virtual PLC service limits are **three resident workspaces and two running simulations per server**. These are simulation-service limits, not WorkHub user limits. Engineering results remain determined by the validation engines; an AI-generated explanation does not approve or release a project.

## Evidence reviewed

- [Project delivery and notification guide](WORKHUB_PROJECTS.md)
- [WorkHub records, workflow and overview queries](../backend/core/workhub.py)
- [File limits, resumable uploads and deduplication](../backend/core/workhub_files.py)
- [Evidence extraction and draft preparation](../backend/core/workhub_evidence.py)
- [WorkHub API and activity limits](../backend/api/workhub.py)
- [Virtual PLC capabilities](../virtual_plc/README.md)
- Local `/api/health` response: `status=ok`, `version=4.81.0`.
