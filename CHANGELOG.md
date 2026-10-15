# Revision history

Current application version is defined in `package.json`; the backend reads that value.
Engine and rule schema versions are independent of the application release.

## 4.65.14 - 2026-10-15

- Refresh the landing page and WorkHub with the requested engineering copy, connected tool navigation, a four-step workflow guide and saved engineering activity. Admin sees activity across users; regular users see their own 7/30-day activity. Keep the old project and validation KPI cards removed.
- Build Chopper machine summaries from the selected project's enabled routines, parsed operations, function calls, branch conditions and source evidence. Preserve project-specific differences instead of using a fixed machine-function list.
- Correct DataInspect reference aggregation and case-insensitive matching. Report conflicting JSON/workbook datatypes as unresolved reference conflicts, retain genuine mismatches and keep different group-code requirements separate. Preserve source evidence and archived reference context.
- Audit container packaging to omit original application Python/TypeScript source and frontend source maps. Preserve private source tracking for release builds; compiled bytecode remains reversible. Existing host source folders require separate cleanup.
- Development verification: both frontend builds, focused regressions and isolated browser checks passed. Physical PLC traffic and live model generation were not exercised by the workspace browser checks. Container build artifacts are prepared separately by the release workflow.

## Development updates - 2026-10-12

- Add an Admin-only Settings tool to export/import shared engineering knowledge in a versioned ZIP. It carries parameter and project mappings, edited knowledge, rules, engineering learning/feedback, imported DataInspect models and machine-prefix configuration, with optional B&R help sources. Import validates paths, makes a pre-import copy of replaced files, overlays matching files without deleting production-only files, and reports imported files. Model weights, users, results and PLC uploads are excluded.
- Move machine/department list and `.apj` prefix detection into a shared Admin-managed configuration. Existing built-in mappings remain the defaults; future machine prefixes can be added from Settings and are used by all users.
- Add permanent deletion for regular accounts. Admin and the fixed demo account cannot be deleted; deleting a regular user revokes sessions and removes their saved settings, history and owned workspaces.
- Bump the application version to 4.65.13. No model fine-tuning occurs on export/import; approved engineering observations remain retrieval data unless separately used in an offline training run.

- Add demo / demo sign-in through the landing page's Explore demo action. Enforce a fixed 30-minute demo session in the server cookie/database and return its expiry for automatic browser logout. Use a separate namespace for each demo login; retain five regular-user slots plus Admin, restrict demo shared-configuration writes/server-file access and keep its fixed credentials out of account password editing. Remove Admin password values from the published installation guides. Implementation added on 2026-10-12; no tests were requested for this change.

- Document the confirmed source/download repository URLs and direct SSH/SCP installation from workflow artifacts. Refresh the public README/LAN guide and the local container-launcher ZIP. Compile the updated Python account modules, rebuild the main/DataInspect interfaces and restart the local development server. No container image or portable EXE was rebuilt locally for these changes.

- Change public registration to create pending account requests. Admin can review and enable requests from WorkHub / User management; pending users cannot sign in and do not use the five regular-user slots. Add request status feedback and a refresh action for Admin.
- Add a reduced private container build bundle for building on Ubuntu without GitHub. Include all runtime knowledge inputs required by the container compiler, fix Windows CRLF in generated SHA256 files, and document the local SCP/build/install steps. The bundle is 4.3 MiB; it excludes uploaded projects, B&R help source, models, training data, dependencies and runtime databases. The Ubuntu image still needs to be built on the destination server.

## Development fixes - 2026-10-11

- Fix Module serial no mapping when the backend runs the rule engine as a script: support the project-info import without requiring the python_engine package on the script path. Exclude Power Panel interface accessories such as 4PP065.IF23-1 from controller/serial inventories; retain target-ownership failures for actual multiple controllers.
- Verify Project 2 and Project 3 through the real local validation API with isolated accounts, workspaces and SQLite history. Project 2 has 33 passing checks and one missing PLC1 SerialNumber binding; Project 3 passes all 125 checks. Confirm separate test IDs, history retrieval and database archiving. All 22 related regression tests pass. Record the source evidence and limitations in MODULE_SERIAL_MAPPING.md. Packaged Windows/container releases were not rebuilt.

## 4.65.12 - 2026-10-10

- Make the optional reviewed Chopper adapter trainer CPU only by default. Preserve --device cpu compatibility; reject GPU selection, use float32, disable GPU visibility, limit compute/tokenizer threads and record CPU threads/precision in the run manifest. Existing llama.cpp inference already uses zero GPU layers.
- Add Windows and Ubuntu CPU PyTorch installation commands and a two-thread training example. Explain that a separate virtual environment separates dependencies but shares host CPU/RAM; use another CPU computer or off-hours on the shared server. Training remains an explicit offline step using reviewed examples; no new weights have been trained.
- Python compilation, both TypeScript compilations and both production frontend builds pass. Refresh the portable Windows EXE and compiled container staging; their raw application source audits pass. No actual training, inference, browser or Docker runtime tests were run.

## 4.65.11 - 2026-10-10

- Add backend engineering task guides for machine functions, communication, RS485/serial review, source lookup and improvement candidates. Normalize common request spelling without rewriting quoted identifiers or source paths. Add communication/RS485/improvement prompt shortcuts.
- Cache compact literal call/assignment/branch/serial-setting records with the selected project index. Resolve ST instances in their declaration scope, recognize B&R TCP/UDP/ICMP/Modbus/DVFrame families, retain enabled ladder block types, trace nearby settings/status and sibling initialization values, and supply bounded source evidence. Separate physical RS485 from protocol, active configuration from live connection, and review candidates from proven defects. Custom/indirect wrappers and complete control-flow semantics remain unresolved without further source review.
- Save source-backed Chopper replies as private pending Q&A drafts in persistent `application.sqlite3`. Add KnowHub **Project answer training**: users see their drafts; Admin can correct, approve/reject and export shared training examples. Include original informal questions, source/help excerpts, source/evidence fingerprints, reviewer and revision checks. Approval validates citation identity and still requires engineering review. Preserve drafts across upgrades with the existing persistent data volume.
- Add an optional offline LoRA trainer and separate dependency file for the original Qwen2.5-Coder 1.5B model. Require reviewed examples, deduplicate, hold out project groups, mask prompt tokens, preserve complete answers, and record interrupted/completed runs. It does not train during app startup, change the serving GGUF, or publish source data. Ship task guides/training instructions in Windows and container runtimes. No new model weights were trained in this implementation.
- Python compilation, both TypeScript compilations and both production frontend builds pass. Refresh the portable Windows EXE, download ZIPs and compiled container staging. No browser, live inference, actual training or Docker runtime tests were run; the optional trainer is compiled but its training path has not been exercised here.

## 4.65.10 - 2026-10-10

- Add `knowledge/help_index/BR_PROJECT_HELP.md`, one readable guide with contents, decoder steps, structured record examples and syntax references. Its 31 JSON topics cover ST, Automation Basic, C, ladder topology/rendering, HMI pages/layers/text/snippets/bitmaps/alarms, global/local variables, arrays/types, RETAIN/permanent storage, libraries, hardware, I/O and active task/configuration ownership. Include AS 2.7 layouts and source editing limitations. All guide source pointers resolve in this checkout.
- Generate a persistent offline SQLite full-text reference index from the supplied B&R collection. Scan 135,466 supported text files; index 127,120 vendor topics and 31 authored guide topics. Record 8,344 files with no extracted text and two files above the 5 MiB limit as skipped; flag 27 topics at the 100,000-character extraction limit. Keep source inventory, digests, categories, library identifiers, help-set labels and original images. The completed index is 341.8 MiB; original documentation remains unchanged.
- Add KnowHub's **B&R help index** with guide contents, category search, topic text/images, coverage/progress and complete guide download. Admin can rebuild the shared index in the background; the completed index remains readable during rebuilds. A missing or outdated guide index is prepared at startup. Ship the compact guide in Windows/container runtime packages; keep the large vendor corpus and derived index in persistent server data.
- Retrieve bounded B&R guide/library evidence for Chopper with separate `[H1]` references and visible help excerpts. Preserve `[S1]` project references, ownership and citation checks. Provide local reference excerpts when the optional model is unavailable. Documentation explains syntax/library contracts; it does not prove a project executes that logic or establish runtime compatibility. This retrieval does not train new model weights.
- Share temporary/generated directory exclusions across comparison, project knowledge, upload handling, snapshots, rules, declarations and HMI/metadata discovery. Prune project scans before descent where shared walking applies, preserve target scope, and reject linked paths outside the selected project. Do not apply project folder exclusions to vendor documentation topics.
- Python compilation, both TypeScript compilations and both production frontend builds pass. Generate the reference index and read its inventory/coverage; no browser, live model inference or Docker runtime checks were run for this change. Refresh the portable Windows build and compiled container staging with compact guide data and source audits.

## 4.65.9 - 2026-10-10

- Give Chopper a default 30-minute model response window, configurable in Settings. CPU queue waiting and answer generation share it; project indexing remains separate. Preserve per-request messages and independent validation workers. Compact the model context JSON, expose the CPU answer token limit, and distinguish model readiness from a user-requested short reply check. Log timing/token metrics without storing prompts or answers.
- Explain citation failures separately from feature availability. Accept supplied source IDs or supported file:line citations; retain rejection of unknown paths, IDs and unsupported line numbers. Log the specific rejection reason. For feature-presence questions, prioritize matching executable source and show literal calls, declaration locations, active task ownership and related HMI bindings. Rebuild the source index with the updated retrieval schema.
- Existing runtime logs show CPU prompt reading plus generation exceeding the previous 60-second cutoff. New inference, browser and Docker deployment checks have not been run for this change.
- Python compilation, both TypeScript compilations and both production frontend builds pass. The Windows EXE builds and its raw-source audit passes; compiled container staging is prepared with the same audit. Refreshed Windows/launcher ZIPs and SHA256 companions are prepared for 4.65.9.

## 4.65.8 - 2026-10-10

- Fix the blank DataInspect page caused by shared workspace components resolving a second React copy from the parent package. Deduplicate React and React DOM in both frontend builds. Add a visible startup message and a render error panel with reload and error details; preserve saved targets, metadata and history.
- Make the assistant welcome page, conversation, composer, tabs and prompt buttons inherit the workspace's common light/dark colors and selected accent. Keep the requested #073B4C sidebars. Add a shared theme switch in the app header.
- Both TypeScript compilations and production frontend builds pass. The rebuilt DataInspect bundle contains only React 19.2.8, removing the extra 19.3.0 copy. The Windows EXE builds and compiled container staging passes its raw-source audit. Refreshed Windows/launcher ZIPs and checksums are prepared. Browser behavior and Docker deployment have not been tested.

## 4.65.7 - 2026-10-10

- Add persistent per-user SQLite settings for saved PLC targets, metadata, manual-frame templates, report covers and UI preferences. Hydrate before opening either frontend, migrate surviving browser records without overwriting server settings, retain deletion tombstones, and reject conflicting stale writes. Surface pending/error saves with retry and unsaved-settings recovery.
- Archive full test results and owner/test IDs in SQLite alongside compatible JSON/files; adopt earlier history without changing identities. Keep rules, Knowledge Hub and learning evidence in their existing persistent JSON/JSONL schemas.
- Add pinned Qwen2.5-Coder 1.5B Instruct Q4_K_M CPU setup with background download, size/SHA256 verification, progress, offline-copy support and persistent weights. Add bounded CPU answer length, independent five-request queue, CPU thread settings and optional startup loading through llama.cpp; no Ollama dependency.
- Add a pinned Linux llama.cpp CPU build to the container and include model license/card in Windows and Linux packages. Add explicit LAN binding, full-volume backups before updates and checksum-checked restore to a new empty volume. Replace the unpublished Internet-tunnel draft with the agreed LAN/VPN instructions.
- Checks and limitations: Python compilation, both TypeScript compilations, both production frontend builds and PowerShell/shell syntax pass. The Windows EXE builds and contains the new storage/model modules and bundled runtime; compiled container staging passes its raw-source audit. Windows/launcher ZIPs and checksums are prepared. The small CPU model downloads successfully and passes its pinned size/SHA256 check; local configuration is saved for the next app restart. Destination Docker build/run, backup/restore, five-user load, inference and live PLC routing remain unverified; no runtime tests were run.

