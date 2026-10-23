# Virtual PLC 0.9.0

An additive engineering and simulation module for uSOPp.ai 2.0. The launcher mounts it into the existing backend, reusing account sessions, project upload, project identity, source indexing, Ladder geometry, HMI decoding and the Chopper model runtime. MatchView's explorer and code-view styling are updated separately at the user's request. Validation engines and imported PLC sources are unchanged by these updates.

## Latest update

Version 0.9.0 schedules every INIT, CYCLIC and EXIT entry in combined source
files at its original CPU assignment, and caches resolved variable identities.
This includes the encoder frequency producers in Project 2.

**Run PLC** is separate from **Simulation jig ON/OFF**. Jig
preparation supplies reviewed healthy contacts, clears injected test faults and
resets the virtual PLC. Delayed actuator-to-sensor rules support automatic
feedback with persistent manual overrides. Project 2 includes load switches,
fan pressure switch/transducer feedback, shaft counters, healthy can presence
and a 2 s FAST pushbutton press. CPU RTC follows the PC local
clock by default, with an editable custom clock. Scan batching removes the
per-quantum host sleep. C floating assignments to integer fields truncate as C
requires; external input validation remains strict.

Version 0.7.1 makes field cards compact and adds **Operate / Edit / Move**.
Moving saves presentation coordinates while scans continue. Editing pauses the
PLC before connection changes. Port inspection remains available during Run.
VC4 local key mappings are resolved from each owning layer, including the
Project 2 export popup START/CANCEL keys. Password dialogs report source
readiness and the scheduled producer task without exposing credential values.

Version 0.7.0 adds the project-derived field environment, dark device topology,
operator contacts, linked drive/motor/encoder models, source signal traces and
live timer/alarm views. Project 2 has a fingerprinted, editable commissioning
profile. See [Field environment](FIELD_ENVIRONMENT.md).

Version 0.6.0 adds reusable B&R Python functions/blocks, a versioned JSON help
registry, expanded ST/Basic/C and Ladder execution, and full-configuration
readiness checks. See the [Python library and project readiness guide](LIBRARY_GUIDE.md).

Version 0.5.0 adds virtual CPU services, source-backed password/login previews, numeric text snippets and immediate layer switching. Version 0.4.1 uses one normal application launcher and adds direct analysis recovery. Version 0.4.0 adds the source-derived controller/bus topology, offline B&R module manuals and a separate program-test workflow. Open **Controller layout → Project topology**, then double-click a module or choose **Module help**. Hardware configuration and virtual device wiring are separate views of the same workspace.

For a supported source program within a blocked machine project, open **How to run**, select a cyclic program and choose **Create program test**. The new workspace explicitly excludes the other machine tasks. Dependencies of the selected program are still checked. This does not establish a complete machine simulation. See [acceptance results](ACCEPTANCE.md) and [topology instructions](TOPOLOGY_GUIDE.md).

## Open on Windows

Use **Start_uSOPp.bat** in the application folder. It starts the main app and Virtual PLC together on the same application port (8200 by default). No separate Virtual PLC batch launcher is needed.

From CMD:

```cmd
Start_uSOPp.bat
Start_uSOPp.bat stop
Start_uSOPp.bat restart
```

Start opens the existing application home. Sign in, then choose **Virtual PLC** in the sidebar or WorkHub. To use LAN access: `Start_uSOPp.bat -Lan`; restart into LAN mode with `Start_uSOPp.bat restart -Lan`. Existing options such as `-Port 8200`, `-NoBrowser` and `-CheckOnly` remain available. Stop/restart refuses unrelated processes.

If a running server predates Virtual PLC integration, finish active jobs and use the same launcher's `restart` command. A restart can interrupt indexing. Reopen the workspace and choose the visible **Retry analysis** button. Interrupted analysis does not show a running percentage or enable simulation.

The separate Start_Virtual_PLC.bat and Stop_Virtual_PLC.bat files have been removed. PowerShell helpers remain available for development and internal use. Base application version: 4.66.0; Virtual PLC module: 0.8.0.

