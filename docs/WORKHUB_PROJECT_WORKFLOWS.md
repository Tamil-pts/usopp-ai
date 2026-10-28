# WorkHub 4.92.0 - project management workflows

## Create a workflow

Open **Settings > WorkHub workflows & document control > Workflows and validation rules**.

1. Edit the default procedure or enter a name and select **Add workflow**.
2. Add the team's steps. Choose Development, Quality review or Handover, planned days, estimated hours, milestones and whether a step waits for the preceding step.
3. Add validation rules. Give each rule a name, choose the project action it checks, the required record and whether an unmet check blocks the action or produces a warning.
4. Save company controls.

Document requirements, independent review, test attachments, FAT acceptance and company numbering remain available in the same settings. Portfolio health thresholds use the existing health-rule API and editor.

New projects can select a named workflow under **Workflow, assignment and target date**. A name is still the only required project field. Configured steps become real WorkHub tasks, with dates and dependencies. Development steps use the responsible engineer, quality steps use the quality reviewer and handover steps use the release owner. Existing assignment controls remain available.

## Track a project

Open a portfolio project and select its **Overview**. Project tracking provides:

- The adopted procedure and its version, with the current responsibility.
- Completed and planned steps for each delivery phase.
- The existing editable project timeline, assignments, milestones and dependencies.
- Custom validation checks with their current result and the record needing attention.
- Project risks and blockers.
- Paginated activity history, including procedure changes and warnings.

The portfolio also shows the workflow, current responsibility, completed task and milestone counts, planned progress, actual progress and health. Its existing filters, role visibility and drill-down links remain available. Progress and health retain their separate calculations. A project without a plan is not given invented progress.

Engineering documents and meeting tools remain available in their contextual views. Their project summary is collapsed so it does not repeat the tracking plan.

## Supported project validation rules

| Check | Source |
| --- | --- |
| Approved document | The current approved MOM, FRD, reviewed flowchart, correction note, validation report, FAT, quality review or closure revision |
| Required project detail | Saved customer, machine, scope, start date or target date |
| No unresolved issues | Existing open project issues |
| Milestones completed | Recorded milestone tasks in the chosen delivery phase |
| Phase tasks completed | Actual tasks in the chosen delivery phase |
| Saved engineering check passed | Recorded outcomes for the latest saved run of each source and target for ByteMap, metadata, DataInspect, MatchView or LogicScan |
| Required test cases passed | Recorded passing executions whose specification hashes still match the current test or FAT cases |

Rules can apply before project start, development completion, submission for quality review, quality completion, release approval or project closure. A completed run, a score or an absent test is not treated as a passing result. Rules that would require a phase's own future work or approval before entering that phase are rejected where the contradiction is known.

These are project workflow checks. Engineering rule definitions in the testing tools are preserved. Standalone document workspaces do not inherit project transition rules.

## Updating an active project

Each project keeps a snapshot of its procedure. Changing Settings affects newly created projects; existing projects adopt the new version explicitly.

Use **Project tracking > Choose / update workflow**, select the procedure and record a reason. Missing workflow tasks are created once. Existing tasks, assignments, dates, completed work and results are retained. Applying the same step IDs again does not duplicate tasks. A changed template does not silently rewrite an engineer's existing task plan.

The existing quality procedure-adoption action also creates missing steps. New development work requires the project to be in planning or development. A completed project must use its existing controlled reopening process.

## Implementation

- Procedures, steps and rules are versioned within the existing `qc_settings` configuration and `qc_projects.policy` snapshots.
- `wh_workflow_steps` only links stable procedure step IDs to existing task IDs in the same WorkHub database. It stores no duplicate project status or task completion.
- Transitions and quality readiness evaluate actual project records on the backend. Browser controls cannot bypass blocking rules.
- Administrator settings, project management rights, assignment visibility, optimistic versions and audit history remain enforced.
- Tracking history is paginated. Record limits and condition-result reuse bound validation reads.
- No production projects, sample workflows or engineering executions are created during acceptance checks.

New endpoints:

- `GET /api/workhub/workflow/catalog`
- `GET /api/workhub/projects/{id}/tracking?event_page=1`
- `POST /api/workhub/projects/{id}/workflow`

Workflow editing reuses `GET/PUT /api/admin/settings/engineering-quality`. Portfolio health editing reuses `GET/PUT /api/workhub/portfolio/rules`.

Acceptance outputs are retained under `.build/workhub-navigation/`, including backend results, browser results, Settings and project tracking screenshots, real local Chopper results and published application health.

## Verification on 2026-10-27

- 54 portfolio, document workspace and workflow backend tests passed.
- 43 growth, reliability and FRD regression tests passed.
- 54 isolated browser checks passed, including creating a template in Settings, selecting it for a project, enforcing a missing-customer gate, satisfying it with a real saved record, advancing the project and viewing tracking on mobile.
- 13 checks of the real running local Chopper model passed for independent FRD creation, source retention, editing, confirmation, reviewer submission, approval, related drafts and PDF.
- 12 checks of the published saved workspace passed without creating production projects or revisions.
- TypeScript and Vite production build passed; published UI/API versions are 4.92.0 and frontend integrity matches.
- All retained project, document, knowledge, dashboard and numbering rows matched their pre-release hashes. There remain zero projects, two independent document scopes, two knowledge articles and one saved custom dashboard.
- 81 engine, planning and performance source hashes matched the earlier baseline. The core project transition file intentionally changed to call the new workflow guard.
- Pre-release recovery data is retained under `.build/workhub-navigation/pre-release-4.92.0-20261027-023018/`; previous frontend entry metadata is retained under `published-backup-20261027-022950/`. Existing Nami assets and Virtual PLC files were preserved.

The latest release summary is `.build/workhub-navigation/project-workflow-acceptance.json`. Source-rule checks and actual-record preservation are recorded in `project-workflow-release-verification.json`.
