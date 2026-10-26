# Engineering Quality, FAT, Document Control and Project Closure — 4.85.0

## Use

Open an existing WorkHub project and select **Quality & Closure**. The six stages are
FRD → Correction Notes → Test Report → FAT → Quality Approval → Project Closure.
There is no new top-level workspace or dashboard.

The project document register, current status, missing conditions, source documents, approved
dispositions and historical packages are on this page. Information already recorded in
WorkHub is reused: name, project/type identity, description/scope, assignments, team, dates,
issues, updates, decisions, uploaded files, shared native results and Project Intelligence records.
Customer and machine details are requested only when the selected procedure requires them
and they are not already available. Recording a missing detail makes it available to every stage.

### Prepare and confirm

1. **Generate draft** queues preparation in the existing persistent Project Intelligence
   job system. Existing requirements and source files are reused. Originals remain downloadable.
2. Edit only missing or inaccurate information. Draft changes save automatically after a
   short pause. **Save now** is also available. Failed/conflicting saves keep edits visible;
   navigation between WorkHub views and sign-out wait for pending saves.
3. **Review & Confirm** records authenticated engineering confirmation of content and proposed
   source/requirement links. Changing content or recording a new execution clears confirmation.
4. **Submit for approval** routes the saved revision to the existing project quality assignee.
   Closure documents route to the existing release owner. Reviewers approve, reject or request
   corrections; remarks are required for rejection/corrections.

The default procedure requires independent author/reviewer identities. Project roles are edited
through the existing assignment controls. Administrators can configure an alternative documented
procedure; changing company settings does not silently rewrite an already adopted project procedure.

### FRD and correction notes

An existing FRD keeps its native document/revision identities. Actual previous approval identity
and timestamps are retained when it enters document control; no approval is invented. Existing
pending reviews require controlled confirmation before resubmission under the new procedure.

FRD preparation uses existing specifications, approved meeting information and uploaded documents.
Configured private local AI can extract source-linked requirement proposals. Without that service,
the fallback quotes explicit requirement statements and identifies unknown criteria for verification.
Approved requirements are retained. Nothing is silently removed from an approved baseline.

**Ask Chopper about this project** provides source-linked drafting and FAT guidance using the
recorded quality snapshot and exact document revisions. Questions run as background jobs and
previous answers remain available. The existing private local model is used when configured;
otherwise the interface explicitly identifies the response as recorded project guidance.
Answers are read-only and flagged when the project baseline changes. They cannot submit,
confirm, approve, execute tests or record acceptance on the engineer's behalf.

Use the FRD's **Prepare a functional flowchart in Project Intelligence** action for the existing
flowchart editor/service. A generated flowchart remains an editable engineering proposal.

Correction Notes summarize recorded issues, changes and native comparison/finding records.
When there are no recorded corrections, the engineer may choose **Not Applicable** and provide
a reason. The server rejects N/A when recorded issues or recognized correction findings exist.

### Tests, FAT and actual acceptance

Test/FAT drafts reuse approved requirement IDs, their stated expectations and acceptance criteria.
Configured FAT items supplement requirement-specific checks. Procedures are proposals for review.
Native validation runs are imported as original recorded facts, with their source identities.
Completion or a numeric score alone is never converted to a pass or physical test execution.

Engineers record an actual outcome, result/observations and existing evidence files. Identity and
recording time are automatic. An unknown physical execution time remains unrecorded rather than
being fabricated. The default procedure requires evidence for a pass. Mandatory failures,
unexecuted tests and inappropriate N/A decisions require correction or an authorized disposition.

FAT customer acceptance requires the actual customer decision, the representative named in that
record, the actual acceptance date and an existing acceptance file. Customer/project details are
prefilled when known. Signatures are retained in original uploaded records; the app generates none.

A new revision can reuse an execution by reference when both its exact test specification and FRD
baseline match. The original actor, outcome, result and recording identity remain unchanged.
Changed specifications invalidate that reuse. Customer acceptance is specific to its FAT revision
and must not be automatically asserted for a changed revision.

## Company controls

Open **Settings → Engineering quality & document control** as Admin.

Defaults:

- Company `PTPL`, department `ES`, team `PLC`.
- Pattern `{COMPANY}{SEP}{DEPARTMENT}{SEP}{TEAM}{SEP}{DOCTYPE}{SEP}{YEAR}{SEP}{SEQ}`.
- Separator `-`, document/year sequence, three digits starting at 1.
- Example `PTPL-ES-PLC-FRD-2026-001`.
- Revision labels `R01`, `R02`, etc.

Admin can change codes, separators, allowlisted numbering tokens, sequence scope/start/digits,
company timezone, revision format, company branding/logo, versioned templates, FAT checklist items,
default required stages and work-type procedures. Quality and authenticated closure decisions remain
required. Stage selections, evidence requirements, customer acceptance, independent review and
deviation procedures are explicit settings.

The server issues numbers while holding the existing WorkHub `BEGIN IMMEDIATE` transaction.
Sequences and globally unique issued numbers reside in the same database. Sequence starts apply
to a new sequence scope; changing settings never reuses or renumbers issued approved documents.
Every controlled revision retains its own label, template version and template snapshot.
Existing projects adopt updated company procedures explicitly with a recorded reason.

## Document control

The controlled stages reuse `pi_documents` / `pi_revisions` and existing project files.
FRDs are not duplicated into a parallel requirements system. Control metadata is additive.

Statuses: Draft, In Review, Correction Required, Approved, Released, Superseded, Rejected,
Archived. Approved/released/superseded/archived content is read-only. A new revision requires a
reason, keeps the same document number and preserves the original content, identity and decisions.
The latest approved native pointer remains the current approved baseline while a newer draft awaits
review. Only a subsequent approval supersedes the previous approved revision. A pending newer
revision still prevents representing a delivery as fully reviewed for closure.

