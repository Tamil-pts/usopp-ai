# Virtual PLC acceptance

## 0.10.0 / application 4.75.0 - 2026-10-23

- All 153 Virtual PLC tests passed. The 29 jig, component-library and workspace API tests also passed with the container's current FastAPI dependency set. Eight application build-version/packaging tests passed separately.
- Main app, DataInspect and Virtual PLC TypeScript/production builds passed. React server-render checks covered 101 components on one topology canvas, Fit all/Fit width, action badges, cylinder symbols and library forms. Interactive browser behavior was not tested in this run.
- A real uploaded MotorCylinderPLC fixture passed the HTTP flow: Run PLC, enable jig without stopping the runtime, explicit START, motor start delay, motor feedback, cylinder extension/retraction and CycleComplete. Faults, manual mappings, explicit mapping confirmation and scenario contact persistence have separate tests.
- Saved Project 2 (`LDF3S_WO_SUCTION`) ran with the reviewed source correction and profile version 5 for 16,250 scheduler scans / 6,500 virtual ms. FAST was explicitly pressed at 2,000 ms; readiness, the FAST latch, drafting/scanning load and inverter command became active. VFD/servo models moved and delivery encoder counts advanced. An explicit left STOP at 5,000 ms cleared the main inverter command and stopped its VFD/shaft. No PLC variables were forced. The servo run command remained under the original PLC stop-delay logic; this short check does not establish completion of that delayed stop or full machine-cycle equivalence.
- The previous top-arm jig assumption was the concrete FAST blocker: its delayed inverse relationship to drafting-load output briefly dropped readiness and reset the latch. The reviewed default now keeps the top arm closed as an independent editable contact. Original PLC files were not changed.
- The running local app reported UI/API 4.75.0, matching compiled UI checksum and no-store headers on all three UI entry pages. The container build was cancelled at the user's request; no 4.75.0 container image or destination-server deployment is claimed.

See [the operation guide](JIG_AND_LIBRARY_GUIDE.md) for the one-time defaults refresh on older saved Project 2 workspaces and library reuse steps. Tests use virtual I/O; physical machine behavior and automatic vendor CAD/EPLAN interpretation are outside this result.

## 0.6.0 update - 2026-10-18

Both complete selected configurations compile with zero active errors and reopen
with all eight assigned cyclic classes. These checks use the original Project 2
and Project 3 directories, not the earlier program/login previews.

Project 2 (`LDF3S_WO_SUCTION`) passed 7,500 scheduler scans / 3,000 virtual ms.
Task counts are 7,500, 60, 300, 100, 30, 6, 3 and 1 for Cyclic#1 through #8.
There were no runtime faults, and all 1,208 source-file hashes were unchanged.
This result includes one recorded simulation-copy correction: the original
255-byte memcpy request from a 17-byte source array is replaced by SIZEOF of
that source. The exact original-code hash, expression, replacement and reason
are saved in `examples/project2-source-corrections.json`. The original PLC file
was not edited. Repeating the source bug without the correction still faults.

Project 3 (`Config7_REG_MCMT_CTL_HPM_ECS`) passed 750 scheduler scans / 3,000
virtual ms with zero dependency/compiler blockers and no runtime faults. Task
counts are 750, 375, 75, 44, 6, 8, 5 and 3 for Cyclic#1 through #8. All 1,785
original file hashes are unchanged.

Following the user's instruction to select representative textile values,
`examples/project3-textile-baseline.json` initializes FRD_VW1904 to 270 (27.0 mm).
The scale is checked against the original HMI and display-conversion logic.
Rieter documents 27 mm as a regular roller size; the project's commented test
value also uses 270. The profile records manufacturer links and identifies the
value as a simulation assumption. No other machine or recipe values are seeded.

This result also uses four recorded source-copy corrections in
`cs_read/cs_readCyclic.ab:98,197,420,554`. The original routine requests a
255-byte copy from the 25-byte SENDBUFFER. Each simulation-copy correction uses
SIZEOF(SENDBUFFER), retaining the original 16-byte transmission length. Exact
original hashes and context fragments are saved in
`examples/project3-source-corrections.json`. Removing the corrections restores
the bounded-memory fault at 1,760 virtual ms. Original PLC sources stay intact.

The checks exercise complete startup scheduling and the observed idle paths
for three virtual seconds. They do not establish every recipe/operation branch,
physical-device behavior or real-time performance.

