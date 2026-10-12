# Build the Windows application

Run these commands in Windows PowerShell from the `usopp_ai_2.0` directory.

The build includes Nami PLC Data Verification V1.5 under **DataInspect**
navigation item. Both interfaces use the same backend and application port.
Use `-RebuildFrontend` when updating an older build to include Nami; no separate
Node server is needed on the target PC. See [Nami integration](nami/README.md).

## GitHub downloads

See [GIT_DISTRIBUTION.md](GIT_DISTRIBUTION.md) for private source/download repositories and the manual Windows/container workflow. After a portable build, create its downloadable ZIP and SHA256 companion with:

```powershell
.\.venv\Scripts\python.exe scripts/package_downloads.py --latest-windows
```

## Recommended portable build

```powershell
Set-Location "C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp_ai_2.0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\build_windows_exe.ps1" -RebuildFrontend
```

The executable is created at:

```text
release\windows-source-free\<build timestamp>\uSOPp_AI\uSOPp_AI.exe
```

Copy only the complete `uSOPp_AI` folder from the new timestamped release to the target computer. The target computer does not need administrator access, Python, Node.js, Vite, or npm. Do not distribute the workspace, `.build`, or older `release/windows` builds: those older builds included raw Python source.

## Optional single-file build

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\build_windows_exe.ps1" -RebuildFrontend -SingleFile
```

The single executable is created at:

```text
release\windows-source-free\<build timestamp>\uSOPp_AI.exe
```

The single-file version starts more slowly because Windows extracts its embedded runtime when the application and each engineering engine start. The portable folder build is recommended for large validation and comparison projects.

## LAN access

For the source workspace, double-click `Start_uSOPp.bat` for local access
or `Start_uSOPp_LAN.bat` for LAN access. Run `Stop_uSOPp.bat` on the server
laptop to stop the web server from this checkout. Finish active validations
before stopping. These scripts accept `-Port 8201` for a custom port.
To switch an already running local server to LAN mode, stop it first.
The stop script checks the process command before stopping it; unrelated
Python applications are not stopped. These batch files are for the source
workspace, not the packaged executable.

Close the running application first. For source development, run
`powershell.exe -ExecutionPolicy Bypass -File .\start_lan.ps1`.
For a newly rebuilt executable, start it from PowerShell with:

```powershell
$env:USOPP_API_HOST = '0.0.0.0'
.\uSOPp_AI.exe
```

On the other laptop, open `http://<server LAN IP>:8200`, for example
`http://192.168.19.240:8200`. Allow inbound TCP 8200 through Windows
Firewall for the intended LAN subnet. Use a trusted LAN: the app provides
access to project files and editing functions on the server.
Without `USOPP_API_HOST`, startup remains local to this computer.

## Runtime data

The packaged application opens in the default browser at `http://127.0.0.1:8200`. It stores writable application data without administrator access under:

```text
%LOCALAPPDATA%\uSOPp.ai
```

This folder contains logs, temporary workspaces, exports, editable knowledge data, rule modules and `accounts.sqlite3` (accounts and browser sessions). Keep this data folder when upgrading the executable.

Application ports are restricted to 8200–8500. `USOPP_API_PORT` selects the
production port (default 8200); optional frontend development uses 8201.
The PLC TCP port in PLC Settings is independent and must match the controller.
Nami Live includes shared light/dark mode and the corrected settings dialog.

## Accounts and shared Help

On the landing page, click **Explore demo** to fill username **demo** and password **demo**, then click **Sign in**. The demo session signs out automatically after 30 minutes. Obtain administrative credentials privately from the server owner. Existing account passwords are preserved across application restarts and upgrades using the same data folder.

**New user** creates a standard account with username, password, designation and company. All engineering APIs require a signed-in session. Password changes sign out the account's other browser sessions. The default is five regular users plus Admin. Uploaded project resources and saved test results belong to their user; Admin can review all users and history. Shared model settings and account administration are Admin-only. See MULTI_USER.md for concurrency and storage details.