Direct Project Intelligence writes/reviews/exports cannot bypass controls once an FRD is controlled;
the server directs those actions to Quality & Closure. Existing source documents, meeting processing,
diagrams, planning and engineering tools retain their existing paths. Approved MOM follow-up uses
the controlled FRD draft path when the project already has controlled requirements.

The audit records registration, changes (with versioned draft content history), human confirmation,
submission, review/approval, release, supersession, archival, deviations, customer authorization,
package generation and controlled downloads. Original approval actor/timestamps are preserved.

## Consolidated review and release gate

The prepared review includes document completeness/current revisions, approved requirement coverage,
tests, FAT, actual acceptance, native results, open issues, dispositions and approval history.
The assigned reviewer confirms six applicable checks, adds remarks when necessary and records a decision.

An approved quality document can advance the existing project's quality action when that action
belongs to the same reviewer and the original workflow conditions are satisfied. Existing planned
steps and roles are not automatically marked complete. Closure still uses the existing release action.

At project release the backend checks mandatory records, approved requirements, test/FAT coverage,
current FRD/review baselines, unresolved issues and authorized quality/closure approvals. Source,
context, procedure, engineering-step, document and native-result changes invalidate stale reviews.
Current native results are grouped by tool/source/target; previous iterations remain in history
without treating iteration volume as a performance penalty.

Deviations carry a specific finding fingerprint, reason, disposition, requester, independent approval
where configured and optional expiry. A changed finding or expired waiver does not silently reuse an
old decision. Authenticated quality and closure approvals cannot be waived. Approved issue dispositions
are honored by the existing release checks without falsely marking those issues resolved.

Previously closed projects keep their existing closure history. Missing historical documentation is
shown explicitly; the system does not create retrospective test results or approvals.

## Packages and customer release

Authorized quality approval queues internal/customer PDFs and prepares a closure draft. Authorized
closure approval can prepare another snapshot. The existing final project release queues a final
snapshot with the actual closure event. Pre-closure packages are labeled **closure pending**.

Internal PDFs include an index/bookmarks, company branding, document register, numbered approved
revisions, requirements/coverage, correction notes, recorded tests, FAT/acceptance, native validation
records, nonconformances, corrective updates, dispositions, approvals, audit trail and file manifest.
Exact archived validation JSON and bounded linked original evidence are embedded. Linked PDFs can
also appear as evidence appendices, while embedded originals retain their original bytes.

Customer copies use a separate projection. Only explicitly authorized approved revisions are included.
Attachments require explicit per-revision file authorization by the existing release approver or Admin.
Internal source excerpts, audit comments, raw tool data and unselected files are omitted. Internal and
ISO audit packs cannot be reclassified as customer evidence attachments. If no revisions have been
authorized, the customer PDF states that it contains no authorized document revisions.

Every registered package has its own audience/revision identity, manifest, baseline signature,
generation actor/time, SHA-256 and persistent file identity. New packages do not overwrite historical
approved files. Generation rejects a changed approved baseline or customer release authorization.
Unregistered preparation outputs cannot be downloaded as controlled packages.

Admins can select projects or a bounded package-creation date range in company settings to queue
an **ISO Audit Pack**. It combines original internal package revisions, bookmarks, embedded records,
an index and overall audit pagination. Direct file URLs also enforce administrator access for ISO packs.

## Runtime and limits

All state uses the existing `.usopp_workhub/projects.sqlite3` database and WorkHub blob storage.
Reuse the existing Linux/Docker persistent volume. No separate database, cloud AI destination or
new top-level module is introduced. Background jobs use existing durable leases, retry/cancel handling
and private local document/AI services.

The backend declares `tzdata` so company numbering and existing reminders have IANA timezone data
on Windows as well as Linux. See [Python timezone data sources](https://docs.python.org/3/library/zoneinfo.html#data-sources).

Local AI is optional via the existing private `USOPP_PI_LLM_URL` service. OCR/conversion remain local
and report a missing dependency when unavailable. PDF text needs a local font covering its characters;
set `USOPP_PDF_FONT` on the document worker where a suitable default font is unavailable.

Inherited bounded processing is explicit: original documents remain stored, automatic extraction
uses up to 20 selected files (100 MiB per document), and prepared source excerpts are bounded with
coverage notes. The full originals and exact source identities remain available. Controlled structured
content is limited to 8 MiB. PDF evidence embedding uses 25 MiB per linked file / 100 MiB per package;
larger native files remain hash-addressed references in storage. Native JSON embedding is bounded
at 100 MiB. ISO scope is at most 100 projects / 500 internal packages / 500 MiB of original PDF inputs.

## Implementation checks

- Python compilation and the WorkHub/Nami/Virtual PLC production builds were run.
- Static inspection checked literal SQL parameter counts.
- SHA-256 comparison covers 79 protected validation/Virtual PLC Python modules; none were changed.
- An online SQLite backup and source baseline were saved under `.build/quality-closure/` before changes.
- No automated feature tests, browser interaction tests or physical FAT executions were run.
- The local service was restarted: UI and API report 4.85.0, with frontend build integrity and
  the served entry script matching the production build.

PDF implementation references: [ReportLab indexed documents](https://www.reportlab.com/docs/reportlab-userguide.pdf),
[ReportLab PDF bookmarks](https://docs.reportlab.com/reportlab/userguide/ch4_pdffeatures/),
[pypdf PDF assembly](https://pypdf.readthedocs.io/en/stable/user/merging-pdfs.html).