### Frontend development

Use the additive development launcher so the main React frontend also receives the Virtual PLC navigation and backend proxy:

```powershell
.\Start_Virtual_PLC_Dev.ps1
```

Open `http://127.0.0.1:8201/`, sign in, and choose **Virtual PLC** in the sidebar or WorkHub. If the original backend is running, use `-ReplaceCurrent` after finishing active jobs. If an older frontend occupies port 8201, close it or use `-FrontendPort 8203`.

The normal `npm run dev` uses the original Vite configuration. The extension development configuration is `virtual_plc/development.vite.config.ts`; it reuses the original configuration and adds only module navigation/proxying. Stop the extension frontend with `Stop_Virtual_PLC_Dev.ps1`.

### Build the new interface

Existing application dependencies and Node.js 20+ are sufficient; no new dependency installation is required.

```powershell
node .\node_modules\vite\bin\vite.js build --config .\virtual_plc\vite.config.ts
```

Output is confined to `virtual_plc/dist`. The main application and DataInspect interfaces are not rebuilt.

## First project

### Run the supplied example

1. Click **How to run** in the simulation toolbar.
2. Click **Open runnable example**. This creates a separate workspace named **Starter PLC - training example**.
3. Wait for analysis, then open **Variable monitor**. Write `StartCommand = TRUE`; keep `StopCommand = FALSE` and `DoorClosed = TRUE`.
4. Click **Single scan**. `MotorRunning` becomes TRUE and `ScanCounter` increases.
5. Use **Run** and **Pause** for continuous scans. Set `StopCommand = TRUE` to stop the example motor command; use **Reset** to restore the initial virtual values.

The example's `VirtualTrainingCPU` is a declared teaching configuration, with no physical connection. Its values are never presented as results from your machine project.

### Why Run is disabled for LH20S

Loading a project establishes its engineering model; it does not make unsupported library or Ladder instructions executable. Click **Review blockers / How to run** to see conversion-support categories and exact source lines. These findings are not a verdict that the original PLC is faulty.

After updating the module, **Recheck project** applies the current interpreter to the saved model without reindexing. It resets virtual values and scan history. Remaining unsupported active dependencies keep Run disabled. Use Automation Studio simulation when the complete project requires B&R library behavior not implemented here.

### Import your own project

1. Choose **Import project**. Reuse an uploaded session, select a project folder, or enter its server-side path. Configuration selection is optional when the active configuration is available in the project.
2. Watch actual indexing and analysis progress. The existing SQLite FTS index refreshes incrementally.
3. Review Controller Layout and Task Configuration. Unknown hardware models, total channel counts, task intervals or mappings remain unresolved; detected channel mappings are distinct from physical channel capacity.
4. Review simulation compatibility and diagnostics. Unsupported active code or unresolved dependencies block Run and Single Scan. Importing and viewing a project do not prove it is executable.
5. For a supported project, set simulated inputs, then use Single Scan or Run. Variable Watch, I/O, HMI controls and controller indicators share the same typed PLC memory.
6. Open HMI Simulation to operate supported source-bound controls. It is a separate memory client; HMI files never become cyclic PLC instructions.
7. Save the workspace or export its portable JSON snapshot. Use Save As to duplicate it; mark saved workspaces as controller, I/O or simulation templates in Configuration.

Virtual configuration overrides, watchlists and scenarios belong to the saved workspace. They never edit `.sw`, `.st`, `.var` or other original files. Changing task/I/O overrides requires a paused simulation and reconstructs virtual memory.

## Conversion and execution support

