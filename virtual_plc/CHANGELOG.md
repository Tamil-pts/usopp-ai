## 0.11.0 - 2026-10-24

- Add a live HMI layer/control workbench with source key functions, current permissions, covering overlays and PLC writer links.
- Implement target-scoped configured current/requested page datapoints, source page indices, the 65535 request acknowledgement and previous-page history.
- Read dynamic button text and bitmap indices. Resolve exact type-matched global declarations inherited by a source DSO program folder, with a diagnostic warning.
- Execute control-dependent live alarm cursor navigation. Validate source key permissions, values and completion writes, and reject unsupported actions explicitly.
- Upgrade locally available saved HMI definitions to adapter 7 while preserving source files, corrections and component configuration.
- Import bounded source string-table data objects for DatObjInfo/DatObjRead. Preserve literal data bytes and documented string termination; report unsupported formats. VA_GetAlCurPos reads the visible source alarm cursor.

## 0.10.4 - 2026-10-24

- Use typed, server-resolved HMI selection choices. Boolean values display as the matching 0/1 caption; text offsets and current source limits are enforced.
- HMI actions return consistent values, formatted text, permissions and layer state. Ignore older polls and previous-page button-release responses.
- Execute scheduled login display/visibility updates after password entry and logout while preserving the prior running or paused state. Explain input locks and provide an explicit Operate HMI control when inspecting.

## 0.10.3 - 2026-10-24

- Persist early faults and source stops immediately, independently of the periodic configuration autosave. Keep the last failure reason available after reopen.
- Display the stop reason below the PLC controls with source navigation and an execution-trace shortcut. Record SYSreset source location and reset mode.
- Preserve worker failure details and clear stale worker errors when the operator resets or restarts execution.

## 0.10.2 - 2026-10-24

- Password Enter completes bounded source startup and scheduled password initialization before comparison. Retained credentials are checked after INIT; source defaults and text-group mappings remain authoritative.
- Paused login changes execute source display/visibility updates and return to pause. Breakpoints, unsupported logic and faults remain visible; pending display updates are reported separately from password comparison.
- Display configured level IDs and the exact login result tag. Verify level IDs through 11, retained passwords, wrong input, startup ordering and the HMI action API.

## 0.10.1 - 2026-10-24

- Device connection rows show linked devices, default references and raw/scaled values. Linked output consumers count as valid feedback connections.
- Drives, velocity/position servos and motors support explicit PLC reference scaling; linked engineering values are not scaled twice.
- Project 2 healthy-default restore adds source-fingerprinted Hank reciprocal guards and analog-reference mappings. Unavailable zero-weight feedback displays zero; target settings keep their previous value. This is an audited simulation convention; it does not establish correct machine calibration.
- HMI numeric inputs show live source bounds and producer locations. Missing numeric limits stay unresolved; the server checks fresh bounds before writing. Login previews link to the parent project.
- How to run shows runtime source faults and recovery steps.

# Virtual PLC module changes

## 0.6.0 - 2026-10-18

- Add source-referenced reusable Python service models, a public BRLibrarySession
  entry point and a versioned JSON registry with documented/implemented status.
- Compile real Ladder dataflow, EN/ENO result retention, arbitrary scalar
  functions, multiple FBs, jumps, RETURN and transition contacts.
- Add nested FB calls, Basic ACTION/LOOP/GOTO/ACCESS, C declarations, bounded
  pointers, casts, sizeof, switch, ternary expressions and string decay.
- Preserve authoritative IEC types when importing C headers. Add documented SG4
  structure alignment and source integer/string assignment behavior.
- Verify complete Project 2 execution with an exact-hash simulation-only serial
  copy correction. Add a manufacturer-referenced Project 3 simulation profile
  for a 27 mm roller and audited serial-copy corrections. Preserve every original
  PLC source file.
- Share integer assignment storage rules across Ladder, ST and Basic. Preserve
  the full extent of arrays addressed inside opaque FB containers, capture
  pointer indexes and retain bounded memory checks. Report faults at the deepest
  source ACTION/function instruction. Compose multiple source-copy corrections
  atomically while checking the original program hash.

## 0.5.0 - 2026-10-18

