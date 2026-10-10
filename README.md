# uSOPp.ai

Local engineering validation and project comparison for B&R Automation Studio projects.
The application version is defined in `package.json`. See [CHANGELOG.md](CHANGELOG.md) for the complete revision history and [ARCHITECTURE.md](ARCHITECTURE.md) for module ownership.

## Private GitHub downloads and containers

Follow [GIT_DISTRIBUTION.md](GIT_DISTRIBUTION.md) for separate private source and
download repositories, the manual release workflow and compiled packages.
Windows users can use the portable EXE without Python, Node or Docker.
For Docker Desktop / Ubuntu containers, see [installation commands](distribution/README.md).
Container data stays in a persistent volume; original application source is
omitted from runtime packages, but compiled code remains inspectable.

For one shared server reached over the existing LAN/VPN, follow
[the server installation and update guide](distribution/LAN_SERVER.md).
See [persistent storage and CPU AI](PERSISTENT_STORAGE_AND_CPU_AI.md) for SQLite,
retained rule/knowledge JSON and the included llama.cpp model setup.

## Ubuntu server deployment

Follow [UBUNTU_DEMO.md](UBUNTU_DEMO.md) for the complete server installation guide:
ZIP transfer, Node/Python PATH setup, Cairo prerequisites, application build,
port 8201, firewall/browser access, accounts, daily commands, troubleshooting,
backup and updates. The SpinConnect deployment reported Health: ready on
2026-10-09. Use the corrected Ubuntu source bundle for a fresh server.

## Microsoft Azure cloud deployment

Follow [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md) for the Microsoft 365/Azure
subscription distinction, Ubuntu VM setup, source ZIP, persistent accounts and
results, initial Admin password, systemd, HTTPS, updates and factory PLC routing.
Templates are in `deploy/azure/`. This uses the current app's accounts; Microsoft
365 sign-in inside uSOPp is a separate future integration.

## Start

Double-click **Start_uSOPp.bat**. The application opens at **http://127.0.0.1:8200**.
Normal startup uses the project-local Python environment and serves the built interface from the same server. It does not install dependencies or need a separate frontend server.

The old `uSOPp_ai_v4.30.bat` is a compatibility shortcut to the same launcher.

For a different port or a launch without opening a browser:

```powershell
.\start_usopp.ps1 -Port 8201 -NoBrowser
.\start_usopp.ps1 -CheckOnly
```

Paths are resolved from the launcher directory, so launching from another working directory is supported. If an unrelated or older service occupies the chosen port, close it or choose another port. Logs are in `logs/`; `logs/server_state.json` records the last launched process and port.

## Local project and metadata selection

1. Open **Validation → Project & metadata**.
2. Paste the full project folder or `.apj` path and click **Use path**, or use **Browse This PC**.
3. Optionally select an `.xlsx` or `.xls` metadata workbook the same way.
4. Run validation or generate metadata.

Local selection reads files directly on the PC running uSOPp; it does not use the browser file-upload control. Paths copied with surrounding quotes and `file:///` URLs are accepted. A browser-generated `C:\fakepath\...` is not a real file path. For network paths, the application must run under a Windows account that can read the share.

Browser folder/file upload remains an optional input method. Metadata may be local or uploaded with either project input method. Compare expects both projects to use local selection, or both to use browser upload.

The Validation summary shows the selected project and reference workbook. Generation uses purple progress feedback, validation uses blue, completed actions use green and errors use red.

Select a single Automation Studio root containing `Logical` or an `.apj` file. If a parent folder contains multiple projects, select the intended project explicitly.

## Pages

| Page | Functions |
| --- | --- |
| Home | Selected project and latest validation counts |
| Validation | Project/metadata selection; configured packets, offsets, metadata and dropdown checks; generated/uploaded workbook viewing, editing and XLSX export |
| Compare | Independent base/developed project selection, progress, differences and JSON/PDF/Word/HTML exports |
| Rules | Engineering checks and assisted rule configuration using the project selected in Validation |
| Chatbot | Questions about the current validation evidence |
| Settings | Theme, metadata columns, table widths and approved knowledge mappings |

Workbook edits survive worksheet and page switches. **Save copy** and **Export XLSX** preserve every worksheet. Source workbooks are not overwritten. **Use for validation** explicitly selects a saved workbook as the next reference. Save unsaved edits before changing project or workbook inputs; page refresh discards in-memory results and unsaved drafts.

Under Settings, choose **Auto width**, **Fit to window**, or **Custom width**. Table widths recalculate when metadata columns are hidden or shown. Wide tables have horizontal scrolling.

## Data and reports

- Customer PLC source files are read without modification.
- `.usopp_workspaces/` stores operation sessions, uploaded inputs, reports and results.
- `.usopp_exports/metadata/` stores generated metadata and edited XLSX copies.
- `knowledge/master/` and `knowledge/projects/` store explicitly approved mappings.
- Reports and workbook sessions are retained; clearing displayed results does not delete them.

The Python v1.71 engine determines engineering results. AI assistance explains evidence and proposes rules or mappings. Self-training and automatic PLC changes are not implemented.

Obsolete backups and separate historical revision files were moved to `../usopp_archive_20260924/`. Customer workbooks, knowledge files and reports were retained.

## Setup / development

Run setup once if dependencies are missing, or after changing source files to rebuild the interface:

```powershell
.\setup_usopp.ps1
# If portable runtimes are not on PATH:
.\setup_usopp.ps1 -PythonPath 'C:\Tools\Python\python.exe' -NodePath 'C:\Tools\Node\node.exe'
# Repair dependencies if required:
.\setup_usopp.ps1 -Repair
```

Setup accepts runtimes in `.runtime/python/` and `.runtime/node/` and can reuse the previous Node selection from `usopp_paths.bat`. The `.venv` is always resolved relative to the current application directory. Moving the application to another PC may require recreating `.venv` with that PC's Python installation.

For development, run `python server.py` and `npm run dev` separately. Vite uses localhost:3200 and proxies `/api` to localhost:8200. Both ports can be configured with `USOPP_API_PORT` / `USOPP_FRONTEND_PORT`.

Copy `.env.example` to `.env` to configure a local Ollama assistant. The launcher reads `.env`; no remote AI service is required for validation or comparison. Without a configured model, the assistant reports its local fallback and rules can use supplied templates.

## Checks

```powershell
npm run build
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Regression checks use temporary projects and mocked engine execution to check API orchestration. Real project checks and browser evidence for this revision are recorded in `logs/functional_checks.json` and `logs/browser_checks.json`. Engineering FAIL/WARNING results in those reports are findings from the selected PLC project, not application test failures.