| Resource | Behavior in this release |
| --- | --- |
| `.st` | Data-only IR for supported Boolean/numeric expressions, assignments, IF/ELSIF/ELSE, CASE, FOR/WHILE/REPEAT, EXIT/RETURN, calls and custom functions/blocks. Unsupported syntax blocks the relevant unit. |
| `.ld` | Reuses existing Ladder network/branch geometry. Executes supported open/closed contact and coil graphs, including parallel branches. Ladder function/FB cells and unresolved connectivity are blocked. |
| `.ab`, legacy `.src` | Explicit Automation Basic control-flow/assignment subset compiled into the same IR. Unrecognized constructs are reported. |
| `.c` | Isolated scalar C subset interpreted as IR: supported declarations/functions, conditions, arithmetic and bounded loops. No native compilation, pointers, macros, casts, system calls or arbitrary code execution. |
| `.h` | Declaration/interface evidence only; never cyclic execution. |
| `.var` | Scoped typed memory, initial values and retention; unresolved vendor types remain visible and block active use. |
| `.typ` | Supported aliases, literal-bound arrays, structures and enums. Symbolic/unsupported definitions remain unresolved. |
| `.fun` | Function/FB interfaces linked to source bodies. A declaration alone is not an implementation. |
| `.page`, `.txtgrp` | Dedicated HMI representation using original geometry, supported controls, text/value mappings and memory bindings. Proprietary controls keep labeled placeholders. |
| `CPU.sw` and hardware | Actual active configuration, task assignments/order, known cycle times, topology and I/O mappings. Missing legacy information remains unresolved. |
| Libraries | Explicit Python implementations for supported IEC timers/counters/edges and bounded numeric functions. Missing proprietary calls block relevant execution. |

IEC support includes TON, TOF, TP, CTU, CTD, R_TRIG and F_TRIG with persistent block state between scans. Task timing follows a deterministic virtual clock; speed changes wall pacing, not PLC arithmetic or timer units. Reported wall execution durations are measured, not fabricated real-controller timings.

## Engineering views

- Resizable/collapsible Explorer, inspector and console; dark and light themes.
- Controller topology generated as SVG; original source hierarchy and paths retained.
- Task timeline, execution counts and measured interpreter durations.
- Read-only source navigation, line references, variable cross references and Ladder diagrams.
- Variable search/paging, watchlists, typed writes, whole-variable forcing and CSV export.
- Source-bound HMI writes, numeric controls, indicators, text and supported navigation.
- Bounded execution trace with source navigation, source breakpoints and instruction stepping. Calls are atomic at breakpoint boundaries.
- Chopper receives source retrieval plus a bounded observed runtime snapshot. Local model errors leave the simulator independent and return source evidence.

## Save/reopen and privacy

Workspace documents, snapshots and results are stored under the existing private work directory in `virtual_plc/<account hash>/<workspace id>`. Access is per account. A workspace reopens stopped; retained variables can be restored, while previous traces remain archived result evidence.

Portable imports recompile source and discard alleged server-side source roots and imported compiled IR. Source views are limited to the analyzed manifest or embedded snapshots. Original source files are never write targets. The runtime does not open physical PLC connections or execute imported Python/native C.

Virtual PLC Chopper inference uses loopback model endpoints; remote model configurations return local evidence instead of transmitting project data. Model weights are not downloaded by this module.

## Bounds and limitations

- At most six resident workspaces and two running simulations per server. Older stopped workspaces can be reopened from disk.
- Up to 15,000 project resources; individual text resources up to 8 MiB. Source analysis/cache and document exports have explicit size limits.
- Typed memory is capped globally at 300,000 allocation cells and 50,000 variables. Unknown/oversized definitions remain unresolved rather than allocating unbounded memory.
- Loops are bounded to 10,000 iterations, execution to 100,000 instructions per scan and calls to depth 24. Violations fault the virtual controller.
- Trace retains at most 3,000 events with bounded value payloads. Public polling limits variable rows and trace events; variable search loads additional pages. Large composite values are previews and are identified as truncated.
- Symbolic array bounds, native/proprietary B&R library behavior and hardware-specific timing are not emulated. This is not a replacement for Automation Runtime or physical commissioning.
- Event-driven tasks, unresolved legacy task configurations and proprietary HMI widgets require further implementation or explicit virtual configuration.
- Nested HMI array/member reads and writes are supported for resolvable literal paths. Forcing individual array/structure members is not supported; whole-variable forcing is supported.
- Named/local HMI data sources that require unresolved `.dso` mappings stay disconnected. VC4 status bits 0 and 1 are interpreted as hide and input lock for controls and layers; unresolvable status/login bindings lock input. Focus/touchpad feedback bits 2, 3 and 12-15 are not emulated.
- Scenario events are applied at scheduler scan boundaries; timestamps do not provide sub-scan physical timing.
- A compatibility verdict describes the supported virtual execution model. It does not prove machine safety or equivalence to physical hardware.