## 4.65.6 - 2026-10-10

- Add GitHub Desktop publishing instructions for the installed client and prepare a separate local downloads repository containing only installation documentation and ignore rules. Keep source and end-user repository access separate.
- Clarify Windows Docker Desktop installation and hosting responsibilities: GitHub Pages can serve a static information/download site, while the complete uSOPp application needs its Python backend and persistent data on a PC or server.
- Prepare private GitHub source and separate download repositories, a publishing helper and a manually triggered Windows/container build workflow. End-user assets contain compiled application packages and installation instructions; source ZIPs, credentials, accounts, uploads, results, logs and model weights are excluded.
- Add a multi-stage Linux amd64 Dockerfile with application bytecode, a non-root runtime, one backend worker, five engine slots, six accounts and persistent data. Add Windows/Ubuntu install/start/stop/status/log/update launchers, initial Admin password files, localhost browser binding and retained volumes on upgrades.
- Add source-file audits, ZIP/checksum packaging, adjacent-bytecode engine execution and release/install documentation. Bytecode and frontend JavaScript remain inspectable; this is packaging, not encryption. Linux containers use a separately configured model service rather than Windows llama binaries.
- Build checks: changed Python files and PowerShell/shell syntax compile/parse; both TypeScript checks and both production frontend builds passed. The Windows portable EXE and 73.7 MiB ZIP built successfully; runtime staging, ZIP contents, checksums and staged private-artifact audits passed. Original knowledge reference bytes are preserved in Git. No runtime/browser tests were run. GitHub is not authenticated and Docker is unavailable on this PC, so remote creation/push, Actions and Docker image build/run are pending.

## 4.65.5 - 2026-10-10

- Prepare an Azure Ubuntu VM deployment guide, systemd service and Caddy HTTPS proxy configuration. Keep six enabled accounts (five users plus Admin), one backend process and five engine slots; place accounts, private inputs, results and history under a persistent data root outside application source.
- Add an offline initial Admin password prompt and service startup check. An optional USOPP_INITIAL_ADMIN_PASSWORD seeds only a new Admin; existing passwords are preserved, and local demo defaults remain compatible. The cloud service refuses the known local-demo password.
- Add a fresh cloud source-bundle command that excludes local accounts, private workspaces/reports, installed dependencies, model settings/weights and the large local B&R help archive. Include current department data models and engineering defaults. Document Azure billing, browser uploads, backups/updates and factory VPN requirements for live DataInspect; Microsoft Entra sign-in and source concealment remain future work.
- Build checks: changed Python files compile, both TypeScript checks and both production frontend builds passed. No runtime/browser tests were run. Azure provisioning, HTTPS, systemd/reboot behavior, cloud load and live PLC routing have not been verified on a destination server.

## 4.65.4 - 2026-10-10

- Refresh the sign-in/create-account landing page using the supplied visual direction: an industrial hero image, PLC engineering headline, green accents, platform overview and directly available account form. Keep uSOPp/Petrus branding, account creation, password visibility and server-connection recovery; support narrow screens and the saved dark theme.
- Restyle Chopper with a dark engineering-assistant header, context banner, spacious welcome view, useful prompt cards and a clearer composer. Show real selected-project context; retain chat attachments, source evidence, processing time, log decoding and existing feature actions. Keep model connection details behind the Admin role.
- Set the shared navigation sidebar and Chopper sidebar background to #073B4C, with readable navigation text and visible active/keyboard-focus states. Add the generated industrial image as a bundled local asset; the app does not depend on a remote image URL.
- Build checks: both TypeScript checks and both production frontend builds passed. Browser testing was not run. This release has not been deployed to the Ubuntu server.

## 4.65.3 - 2026-10-10

- Ignore uppercase/lowercase differences in DataInspect parameter names while retaining strict word/punctuation, datatype and Group Code checks. Map DrawFrameFinisher to Finisher and DrawFrameBreaker to Breaker; keep their requirements separate and reject imports declaring a different department.
- Store 23 fixed department models under knowledge/data_models/PMS, QMS and CMS in the supplied controleCode/keysList database JSON format. Split mixed-service collections into their own services, preserve database keys and raw flags, and retain original JSON/Excel sources with hashes and worksheet/row evidence. Prefer service-specific database JSON; use embedded service collections before workbook fallback.
- Exclude the mislabeled QMS/JSON Keys V1/DRAWFRAMEBREAKER.json (its controleCode and collections identify Finisher). Use the correct Breaker QMS collections from PMS V5 and retain a source warning. Keep earlier catalog IDs accessible for saved history; personally imported references remain private.
- Check fixed references automatically when metadata loads. Group the frontend column as parameter name, PMS/QMS/CMS and Pass or the failure reason. List unavailable expected parameters even without a metadata row. Keep calculated, optional, incomplete and server/host fields distinct; let users save a check to history and download the original database JSON format.
- Include automatic requirements, missing parameters and service/source evidence in verification Excel/JSON exports. Update Help and knowledge documentation. Deployment requires the updated knowledge folder, rebuilt frontends and a backend restart.
- Build checks: Python compilation, both TypeScript checks and both production frontend builds passed. This release has not been deployed to the Ubuntu server.

## 4.65.2 - 2026-10-10

- Set the default capacity to five regular users plus Admin (six enabled accounts total). Keep USOPP_MAX_USERS as the total account limit; deployments with an explicit value of 5 should change it to 6. Show the regular-user count separately in User management and update Help/deployment guidance. Existing accounts and saved results are preserved.
- Extend isolated concurrent-engine, report, browser, DataInspect and ownership checks to all six accounts. Five project engines run together; a sixth waits safely for a slot. Check concurrent registration and Admin creation against five regular-user slots.
- Verification: all 156 regression checks passed, including 16 concurrency/browser checks and 85 retained runs from five regular users plus Admin across a backend restart. Python compilation, both TypeScript checks and both production builds passed. The six browser profiles also verified the regular-user capacity display. The running server and earlier demo packages require an update/rebuild/restart; physical-PLC and Ubuntu-server load testing remain pending.

## 4.65.1 - 2026-10-10

- Correct duplicate Admin history entries caused by read-only history-view workspaces being scanned as earlier runs. Keep data model validation pass/fail counts in the saved result and history. Move imported-model parsing and JSON writes to the thread pool so other users' requests can proceed.
- Add five-account checks using an isolated live server, real packet/metadata/rule/comparison engines, concurrent reports, private uploads and results, per-account data models/simulators, mixed tools, source-edit protection and a loopback TCP controller. Exercise five independent browser profiles through Run validation and saved DataInspect views; retain accounts, results and downloads across a backend restart.
- Update MULTI_USER.md and the Ubuntu guide with verified behavior and deployment limits. Existing accounts/data and the running Ubuntu installation are not changed automatically; this source release needs rebuilding and a backend restart.
- Verification: all 155 regression checks passed, including 16 concurrency/browser checks and 71 retained five-account runs across a backend restart. Python compilation, both TypeScript checks and both production frontend builds passed. The loopback tests do not establish physical-PLC or Ubuntu-server throughput.

## 4.65.0 - 2026-10-09

- Add a configurable limit of five enabled accounts including Admin. Enforce registration, Admin creation and re-enabling in SQLite transactions; show capacity in User management. Preserve existing accounts, password hashes, roles and over-limit installations.
- Replace the single global validation lock with five concurrent engine slots and per-project locks across packet validation, metadata generation and rule validation. Serialize comparisons using both source projects; prevent source saves/cache cleanup during active or queued processing.
- Give each DataInspect read, connection test, Run All, manual decode and RTC/raw transmission a unique test ID and owner. Archive the target, exact metadata, raw packets and decoded values; retain failed and interrupted runs. Save data-model checks in history as well.
- Show all users' DataInspect, ByteMap, LogicScan, MetaWorks and MatchView records in Admin WorkHub history. Regular users see their own tests. Add activity/user/status/search filters, explicit test IDs, archived JSON/Excel/report downloads, and read-only DataInspect reopening. Include per-group test IDs in collected Excel and JSON reports.
- Persist workspace/export ownership and enforce access to sessions, results, downloads, source reads and reuse. Store browser selections/preferences and simulator state per account; preserve Admin's earlier browser preferences. Keep real-PLC request serialization.
- Retain project snapshots, comparison source/HMI/ladder details and each prepared HTML/PDF/Word report version with its test. Cache clearing retains results and skips other users' sources. Honor USOPP_DATA_ROOT for source launches and packet-engine knowledge references.
- Document capacity, history, storage and Ubuntu update commands in MULTI_USER.md, ACCOUNT_COMPATIBILITY.md, Help and UBUNTU_DEMO.md. Python compilation, main/Nami TypeScript compilation and both production frontend builds passed. This source release requires a rebuild/backend restart on the deployed server; prior demo ZIPs/EXEs are unchanged. Five simultaneous browser sessions and the Ubuntu deployment of this release remain unverified.

## 4.64.8 - 2026-10-09

- Correct Sheet2 alarm captions for projects that use individual BIT_SET assignments instead of FOR loops. Read the selected HMI and VCShared alarm groups, retain configured IndexMap/ImageOffset and the exact source buffer/byte/bit. Report duplicate bit assignments and retain both captions in one Sheet2 bit entry. Verify MO_5102 against its shared MBO_Alarm.algrp: all 22 captions restored across 21 occupied bits; only three unused bits remain NA. Ten focused alarm regression checks passed. Existing executables/server copies need the updated engine.
- Show source parameter names directly in DataInspect's Data model column, with service/sheet captions such as PMS Shift live. Automatically load the current machine's supplied workbook/JSON references, retain source files/rows and all versions, and narrow to a source when selected. Keep name differences visible, skip server fields and include reference names/provenance in Excel/JSON exports. Backend Python compilation, main/Nami TypeScript compilation and both production frontend builds passed.
- Add a Data model check column beside Parameter Name in DataInspect. Show expandable expected name/type/group and source details using the existing model validator; retain results when the model window closes and clear them when metadata, machine or reference changes. Mark unlisted parameters separately and retain missing requirements in the complete model view. Include check results in verification Excel/JSON, with a separate Excel requirements sheet for missing fields. Update Help; main/Nami TypeScript compilation and both production frontend builds passed.
- Add AS 2.7 discovery for the supplied layout: select the sole user Physical configuration without LastUser.set, exclude support folders, and resolve pgm/<project>/CPU for MatchView, Chopper and serial mapping scope. Read the HMI MasterPanel type from active hw.cfg separately from the PLC type; show HMI type and legacy source path for local/uploaded folder summaries. Retain the existing VCShared alarm fallback and document the layout in AS27_PROJECT_LAYOUT.md. Source inspection only; this patch has not been built, tested or repackaged.
- Expand UBUNTU_DEMO.md into a complete deployment guide for another server: transfer, prerequisites, Node/Python PATH, install, port/firewall, accounts, daily commands, reboot, troubleshooting and data-preserving backup/update steps. Record the user's successful SpinConnect deployment on 192.168.19.10:8201 with Health: ready; Docker occupies port 8200. Repackage the source bundle with the current guide and build fixes. A fresh install of this corrected bundle on a second server is pending.
- Correct the clean Ubuntu build order: install Nami dependencies before the main TypeScript build, which imports Nami's xlsx metadata parser. Approve the locked esbuild install scripts in both projects for newer npm versions. Document Python 3.12 environment setup, Cairo/pkg-config prerequisites and recovery commands for the original Ubuntu demo ZIP.
- Add an Ubuntu source-demo launcher with install/start/stop/restart/status/logs commands and equivalent npm shortcuts. Use a separate .venv-ubuntu and verify PID/start identity before stopping the server. Document prerequisites, browser access and updates; Linux source-free packaging is deferred.
- Keep identical-content data-model files separate by source filename, service and machine. Preserve their content hashes for provenance instead of merging the two DrawFrame QMS JSON references.

