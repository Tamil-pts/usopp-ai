# WorkHub document actions and configurable project reports

Implemented 2 November 2026, using the existing uSOPp account and project permissions.

Document Management now gives every document row explicit **Edit** and **Delete** actions. This includes MOM, FRD, Validation Report, Test Report, FAT and Project Closure, whether independent or project linked. Authors and project managers retain their existing rights; a library reader cannot edit or delete another account's document. A closed project must be reopened before its documents can be deleted.

Edit opens the structured form. Controlled approved documents use the existing new revision action and require a reason. Native MOM saves also create revisions. Delete requires a reason and the current revision/version, removes the record from active lists and clears its active approved pointer. The archived record, content, revision identifiers, recorded approval evidence and frozen PDF snapshots remain available in history. An archived document cannot satisfy an active approval requirement.

Create Project includes custom project fields, with text, number, date and checkbox types. Names and types produce stable column identifiers. Values are validated and saved atomically with the project. Custom fields are also included in saved creation templates, which need no template approval. In Portfolio, use **Columns** to show fields and **Custom project fields** to update a project's values.

Portfolio's **Export Projects** prepares project management reports, separately from engineering documents. It offers XLSX, CSV, PDF and JSON; reporting scope; individual, team, project, status and delivery date filters; available and selected columns; ordering; optional file names; private saved views; and private export history. Team filters use configured organization membership. Project rows remain unique even when several team members are assigned. Billing hours total only approved time entries from the project and its tasks. PDF splits wide column selections into readable groups with Project Name repeated. CSV and XLSX neutralize spreadsheet formula text.

Export history records settings, timestamp, project count and the generated file hash. Reusing history settings generates a current report. Exports are downloaded immediately; no background scheduling or automatic messages are configured.

Team Management, Team Activity and Reports are removed from the Projects sidebar submenu. Existing team widgets remain available. My Work uses uSOPp typography and distinct blue, green and purple cards. WorkHub dialogs, tables and project windows use theme-aware surfaces in both light and dark mode. New dialogs support keyboard focus containment, Escape and small viewports.

Verification uses temporary accounts and storage through `tests/test_workhub_document_actions_exports.py` and the existing workspace, approval, dashboard and MOM regression suites. Browser artifacts are in `.build/workhub-project-reference/`: `document-actions-result.json`, `projects-browser.xlsx`, and the project export, My Work and custom field screenshots.