- Add workspace CPU services for RTC_gettime/RTC_settime, DTGetTime/DTSetTime, BatteryInfo/SYS_battery, SysInfo/RTInfo and CfgGet/CfgSet Ethernet configuration. Bound virtual memory to the exact documented RTC structure; publish serial numbers only via original I/O mappings.
- Extract explicit comma-separated C _GLOBAL declarations, preserving configuration scope and incompatible declaration blockers. Support zeroed standard timer initializers and Basic trailing comments, LOOP/ENDLOOP and EXITIF.
- Compile unambiguous single scalar conversion Ladder networks to typed assignment/call IR. Branches, unknown functions and unresolved graph scheduling still block.
- Add separate source-backed password/login preview workspaces, integral numeric text snippets, width-correct IEC NOT for declared integer references, target-scoped page navigation, independent layer status polling and immediate HMI action state updates. Show the original keys that switch each runtime layer and distinguish editor active layers. Remove editor-only layer BackColor covers that intercepted runtime controls.
- Hide IEC.prg and .pkg in the project tree without discarding their scheduling metadata. Keep the single Start_uSOPp.bat launcher and base application 4.66.0.


## 0.4.1 - 2026-10-17

- Use Start_uSOPp.bat as the normal launcher for the complete application and Virtual PLC on one port. The same file accepts stop and restart. Remove the separate Virtual PLC batch files. Preserve exact checkout/process ownership checks when stopping either server entry point.
- Check that a reused server includes Virtual PLC navigation; give the unified restart command when the running server predates this integration.
- Add Retry analysis directly to interrupted, cancelled and failed analysis views. Show progress/Cancel only while analysis is running; retain failure messages across reopen and persist interrupted status.

## 0.4.0 - 2026-10-17

- Reconstruct the selected configuration's CPU, local and remote bus topology from Hardware.hw connections and Hardware.hwl coordinates. Collapse bus bases to their host modules, keep base/terminal parts inspectable, preserve interface ports and cable branches, and number stations within each branch.
- Add a searchable hardware tree, connected diagram, selectable ports/links, pan, zoom and Fit. Distinguish physical channel counts from mapped PLC signals. Configurable DI/DO/AI/AO/motor/servo/VFD/encoder wiring remains available beside project topology.
- Add offline module-name lookup, including explicit shared-family manuals, technical data, pinouts, registers and local images. Vendor HTML scripts and drivers are not executed.
- Stop allocating .fun interface parameters as global PLC memory. Actual unresolved instances remain execution blockers. Support Basic semicolon comments, ELSE IF and declared alias FUB calls; preserve source line references and reject mismatched block types.
- Treat an empty unresolved task Source as an informative unassigned slot, following the user's configuration clarification. Nonempty unresolved mappings remain blocked; no original source or task configuration is edited.
- Add a separate source-program test workspace with its original interval, lifecycle and dependencies. Clearly show excluded machine tasks. Preserve the complete project's blockers and original source snapshot.
- Include HMI status, layer, login/locking, text and limit bindings in bounded live memory polling, including variables outside the first variable page.

Verification and remaining full-project limitations are recorded in ACCEPTANCE.md.

## 0.3.1 - 2026-10-17

- Preserve case-sensitive B&R variable, member, enum, type and callable identities. Restore the eight case-distinct declaration pairs from the cached LH20S source without changing the original project. Preserve exact duplicate-declaration blockers and remap saved watch/device identities to the same original declaration.
- Apply VC4 StatusDatapoint bit 0 (hide) and bit 1 (input lock) at both control and layer levels. Evaluate LockingDatapoint/LockingLevel comparisons. Ignore editor-only VisibilityMode during runtime.
- Add server-checked HMI actions and keypad confirmation. Recheck current status, login limits and covering hotspots at submission; allow release of an already pressed momentary button after a layer hides.
- Render hotspots transparently during operation, add a read-only runtime layer inspector, resolve dynamic SingleString login text, and remove overlapping missing-bitmap/control-name labels.
- Add masked local password entry using the source-defined text group or STRING array and supported STRING snippets. Passwords never enter PLC memory or traces. Uninitialized passwords and unsupported snippet formatting cannot authenticate; PLC-derived login/status values still need actual program scans.
- Keep the base app at 4.66.0. Full project execution still requires unsupported vendor blocks, Automation Basic forms and Ladder networks. Syntax, TypeScript and isolated production build checks are separate from execution/browser verification.

