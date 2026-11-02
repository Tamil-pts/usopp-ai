# Chopper and Virtual PLC: source-linked machine context

The shared decoder connects active hardware, source-associated HMI names,
machine/process settings, guarded operations, callable identities and explicit
state assignments. It reads the original PLC project. It does not change PLC
source, run the virtual scheduler, create a drive, or generate feedback signals.

## Shared implementation

`virtual_plc/core/machine_identity.py` consumes the existing Virtual PLC project,
hardware, HMI, declaration and task adapters. Chopper uses those same adapters
through an owner-scoped cache in `backend/core/machine_context.py`. Existing
Virtual PLC workspaces can generate missing context from saved source snapshots.
The packet validator and existing simulation compatibility checks are unchanged.

- The saved active configuration and configured visualization select hardware
  and HMI evidence. Other targets cannot supply an active alias or I/O route.
- A status lamp's ColorDatapoint is traced through its PLC producers to a unique
  Boolean. A uniquely aligned label in the same layer supplies a **candidate**
  machine name. Position is recorded as an association needing review.
- Dropdown text choices retain their selector and source index. `Not Used` is a
  conditional HMI caption, not proof that all related motor logic is inactive.
- Setting controls retain value, index, status, layer status, locking, visibility,
  minimum and maximum bindings. Defaults/retained declarations are not live values.
- Guarded assignments and network reads connect related scoped variables across
  routines. Explicit CASE state assignments provide condition-labelled graph
  edges. Neither source order nor read dependencies establishes task scheduling.
- Unresolved targets, members and parser coverage stay visible. Complex Ladder
  network reads do not become a claimed exact coil expression.
- Calls resolve instance types and callable declarations from project source.
  Named arguments, positional source arguments and declared ports are retained.
  Nested arguments are preserved. Complex argument binding and implementation
  internals remain unresolved when no proof is available.
- Exact callable topics from the installed B&R help are attached separately.
  A documentation match does not establish library-version compatibility or
  prove project execution. Generic manual history is not a callable-topic match.
- RS-485/CAN interfaces are connected to literal device paths in source calls.
  Node/index/subindex expressions stay attached. A serial interface alone does
  not establish Modbus, a drive identity, or a motor-speed register mapping.

## Interfaces

Virtual PLC has a **Machine functions** tab with names/settings, sequence and
dependency diagrams, typed calls/B&R references, and hardware/communication.
Its context endpoint reads current virtual values and existing VC4 control/layer
status evaluation. It never advances the simulation to obtain those values.

Ordinary Chopper project replies resolve a unique HMI-name candidate to its PLC
symbol before the existing writer investigation. Replies include the same
linked-context view. Project machine-flow questions use this investigation;
explicit routine/file flow requests retain the existing routine viewer.

REST:

- `GET /api/assist/projects/{key}/machine-context?q=...&limit=60`
- `GET /api/virtual-plc/projects/{id}/machine-context?q=...&limit=60`

MCP: `get_machine_context(project_id, question, limit)`. Engineering foundation
candidate discovery also includes source-associated HMI-name candidates.

Queries remain account bound. Chopper rejects combinations with changed indexed
sources, invalidates context when source inventory/configuration changes, and
withholds context publication if a project changes during investigation.
Individual published source references are checked against decoded content hashes.

## Verification

The regression fixtures exercise dynamic labels, target isolation, private scope,
parent status/dynamic limits, guarded state transitions, instance types, exact
vendor-help matching, stale publication rejection, cached-workspace upgrades,
API ownership and virtual status values without running scans.

Checked on 2 November 2026:

- Combined targeted suite: **89 passed**. This includes the actual MCP HTTP
  transport for `get_machine_context` and another-account denial.
- Main UI, PLC Data UI and Virtual PLC production builds passed. Browser checks
  covered real-project labels, selector conditions, settings search, dependency
  source links, hardware and B&R help in six light/dark responsive layouts.
- After the supported application restart, the existing saved Project 2 opened
  the new tab and its can-changer dependency graph with no browser errors.
  Its scan count and virtual time both remained zero; inspection ran no scans.
- `C:\Users\PTPL0241\Projects\JAY\LR9SXV6319`: saved configuration
  `Config7_REG_MCMT_CTL_HPM_ECS`; 832 HMI-name associations, 14,397 controls,
  274 routines, 10,545 resolved assignments/network records, 320 explicit state
  assignments, 300 I/O mappings, three communication interfaces and 7,826 call
  records. These counts are source records, not verified machine functions.
- `HS fan motor` resolves to `@global:HS_Q27_FanMotor`; its conditional HMI
  captions retain `DOFFER_INV_SELECTION`, and its active output mapping retains
  `%QX."X20DO9322f".DigitalOutput02`. Three selected `FRM_xopen` call records
  matched installed vendor help; serial device `SS1.IF2` remains a source link
  rather than proof of a particular attached drive.
- The final shared-decoder/writer/call check took 72.34 seconds, requested no
  model inference, and confirmed unchanged raw source hashes. The independent
  graph build and HMI-name candidate check also passed in the preceding run.
  **6,674 assignment targets/member expressions remain unresolved** in this
  project; complete operating sequence verification remains open.

Evidence is under `.build/chopper-machine-context/`: `verification/result.json`,
`verification/answer.json`, `verification/call-answer.json`,
`verification/foundation-candidates.json`, `final-regression.log`, `build.log`
and `browser-result.json`.

Reproduce real-project decoding in an isolated derived index:

```powershell
.venv\Scripts\python.exe scripts/verify_machine_context.py --project C:\path\to\project --query "HS fan motor" --foundation --call-name FRM_xopen
```

Artifacts default to `.build/chopper-machine-context/verification`, outside the
PLC project. The script verifies unchanged raw source hashes. It does not request
model inference. Full machine timing, unsupported library internals, complex
member/argument semantics and physical device feedback still need separate proofs.
The broad complete-machine publication gate remains closed.
