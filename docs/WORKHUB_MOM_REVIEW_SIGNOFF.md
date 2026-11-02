# WorkHub MOM and review sign-off

The default structured MOM follows the supplied reference: document number and revision, project and customer, date and time, meeting mode and type, objective, agenda, participants with role/organization and recorded attendance, discussion outcomes, action owners/dates/status, next meeting and approval identities. Existing transcripts, sources, clarifications and attachments remain available. Participant names from older MOMs remain readable; attendance is **Not confirmed** until entered.

The MOM form and PDF use these saved fields. Approved PDF source/layout snapshots retain their original revision and bytes. Configured document numbering remains in use. Preparing or copying a template does not approve it, record attendance, complete actions or create test results.

Workflow decisions and native/controlled document reviews open **Electronic Sign-off & Audit Stamp**. The options are **Approve & Sign**, **Request Changes** and **Reject**. Approval requires confirmation of the signed-in account name and an explicit review acknowledgement. Changes and rejection require remarks. These are authenticated account attestations; the UI does not claim certification under a particular electronic-signature regulation.

The expandable **Documents, reports & issues** area supports selecting exact document revisions, creating a MOM/FRD/report/FAT/closure draft, and recording an issue with an owner. New drafts use their existing document review process. A reviewer can add workflow evidence, but cannot remove or replace submitted revisions during review. Return the work for changes to alter that submitted evidence. Existing document, report, issue and phase gates still determine whether an approval can proceed. Project quality approval continues through its consolidated Quality Review.

Each explicit sign-off stores the authenticated actor, confirmed account name, assigned review role, server timestamp, decision and remarks. It also stores immutable snapshots of the reviewed subject/revision, selected documents and selected issues, with a SHA-256 evidence hash. Actor identity, role, timestamp and source hashes come from the server. Failed decisions roll back their stamps and workflow updates together. A workflow rejection is distinct in history and returns the work for rework with an issue; it does not cancel the project. Rejected MOM revisions retain their previous approved baseline.

Existing API integrations can still make ordinary review decisions. A review without an explicit `sign_off` payload does not receive an inferred signature stamp. Historical approvals are preserved as recorded.

Verification: `tests/test_workhub_mom_signoff.py`, the existing workspace/inbox/approval-document/report suites, and browser/PDF artifacts in `.build/workhub-project-reference/mom-*` and `review-*`.
