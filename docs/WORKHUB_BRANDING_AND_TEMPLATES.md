# WorkHub organization branding and document templates (4.88.0)

## Use

- **Settings → Users & Roles → Manage users**: create or edit the optional email ID. Personal users can also save their email under **My profile**. Account requests include an optional email field. Email is contact information; it does not authorize Microsoft mail delivery or change login credentials.
- **Settings → Organization Branding**: save a company profile, upload its logo, select header and separator colors, and configure company/address/department/team/header/footer. The initial codes are PTPL / ES / PLC. Set the default organization or select one per project.
- **Settings → Customer Master**: save customer details and optional logo once. Customer records can be archived through the availability checkbox; previous versions remain available in history.
- **Settings → Document Templates**: choose FRD, MOM, Correction Notes, Test Report, FAT, Quality Approval or Project Closure. Configure title, header/footer, paper/orientation, table style, logos, metadata, page numbers, signature labels and section order. Each save creates a version. The first active template of a document type becomes its shared default; an administrator can explicitly choose another default.
- **Project → Meetings & Requirements / Quality & Closure → Project document setup**: link the organization/customer and optional template overrides. The customer, machine, scope, project name, due date and existing review identities are reused in exports. Closed projects retain their existing editing restrictions.
- **Preview layout** uses clearly labelled sample data, including an illustrative flowchart. It creates no project results, document numbers, tests, signatures or approvals.
- **Prepare PDF** continues to use existing background jobs and project download permissions. Existing direct export APIs remain available. JSON, DOCX and SVG interfaces retain their supported behavior.

## Document and asset control

The existing WorkHub SQLite database stores append-only profile/template versions and decoded PNG logo assets. Logo uploads accept still PNG/JPEG/WebP files up to 2 MiB and 4 megapixels, normalize orientation, strip metadata by re-encoding, and bound the output dimensions. Assets have SHA-256 hashes and version numbers. Removing a logo from a profile does not delete its historical bytes.

The existing atomic document allocator still owns numbers, sequence scope and revision labels. A selected organization supplies the three prefix tokens for newly issued numbers; issued numbers and their original numbering snapshots are not rewritten. Patterns, sequence settings and approval procedures remain under **Engineering quality & document control**.

New approvals freeze the source revision, actual recorded content/results, organization/customer versions, logo hashes, selected layout version, Jinja source and rendering implementation hash. The first PDF is stored once in `wh_pdf_snapshots`; concurrent rendering retains the first successfully stored bytes. Repeated exports verify and return those bytes. A later profile, template, customer or color change does not replace them. An integrity failure stops the export rather than replacing the snapshot. An unrendered approval made with an older rendering implementation requires that implementation to produce its first PDF.

Approvals predating this feature have no historical layout snapshot. Their first capture is explicitly audited as a legacy capture; it does not claim that the new layout was present at their original approval. When a prior completed export records an approved source and its original PDF passes integrity checks, the existing PDF bytes are adopted. Its historical layout metadata is explicitly marked unavailable rather than attributed to a new template. Existing project files, exported blobs and closure packages are retained. The `pdf-snapshots/{revision_id}` project API exposes the saved manifest and hashes to authorized project readers.

Native MOM and other project document PDFs use the same view model and layout renderer. Existing closure/ISO audit compilations retain their existing appendices, customer projection, approved package files and release rules. Individual controlled closure and quality approval documents use the shared template engine.

## Rendering and security

The application ships a fixed Jinja2 HTML template. Administrators edit schema-validated configuration, not executable template source, CSS, JavaScript or SQL. Text is autoescaped; only server-generated, escaped flowchart SVG is marked safe. Preview frames are sandboxed. Chromium runs with JavaScript disabled, service workers blocked, offline mode and blocked requests; logos are embedded data images. No company content is sent to an external AI service.

The existing PDF worker lane limits concurrent jobs, execution time and memory. Install application requirements and Chromium on the worker:

```sh
python -m pip install -r backend_requirements.txt
python -m playwright install --with-deps chromium
```

The existing `deploy/intelligence/Dockerfile` installs Chromium in its shared worker image. `PLAYWRIGHT_BROWSERS_PATH` is set to a readable image location. No new container is required. The compiled container packager includes the Jinja layout assets. Existing installations without Chromium use the ReportLab compatibility renderer with the same frozen data/configuration, watermarks, flowchart and page numbering; the snapshot records which renderer produced its bytes. `USOPP_PDF_CHROMIUM` optionally selects an installed compatible executable.

The local sample artifact is `.build/workhub-branding/sample-template.pdf`. Python compilation, TypeScript compilation and the production frontend build were performed. No automated tests were added or run. Linux/Docker deployment was not performed in this Windows workspace.

Implementation references: [Jinja sandbox guidance](https://jinja.palletsprojects.com/en/stable/sandbox/), [Playwright PDF API](https://playwright.dev/python/docs/api/class-page#page-pdf).