- Parse unchanged ladder files and load their diagrams on demand. Rebuild diagrams for older saved comparisons from retained source/declarations. Open .ld files in the explicit Ladder diagram view by default; unchanged files initially show every network. Keep source XML and source differences as separate choices, and include selected unchanged diagrams in HTML/PDF/Word reports.
- Support older ladder XML with type-less function-block headers/continuation rows: infer the type from the same-column top row and retain one continuous block and its instance. Upgrade saved models during rendering; advance diagram/report cache version.

- Add a Screen preview Control selector for every paired control, including unchanged controls and hidden layers. Clicking overlapping objects shows Controls at this point, so a hotspot cannot prevent access to dropdown or numeric properties. Keep source positions and draw order; support source-coordinate hit testing at every zoom.
- Add report section/status checkboxes before comparison or when preparing another report: Logic, Screen, Project/configuration, Hardware and Project knowledge base; modified, added, removed and optional unchanged files. Filter before resolving report details and include selections in the background-job cache identity.
- Add linked HTML contents with a resizable navigation sidebar and PDF contents links/bookmarks. Add a draggable/keyboard-adjustable comparison tree divider, persistent tree width and compact object icons/expansion. Skip .pkg and .prg files in comparison differences while still reading package descriptors for project object order/descriptions.
- Add DataInspect data model requirements: browse bundled PMS/QMS/CMS workbook/JSON versions, import new XLSX/JSON, check exact parameter names, datatype and group code against loaded metadata, and download model/check JSON. FLOAT maps to REAL; NCHAR/VARCHAR map to STRING. Skip the requested server IDs/timestamps; show formula fields separately. Missing reference names/types/group codes remain unresolved.
- Save 35 source models from Data Modelling as versioned JSON (13,746 entries); retain source workbook/sheet/row, formulas and 1,454 incomplete requirement warnings. Two spreadsheets without the required column schema are recorded in catalog importIssues.

## 4.64.7 - 2026-10-09

- Resolve HMI and touchpad bitmap references through the correct local/VCShared BitmapGroup IndexMap, .bminfo definition and original image file. Render bitmap backgrounds and control images in Screen preview; retain bitmap names, indexes and readable missing-file evidence.
- Add Bitmap / Released and Pressed property sections, with resolved image name, file, index, availability and per-level mappings. Add shared Released / Pressed and touchpad level preview selectors; keep the touchpad key grid transparent and show the edit field's simulation value.
- Render the same resolved bitmaps in HTML/PDF/Word report previews. Include bitmap resolution evidence and detect referenced image changes even when the HMI XML is unchanged. Live bitmap indexes remain explicitly unavailable in the static preview.
- Keep image resources scoped to the selected visualization or explicit VCShared owner. Older saved comparisons need a rerun to populate bitmap assets; invalidate previous preview/report caches.
- Verify the actual AlphaPadQVGA3 bitmap group/index/image chain, missing-image handling, browser state/level selectors and properties, HTML/PDF/Word/JSON exports, 43 regression checks, unchanged full-project comparison counts, production builds and the packaged EXE engine.

## 4.64.6 - 2026-10-09

- Replace MatchView Project View's flat change list with an Automation Studio object tree. Keep Base and Developed projects aligned, with Object Name / Description columns, program and library icons, plus/minus expansion and tree connectors.
- Read object order, types and descriptions from Package.pkg, program .prg and library .lby files. Include unchanged source files and library interfaces; keep active HMI and Physical configuration scope. Preserve original paths on each side.
- Add object search, change filters, Expand all / Collapse all and an optional Project descriptors switch. Opening a file routes to its source, HMI or hardware comparison; unchanged configuration/library text loads on demand.
- Include the complete scoped object inventory in comparison JSON. Older saved comparisons show their available objects and a rerun notice for the full inventory.
- Verify actual LRJ program/library descriptors, the complete SC_PV5046/SC_PV5047_V0 comparison with unchanged counts, browser tree/filter/source behaviour, 34 regression checks, production builds and the packaged EXE engine.

## 4.64.5 - 2026-10-09

- Replace the single-value Text Group inspector with paired index/language tables and a separate Text Snippets table, following the Automation Studio reference. Sort indexes numerically and show language names, with search, language filtering, Changed only / Show all and optional text IDs.
- Show snippet Name, Type, StyleClass, Details and Description, including datapoint bindings. Highlight changed cells and added/removed rows; select an index or snippet to inspect every original source property in the categorized details view.
- Parse TextSnippet definitions and detect additions, removals, datatype changes and binding/property changes independently of translated values. Preserve empty IndexMap entries and distinguish absent translations from explicitly empty text. Include complete snippet evidence in HTML/PDF/Word/JSON reports.
- Retain separate text-group files for each HMI/shared location. Existing cached results can display the new values table; rerun the comparison to populate snippet definitions and regenerate their report evidence.
- Verify the SC_PV5046/SC_PV5047_V0 password text-group sources (nine indexes, six snippet definitions and the added Numeric binding), full-project comparison, browser filtering/details/highlights, HTML/PDF/Word/JSON evidence and the frozen EXE engine. Production builds and 25 regression checks passed.

## 4.64.4 - 2026-10-08

- Categorize Screen Preview and Structured HMI properties into expandable Identity, Position, Appearance, Format, Value, Text Group, Input, Navigation, Cursor and Runtime sections, with Alignment under Format and Completion/Locking under Runtime.
- Share expansion state and property rows between both projects. Open changed sections automatically, show category change counts, and add Expand all / Collapse all. Keep missing controls, unknown properties and the layout-property skip option visible and consistent.
- Preserve complete source property names in tooltips while using contextual labels such as Horizontal, Vertical and Datapoint inside their sections. Preserve the actual preview geometry and existing comparison/export evidence.

## 4.64.3 - 2026-10-08

- Rebuild MatchView ladder geometry from logical XML columns: functions and function blocks span two columns; retain header instances, continuous multi-row bodies, pins, contacts, S/R coils and independent analog connections. OR junctions join the right cell boundary without creating a bypass from the power rail.
- Verify hs_mcseq networks 7, 11 and 12 against the supplied screenshots and hs_flts branch/timer networks against the supplied PDF. Read BOOL/TIME/UINT/UDINT labels and comments from applicable local/shared declarations; expose source and declaration details on symbol selection.
- Align network insertions/removals using logic identity before comparing their elements. The faultCyclic reference now identifies developed Network 27 as added and pairs Network 28 with the changed timer PT input. Ignore XML indentation and attribute order as logic differences.
- Keep graphical comparison first, with shared zoom and linked scrolling. Upgrade saved diagram geometry when displayed; rerun older comparisons to obtain corrected network pairing.
- Export the same diagrams in HTML, PDF and Word; JSON retains normalized network models and SVG evidence. Tile large drawings at grid boundaries with named continuation sections, keep short blocks together, and invalidate report caches made with an earlier renderer.
- Sample checks: 207 source networks parsed without warnings, 17 regression tests passed, authenticated SVG/PNG/view endpoints checked, and actual Project 2 vs Project 1 fault comparison exported in all four formats. Geometry follows source topology; unsupported XML elements report warnings, and this release does not claim pixel-identical Automation Studio typography.

## 4.64.2 - 2026-10-08

- DataInspect RTC defaults to the 30-byte SpinConnect request: Function 1 / GC 10, two reserved bytes, and YYYY-MM-DD HH:MM:SS ASCII at indices 9..27. Validate complete timestamps, align the preview and backend, retain the optional legacy byte-5 layout, and send GC 11 after the RTC exchange even when the response times out.
- Show the actual RTC request and GC 11 close frame separately. Communication success does not claim the PLC clock was applied; verify the clock through metadata-mapped GC 150 and the PLC's RTC conditions.
- Keep GC 30 TAG_DATA_TYPE as BYTE through final Excel normalization. Display alarm packing/copy/binding findings with generated metadata.
- Read active HMI alarm definitions together with Logical/VCShared/AlarmGroups, including when the active AlarmGroups folder is empty. Keep multiple shared groups, exclude SystemAlarms.algrp and .alcfg files, and retain byte/bit identities. Use the active physical configuration when resolving the HMI target.
- Cross-check SC_3101: its packer writes bytes 1..4 but GC 30 copies bytes 0..2, excluding alarms 16..23. The AlarmImage and packed array names also differ; corrected metadata includes BYTE and accompanying source findings rather than inventing untransmitted fields.

## 4.64.1 - 2026-10-08

- Fix MatchView report requests reaching the legacy export handler. Background reports now use separate `/compare/reports/` API paths; keep compatibility routes registered before legacy exports. Invalid cover fields have readable error messages.
- Add Project details beside Chopper summary, available before comparison: name, description, validated by, date, validation details and approved by. Prepare selected HTML/PDF/Word/JSON formats automatically after comparison, with elapsed time, per-format downloads and separate versions when details change.
- Persist account-scoped prepared report manifests and files; reuse identical completed reports and cached HMI preview images across formats and cover edits. Rendering runs in two background workers; the download window can close during preparation.
- Cache Word table columns once instead of repeatedly flattening all cells for each row. Bound PDF table sections to 80 rows to reduce repeated layout/splitting work; retain every comparison row and expose PDF page-layout progress.
- Add the screen-view checkbox to skip Width, Top, Left, AlignmentVertical and AlignmentHorizontal from property differences and report rows. Preserve actual preview geometry and raw file comparison counts.
- Resolve legacy compact declarations such as BOOL[0..400]. Accept smaller alarm loops within declared bounds; inclusive 0..175 packs 176 bits into 22 bytes. Preserve out-of-bounds, wrong-buffer and copied-length checks.
- Omit the seven specified Ring Frame alarm caption prefixes from generated Sheet2 references while retaining original byte/bit positions and NA placeholders. Other machine alarm captions remain unchanged.

## 4.64.0 - 2026-10-08

- Route machine-function questions to active cyclic PLC logic and enabled ladder networks; avoid generic instruction words ranking HMI settings and empty initialization files first. Diversify evidence across control tasks and refresh cached indexes.
- Explain extracted ST/AB conditional assignments and simple ladder series rungs in the local fallback. Keep complex branches, shared ownership, commented networks and incomplete sequence coverage explicit.
- Report optional-model timeouts clearly; limit machine-function model responses to 60 seconds and keep reading/retrieval/model progress visible. A previous log attachment no longer displaces a machine-function fallback.
- Preserve self-registration, own-password changes and Admin account creation/management as standing release requirements in ACCOUNT_COMPATIBILITY.md. Account databases and passwords remain in the persistent data root.