Use **Help** below **Settings** at the bottom left for all five workspaces: **ByteMap**, **DataInspect**, **MatchView**, **LogicScan** and **Chopper**. Each workspace also displays its own Chopper guidance. The whole app, including login, remains on the configured application port.

Sign-in, registration and Settings password fields have **Show / Hide** controls. If the sign-in page reports that the server needs an update, finish active jobs and stop the running uSOPp process before relaunching the updated application. A frontend rebuild changes files on disk immediately, while an already running Python process keeps its original API routes until restarted. This mismatch caused `Method Not Allowed` on login/registration. The launchers now check account support before reusing an existing server, and the sign-in page offers **Check connection** after restart.

## Chopper chat and attachments

The portable EXE includes the unified Chopper chat and document readers. Use
AI Assistant / Chat and its paperclip to attach logs and metadata, or paste a
collected log. Decoded tables and simple-text results appear inside chat without
Ollama or a selected project. Feature shortcuts provide guidance across uSOPp.
PDF text, Word and spreadsheet previews are included; unsupported binary files
need a text export. Optional Ollama/model weights are installed separately.
Restart the updated app to load its new attachment API.

## Source visibility

The build compiles engine scripts to bytecode, bundles backend modules, disables frontend source maps, and audits the release directory for `.py`, `.pyw`, `.ts`, `.tsx`, and `.map` files. Current active rules and master knowledge are bundled as editable defaults. Rule archives, learning history, project knowledge caches and the local Automation Studio help installation are excluded.

This is a portable application build, not an installer wizard. Source-free packaging prevents opening the original Python/TypeScript files directly; it is not encryption. Python bytecode can be decompiled, browser JavaScript remains inspectable, and rule JSON remains readable. Stronger protection requires native compilation of sensitive modules or moving proprietary processing to a controlled server. Never embed secrets in a desktop release.

## Historical checks and optional maintainer verification

These commands and runtime results refer to earlier releases; they were not run for the current packaging preparation.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe check_api_surface.py
```

The API surface check uses temporary storage and exercises every route's empty-input/missing-resource handling. It does not establish correctness for every project or replace successful workflow tests. Its report is saved to `logs/api_surface_check.json`.

The 2026-10-05 PLC Data integration was checked with six local API/TCP
regression tests and browser checks for theme synchronization, Help, Save,
Cancel and simulator handshake. The portable executable was started on 8301
with isolated application data; its feature assets, metadata and simulator API
loaded successfully. Physical-controller reads and writes remain unverified.

The 2026-10-05 account/shared Help update was checked with five account API tests, browser registration/login/password-change/navigation checks, 76 API route checks and the packaged executable's Admin login and simulator handshake on 8301.

The historical 2026-10-06 portable build was `release/windows-source-free/20261006_070638/uSOPp_AI`, including the redesigned sign-in page, Show/Hide password fields and stale-server detection. The production frontend and Windows packaging builds completed; the restarted source server advertises the login and registration routes. Copy the complete folder and restart the app to use it.
## 4.61.0 local model and MCP additions

Historically verified 4.61.0 package: `release/windows-source-free/20261007_205107/uSOPp_AI_4.61.0_Windows.zip`.
Extract it and launch `uSOPp_AI/uSOPp_AI.exe`. Keep the complete extracted folder.
The packaged app passed sign-in, ladder HTML/PDF/Word exports, authenticated MCP,
local GGUF inference/start/stop, and embedded Project 2 metadata generation.

The Windows package includes `local_ai/runtime` (official llama.cpp CPU runtime,
license and checksum provenance). Keep the complete distribution folder.
No model weights, account data, API keys or project histories are bundled.
Choose a local GGUF in Settings to use Chopper without installing Ollama.
MCP runs inside the existing backend on `/api/mcp/`; the optional local model
defaults to loopback port 8202. See MCP_LOCAL_TOOLS.md for setup and checks.
