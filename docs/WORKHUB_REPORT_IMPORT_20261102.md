# Project report replacement and layout repairs — 2 November 2026

Imported `C:\Users\PTPL0241\Downloads\sample.xlsx` into the current installation after checking a separate staged database.

- Replaced the nine previous WorkHub projects and their linked task/document records with **53 report projects**. Cleared existing notifications and their delivery queue.
- Created **25 missing personal accounts**. Existing account passwords were retained. The initial password for new accounts was provided by the user through the import environment.
- Assigned **Sampathkumar A** and **Sasikumar T** the Delivery Manager professional role and team management membership. Assigned source engineers, quality reviewers and project delivery responsibilities.
- Created **212 linked draft documents**: FRD, Validation Test Report, FAT and Project Closure for each project, with document numbers and revisions from Settings. Each project includes the source workbook as an attachment and its exact row reference.
- Retained the source project statuses: 41 Completed, five Completed by Customer, four HOLD, two Customer Withdrawn and one In-QC. Historical completion is imported as historical status; it does not generate new approval signatures or test executions.

The report headers are shifted by one column relative to the data. Excel duration values were converted from day fractions to hours. The expanded `LMW-SOF-674` row contains conflicting In-QC/HOLD values; the aligned status was retained and the conflict recorded. Invalid dates and missing planning values use documented defaults. `LMW-SOF-717` reports 273 engineer hours and 84 total hours; both original values remain, with the discrepancy flagged in its fields and all four drafts. No source hours were converted into approved billing entries.

Technical wording and proposed acceptance/test cases are editable draft material. Actual test evidence, customer acceptance and sign-off remain pending where the workbook provides none. Independent document spaces, account settings and unrelated engineering source files were preserved.

Backups and evidence are in `.build/sample-report-import-20261102/`: the original workbook, normalized rows, created-user list, source issues, staged verification, PDF previews, database fingerprints and `pre-install-backup/`. Installation checks detect concurrent business-data changes and restore both database backups if the replacement fails.

The same update removes Three.js scenes and dependencies, restores the static landing image and standard sidebar, and repairs the Portfolio Columns selector. Its checkboxes no longer inherit search-input widths; the selector stays inside the viewport and scrolls vertically. Document Settings reflows to its panel width. Virtual PLC commands wrap at narrow widths, and its side panels collapse when the viewport becomes compact.

Backend logs identified missing hashed Portfolio/Praxis page files as a source of blank pages after rebuilding. The main build now retains previous page modules for existing tabs. A workspace error boundary displays an explicit reload action when a page cannot load. A browser test aborts a page-module request, verifies the recovery panel, and verifies that reload recovers the application.

Verification includes staged login and role checks, 53 project identities, 212 draft documents and workflow attachments, actual PDF exports of all four document types, live database integrity/counts, prior-asset retention, and desktop/mobile page checks at CSS widths representing 100–200% desktop zoom plus a 390 px phone viewport. No PLC logic, source, validation rules or simulated execution semantics were changed.