Virtual Control System and Virtual Machine are not implemented in this phase. Stable virtual I/O signal snapshots expose identity, type, direction, value, timestamp and quality through `/api/virtual-plc/projects/{id}/signals` for future consumers.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest .\virtual_plc\tests -q
```

Fixtures cover supported compilation/execution, Ladder branches, IEC blocks, declarations, hardware/tasks, HMI memory writes, source immutability, unsupported-call blocking, account isolation, save/export/import, retained memory and AI-failure isolation. Real-project analysis evidence and original-file hash checks are recorded separately under `.build/virtual-plc` during development. Physical PLC traffic is not used by these tests.

See [acceptance results](ACCEPTANCE.md) for the tested release scope and real-project limitations.

## Virtual device connections (0.2.0)

Open **Components**, choose **Add component**, select a generic analog input/output, servo, VFD or encoder, and map each required port marked `*`. Inputs read PLC commands; outputs publish virtual feedback to the same PLC memory used by ST, Ladder and HMI. Use the variable picker or copy a scoped declaration ID and append a literal member/index, such as `@global::Alarm[0]` or `Logical/axis::Axis.Position`. Save connections, explicitly enable the desired device, save again, and use Run or Single scan on a supported project.

- Device configuration is private to the workspace and travels with its export. Imported devices start disabled. Device motion resets on reset, recheck, reopened workspaces and connection changes.
- Edit while paused with no pending breakpoint scan, or reset first. Feedback starts only after an explicit supported Run/Scan/Step. Paused/stopped devices do not advance, and forced variables take precedence.
- All device command inputs are sampled before feedback is published at each completed scan boundary. Chained devices therefore use the previous boundary's feedback, independent of card order. Generic component model errors are shown on their cards.
- Output ports reject duplicate writers, constants, incompatible types, invalid indexes and integer ranges that cannot hold the configured feedback. Disabled drafts may leave required ports unbound. Device ports use exact scoped identities; same-named local variables in different programs remain separate.
- These are generic simulation models: no physical PLC/drive connection, fieldbus protocol, vendor firmware, safety function or closed-loop machine dynamics is emulated.

The Ladder interpreter now resolves the selected leaf type (for example a BOOL array element or timer Q output), rather than treating the entire array/block as the contact. It implements Boolean contact/coil networks and explicitly wired networks with one supported IEC block. Unsupported multi-block geometry, vendor calls and unresolved declarations still block active execution. PLC-to-Python conversion uses inspectable IR interpreted by Python; no source files are overwritten.

The 0.2.0 changes have Python syntax, TypeScript and production build checks recorded separately in ACCEPTANCE.md. They have not had execution or browser tests run.

## 0.3.0 workspace updates

See [TOPOLOGY_GUIDE.md](TOPOLOGY_GUIDE.md) for device wiring, live DI/AI controls, HMI input and the Windows batch launchers. See [LIBRARY_SUPPORT.md](LIBRARY_SUPPORT.md) for supported B&R library interfaces, reference paths and execution limits. Current static compatibility and HMI resource-analysis results are under `.build/virtual-plc/0.3.0-*.json`. Full LH20S execution remains blocked by other active dependencies. No execution or browser tests have been run for 0.3.0.

## 0.4.0 - declaration blockers and HMI permissions

The B&R help compliance list explicitly distinguishes `aBcD` and `ABcD`. For example, the LH20S source declares `calender_roller_piecing_v : BOOL` and `calender_roller_piecing_V : INT` in the same program. They are separate variables. Earlier Virtual PLC versions incorrectly folded these names together. Reopening a workspace with a complete source cache upgrades its declarations, HMI bindings, watchlist and device IDs. A partial cache requires **Refresh project**; the workspace remains inspectable.

In **HMI simulation**, use **Inspect objects** to see transparent hotspots and the runtime layer list. Bit 0 hides each layer/control; bit 1 locks its input. Field locking also evaluates the configured login datapoint and level. Hidden hotspots are absent from hit testing. Visible hotspots keep their source action and intercept covered fields; Enter checks permissions again on the server.

Click the password field for masked local entry. The configured password source determines the login level; there is no built-in universal password or automatic level elevation. Dynamic password strings, login text and `Login_*_V` values require the original PLC programs to execute. If Run is blocked or the PLC is stopped, the HMI reflects current virtual memory and does not invent the missing scan results. Unsupported text snippet formatting and unavailable dynamic credentials are reported explicitly. This emulates the virtual HMI behavior; it does not replace the application's account permissions.

Remaining blockers include the project's source-backed `CUMULATION` block (Automation Basic `FUB` calls/time dependencies), `LCRLimScal` and unresolved multi-block Ladder networks. Viewing a library's source or help does not provide an executable implementation. **How to run / Review blockers** lists current file and line evidence. Original PLC files and the existing validation engines remain read only to this module.

Reference pages in `knowledge/br_help/AS12/Help-en/Data/`:

- `programming/programmingmodel_compliancelist.html`, identifier feature 2-1.
- `visualization/viscompvc4/controls/ref-commonproperty_statusdatapoint.html`.
- `visualization/viscompvc4/controls/ref-commonproperty_locking.html`.
- `visualization/viscompvc4/common/ref-locallayer_visibility.html`.
- `visualization/viscompvc4/controls/ref-property_password_source.html` and `ref-property_password_leveldatapoint.html`.

## CPU services and HMI login

The login popup follows the original virtual-key chain. `MMS_CONFIG.HotSpot_13` uses `LOGIN_LAYER`, whose SetDatapoint action writes `0` to `loginout.Login_Layer`. The `LOG_IN_OUT` layer reads that same variable through StatusDatapoint. Its declaration starts at `1`, so the popup starts hidden. The BACK button uses `CLOSE_LOGIN_LAYER`, which writes `1` to hide it again. These are persistent SetDatapoint actions: releasing either control does not reverse the write. The hotspot's separate `Login_11_V` status controls whether that hotspot is visible and can be used.

- Open **Controller layout ? CPU services**, pause the simulation, configure the virtual RTC seed (UTC), Ethernet interfaces, battery states and explicit module serial numbers, then save. These values belong to this workspace; the host clock and network are untouched. RTC advances with virtual scans; reset/reopen restores the configured seed. Serial values are published only through exact SerialNumber I/O mappings.
- To inspect login while the full machine is blocked, choose **HMI simulation ? USER_LOGIN ? Create password/login preview**, then **Run**. The separate, clearly labeled workspace executes the original assigned password and login visibility programs with their original task intervals. Project 2 initializes its role passwords on Cyclic#7 (1000 ms), so wait at least one second of virtual time. Other machine tasks remain excluded and the parent project retains all its blockers. Machine-specific popups such as AL_popup still need their original initialization/cyclic logic; a preview does not invent hidden states for them.
- **Inspect objects ? Runtime layers** shows each layer's status binding, current word and original switch key count. Select a row to inspect the keys and pages that write it. Runtime status 0 shows, 1 hides, 2 shows with input locked, and 3 hides with input locked. The source Login_Layer keys write 0 to open and 1 to close. Login flags and covering hotspots are evaluated from the same PLC memory.
- B&R **Set Layer As Active** selects the layer for editing. It does not define a runtime trigger. A layer with no runtime StatusDatapoint is always visible. Editor VisibilityMode Hidden/Frozen does not replace runtime status. Layer BackColor is editor-only; the page and actual controls provide runtime backgrounds.
- IEC.prg and .pkg descriptors are hidden in the source tree, while their task/file metadata remains available to the project adapter. Original files are unchanged.