## 4.63.0 - 2026-10-08

- Add complete project folders and project ZIP uploads to Chopper's paperclip menu, with upload progress and selectable project context. A descriptor alone explains how to attach the complete source.
- Handle older servers without the asynchronous chat route by using their existing chat route; show restart guidance if neither route is available.
- Restrict shared model configuration and connection displays to Admin; remove model connection details from public health responses.
- Add Admin-only WorkHub user management: create accounts, edit username/designation/company, reset passwords, enable/disable access and revoke affected sessions. Existing accounts are migrated without resetting passwords.
- Add an on-demand Chopper comparison summary popup bound to the current MatchView session, with elapsed processing time, copyable explanations and before/after examples.

## 4.62.0 - 2026-10-08

- Add a cached, source-backed Chopper project index for active configuration/task scope, declarations, logic chunks, ladder networks, HMI, alarms and hardware/I/O; refresh after source changes and report unresolved scope or reading limits.
- Connect the current MatchView result to Chopper and categorise variable, logic, ladder, HMI layout/behaviour and hardware/configuration differences. Add authenticated MCP project-understanding and comparison-summary tools.
- Add asynchronous, account-scoped chat processing with reading/retrieval/model stages, elapsed seconds, approximate file-processing estimates and completion duration.
- Add suggested chat questions and detailed Help examples for machine functions, start/stop logic, alarms, variable traces, HMI changes and ladder networks. Existing local GGUF/Ollama/API models explain retrieved evidence; no new model weights are trained.
- Improve graphical ladder rendering: continuous function-block bodies, single-row conversion functions, connected empty OR junctions, full rung output wires, standard coil curves and numbered networks. Collapse text summaries and element lists below the diagram for review.

## 4.61.0 - 2026-10-07

- Correct five shifted GC 50 previous-shift parameter name mappings. Reject configured aliases that duplicate a different PLC parameter in the same group, with source evidence; preserve packet fields, offsets and genuine repeated PLC captions.
- Normalize generated and edited metadata MIN/MAX and scale/offset factors to numeric Excel cells with General formatting. Reject unresolved limits with sheet/cell evidence; preserve null markers and Sheet2.
- Introduce persistent `BndR_ID_xxxxxx` display IDs and unique project/department TEST IDs for frontend run history and export filenames; preserve existing rule references.
- Reconstruct Ladder XML into a shared row/column model with instances, pins and OR connections; add interactive SVG, PNG downloads, difference colors and diagrams in HTML/PDF/Word comparison exports.
- Fix Word export failures caused by legacy control characters and an undefined ladder-report variable.
- Bundle the verified official llama.cpp Windows CPU runtime for Chopper's app-managed local GGUF mode. Keep model weights separate; preserve optional external Ollama/API settings.
- Add authenticated MCP Streamable HTTP project/source/reference/ladder/validation/draft tools, revocable account tokens, and Settings controls. See MCP_LOCAL_TOOLS.md and CHOPPER_LOCAL_AI.md.

## Unreleased - 2026-10-06

### 2026-10-07

- Scope Module serial no mapping to the active configuration in LastUser.set; use the single AS 2.7 CPU configuration. Exclude inactive targets and report missing/conflicting active selection without combining configurations.

- Keep Module serial no mapping as its dedicated validator when opened or edited through Chopper. Add a complete GC 420 requirement review and mandatory hardware, I/O binding, declaration and task-ownership cross references. Configure project-relative source scopes, discover scalar/array variables automatically, validate declarations and complete bulk-copy bounds, and repair the empty generic-rule conversion without requiring an exact source snippet.

- Unify Chopper into one chat for all uSOPp features. Add a paperclip for logs, metadata and readable documents, optional collapsed project context, feature shortcuts and friendly missing-file/workbook choices. Render local decoded readings in chat with Group Code/asset/time selection, table/simple-text views, copying and capture explanations. Remove the separate PLC log decoder form; keep rule configuration and KnowHub. Validate connection responses to prevent the undefined label. Include bounded PDF/DOCX/spreadsheet text readers in the optional Windows package.

- Add table/simple-text views for Chopper log readings with raw decimal bytes per metadata field, screen names, payload-relative offsets, copyable results and optional full REAL precision. Keep four-decimal display as the default and preserve decoding without Ollama.

- Add Chopper's local PLC log decoder: upload/paste SpinConnect logs with XLSX/CSV metadata, correlate requests by asset/group/device, retain every timestamped capture, and map values/Sheet2 alarms using payload offsets. Separate PLC rejections, metadata-length/data issues, log errors and unconfirmed replies; retain GC 11 close-command semantics and flag incompatible workbook version ranges.
- Add administrator-managed Chopper model settings for local tools, Ollama and compatible model APIs. Keep API credentials on the backend (Windows account encryption), support installed-model discovery, conversation history and local fallback. Source evidence opens the existing B&R editor with backups and file-version checks. Keep model transport independent of deterministic decoding and validation.

- Add admin-only WorkHub run history for packet validation, generated metadata, rules and comparisons. Store per-run results/user/timestamps under `.usopp_exports/history` and independent project snapshots under `.usopp_workspaces/history`; retain them during cache clearing. Open saved results with archived source or reuse an editable project copy in ByteMap, MetaWorks and LogicScan. Earlier results remain listed with unrecorded-user/source limitations clearly shown.
- Add the Module serial no mapping rule: trace each physical configuration's electronic modules/controller through SerialNumber I/O bindings and scalar/array variables into every GC 420 packet path. Check unique mappings, four-byte integer types, array bounds, byte counts, packet header and send setup; expose missing physical configuration bindings separately.
- Make the response Payload card open all payload bytes and the complete frame. Add AS 2.7 project-root recognition and decoded, read-only viewing of B&R-wrapped `.src`/`.pgp` containers, preserving validation line numbering. Add direct source access to configured-packet rows.

- Decode HMI touchpad key mappings into actual letters with preserved case (A / A or A / a), and show lowercase failures without raw virtual-key identifiers. Expand ByteMap and Group Code recommendations with payload/header arithmetic, cursor increments, alarm packing, impact and follow-up checks.
- Add a separate offline Manual received data window to DataInspect: choose a metadata group, paste a complete decimal response, validate frame size, machine ID, checksum and end marker, then populate the existing parameter table. Label pasted frames as manual and keep them out of live PLC connection, version and clock indicators.
- Change DataInspect acceptance from MIN/MAX range checks to decoded data quality: fail unavailable/non-finite values, positive-exponent scientific values and empty lot names. Keep MIN/MAX as reference and show each failure reason.
- Show rule findings as readable expected/actual checks, source locations and recommendations instead of raw JSON; retain readable evidence in HTML/PDF exports. Add AND/OR cross-reference choices for grouped HMI, ladder, ST and Automation Basic checks and legacy cross-function rules, with AND as the default.
- Validate each alarm bit-packing loop against declared array bounds, inclusive bit count, byte rollover, buffer capacity and matching BIT_SET buffers. Check Group 30 copy start/length against the packed bytes. Generate Sheet2 alarms separately for every transmitted packed buffer, including nonzero alarm ranges and multiple alarm arrays; keep missing alarm bits as numbered NA entries.
- Validate response length setup and the response trigger on every data-group packet path; GC 11 remains a close-only command. Report task-local `nw_i` declarations using one-byte types such as USINT, point payload overflow findings at the size-header assignment, and include group control failures in the validation totals.
- Include all non-system `.algrp` files in generated Sheet2 alarms, including AS 2.7 `Logical/VCShared/AlarmGroups` projects and multiple alarm groups. Use configured alarm indices/image offsets without requiring the AlarmImage variable name to equal the packet array; exclude `SystemAlarms.algrp`, `.alcfg` files and generated project trees.
- Simplify DataInspect with inline PLC IP editing, one metadata action, and collapsed server/PLC details. Remove the visible request-settings row, address port suffix and duplicate frame/RTC shortcuts.
- Correct Test All reporting: identify the group that timed out, keep its error off successful group responses, count skipped groups separately, and require valid metadata length/ranges before displaying Passed. Reset old readings before a new run and clear stale connection status after a failed read.
- Treat GC 11 as an outgoing close command with no expected reply frame, including simulator results. Show metadata mismatches separately from transport success, including a four-byte GC 10 payload versus a six-byte workbook layout.
- Keep one TCP connection for a DataInspect single-group test or an entire Test All sequence. Send GC 11 in cleanup even after a read failure and wait briefly for PLC closure without expecting a GC 11 response frame.
- Log target, Machine ID, request bytes, receive stage, byte count, timing and confirmed PLC closure under a shared trace ID. Preserve partial response bytes and identify groups skipped after a transport failure.
- Distinguish TCP Connected / No valid PLC response from a failed TCP connection. Show failed reads as unavailable, include request/closure details, and provide guidance for enabling SpinConnect and checking Machine ID and stale sessions.
- Prevent Live Poll from restarting immediately whenever its own connection status changes; stop Live Poll when Test All starts.
- Replace the DataInspect toolbar with a responsive Server / TCP exchange / PLC mimic. Open metadata, request-port and frame settings from the server side; open IP/target settings from the PLC side. Show backend RTC, metadata filename, sent requests, responding groups, GC 10 version and the six-field GC 150 clock in both themes.
- Clear readings on metadata/connection changes and discard responses from a previous target, so the mimic cannot display an old PLC's data.
- Correct DataInspect Sheet2 parsing: resolve PLCVAL and SHOWNVAL explicitly instead of using MACHINE VARIANT as displayed text. Mark old saved variant-label mappings for workbook re-upload.
- Display BOOL values as 0 : OFF / 1 : ON and round displayed numeric values to at most four decimal places while retaining full raw values for validation and diagnostics.
- Return the decoded group response to the RTC tester and read Date, Month, Year, Hour, Minute and Second from Group 150 metadata. Show tag/offset/datatype traceability, reject missing or invalid clock fields, and discard responses belonging to a previous target.
- Complete the six RTC fields in built-in metadata profiles without changing uploaded metadata offsets.
- Rename shared navigation and workspaces to WorkHub, DataInspect, ByteMap, MetaWorks, MatchView, LogicScan, KnowHub, AI Assistant and ResultView.
- Add complete LogicScan pipeline result exports as standalone HTML and PDF, with rule names, IDs, statuses, flow outcomes, source locations, configured requirements and all evidence.
- Ask for project name, description, validated by, validation details, approved by and date before HTML/PDF report exports; place those details on the front page. Apply the same cover form to MatchView HTML/PDF exports.
- Give every report export a separate output directory so concurrent exports cannot overwrite one another. Preserve XLSX, CSV, JSON and importable metadata export formats.
- Redesign sign-in and account creation with a shared feature overview, responsive layout and light/dark theme support.
- Add accessible Show/Hide controls to login, registration and Settings password fields.
- Explain missing account routes as an outdated running server, disable account submission until the service is ready, and provide Check connection.
- Advertise account support in server health; source and executable launchers refuse to reuse a pre-account server with the same release number.

## Unreleased - 2026-10-05