Full-project evidence: `.build/virtual-plc/project2-readiness/readiness.json` and
`project3-readiness/readiness.json`. Saved complete-workspace IDs and reopen
results are in `0.6.0-workspaces.json` and `0.6.0-reopen-checks.json` in the same
build directory. Saved-workspace runtime status is stopped.

All 138 Python tests passed (two dependency deprecation warnings). The isolated
Vite production build and strict TypeScript check passed. The
single existing Start_uSOPp.bat launcher activated the exact named checkout on
port 8200. Base health reports 4.66.0; the served Virtual PLC asset contains
0.6.0. The library reference endpoint requires authentication (401 without a
session). HTTP evidence is `0.6.0-http-checks.json`.

The portable JSON registry contains 2,278 documented entries and 391 executable
interface names, including conversion families and string aliases. Metadata
does not execute help examples. Undeveloped entries remain explicitly marked
unsupported. The public Python facade, source correction guards, scoped state,
virtual buffers, C pointer operations, CSV and configured CAN data have focused
regression coverage. See [library usage and limitations](LIBRARY_GUIDE.md).

Additional regressions cover shared Ladder/ST/Basic integer assignment storage,
complete array bounds within opaque FB containers, captured pointer indexes,
deep ACTION/function fault locations, and atomic composition of multiple
source-copy corrections. Failed correction validation leaves the model intact.

## 0.5.0 update - 2026-10-18

77 Python compiler/runtime, adapter and API tests pass (two dependency deprecation warnings). Strict TypeScript, 32 Python syntax checks and the isolated Virtual PLC Vite build pass. The unified launcher activated this checkout on port 8200; base health reports 4.66.0, the Virtual PLC asset contains 0.5.0, and protected project routes return 401 without a login.

CPU fixtures cover RTC set/get and documented structure-member bytes, virtual clock advancement, DATE_AND_TIME, zeroed timers, asynchronous IP reads, invalid buffer pointers, battery encodings and exact mapped serial inputs with force precedence. Additional tests cover Basic IP-program syntax, C _GLOBAL declarations, exact scalar Ladder conversion geometry, numeric password snippets, role writer selection, HMI page target scoping, layer bits, hidden hotspot/opaque shape input blocking and immediate layer states returned by authenticated API actions. Separate previews retain account ownership and parent blockers.

Read-only compilation of Project 2, configuration LDF3S_WO_SUCTION, finds 4,717 declarations after restoring explicit C globals. Full-project execution remains blocked by 497 active findings: 301 unresolved symbols, 80 unsupported Ladder networks, 41 wiring findings, 37 unsupported calls, 19 syntax findings, 17 element types, one missing coil and one pointer-layout dependency. Thirty-five unambiguous scalar conversion networks now compile. These counts expose newly parsed source dependencies; they are not a complete-machine execution result.

The source password/login preview selects passwordCyclic.st and loginoutCyclic.ab with original task intervals (1000 ms and 30 ms). A source-backed execution check initialized role credentials, accepted the source-defined role-one password, updated Login_1_V and rejected an invalid entry. No password strings were printed in evidence. Other machine tasks and their popup initialization remain excluded. AL_popup, for example, follows ALL_Layer_Popup, whose original initialization is in al_logicInit.ab; it is not hidden automatically by a login preview.

Layer Active and BackColor are editor properties according to the supplied B&R help. They do not define runtime triggers or opaque covers. Login_Layer is bound through StatusDatapoint; original virtual keys write 0 to open and 1 to close. Independent layer status polling covers even empty layers. The runtime preserves visible hotspot/shape input blocking and exact control drawing order.


Headless Edge verified a temporary Project 2 HMI preview: CPU service settings saved; descriptor files were hidden; Run initialized the source role password; the original password control accepted login level 1; login visibility logic updated; AUTOLEVELLER_SETTING3's original hotspot opened LOG_IN_OUT and its BACK virtual key closed it. The runtime layer inspector displayed source switch keys. No browser script errors occurred. The existing account middleware logged cancelled polling requests during page changes; those did not prevent the interaction checks. Machine-specific popup initialization is outside this limited preview.

All 1,208 original PLC project files retained identical SHA256 hashes before/after the browser check. Detailed results: `.build/virtual-plc/0.5.0-project2-results.json`; screenshots: `0.5.0-login-layer-open.png` and `0.5.0-hmi-layers.png`; build and HTTP evidence: `0.5.0-build-checks.json`.

