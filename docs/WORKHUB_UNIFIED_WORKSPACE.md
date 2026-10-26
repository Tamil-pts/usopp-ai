# WorkHub unified engineering workspace — 4.86.0

## Default dashboard

WorkHub Overview includes one **Engineering project overview** template:

- Active projects, completed development tasks, pending workflow reviews and reviewed contributions.
- Actual project completion, delivery stages and scheduled WorkHub tasks.
- Work needing attention, validation run counts and project document links.

All ten widgets use the existing authorized data-source registry and server aggregations.
The template contains layout and query settings, not example project values or performance scores.
Validation counts remain activity counts. Missing records use the existing empty states.

A personal account with no accessible dashboards gets a private saved starter on first opening
My Dashboard. First-use creation is atomic, including simultaneous browser sessions. Existing
dashboards and sharing remain intact. An empty saved dashboard offers **Use WorkHub template**;
that applies an editable design which is persisted only on Save. **New** offers the template or
a blank canvas. Every widget, title, query, appearance and responsive layout remains editable.

## Four project sections

**Overview | Meetings & Requirements | Engineering Documents | Quality & Closure**

These are the project-level sections. Existing WorkHub Overview, My work, Team activity,
Recent work, Approvals, Reports, Performance & Capability and Contribution Passport remain.

### Overview

Shows project completion, assignments, pending engineering actions, recent documents, latest
meeting and actual milestones. The project summary includes the existing Gantt schedule.
The contextual view selector opens workflow/timeline, sprint/backlog, updates/iterations/files,
issues, planning proposals/roadmap and project approval history. Plans still update the original
WorkHub tasks only after their existing review and confirmed Apply action.

### Meetings & Requirements

Reuses the existing Teams recording/transcript upload, browser recorder, transcript correction,
audio replay, local speech processing and MOM editor. Meeting review includes decisions, actions,
owners, dates and clarifications in the same MOM. Sources retain transcript/audio references.
Approved meeting information supplies the controlled FRD; draft meetings are not treated as approved.

The FRD editor includes:

- Company numbering, project/machine/department, actual owner and revision identity.
- Purpose, scope, requirement IDs, functional descriptions, triggers, expected behavior,
  subsystem, acceptance criteria, original sources and change classifications.
- Comparison with the retained approved revision and controlled revision history.
- **Document / Flowchart** views inside the same FRD workspace.
- Collapsible **Chopper — FRD Assistant**, with the selected requirement as context.
- Persistent project clarifications, confirmed answers, Not decided and Ask later.
- Existing requirement-to-FAT links and recorded coverage. Missing physical outcomes are not passes.

Chopper analyzes missing details, proposes clearer wording/clarification questions and proposes or
updates an editable diagram. Proposals are separate background-job results. The engineer explicitly
applies reviewed wording, a reviewed flowchart or clarification questions to an editable draft.
Applying checks the exact project/document/revision/content hash and current draft version, clears
prior confirmation and records an audit event. A stale proposal cannot replace newer work.
An approved FRD requires a controlled new revision before changes can be applied.

Unknown technical behavior, reset conditions, interlocks and acceptance values remain questions.
Proposed removals and unresolved requirement changes cannot be confirmed until explicitly reviewed.
Original approved revisions remain unchanged. The illustrative Ring Frame content supplied as a
design reference is not inserted into company project records.

The React Flow editor supports nodes, decisions, connectors, requirement links, arrangement,
zoom/pan, fullscreen, SVG/PNG export and the controlled FRD PDF. Embedded diagram changes use
the FRD's draft autosave and approval identity. Legacy standalone diagram revisions remain accessible
as contextual existing engineering diagrams; new FRD diagrams do not require a separate module.

### Engineering Documents

Contains the existing local file/document viewer and editors plus contextual Correction Notes and
Test Report controls. Original documents, PDF utilities, OCR, comparison, revision history and
downloads use existing APIs and storage. The central controlled document register remains available.

### Quality & Closure

Contains FAT preparation/execution, current requirement coverage, nonconformances, approved
dispositions, quality approval, closure approvals and internal/customer/ISO packages. Existing
reviewer permissions, actual execution records and mandatory release gates remain in force.
Physical test results, customer acceptance, signatures and approvals are never generated by AI.

## Internal services and deployment

The existing private Chopper model configuration, including local Qwen, is reused when no explicit
`USOPP_PI_LLM_URL` override is set. Private-network/loopback URLs are enforced, redirects and proxy
environment forwarding are disabled, and there is no external AI fallback. Local model context
limits produce an explicit saved-job message rather than silently dropping source text. Requirement
extraction uses bounded source chunks. No model or runtime is downloaded by a documentation job.

Speech processing still requires the configured offline Whisper model. OCR, conversion and Office
editing use the existing optional local services. Missing services preserve original files and leave
jobs available to retry. This change does not activate new Linux/Docker services or alter existing
deployment credentials, validation calculations or PLC engines.

All records continue to use the existing WorkHub SQLite database, Project Intelligence jobs,
controlled document revisions, task records, authentication, files and persistent storage.
No duplicate task/timeline database or separate application is introduced.

## Checks performed

- Python compilation and TypeScript/production builds.
- Static SQL parameter-count review and hashes of the 79 protected validator/Virtual PLC modules.
- Local restart, UI/API version and served-asset integrity checks.

No automated feature tests, browser interaction tests, AI inference, speech transcription or physical
FAT executions were run for this change. The implementation does not claim ISO certification.