- Add application sign-in, self-service account creation with designation/company, sign-out and password change in Settings. Seed Admin only on first initialization and store password hashes and revocable sessions in SQLite.
- Rename workspaces to Packet Lens, Nami Live, Twin Scope, Rule Pilot and Chopper Desk; add shared Settings/Help at the bottom left and feature-specific Chopper guidance.
- Fit the Nami workspace into the available screen height so its settings footer remains accessible below shared guidance.
- Synchronize PLC Data light/dark mode with the uSOPp theme and add integrated workflow/connection help.
- Fix PLC Settings draft reset, cancellation, target selection, numeric validation, stale handshake feedback, hidden API errors and clipped connection fields.
- Reject invalid Group 10 handshake frames; display simulator update errors and the actual configured PLC TCP port.
- Restrict application launch ports to 8200–8500; use 8201 for optional frontend development while keeping the controller TCP port configurable.
- Correct PLC Data loading on an older running backend: request the feature document explicitly and reject the main application fallback to prevent repeated nested uSOPp navigation.
- Integrate the Nami PLC Data Verification V1.5 frontend into the PLC Data navigation item with its original layout, controls, metadata import, and reports.
- Host PLC reads, multi-group reads, RTC/manual frames and simulator APIs in the Python backend under /api/nami; serve the isolated frontend at /nami on the existing application port.
- Build both frontends with npm run build and include both in the existing optional Windows executable packaging.
- Write literal MIN/MAX and scale/offset factors as numeric Excel cells during metadata generation and workbook Save/Export, preserving null markers.
- Keep generated metadata headers unfilled with black bold italic text and wrapping, without filters; preserve both worksheet schemas.
- Add Start_uSOPp_LAN.bat and Stop_uSOPp.bat alongside the existing local start script.
- Show rule names and IDs in separate result columns, with alphabetical name order and row numbers.

## 4.60.3 - 2026-09-29

- Add a payload-relative TCP offset column starting at zero while retaining the PLC buffer offset that includes the five-byte header.
- Add Group Code wise parameter checks for selected codes, all codes, or all codes except specified codes.
- Expand guided rule check categories for PLC, declarations, cross-subroutine traceability, HMI and library checks.

## 4.60.2 - 2026-09-29

- Show Group Code 30 alarm array elements as the effective BYTE metadata contract in the Metadata Validation screen and Excel report.
- Preserve the source PLC declaration separately as plcDeclaredType for engineering traceability.

## 4.60.1 - 2026-09-29
- Made Group 30 alarm/fault metadata strictly BYTE even when the PLC temporary alarm array is declared USINT.
- Restored metadata alignment by stable Group Code and payload-relative offset before descriptive Parameter text.
- Keep real PLC and uploaded workbook rows together when their labels differ, then report the Parameter mismatch instead of showing two misleading blank-sided rows.

## 4.60.0 - 2026-09-29
- Added a persistent Settings choice for PLC BOOL metadata representation: BOOL (default) or USINT.
- Kept PLC declarations unchanged while applying the selected representation consistently to metadata generation and datatype validation.
- In USINT mode, generated Sheet2 rows use the required `0 = ON` and `1 = OFF` mapping; validation fails converted BOOL rows when the USINT datatype, Sheet2 pairs, or `IS_SHOWN_VALUE_DIFFERENT=YES` are missing.
- Preserved Group 30 alarm-byte metadata as BYTE and included the active BOOL mode in generated and validation results for auditability.

## 4.58.2 - 2026-09-28
- Moved project selection to the pipeline start node and placed the folder picker in the pipeline workspace.
- Added a visible connected Results / Reports drop target that appends dragged features to the end of the flow.
- Added delete actions for saved pipelines, active pipeline and empty custom features; feature deletion prunes references from saved flows.
- Improved local API unreachable feedback for pipeline validation.

## 4.58.1 - 2026-09-28
- Exclude Temp, AS, Binaries and Diagnosis before browser project upload. Reuse the staged project for validation and metadata generation.
- Bound metadata reads, editing and duplicate highlighting by populated cells; preserve original row numbers, hidden rows, formulas and workbook styles. Avoid expanding formatting-only Excel rows/columns.
- Separate upload/processing timing and show when an initial estimate is exceeded; log engine duration.
- Focused LH20S_PV2042 check: validation 29.46 seconds, all 1,794 result totals preserved; uploaded metadata view 0.59 seconds.

## 4.58.0 - 2026-09-28
- Added connector + menus for inserting features, Yes/No decisions, and nested parallel paths. Inserting a fork places following steps on Yes / Path 1; paths rejoin before the next common step.
- Added actual conditional execution based on a preceding feature result or selected department, skipped-path evidence, and parallel joins. Flow validation rejects forward or conditional-only source references.
- Preserved legacy saved series/parallel pipelines through conversion to structured flows. Decision/parallel nodes can switch type without discarding either path.
- Reduced node dimensions and empty canvas space, compacted the library/status controls, and replaced New/Save text buttons with labelled icons.

## 4.57.0 - 2026-09-28
- Rearranged the feature pipeline with a top validation status and elapsed time, horizontal department/feature cards, selected project, saved pipelines on the right, and a project-to-results canvas.
- Added saved branch assignments and branch execution: stages run in order within each path, independent paths run concurrently, and result evidence identifies its branch and stage. Existing series and parallel modes remain available.
- Added dropdown table editing, Add mapping, Save/Cancel, editable PLC value/label pairs, CSV template/data export, file import and local Browse This PC, alongside Chopper configuration.
- CSV dropdown import validates the complete file before saving, retains unrelated mappings, detects conflicting values and uses revision-checked atomic writes.

## 4.56.0 - 2026-09-28
- Replaced the Rules selection page with a department and feature pipeline canvas, existing rule assignments, series/parallel execution, per-feature result summaries, and named saved pipelines.
- Organized existing rules into feature JSON files, preserving source definitions, department scope and ready/draft status. New rule configuration asks which feature to use.
- Reorganized Learning Center into Rule library, Parameter mappings, Dropdown mappings, and engineer feedback. Added guided Chopper mapping configuration with review/save, dropdown value editing, and CSV exports.
- Exposed frontend and API versions separately and disabled HTML caching to distinguish an old browser interface from the current backend.

## 4.55.0 - 2026-09-28
- Moved master parameter mappings from Settings to Assist / Learning Center with searchable table, edit, add, save, CSV template and populated export, and CSV import.
- Preserved master mapping storage and document metadata; added conflict detection and atomic writes. CSV imports match parameter, PLC tag and metadata identity to preserve repeated descriptions.
- Added a Learning Center rule library with rule details and access to Chopper configuration and draft testing.
- Made Feature pipeline the initial Rules view and rebuilt the production frontend to publish the existing pipeline interface.

## 4.54.0 - 2026-09-28

- Keep Validation project/metadata selection, active configuration facts, run controls and processing status above the result tabs in two compact input cards.
- Recognize IF/ELSIF headers ending in THEN; and ELSE; in packet parsing. This preserves mutually exclusive byte assignments and their shared post-END_IF cursor increment in GC130-style logic.
- Add source-file viewing/editing from expanded offset rows with line numbers, search, explicit Edit/Save/Discard/Reload actions and declaration-file access.
- Restrict editor paths to the validated project, detect conflicting external edits, preserve encoding/newlines, keep a backup and audit record, and save atomically. Source edits mark displayed results as stale until validation runs again.
- Include the engine's resolved declaration index in validation results for searchable PLC tag/datatype browsing.
- Python compilation and TypeScript/Vite production build completed. Interactive editing and full validation runs were not tested for this revision.

## 4.53.0 - 2026-09-27

- 2026-09-28: Add prominent A− Smaller/A+ Larger buttons (25-150%), a sticky preview toolbar and scrollbars for the previously clipped HMI properties area. Link Base/Developed screen, structured-property, logic-difference and hardware/ladder pane scrolling. Use one aligned property table below the HMI screens with View properties and Back to screens actions.
- Add a persistent 50-150% font-size slider and reset action to HMI preview. Resolve language-specific font settings from .fninfo, reduce default text size on 320-pixel screens, keep PLC bindings inside their controls, and hide placeholder control names unless requested.
- Correct SingleText button captions by accepting TextIndex as well as TextIndexOffset and preferring explicit control indexes over stylesheet defaults; avoid silently resolving a missing index to text 0 (LOGOUT).
- Add a View rule action with a read-only dialog for requirements, scope, checkpoints, exact logic and every configured condition.
- Follow-up performance fix: store HMI detail files in the temporary compare workspace and load only the selected screen. Keep structured exports complete by loading the required details during export; avoid duplicate raw XML diffs for parsed HMI files.
- Exclude Temp, AS, Binaries and Diagnosis before browser upload, and write compact comparison JSON to reduce result delivery time and memory use.
- Compare HMI XML content independently of indentation, source line positions, XML attribute order and Property element order. Preserve control/layer stacking order, IDs, text values and geometry when deciding whether a file changed.
- Include unchanged HMI files in the All tree so their screen layouts remain available for inspection.
- Add a monitor-icon Screen preview beside Structured HMI, with Base and Developed layouts, fit/zoom, layer/language choices, optional control names and click-to-inspect properties.
- Place controls using Left/Top/Width/Height. Resolve embedded and target-scoped text groups through IndexMap and language TextLayer; show Numeric/String PLC bindings.
- Resolve the selected visualization's palette, Color stylesheet and referenced layers. Include resolved text and inherited appearance in structured control differences; separate controls by layer identity.
- Preview is static: raster assets use labeled placeholders and live PLC values/visibility are not simulated. Existing comparison results must be regenerated to include the new layout data.
- Build checks: Python compilation and TypeScript/Vite production build completed. Interactive browser behavior has not been tested.

## 4.52.0 - 2026-09-27

- Restrict Rules to the configured rule library, checkbox selection, validation runs and results. Open result assistance in the Assist workspace.
- Add Chat, Rule configuration and Learning Center tabs under Assist; use Chopper consistently and position Settings at the bottom of the desktop sidebar.
- Replace the configuration form with sequential chat questions, suggested answer buttons, typed answers, code/XML uploads, editable prior answers and review/save/enable actions.
- Preserve both accepted ST alternatives, the configured Group Code, machine scope and optional variable/datatype checks in generated rules.
- Correct SC-BR-LOGIC-006 to require complete Lot Name transfer logic and matching PLC/HMI variable identity on one String input control; ignore variable Text IDs and ClassIds, honor Process page prefixes, and report HMI targets separately.
- Fix saved rule overrides so individually reviewed configurations take precedence over bundled collections; reload the rule library after saving.
- Verification: frontend production build, Python compilation and 15 focused positive/negative rule checks passed. Model weight training is outside this release.

## 4.51.0 - 2026-09-27

- Name the project assistant Tony “Chopper” and add a modern project-aware chat workspace with evidence links, quick engineering questions and learning-record status.
- Replace the free-text Rule Configuration Assistant with Chopper's option-based flow for machine department, validation category, rule selection, subroutine, Group Code, PLC variable, declaration datatype and exact ST logic.
- Add machine department choices for All, Blow Room, Carding, Breaker, Finisher, Comber, Lapformer, Speedframe, Ringframe, plus All, Selected and Spin Connect rule selection.
- Add deterministic `exact_logic_declaration` validation so reviewed drafts can check exact ST logic and the configured PLC declaration datatype.
- Add a Learning Center for assisted PASS, FAIL, WARNING and NOT FOUND evidence, engineer feedback, retrieval statistics and approved training-dataset export.
- Use engineer-approved observations as Chopper's local evidence retrieval model while keeping automatic weight retraining and deterministic verdict changes disabled.

## 4.50.0 - 2026-09-27

- Complete the Rule Assist learning phase with append-only engineering observations for every assisted rule result and every engineer feedback decision.
- Make `Create rule from this` produce a disabled draft that must be reviewed before it can be saved or enabled; learned evidence never changes the deterministic verdict.
- Add guided rule configuration fields for source file, Group Code, PLC variable or HMI datapoint, and expected evidence while retaining checklist uploads and free-text requirements.
- Let the chatbot search the selected Automation Studio project across PLC, HMI, hardware and configuration sources while excluding `Temp`, `AS`, `Binaries` and `Diagnosis`.
- Show project source evidence with file names, line numbers and excerpts in the chatbot, and provide rule result summaries and report downloads in the Rules page.
- Preserve every uploaded metadata workbook row in Metadata Validation and keep mapping suggestions separate from actual workbook comparison values.