## 0.4.1 update - 2026-10-17

The normal Start_uSOPp.bat now launches the existing app and Virtual PLC in one server; stop and restart are commands on that same file. Separate Virtual PLC batch files were removed. The unified launcher restarted this checkout on port 8200. The base health, application home, installed Virtual PLC navigation and current module assets were read successfully; protected project APIs still returned 401 without a login.

Interrupted/cancelled/failed analysis now offers Retry analysis directly. A stopped analysis does not show a running percentage or Cancel button. Failure messages survive reopen, and an old analyzing marker without a saved model becomes a persisted interrupted status.

Python, PowerShell and strict TypeScript syntax checks and the isolated production build passed. No execution or browser test suite was run for this patch; 0.4.0 results below are historical. Readiness evidence: `.build/virtual-plc/0.4.1-build-checks.json`.

## 0.4.0 update - 2026-10-17

61 Python compiler/runtime, project adapter, topology and API/storage tests pass. Strict TypeScript checking, 26 Python syntax checks and the isolated production build pass. The base application remains 4.66.0.

Headless Microsoft Edge opened a temporary copy of the user's Project 2, configuration LDF3S_WO_SUCTION. It rendered 18 visible hardware nodes and 17 source-backed links, with 32 base/terminal accessories. Fit and zoom worked. Double-clicking X20AP3131 opened its explicitly labeled shared family manual; searching X20DI9371 opened the exact module manual. There were no page JavaScript errors or failed requests during the completed check.

The browser created a separate program-test workspace for Logical/loginout/loginoutCyclic.ab and executed five Single scans using its original 30 ms task interval. At current_password_level 0, 1, 3, 9 and 10, the values of Login_1_V / Login_3_V / Login_9_V were respectively 0/0/1, 1/0/1, 1/1/1, 0/0/0 and 0/0/1. Virtual time reached 150 ms. These values matched the original source logic. This is one program's execution, not a complete machine simulation or a complete HMI/password test.

The full Project 2 stayed stopped at zero scans with 523 active blockers: 282 unresolved symbols, 115 unsupported Ladder networks, 41 Ladder wiring findings, 39 unsupported calls, 26 unsupported syntax findings, 17 unsupported Ladder element types, two pointer layout findings and one network without a supported coil. More findings can become visible as previously unsupported syntax is parsed. No active dependency was bypassed.

The explicitly empty usb_val1 Source is now an informative unassigned slot, following the user's clarification. A nonempty missing Source still blocks execution. Library .fun formal parameters produce zero standalone memory-type warnings; actual active unresolved PLC instances remain checked. HMI status/layer/login bindings outside the first 1,000 variable rows are covered by the bounded polling regression test.

All 1,208 files under the original Project 2 source root had identical SHA256 hashes before and after verification. The browser used temporary accounts and copied workspace storage. Detailed evidence and screenshots are under `.build/virtual-plc/0.4.0-project2-results.json`, `0.4.0-project2-topology.png`, `0.4.0-module-help.png` and `0.4.0-program-test.png`.

A separate saved workspace named **project 2 - program test: loginoutCyclic** is available under the original Project 2 account. Identity: `6d5e268702ac432a86262fbda80a20c0`. It starts stopped and watches current_password_level, Login_1_V, Login_3_V and Login_9_V. The original full workspace is retained. The 0.4.0 launcher was activated on port 8200; the base health and current module assets returned HTTP 200, and protected module endpoints returned HTTP 401 without a login. Build/health evidence is in `.build/virtual-plc/0.4.0-build-checks.json`.

## 0.3.1 update - 2026-10-17

Build checks: all 22 module/launcher Python sources parsed, strict TypeScript passed, and the isolated production Vite build passed. No execution or browser tests were run. Evidence: `.build/virtual-plc/0.3.1-build-checks.json`.

Read-only source analysis restores 9,776 variables (eight additional case-distinct declarations), with zero exact declaration conflicts. The HMI adapter reads 230 pages, 1,667 status-bound controls and 76 status-bound layer instances. These are source extraction counts, not evidence of working browser interaction.

Static compilation of the same saved LH20S model reports 598 active errors: 59 unsupported calls, 234 unresolved symbols, 138 unsupported Ladder networks, 133 block wiring findings, 28 unsupported syntax findings and six unsupported element types. Run remains blocked; virtual time and scans remain zero. The old case-folding errors are removed; all remaining active dependency findings stay visible.

