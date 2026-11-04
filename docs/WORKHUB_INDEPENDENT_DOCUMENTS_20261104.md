# Independent documents, Flowcharts and Mind Maps

WorkHub's **Create Document** action creates an independent numbered document.
Choose FRD, Validation Report, Test Report, FAT, Project Closure, Flowchart or
Mind Map (the existing MOM, corrections and quality templates remain available).
An optional project link copies its identifying details into the document's
editable information fields. Editing those fields changes the saved document
revision, without rewriting the project's records.

FRD Document Information now supports editing the date, project name/number,
customer/reference, project type and base/developed references. The same editor
is available in the other controlled report forms. Issued document numbers,
revision identities and recorded approvals remain controlled system records.
Choose an independent reviewer in document settings and use the existing
confirmation, submission and review actions to record decisions. Changing saved
content invalidates its prior confirmation. In-flight reviewer changes are
rejected by the backend. Changing a document link updates its saved revision
content and clears confirmation, including when project prefilling is disabled.

Independent FRD confirmation no longer automatically creates validation, FAT
and closure documents. Independent document approval does not release or close
its linked project. Existing project delivery gates still apply to project work.
Existing project documents and historical approvals are retained.

**Document Management → Flowcharts / Mind Maps** opens each document type in
the common register. Their numbers use the existing allocator, with FLOW and
MMAP type codes, and have independent revision histories. A diagram can link to
an accessible project and a specific saved FRD revision. Linking does not grant
access to an otherwise private project or FRD.

The diagram workspace provides a shape palette, drag and resize controls, grid
snapping, connection handles, labels and line styles, colors, duplication,
Undo/Redo, arrangement, zoom/fit, a minimap and full screen. Mind Maps have a
central topic and an Add branch action. Save diagram creates a new revision;
the workspace also flushes its pending draft when navigating within WorkHub.
Exports include editable JSON, SVG, PDF and PNG. This is an in-app diagram editor;
Microsoft Visio VSDX import/export is not implemented.

Chopper uses an author brief and, when linked, the saved FRD revision to prepare
a bounded diagram proposal through the existing local model queue. The saved
diagram remains available during drafting. Model source IDs, geometry and graph
links are validated; changes to the diagram or source revision reject stale
application. The author reviews the proposal and applies it as a new draft
revision. Applying a proposal does not approve it or certify PLC behavior.

Validation artifacts are retained under
`.build/independent-documents-20261104/`.

TypeScript and the main production build passed. The final focused regression
suite passed 37 tests and covers document independence, saved metadata, private links, separate
reviewers, stale-proposal rejection, numbering, confirmation invalidation on link
changes, and existing project/workflow behavior. An additional 24-test document
and Studio compatibility run passed. Sixteen browser checks passed, including
FRD/FAT/validation/closure information edits, project prefilling, saved diagram
connections, shape resizing, Mind Map branches and Undo/Redo. Twelve viewport
checks covered 1600, 1067, 800, 760, 390 and 320 pixels in light and dark themes.

Actual installed local-transformer checks produced a three-node flowchart in
12.45 seconds and a three-node Mind Map in 21.47 seconds. These verify proposal
generation and structural/source-ID acceptance, not sequence correctness. The
local model can return malformed output; unsupported source IDs are rejected.
An exact duplicate edge record in the model's node array can be removed without
adding any nodes or claims; this normalization is recorded in the job result.

The local application was restarted with its supported launcher after idle-job
checks. Authenticated document-register requests for FRD, validation, FAT,
closure, Flowchart and Mind Map returned HTTP 200, and the new assistant route
rejected an unavailable scope. UI assets and API report **4.99.3**. The existing
53 projects and 34 accounts were retained; live verification used read-only
document requests and a temporary session that was revoked afterwards.

## Creation, menus and numbered downloads follow-up

The green **Create New** button now creates and opens the selected document,
including when its title is blank and it has no project link. The footer also
names the action explicitly, such as **Create FRD**. Flowcharts and Mind Maps
now pass through the navigation event whitelist and open their filtered lists.
Switching document workspaces resets the selected editor to the new document.

All ten Create Document types use their issued number in supported download
filenames: MOM, FRD, Correction Notes, Validation Report, Test Report, FAT,
Quality Review, Project Closure, Flowchart and Mind Map. The revision follows
the number, for example `PTPL-ES-PLC-FRD-2026-076-R01.pdf`. PDF, Word, JSON and
diagram SVG/PNG downloads share this convention. Existing originals keep their
uploaded filenames, and approved export bytes retain their existing snapshots.

Controlled forms now offer **Save document** and **Save & download PDF**. These
flush pending edits before saving/exporting the selected revision. Saving keeps
the issued number and does not record reviewer approval. Native MOM and diagram
editors retain their existing revision save controls and numbered downloads.

Follow-up verification: TypeScript and the main production build passed; 38
document/workflow/Studio compatibility tests and four final filename tests
passed. Filename tests exercised PDF, Word and JSON exports for all ten types,
unique number allocation, idempotent creation and leased queued native exports.
Eight browser checks passed, including both menu routes, the actual Create New
button, FRD saving and downloads. Eight light/dark viewport checks covered 1600,
800, 390 and 320 pixels. The downloaded FRD's text contained its latest saved
edits. Artifacts: `.build/document-create-fix-20261104/`.

After an idle-job check and supported restart, all ten authenticated document
register requests, existing FRD PDF export and current UI assets returned HTTP
200 on the local installation. UI/API remain **4.99.3**. The 53 existing projects
and 34 accounts remain present; the verification session was revoked.