## 4.49.0 - 2026-09-25

- Normalize the 32-row Spin Connect 2.0 Finisher CSV into the versioned `SC-FIN-CHECKLIST` v1.0 collection while preserving blank separators and original row identity.
- Classify imported rows as packet signatures or source signatures and extract Group Codes, PLC variables, `memcpy` sizes, `nw_i` increments, executable assignments, and array declarations.
- Keep all imported checklist rules disabled until engineer review; identify ambiguous ranges and per-shift/report substitutions as `Needs engineer review`.
- Add deterministic execution for reviewed packet and source checklist rules with file, line, expected size, actual size, expected increment, and actual increment evidence.
- Add CSV checklist normalization to the Rule Configuration Assistant and show import counts before saving drafts to the Rule Library.
- Resolve filenames supplied in checklist instruction fields, including `ip_add.var`, and validate shorthand array declarations against B&R declaration syntax.

## 4.48.0 - 2026-09-25

- Add the reviewed `SC-BR-LOGIC` v1.0 rule collection with deterministic checkpoints `001` through `006` and `008`; reserve `007` because its engineering requirement was not supplied.
- Validate timeout defaults, RTC indexes 9 through 27, Group 20 machine status, Product Code placement, Group 140 Lot Name PLC/HMI traceability, and MMS_CONFIG page structure.
- Return file, line, excerpt, expected value, actual value, and corrective evidence from the Rule Engine without changing the Validation or Compare engines.
- Present rule results as an engineering table and provide an evidence-scoped Assist action on every result.
- Store engineer feedback as append-only rule feedback with Correct, Incorrect, Partially correct, Ignore, and Create rule from this decisions; feedback does not change deterministic verdicts.
- Load child rules from versioned rule collections and keep the AI-generated configuration in draft/review/save workflow.
- Accept reviewed TXT, CSV, JSON, and Markdown checklist attachments in the Rule Configuration Assistant.

## 4.47.1 - 2026-09-25

- Update comparison Base styling to teal `#00C6B5`.
- Update comparison Developed styling to mauve `#B5718F` across the frontend and structured HTML, PDF and Word exports.

## 4.47.0 - 2026-09-25

- Add a PyInstaller Windows build workflow that produces a portable `uSOPp_AI.exe` without requiring Python, Node.js, Vite, npm or administrator access on the target computer.
- Add frozen runtime dispatch so validation, rule and comparison engines run through the packaged executable instead of requiring an external Python interpreter.
- Serve bundled frontend assets and read-only engine resources from the packaged application while storing logs, workspaces, exports, editable knowledge and rule modules under `%LOCALAPPDATA%\uSOPp.ai`.
- Open the packaged application in the default browser and reuse an existing local instance on port 8200.
- Provide recommended portable-folder and optional single-file build commands in `BUILD_WINDOWS_EXE.md`.

## 4.46.0 - 2026-09-25

- Replace raw comparison exports with the structured Base and Developed presentation used by the frontend in HTML, PDF and editable Word reports.
- Group PLC logic by difference with explicit Base and Developed line numbers; format ladder logic by networks, contacts, coils, functions, pins and layout.
- Format HMI changes by control and property groups instead of exporting source XML.
- Format hardware changes by module, station, channel and mapped PLC tag instead of exporting hardware source records.
- Add a complete Project Knowledge Base section containing Automation Studio identity, active configuration, PLC type, HMI target, project inventory, cyclic task assignments, active objects, permanent variables, subroutines, hardware modules, I/O mappings and screen inventory.
- Apply Base navy teal `#075985` and Developed deep ocean blue `#073B4C` to every exported split view.

## 4.45.1 - 2026-09-25

- Use navy teal `#075985` consistently for the Base project in comparison upload cards, tree labels, project headers, source panes, HMI properties, hardware modules, ladder networks and line-difference labels.
- Use deep ocean blue `#073B4C` consistently for the Developed project in the same comparison views.
- Render side labels as solid colors with white text so both project identities remain readable in light and dark themes.

## 4.45.0 - 2026-09-25

- Constrain the comparison workspace height so the project tree has its own persistent vertical and horizontal scrolling instead of extending below the browser viewport.
- Increase scrollbar visibility and reserve scrollbar space in both light and dark themes.
- Give project tree folder levels distinct blue, violet, green and amber backgrounds, with alternating file-row backgrounds.
- Exclude B&R `X20BM11` base modules and `X20TB12` terminal blocks from parsed hardware, Hardware View and the Knowledge hardware list; apply the frontend filter to cached comparison results too.
- Show explicit `L<number>` references on every Base and Developed logic row, plus the Base and Developed line ranges in each difference header.
- Show the same `L<number>` format in the synchronized full-source viewer.

## 4.44.0 - 2026-09-25

- Add structured comparison for B&R `.ld` ladder files while retaining the synchronized raw source view and ordinary line diff.
- Parse and align ladder networks so inserted networks do not shift every later network into a false modification.
- Present each changed ladder network in Base and Developed panes with network index, label, comment, active/commented state, contacts, coils, analog variables, functions, function blocks, pins and branch markers.
- Include row layout and wiring evidence so line, empty-cell and OR-branch changes remain visible even when the named contacts or coils are unchanged.
- Include ladder network evidence in HTML, PDF and editable Word comparison exports.
- Verify all 28 `.ld` files in the supplied projects: 11 changed, 17 unchanged and zero parse failures.

## 4.43.0 - 2026-09-25

- Keep browser-uploaded projects and transient comparison or validation data under the temporary application workspace; the Settings cache action now deletes these workspaces and cached job results while retaining exported reports.
- Exclude `Temp`, `AS`, `Binaries` and `Diagnosis` folders from browser upload storage, project comparison, packet validation discovery, metadata source discovery and rule scanning.
- Show a small processing popup during comparison, validation, metadata generation and browser project preparation with elapsed time and an adaptive estimated remaining time.
- Add All projects, Base project and Developed project tree scopes so each project can be inspected using its original folder paths.
- Add a visible tree scrollbar, colored folder levels, filled green, amber, red and teal status circles with white symbols, and a status legend.
- Rebuild HTML, PDF and editable Word comparison reports as detailed Base and Developed split views with the actual project-relative file path and line or structured property evidence for every change.

## 4.42.0 - 2026-09-25

- Show Automation Studio version, active configuration, PLC type and screen folder on the Validation project card for local and browser-uploaded projects.
- Remove the `active in Cpu.sw` suffix from comparison screen-folder selections and replace broken encoded separators with readable labels.
- Add project names and actual Base and Developed filenames to the comparison tree with green added, amber modified, red removed and teal unchanged symbols.
- Include unchanged PLC logic files in Logical View while keeping project change totals limited to actual differences.
- Replace the line-context buttons with compact All, Modified, Removed and Added filters beside Differences and View source.
- Rebuild Hardware View as Base and Developed module lists; expanding a module shows its station, type and mapped PLC channels, tags, directions and addresses.
- Apply the selected application theme to Project and Knowledge views and increase tree text contrast.

## 4.41.0 - 2026-09-24

- Reshape comparison into Logical, Screen, Project, HW, Config and Knowledge views with a persistent file tree and Base versus Developed panes.
- Read the active configuration from `LastUser.set`, the PLC type from the active `Hardware.hwl` or `Hardware.hw`, and visualization objects from active `Cpu.sw`.
- Detect real visualization targets by their `Pages` folder, exclude shared `VCShared` resources from the target selector, and compare the selected Base and Developed targets under one canonical HMI path.
- Add structured HMI navigation with a control tree and two readable property panes, including per-property change highlighting and Changed only or Show all modes.
- Show Automation Studio version, active configuration, PLC type and selectable screen folder below each selected project before comparison.

## 4.40.0 - 2026-09-24

- Complete comparison report exports for HTML, PDF, editable Word and JSON using the server-side comparison result.
- Add the uSOPp.ai logo at the top right of formatted report headers with dark blue report branding.
- Add the generated date at the bottom left and `Page X / Y` at the bottom right of PDF, Word and paged HTML output.
- Include structured HMI and physical configuration property changes in exported reports.

## 4.39.0 - 2026-09-24

- Add structured active-configuration parsing for `Cpu.sw`, `ACTIVE_GDM.osl`, `Cpu.per`, `Hardware.hwl` and `IoMap.iom`.
- Compare cyclic task assignments, active software objects, permanent variable addresses, hardware modules and I/O channel mappings as readable engineering records.
- Match hardware modules by station number and I/O mappings by station plus channel; exclude X20TB12 terminal blocks and X20BM11 base modules.
- Expand the Project Knowledge Centre with task classes, active objects, station-ordered hardware, module-grouped I/O mappings and permanent variables for both projects.

## 4.38.0 - 2026-09-24

- Add structured comparisons for B&R `.page`, `.layer`, `.txtgrp`, `.algrp`, `.tpr` and `.dso` HMI files.
- Match equivalent active visualization folders using the `VcDataObject` selected in the active configuration `Cpu.sw`, including projects named `HMI`, `C70` or `T30`.
- Present screen controls, layer controls, touch pad controls, multilingual text values, alarm definitions and HMI data points as readable engineering records.
- Add Changed only and Show all modes inside the structured HMI inspector; raw XML is no longer the primary HMI review interface.

## 4.37.0 - 2026-09-24

- Start the isolated comparison module with `python_engine/compare.py`, `CompareModule.tsx` and `CompareView.tsx`; validation and metadata generation are unchanged.
- Scope B&R comparison to `Logical` and the active `Physical` configuration read from `LastUser.set`, while excluding `Temp`, `AS` and `Binaries`.
- Recognize PLC logic, HMI and physical configuration source extensions, with `.ld` available as source preview only.
- Add a clean synchronized two-project source view and sidebar filters for all changes, differences, removed files and added files.
- Keep HMI review in the structured property view and create dedicated comparison workspaces and logs.

## 4.36.0 - 2026-09-24

- Show the Automation Studio major/minor version from the root `.apj` or `.GDM` descriptor beside the selected project.
- Show only the active configuration name read from root `LastUser.set` beside the selected project.
- Add GC240 hardware module status Sheet2 mappings: `0 = MODULE MISSING` and `1 = MODULE OK`.
- Normalize legacy AS 2.7 string-array tokens such as `ARRAY015OFSTRING1` to the metadata datatype `STRING`.

## 4.35.1 - 2026-09-24

- Parse Automation Studio 2.7 `VAR_EXTERNAL`, `VAR_GLOBAL`, `VAR_GLOBAL RETAIN` and `VAR_CONSTANT` declarations from `CPU.txt` or `incpi.txt`, including `%M*` and `%C*` address markers.
- Recover exported C `typedef struct` definitions and map legacy function-block names such as `_$SHIFT_REPORT` to their member datatypes.
- Resolve nested packet expressions such as `MC_SHIFT_REPORT.CURRENT_SHIFT_PARAMETER[index]` from the exported structure definition instead of reporting `UNKNOWN`.

## 4.35.0 - 2026-09-24

