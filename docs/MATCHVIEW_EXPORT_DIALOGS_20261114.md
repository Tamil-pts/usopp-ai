# MatchView export dialogs - 14 November 2026

PLC PDF and project-folder exports now share one accessible dialog shell and the
same project-information fields. The desktop layout places project/source/review
details beside export options. Mobile stacks the panels. Header and footer stay
available while scrolling; native dialogs provide modal focus and Escape handling.
Export errors appear inside the dialog.

The common fields are project name, project ID, department, description,
objective/scope, base/reference, developed/compare, reviewed by and approved by.
Compared source names prefill from the current inputs. Entered reviewer/approver
names are printed metadata and do not create WorkHub approvals.

Project-folder **Reports / download** opens the options form before preparing a
report. PDF, HTML, Word and JSON format selections are retained, along with report
sections, control-name references and normally-visible/all-layer screen views.
Status presets include All, Differences, Modified, Added, Removed and Unchanged;
individual checkboxes remain available for custom combinations. Differences selects
exactly modified, added and removed files. The existing PDF comparison also retains
its explicit Needs review option and counts.

PDF, Word and HTML project-folder reports include the entered cover details. Word
now has the cover ahead of the comparison. PLC PDF comparison reports also retain
those fields in PDF, Word and HTML. Empty optional fields are omitted from MatchView
covers; generic report-cover behavior elsewhere is preserved. Description/scope
values are no longer silently shortened to 500 characters in PLC PDF exports.

CSV exports and marked source PDFs keep their existing purpose: filtered evidence
and annotated original pages respectively. They do not receive an extra report
cover. Source comparison, ignored metadata/comment settings, status classification,
paired highlights and source ownership/staleness checks are unchanged.

Verification: 26 targeted export/source-context/status/ownership tests passed.
Production TypeScript and Vite checks passed. Isolated browser checks cover both
dialogs, saved metadata/status selections, keyboard dismissal, reachable actions,
actual filtered PDF download and first-page metadata at 390, 760 and 1,440 pixels.
Artifacts: `.build/matchview-popup-tests.log`, `.build/matchview-popup-browser.log`
and `.build/matchview-export-popup-20261114/`.