For validation in the UI: reopen the saved project, inspect the layer status words, log in using source-defined passwords, and inspect numeric fields at each permitted level. Dynamic credentials and PLC-calculated `Login_*_V` states require executing their original programs. Original source is never changed, and unimplemented library/network behavior is not bypassed. Status focus/touchpad feedback and unsupported password snippet formatting remain limitations.

## 0.3.0 update - 2026-10-17

Python syntax parsing (20 module files) and strict TypeScript checking completed. The isolated module production build is recorded in `.build/virtual-plc/0.3.0-build-checks.json`. No execution or browser tests were run for this update; results under 0.1.0 are historical.

Read-only analysis of the saved LH20S reference model reports 611 active errors: 59 unsupported calls, 239 unresolved symbols, 138 unsupported Ladder networks, 133 block-wiring findings, 28 unsupported syntax findings, eight declaration findings subsequently identified as false case merges in 0.3.1, and six unsupported Ladder element types. Virtual time/scans remain zero; complete project execution is blocked. This is a saved reference snapshot, not a claim about every uploaded variant.

Read-only HMI analysis finds 230 pages, 16 unique bitmap assets, four alarm groups containing 469 indexed definitions, 126 hotspots with resolved actions, and 1,074 bindings resolved to scoped declarations. This verifies resource extraction, not browser interaction or vendor runtime equivalence. Password management, alarm history/acknowledgement and unimplemented vendor controls remain explicit.

The new batch files target port 8204. Existing PowerShell launchers can target 8200 or another supported port. Original PLC sources and the existing validation engines are not edited by this module patch.

## 0.2.0 update - 2026-10-17

Completed: Python syntax parsing of all 19 Virtual PLC Python files, strict TypeScript checking of the Virtual PLC entrypoint and its imports, and the isolated Virtual PLC Vite production build. The local launcher restarted the API and reported Virtual PLC 0.2.0 ready on port 8200.

No device, Ladder execution or browser tests were run for this update. These build checks do not establish complete B&R compatibility or a successful run of the complete LH20S project. Existing unsupported vendor calls, multi-block networks and unresolved declarations remain explicit execution blockers. The original 0.1.0 results below are historical evidence.

## 0.1.1 update

MatchView's explorer/editor changes and the Virtual PLC run guide were built successfully. Main and Virtual PLC TypeScript checks, Python syntax checks, and the DataInspect asset build completed. This patch's new edge/counter aliases and starter workflow have not had execution tests run; the test results below belong to the original 0.1.0 verification. Full LH20S execution remains blocked by unsupported active dependencies.

Date: 2026-10-17. Base application: uSOPp.ai 4.66.0.

## Completed checks

- 49 Python compiler, runtime, adapter and API/storage tests pass.
- Frontend TypeScript checking and the isolated Vite production build pass.
- Headless Microsoft Edge renders the controller, variables and HMI views with no JavaScript errors or failed requests. A supported fixture completes Single Scan and variable search.
- The authenticated development frontend renders the Virtual PLC sidebar entry and WorkHub card, and both open the workspace. Shared Nami parser source and its XLSX dependency load through Vite instead of the backend static proxy.
- Local application health and module assets respond successfully. The existing application home exposes the new module entry. Protected module APIs retain existing authentication.
- All 759 existing tracked files match the hashes recorded before this feature. Pre-existing changes from earlier work are preserved.

## Real Lapformer project

The read-only `LH20S_PV2042` import identifies 829 relevant resources, 156 programs, 9,768 scoped variables, 8 task classes, 19 I/O modules, 180 mapped channels and 230 HMI pages. All 1,100 non-generated source-file hashes remain unchanged during analysis.

Whole-project execution is **blocked**. The project uses active Ladder function/FB networks and vendor constructs outside the supported interpreter subset, and contains ambiguous declarations. A scan attempt leaves virtual time and scan count at zero. These findings must be resolved or implemented before claiming a complete virtual run of this machine.

The imported engineering model, controller/task inspection, original-source views and supported simulation subsets are ready for review. This release does not claim complete B&R Automation Runtime compatibility, physical-controller equivalence or proprietary HMI reconstruction.

## Evidence

Development evidence is stored under `.build/virtual-plc`: unit/integration results, source integrity checks, real-project adapter/runtime reports, browser results and screenshots. Real PLC traffic, model downloads and a container release are outside these checks.