- Add Automation Studio 2.7 project support for `.pgp` project directories with packet logic in `pgm/.../CPU/mms_nw_r.src`.
- Read AS 2.7 global declarations from project-level `CPU.txt`, including `%MB`, `%MW`, `%ML`, `%MX`, arrays and `STRING(n)` declarations.
- Reuse the existing `Logical` HMI discovery for AS 2.7 projects and include `.src` logic in project comparison, rule validation and program-version discovery.
- Move the uSOPp logo into the navigation sidebar and increase its displayed size; retain the Petrus logo at the top right.

## 4.34.2 - 2026-09-24

- Remove the LastUser.set active-configuration content from the Validation page.
- Add the uSOPp logo at the top left and Petrus logo at the top right using the packaged PNG assets.
- Report a missing `nw_i := 5` before the first packet payload write as a Packet Cursor Initialization failure.
- Report fixed packet destinations that disagree with the cursor-relative destination. For the supplied GC30 case, the evidence shows expected `nw_snd_buffer[nw_i+2]`, actual `nw_snd_buffer[5]`, and the resulting overlap.

## 4.34.1 - 2026-09-24

- Replace the single large browser-folder request with bounded sequential upload batches before validation or metadata generation.
- Show transferred versus total project files while a browser-selected folder is being staged. The folder count is labelled as selected until transfer completes.
- Cache a completed staged folder for the current browser selection so Generate Metadata and Run Validation do not upload the same project twice.
- Return an actionable browser-transfer error with the completed file count and the Browse This PC fallback when the network request is interrupted.
- Add an end-to-end regression check that stages exactly 2,933 project files before resolving the Automation Studio project root.

## 4.34.0 - 2026-09-24

- Resolve Automation Runtime `_GLOBAL` and `_GLOBAL_RETAIN` declarations from C modules, including comma-separated REAL variables, so declared packet types are no longer reported as UNKNOWN.
- Recover later packet groups after an extra `(*` marker inside a legacy comment, report the source line, and report a missing outer `END_CASE` as a source failure. Large packet files are scanned without a parameter-row limit.
- Validate `IF`, `ELSIF` and `ELSE` packet paths independently with path-specific cursor positions and configured sizes. The GC140 four-byte copy with a two-byte increment is now isolated to `CUR_PGM = 2` with overlap evidence.
- Treat the GC20 Auto Coner memcpy/direct assignment as one conditional byte, expose standalone cursor gaps, and report each Tail Stroke packet layout separately.
- Fix validation and generation crashes when two packet writes have identical offsets by sorting with numeric source order.
- Show packet paths and conditions in the frontend and add a Packet Variants worksheet to validation reports.
- Highlight duplicate Parameters in purple only when they repeat inside the same Group Code. The generated workbook, uploaded/generated metadata viewer, edited copy and XLSX export use the same rule; Sheet2 is excluded.

## 4.33.2 - 2026-09-24

- Parse direct `nw_snd_buffer[nw_i] := value` byte assignments alongside memcpy fields, including shared increments after IF/ELSE.
- Count alternative branch assignments once; retain both branches with source lines in offset details and Excel reports. Exclude line and block comments from packet parsing.
- Include direct fields in metadata generation and validation with payload-relative offsets.
- Correct the offset table to compare actual and expected buffer offsets; show the metadata offset separately.
- Show the byte difference in packet size warnings. The supplied GC310 logic writes 40 bytes at buffer offsets 5-44, while configuring 42 bytes; the remaining 2 bytes still require PLC review.
- Use field-size labels for both write methods and correct Excel logic-result row colouring.

## 4.33.1 - 2026-09-24

- Added persistent selected-project and metadata summaries to the Validation workspace.
- Display the saved active configuration from the selected project's LastUser.set, for local and browser-selected folders; missing or unreadable settings are identified explicitly.
- Added separate generation, validation, upload, success and error colours with icons and elapsed time.
- Generate metadata and Run validation buttons change colour and show Generating / Validating while running.
- Increased small text throughout the interface; converted legacy font sizes to relative units.
- Added responsive navigation, forms, rule panels and comparison panels for narrow windows and browser zoom; wide tables retain their own horizontal scroll.
- Added a read-only project details API. Engineering engine behavior is unchanged.

## 4.33.0 - 2026-09-24

- Reorganized navigation into Home, Validation, Compare, Rules, Chatbot and Settings.
- Isolated validation state, workbook editing, comparison state, rules and chatbot modules.
- Repaired local path routes and added pasted paths, quoted paths, file URIs and .apj selection.
- Added explicit project-root discovery and errors for ambiguous/missing project folders.
- Unified local/upload validation and metadata generation. Mixed metadata input methods now work.
- Added Windows extended-path handling for browser upload staging and path traversal checks.
- Resolved workbook inputs explicitly; generated workbooks from either mode are retained.
- Preserved all worksheets, formulas, styles, blank rows and original files during workbook edits.
- Added Auto, Fit to window and Custom column-width settings for all tables; corrected dynamic headers.
- Retained reports and workbook sessions instead of deleting them automatically after ten minutes.
- Fixed local CSV knowledge imports to merge records using the existing dictionary schema.
- Added a single local production server and portable script-relative startup/setup paths.
- Setup reuses installed dependencies and does not duplicate node_modules on every run.
- Consolidated historical notes here and archived obsolete source/build/setup backups outside the running app.
- Removed the external font request so the interface works without a Google Fonts connection.
- Kept the v1.71 validation engine and current comparison/rule engine implementations unchanged.

Verification: production build, 15 API regression checks, real project generation/validation,
local comparison with JSON/PDF/DOCX exports, rule execution, and browser interaction checks.
Detailed run evidence is in `logs/functional_checks.json` and `logs/browser_checks.json`.

## Earlier release notes (preserved)


### CHANGELOG_v4.31_COMPARE.md

# uSOPp.ai v4.31 — Project Compare Update

## Compare execution
- Local comparison now runs as a background job instead of blocking the HTTP request.
- The UI polls comparison status and displays live progress.
- The previous 180-second local comparison timeout is removed from the new workflow.
- The comparison engine emits progress events including Base and Developed relative file paths.
- Unchanged files are checked by exact bytes before text diffing to reduce unnecessary decoding.
- Very large files are bounded to avoid pathological SequenceMatcher delays.

## Compare UI
- Progress bar and current Base/New file are shown while comparing.
- A Compare Console sub-window shows live engine activity and both project paths.
- Changed files can be expanded to inspect logic additions/removals and diff hunks.
- JSON, PDF and Word exports are available after a local comparison.
- HTML report remains available.

## Engine separation
- PLC validation remains Python v1.71.
- Rule validation remains rule_engine_v4_30.py.
- Project comparison remains the separate python_engine/project_compare_engine.py.


## v4.31.1 local metadata and compare reliability
- Added Browse This PC tree for local `.xlsx` / `.xls` metadata selection on the Project page.
- Added the same local file-tree selector to Settings for metadata workbook configuration.
- Added Browse This PC for local CSV engineering-knowledge mapping import in Settings.
- Configured local metadata path is persisted in browser settings and is passed to the local v1.71 validation engine.
- Generated local metadata workbooks are copied to `.usopp_exports/metadata` so the Export XLSX action remains available after the temporary workspace is cleared.
- Project comparison now excludes generated `Temp`, `.git`, `Binaries`, `bin`, `obj`, and Python cache directories.
- Large non-logic/config files use bounded diff processing; detailed SequenceMatcher work is retained for normal engineering logic files.
- Comparison engine emits a detailed-diff progress event so the console continues to show activity during expensive file processing.

### CHANGELOG_V4.31_HMI_COMPARE_REFINEMENT.md

# uSOPp.ai v4.31 — HMI Structured Property + Compare Summary Refinement

## HMI structured view
- Removed the **Elements & Geometry** tab.
- Removed the old **XML Compare** tab from the HMI property inspector.
- Kept a separate **XML View** option for raw `.page` source-level comparison.
- Structured HMI view never embeds raw XML.
- Property sheet now presents the complete selected control property set, not only changed properties.
- Added explicit engineering focus on:
  - Name / Identity
  - StyleClass / Appearance
  - Value
  - Text Group
  - Runtime
  - Input
  - Completion
  - Locking
  - Position
  - Other
- Changed values remain highlighted between Base and Developed projects.
- Selected control header shows Name, Style Class and Control Type.
- HMI property styling now respects Light and Dark application themes.

## Logic comparison
- Added a dedicated **Summary** tab.
- Summary is focused on PLC Logic changes.
- Filters:
  - All
  - Modified
  - Added
  - Removed
- Selecting a summary row opens the corresponding side-by-side file comparison.

## UI
- Increased HMI/control/property text readability.
- Added theme-aware styling for Compare and HMI windows.
- Existing dark engineering comparison layout remains the reference for Dark mode.

## Engineering engines
- `packet_validation_report_uSOPp_v1.71_final.py` unchanged.
- `project_compare_engine.py` remains a separate comparison engine.
- Updated only the HMI property grouping logic in the comparison engine.

### CHANGELOG_V4.31_HMI_STRUCTURED_XML.md

# uSOPp.ai v4.31 – HMI Structured Compare + XML View

- Improved B&R `.page` parsing from nested `<Property Name="..." Value="..."/>` nodes.
- Added structured HMI control/property comparison with Base vs Developed values.
- Added property groups: Position, Appearance, Format, Value & Datapoint, Input, Runtime, Text/Description.
- Added B&R control type mapping for common ClassId values in the supplied page structure (Button, HotSpot, Text, Numeric, String), with ClassId retained for traceability.
- Added Elements & Geometry view for Left/Top/Width/Height and PLC/Value Datapoint.
- Added raw XML (.page) side-by-side comparison option.
- Kept raw line diff available for traceability; structured view is the default for HMI files.
- Python v1.71 validation engine remains separate and unchanged.

### CHANGELOG_v4.31_WHITE_SCREEN_FIX.md

# uSOPp.ai v4.31 — White Screen & Project Persistence Fix

- Fixed missing `ChevronDown` Lucide import used by Compare expand/detail and knowledge panels.
- Fixed undefined `hmiLookup` used while normalizing validation metadata/HMI results.
- Added null-safe Compare search/filter handling for partial diff records.
- Persisted the selected local B&R project path/name in browser localStorage so navigation or refresh does not clear the project while the metadata path remains configured.
- Metadata selection remains independent from project selection.
- Python v1.71 validation engine and separate project comparison engine are unchanged.

### CHANGELOG_V4.32_COMPARE_HMI_FINAL.md

# uSOPp.ai v4.32 – Compare/HMI Final Refinement

- HMI structured view aligned to Automation Studio-style engineering property inspection.
- Primary HMI focus groups: Name, Style Class, Value, Text Group, Runtime, Input, Completion, Locking, Appearance.
- Structured HMI view does not embed raw XML. XML is available only through the separate XML View tab.
- Removed Elements & Geometry and XML Compare concepts from the HMI structured workflow.
- Logic Compare includes Summary with All / Modified / Added / Removed filtering.
- Compare file navigator uses a project tree.
- Increased engineering UI font sizes for readability.
- Light and dark theme overrides retained for Compare, HMI property sheet, tree, summary and XML viewer.
- Python v1.71 validation engine remains unchanged and separate from project_compare_engine.py.

### CHANGELOG_V4.32_COMPARISON_RESTORE_DATATYPE.md

# uSOPp.ai v4.32 — Comparison Restore + Metadata Datatype Fix

Changes in this hotfix only:

1. Restored the Metadata Comparison view as the default Comparison tab.
2. Generated/Uploaded workbook views remain separate and do not show the comparison table underneath them.
3. Added final XLSX TAG_DATA_TYPE normalization so REDUNDUNREPLICABLEREAL is persisted as REAL.
4. Kept Sheet2, Edit/Save, Export XLSX, and workbook scroll behavior.
5. No PLC validation, offset, sequence, HMI, Compare, or Rule Engine logic was changed.

