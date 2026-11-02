# WorkHub project creation and default FRD

The project dialog keeps four main steps: Basic Information, Requirements,
Workflow, and Review & Create.

Requirements opens with the original simple text entry. Detailed requirement rows
remain available through the entry-method selector. Acceptance criteria,
deliverables, attachments and optional project background/outcome are retained.
The symbol picker inserts symbols at the text cursor. Requirement identities stay
stable when switching between simple and detailed entry.

**Create an FRD from these details** is an optional selection, initially off.
**Create prefilled FRD** prepares the ten reference sections using the entered
project data. Its structured editor supports changes before project creation. The
same editable flowchart workspace is available when the FRD option is selected. **Save FRD
as project default** also saves the account draft, so reopening or reloading does
not discard the edited FRD. Final creation registers this document as the project's
FRD draft; attachment uploads then link to that same document. When the option is
selected, a prefilled draft is created even if the editor preview is skipped.
When it is not selected, files remain project attachments and no FRD is created.
Failed uploads resume against the already-created project.

The popup is rendered at the viewport level with a scrollable body and fixed
header/footer. **Enlarge** and **Restore** change its size. Tables scroll within
their own area; the project dialog, FRD and flowchart stay within the window.

Each workflow milestone has a visible active-user selector, along with editable
step details, dependencies and delivery phase. Saved project templates can include
requirements, criteria, deliverables, references, workflow assignments and a
diagram. Creating these reusable templates requires no approval.

The FRD includes document/project/customer metadata, objective, background,
expected outcome, included/excluded scope, requirement category/priority/source/
status, functional description, diagram preview/editor, deliverables, acceptance
criteria, additional information, attachments and the actual review/approval
record. Acceptance checkboxes confirm criterion wording; execution and customer
acceptance remain in the existing Quality & Closure records. Saving a draft does
not grant document approval.

PDF exports include the additional content and symbols. Approved PDF snapshots
remain immutable. Document Studio remains in Settings for template design;
project documents use the structured forms.

Verification uses isolated WorkHub data. Backend tests are in
`tests/test_workhub_workspace.py`, alongside the existing workflow, FRD and Studio
regressions. Browser evidence for this change is under
`.build/workhub-project-reference/`.
