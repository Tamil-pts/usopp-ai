# WorkHub document editing and interface update

Checked on 4 November 2026 (Asia/Calcutta). This update keeps the existing
document numbers, saved revisions, optional project links and review authorities.

MOM now opens in the document workspace instead of a large nested modal. Meeting
details, participants, discussion topics, actions, follow-up and review have clear
section links. Discussion and decision fields have visible labels and separate
cards. Participant and action forms adapt to narrow screens. Saving preserves
the document number, retains editing mode and blocks competing edits during the
save. Discarding edits requires an explicit decision and waits for the saved
revision to load. Opening recording tools flushes pending MOM edits first.

Clearing a MOM decision now clears both its topic value and decision record;
old text is not used as a fallback for an intentionally empty field. Removing
a topic also removes its corresponding decision. Attachment completion merges
file IDs into the latest draft rather than overwriting intervening edits.

FRD uses a wider, sequential editing layout with section navigation. Document
information has labeled fields; project/reviewer settings and layout templates
are secondary controls. The **Additional engineering details** option is removed
from the FRD editor as requested. Existing saved sections remain in the document
record. The separate **Additional Information** section remains available.

Validation, Test Report and FAT provide **Cards** and **Table** views of the same
test cases. Cards expose the description, procedure, expected result and
acceptance criterion, with requirement links, evidence and actual-result actions.
Switching views does not create another set of cases. Actual outcomes still use
the existing execution-record API. Editing a specification does not fabricate
or preserve a matching pass for a changed test.

Duplicate objective/scope/conclusion editors have been removed. Editing the
primary field updates its corresponding saved section; clearing it remains an
intentional empty value. Summary and document-information editing were checked
for corrections, quality and closure as well. Independent documents no longer
offer unrelated report types from the project-stage selector.

The controlled-document toolbar puts **Save document** and **Save & download
PDF** first, with Word, preview, history and other actions under **More actions**.
Draft state remains visible. Read-only/review states and backend permissions
remain enforced. The API's native-document editing flag reflects current access,
including the restriction on a diagram reviewer editing the author's diagram.

## Diagram starter templates

Create Document and the canvas **Templates** control provide:

- Programming flowchart: inputs, a decision, processing and output.
- Process flowchart: work, review and a correction loop.
- System flowchart: interface, service, data and response.
- Navigation flowchart: entry, sign-in, workspace and destination pages.
- Project planning Mind Map: scope, people, milestones and risks.

Templates create editable nodes and connections. They are labeled starter
examples, with no project evidence or approval. Replacing an existing canvas
requires an explicit Apply action; Cancel, Undo and Redo remain available.
Saving retains earlier revisions and the issued document number. A template
does not establish the behavior of an actual PLC or machine.

## Verification

TypeScript and the main production build passed. Forty-seven distinct focused
tests passed across document editing contracts, template creation, numbering,
private access, diagram review restrictions, exports, Studio and existing
document/workflow behavior. Seventeen browser checks covered all ten created
document types, continuous typing/focus, save/reload, clearing fields, discard,
recording-tool navigation, Cards/Table switching and template revisions.
Twenty-six viewport checks covered desktop/mobile layouts, including MOM in
both light and dark themes. No browser page errors were recorded.

Artifacts are in `.build/document-ux-20261104/`. Browser writes used an isolated
test database. Existing local projects, users, approved records and PLC packet
validation source were not rewritten for these checks. UI/API remain **4.99.3**.

After an idle-job check and supported restart, authenticated register requests
for all ten types, the four-flowchart template catalog, an existing numbered FRD
PDF export and current UI assets returned HTTP 200. The local installation
retained 53 projects and 34 accounts. The verification session was revoked; the
isolated browser server was stopped and its fixture credentials removed.