### CHANGELOG_V4.32_MASTER_METADATA_FIELDS.md

# v4.32 Master Metadata Fields

- Preserved every existing PLC parameter, PLC tag, metadata parameter, and status value.
- Added missing master metadata configuration fields to every existing mapping:
  - `units`: `null`
  - `offset_factor`: `1`
  - `scale_factor`: `1`
  - `is_visible`: `YES`
  - `is_writable`: `NO`
- No PLC validation, offset/sequence, comparison, HMI, or Rule Engine logic was changed.
- Metadata generation already reads these master fields; the explicit values are now present in the master database and therefore are used on the next metadata generation.

### CHANGELOG_V4.32_METADATA_VIEW_UI_FIX.md

# uSOPp.ai v4.32 — Metadata View UI Fix

## Changes
- Auto-clear validation cache is now **Disabled by default**. It only runs when explicitly enabled in Settings.
- Fixed the Auto-clear toggle state logic.
- Metadata comparison table now has an internal vertical scrollbar and horizontal scrollbar when the columns exceed the viewport.
- Comparison table header rows are sticky/frozen while scrolling vertically.
- Expanded the Uploaded Metadata Workbook columns shown by default:
  - Metadata S No.
  - Screen Name
  - Machine Variants
  - TAG_CODE
  - Parameter
  - Group Code
  - Data Type
  - Offset
  - UNITS
  - MIN
  - MAX
- Added tolerant field extraction for common workbook field names such as Screen Name, Machine Variants, MIN, MAX, GROUP_CODE and OFFSET.
- Existing validation engine, metadata comparison logic, HMI logic, Compare logic and Rule Engine were not changed.

## Verification
- Python source compilation: passed.
- TypeScript type-check (`npx tsc --noEmit`): passed.
- Full Vite build was not run because `node_modules` is not installed in the build environment.

### CHANGELOG_V4.32_METADATA_WHITE_SCREEN_DATATYPE_FIX.md

# uSOPp.ai v4.32 — Metadata datatype + white-screen fix

## Fix 1 — Generated metadata datatype
- Normalize legacy `REDUNDUNREPLICABLEREAL` to `REAL` in the Python metadata generation path.
- Normalize the same legacy value in the metadata workbook viewer so an old/generated workbook cannot display the malformed datatype.
- STRING(n)/STRING[n] continues to display as `STRING`.

## Fix 2 — Metadata white screen
- Fixed the Metadata page render crash caused by `uploadedFallback` being referenced before it was defined.
- Generated/Uploaded metadata tabs now always have fallback row data available even if workbook-sheet loading fails.

## Scope
- No PLC packet validation logic changed.
- No offset/sequence validation changed.
- No HMI validation changed.
- No Compare engine changed.
- No Rule Engine behavior changed.

### CHANGELOG_V4.32_METADATA_WORKBOOK_MASTER_FIX.md

# uSOPp.ai v4.32 — Metadata Workbook / Master Configuration Fix

## Changes

1. Generated metadata first worksheet is now named using the Automation Studio project name (Excel 31-character sheet-name limit applied).
2. Generated metadata normalizes `STRING[n]` to metadata datatype `STRING`.
3. Generated metadata reads optional approved values from `knowledge/master/parameter_mappings.json` by generated metadata parameter name:
   - `units`
   - `offset_factor`
   - `scale_factor`
   - `is_visible`
   - `is_writable`
4. Existing defaults remain unchanged when master values are not configured.
5. Uploaded metadata source records now preserve screen name, machine variants, units and metadata field values for the UI.
6. Added Metadata workbook views:
   - Comparison (default)
   - Generated Metadata
   - Uploaded Metadata
7. Generated/uploaded workbook views support internal vertical and horizontal scrolling with sticky headers.
8. Added row editing, Save, and Export XLSX controls to workbook views.
9. Added backend endpoints for metadata-view save/export.
10. Master mapping CSV/template and Settings form now support UNITS, OFFSET_FACTOR, SCALE_FACTOR, IS_VISIBLE and IS_WRITABLE.
11. Auto cache clear remains disabled by default.

## Validation boundary

The PLC validation engine, metadata comparison rules, HMI validation, Compare engine and offset sequence logic were not replaced. The changes above add metadata presentation/export and master-field configuration while preserving existing validation behavior.

### CHANGELOG_V4.32_OFFSET_SEQUENCE_FIX.md

# uSOPp.ai v4.32 — Offset Sequence Fix

## Scope

Small validation-engine-only fix for packet offset sequencing in `packet_validation_report_uSOPp_v1.71_final.py`.

## Change

The validator now explicitly recognizes the B&R pattern:

```text
IF / ELSIF / ELSE
    memcpy(...)
END_IF
nw_i := nw_i + N;
memcpy(... next parameter ...)
```

The shared `nw_i` increment immediately after the conditional is associated with the preceding conditional packet parameter, not the next parameter.

A sequence validation check also verifies that the next parameter starts at the offset produced by the previous validated increment.

## Evidence added to JSON

Each parameter now exposes:

- `incrementLineNumber`
- `incrementRelation`
- `sequenceValidation`

Existing memcpy, datatype, packet-size, metadata, HMI, and other validation logic was not replaced.

## Verified with Group Code 20 pattern

The sequence is correctly resolved as:

- AUTOCONER LINK STATUS: running offset 38, increment +1, `POST-CONDITIONAL`
- RING CENTERING STATUS: running offset 39
- TRAVELLER RUNNING STATUS: running offset 40
- MACHINE STATUS: running offset 41

No `Offset Sequence` failure is produced for the valid logic.

### CHANGELOG_V4.32_OFFSET_SEQUENCE_V3.md

# uSOPp.ai v4.32 — Offset Sequence V3

## Fix
Corrected packet cursor tracking when the previous `nw_i := nw_i + X` occurs after conditional logic or is separated from the previous `memcpy()`.

The parser now synchronizes the next memcpy running offset from the actual increment found between the previous parameter and the current memcpy.

## Preserved
- Existing metadata validation
- Existing HMI validation
- Existing Compare functionality
- Existing datatype validation
- Existing packet-size validation
- Existing offset/increment validation
- Existing server ports (frontend 3200 / backend 8200)

### CHANGELOG_V4.32_OFFSET_SEQUENCE_VALIDATION_V2.md

# uSOPp.ai v4.32 — Offset Sequence Validation V2

## Change
Added an independent consecutive-parameter offset sequence validation.

For each visible packet parameter:

`next running offset = previous running offset + previous memcpy size`

This validation is independent of whether the parser successfully associates the textual `nw_i := nw_i + X` statement with the preceding parameter. The existing Offset Increment validation remains responsible for checking the actual increment statement.

## Purpose
Catches sequence shifts around B&R IF/ELSE/END_IF/CASE control-flow where a valid increment may be present in the source but the parameter association can otherwise be missed.

Example:

```text
memcpy(... Ring_center_sel..., 1);
nw_i := nw_i + 1;
memcpy(... Traveller_Run..., 1);
```

The Traveller parameter must start one byte after Ring.

## Scope
Only the packet sequence validation block was changed. Metadata, HMI, Compare, existing packet validation, and rule engine behavior were not intentionally changed.

### CHANGELOG_V4.32_RULE_ENGINE.md

# uSOPp.ai v4.32 — Configurable Rule Engine

## Base
This build keeps `uSOPp_ai_v4.32_compare_hmi_final.zip` as the functional baseline.

## Added
- Configurable rule kind: `common_group_packet`.
- Rule module: `SC-COMMON-PACKET` v1.0.
- Automatic discovery of active `CASE nw_group_code OF` branches in `mms_nw_rCyclic.st`.
- No hard-coded Group Code numbers or parameter names.
- Skips commented/incomplete Group Code branches.
- Packet size validation from `nw_snd_buffer[3]` and `[4]`.
- `memcpy()` parameter extraction.
- Parameter description extraction from `(* ... *)`.
- Datatype/size validation using project symbols.
- `nw_i` increment validation against `memcpy` size.
- Excel report with:
  - GroupCode Summary
  - Parameter Validation
  - Validation Errors
- Report workbook uses the Automation Studio project name.
- Rule module registry endpoints:
  - `/api/rules/modules`
  - `/api/rules/modules/{module_id}`
- Rule validation API now returns generated module report download paths.
- Rule Configuration Model accepts `common_group_packet`.

## Compatibility
Existing checkpoint rules remain on the legacy deterministic path. Existing project validation, metadata and HMI comparison code was not intentionally replaced by the new rule module.

### CHANGELOG_V4.32_RULE_ENGINE_UI.md

# uSOPp.ai v4.32 Rule Engine UI

## Rule configuration workflow

The Rules page now provides a simple front-end rule configuration workflow:

1. Open **Rules**.
2. Describe the engineering requirement in plain language in **AI Rule Assistant**.
3. Click **Generate rule**.
4. Review the generated configuration.
5. Click **Save to library** to reuse the rule in future projects.
6. Click **Run now** to validate the current project, or **Run active rules** to execute all enabled rules.

## Rule Library

- Loads existing default rules and saved rule modules.
- Shows rule ID, version and state.
- Rules can be enabled/disabled from the UI.
- Saved AI-generated rules are stored under `rules/modules/`.

## Backend additions

- `POST /api/rules/modules` saves a reviewed rule configuration as a reusable module.
- Existing `GET /api/rules/modules` and `GET /api/rules/modules/{module_id}` are retained.
- Existing deterministic Python validation remains responsible for validation; AI only generates configuration.

## Safety/design principle

AI does not modify PLC source files and does not decide PASS/FAIL. The deterministic Python Rule Engine performs the actual project validation and report generation.

### CHANGELOG_V4.32_SERVER_PORT_SEQUENCE_FIX.md

# uSOPp.ai v4.32 — Server Port + Offset Sequence Hotfix

## Offset sequence fix
- Fixed the JSON serialization crash where `ParameterRow` did not expose the new sequence evidence fields.
- Preserved existing validation logic; the added fields are evidence only.
- Post-conditional `nw_i := nw_i + X` remains associated with the preceding conditional parameter.

## Server ports
- Frontend/Vite default port changed from **3100** to **3200**.
- Backend/API default port changed from **8100** to **8200**.
- Ports are configurable through `USOPP_FRONTEND_PORT` and `USOPP_API_PORT`.
- Frontend binds to `0.0.0.0` so the server can be reached from the LAN.
- Vite proxies `/api` to backend `127.0.0.1:<USOPP_API_PORT>`.
- Recommended server firewall exposure: expose only TCP 3200 initially; keep API 8200 local unless direct API access is specifically required.

### CHANGELOG_V4.32_THREE_METADATA_FIXES.md

# uSOPp.ai v4.32 — Three Metadata Fixes

Only the three requested changes were made on top of the previous metadata-view build:

1. **Datatype cleanup**
   - Generated metadata normalizes the malformed `REDUNDUNREPLICABLE...` datatype token to `REAL`.
   - `STRING[n]` normalization remains unchanged.

2. **Generated Metadata Sheet2**
   - Generated metadata workbook already contains the real `Sheet2`.
   - The metadata viewer continues to load all workbook worksheets.
   - If the viewer has to use the generated-data fallback, generated `Sheet2` records are now included as a second worksheet tab.

3. **Remove comparison table below workbook views**
   - The Metadata page no longer renders the old comparison table beneath the Generated/Uploaded workbook viewer.
   - No PLC validation/comparison engine logic was changed.