## 0.3.0 - 2026-10-17

- Implement bounded ADR/SIZEOF, AsString/AsBrStr string and memory functions, TON_10ms, and virtual FileIO instances using the supplied B&R help. Resolve library calls through their declared instance types; preserve remaining unsupported calls and source conflicts as execution blockers.
- Add DI, DO and motor models and a configurable topology canvas for all eight device types. Save positions, use scoped PLC port connections, show linked devices and allow DI/AI signal changes without resetting drive/motor motion. Preserve forces and scan-boundary timing.
- Correct legacy single-colon declaration identities and exact scoped address resolution. Decode .dso program folders for source-backed HMI bindings.
- Add HMI zoom through 900%, numeric/string keypads with explicit errors/limits, set/toggle/momentary key actions, resolved bitmap assets, line objects and current AlarmImage captions. Keep password management, historical alarm behavior and unresolved vendor controls explicit.
- Reuse MatchView's Ladder geometry/render endpoint with pagination, Fit/zoom, source selection and SVG export. Support powered RETURN coils. Arrange controller and I/O stations naturally (ST2 before ST10).
- Add separate Windows batch start/stop launchers on port 8204 and configuration/reference guides. The base uSOPp application remains 4.66.0.

Read-only compatibility/resource analysis and build checks are distinct from execution verification. New execution/browser tests have not been run for this update.

## 0.2.0 - 2026-10-17

- Add configurable generic analog input/output, servo, VFD and encoder components with graphical cards, scoped port mapping, live values, explicit enable/save and workspace export/import persistence.
- Advance component feedback at supported completed scan boundaries; honor forces, reject duplicate output writers and incompatible bindings, and reset device motion on reload/reset/recheck. Imported devices start disabled.
- Resolve Ladder contacts/coils through the same array/member leaf types as ST. Add complete expression parsing, source-line references, separate per-network edge state and conservative single standard IEC block wiring.
- Show shared declaration identity and same-named scopes in the variable inspector. Correct nullable workspace polling state.

These changes have not had execution tests run. Complete LH20S execution remains blocked by unsupported active dependencies. Original PLC files and existing validation modules are unchanged by this patch.

## 0.1.1 — 2026-10-17

- Add How to run with source-linked, searchable execution blockers and clear conversion-support explanations.
- Add a separate, labeled starter PLC example with motor-command interlocks and a scan counter.
- Recheck saved-project compatibility using current interpreter support without reindexing; reset virtual state explicitly.
- Support program-local EDGEPOS/EDGENEG call-site state and B&R CTU RESET / CTD LOAD aliases. Unsupported edge state in user functions/blocks remains explicit.
- Prevent stale source responses and keep the source dropdown and inspector selection aligned.

The complete LH20S project still requires unsupported vendor libraries and Ladder/Automation Basic execution features. Run does not bypass those findings.

## 0.1.0 — 2026-10-17

- Add the opt-in extension launcher and industrial engineering workspace, preserving all existing application files.
- Show Virtual PLC in the main sidebar and WorkHub, including SPA reloads, and provide an additive React development launcher/configuration.
- Adapt existing project identity, source indexing, hardware, task, I/O, Ladder and HMI readers into one source-referenced engineering model.
- Add typed/scoped PLC memory and deterministic IR execution for supported ST, Automation Basic, scalar C and contact/coil Ladder subsets.
- Add bounded IEC timer/counter/edge implementations, persistent block state, task execution, source trace, whole-variable forcing and breakpoints/stepping.
- Connect controller graphics, variable watch, I/O and a separate source-bound HMI to the same simulated memory.
- Add private workspace save/reopen, portable source/model export/import, virtual overrides, scenarios and saved templates.
- Reuse offline Chopper retrieval/model transport with source and runtime evidence; AI errors do not stop simulation.
- Add compiler/runtime, adapter and API/storage integration tests, including source hashes and real Lapformer project analysis. Unsupported active dependencies remain blocked and explicit.

The existing uSOPp application remains version 4.66.0. Container release files are unchanged.
