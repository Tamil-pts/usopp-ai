# How Chopper reads and explains a B&R project

This is the method used to prepare source-derived training answers and guide
backend analysis. Project facts come from the selected project's decoded source;
library contracts come from the supplied B&R help index. A trained adapter teaches
the answering method. It does not supply the current project's live values.

## 1. Establish what is being analyzed

1. Read project identity and Automation Studio version.
2. Resolve the selected physical configuration, CPU, HMI and software task list.
3. Keep task ownership, enabled/disabled state, local scope and HMI target separate.
4. Inventory retained source files, declarations, ladder networks, HMI references,
   alarms and hardware. Skip temporary, generated and build output directories
   through the project scanner's existing exclusions.
5. Record coverage and unresolved references. An inventory is not proof that every
   function has been understood or that a configured task currently runs.

Related revisions of the same project belong in the same training split. Use a
different project family for held-out examples; do not evaluate on a near-copy
of a training project and call that an unseen project.

## 2. Decode each format in its own language

| Source | Preserve when decoding | Check before explaining |
| --- | --- | --- |
| `.st` | Program/function-block sections, assignments, nested branches, calls, state transitions and source lines | Comment masking, call scope, declared types, other writers and complete conditions |
| `.ab` | Automation Basic sections, `IF`/`ENDIF`, assignments, FUB calls and comments | Its actual syntax; do not automatically rewrite it as ST |
| `.c` | Preprocessor conditions, declarations, `_INIT`/`_CYCLIC`/`_EXIT`, calls, pointers, states and buffer sizes | Compile options, definitions versus calls, active includes, signedness and pointer/length producers |
| `.ld` | Network enabled state, row/column topology, normally open/closed and edge contacts, coil kind, block instance and pins | Join header/top/middle/bottom segments; retain parallel junctions and set/reset writers |
| `.var` | Declaration blocks, name, type, initial value, retention qualifier and scope | Local versus global, alias resolution, type definitions and array bounds |
| `.typ` | Named types, structures, nested types and array dimensions | Resolve referenced types in the appropriate scope/library |
| `.page` / layers | Page dimensions, layer references, controls, geometry, bindings, key actions, text and bitmap references | Selected HMI target, shared layers, datapoint aliases, Z-order and runtime visibility |
| Text/alarm groups | Numeric identities, language values, alarm bindings and referenced messages | Actual source mapping; a placeholder is not a decoded alarm description |
| Physical configuration | CPU/software tasks, device addresses, modules and I/O mappings | Selected configuration and linked implementation; physical presence is not proof of communication |

A file may mix a program wrapper with generated ladder XML. Explain the
reconstructed network, not just its XML tags. A library definition or declaration
is not proof that an instance is called. Comments and disabled networks do not
execute.

## 3. Answer the user's engineering question

### Project functions

Group source-supported functions, then trace their entry conditions, operating
modes, outputs and stop/fault paths. Explain the requested scope first. Mark machine
purpose as inferred unless source identifies it. Do not turn a task list or the
order of retrieved excerpts into a complete machine operating sequence.

### A specific function

Follow the requested symbol from its declaration through its callers, guards,
assignments and consumers. For a timer, give its actual preset and pin wiring;
the instance's name does not establish a duration. For HMI actions, follow the
control's binding to the correct local/global variable and its executable use.

### Why a fault occurs

Trace:

`alarm or failing status -> set/normal writer -> upstream conditions/timer/state -> reset/recovery writers`

Preserve complete ladder branches, latches, prior assignments and state-machine
order. Explain the static trigger path. Distinguish that path from a possible
physical cause and from the actual cause of an observed incident. Ask for the
smallest relevant live set: input/feedback, command, state, numeric block status,
timer IN/PT/ET/Q and latch/reset values.

### Communication

Identify actual calls and their declaration types, physical interface, application
protocol, role, device/endpoint, enable, open/handle, request/response, status,
timeouts, retries and close/recovery. RS485 is a physical interface; DVFrame or
Modbus naming alone does not prove it. Trace literal mode strings and hardware
configuration. Use version-matched help for timeout units and numeric errors.

### Syntax and improvement review

Identify the language, project/compiler settings and declarations first. Review
complete blocks, data types, array bounds, block signatures, pointer lengths,
other writers and comment/disabled state. Use deterministic application checks
where available, retaining their exact verdicts and coverage.

An LLM/source review can identify candidates. A matching Automation Studio build
provides authoritative syntax/type diagnostics. Do not call a project
compiler-verified without those diagnostics. Proposed edits should include their
source location, reason, expected effect and required verification; the engineer
controls saving PLC changes.

## 4. Give a concise, traceable answer

1. Direct answer to the requested function or symptom.
2. Conditions, action and effect supported by source.
3. Supplied `[S1]` project evidence and `[H1]` help references.
4. Unresolved facts and the next useful check.

Do not claim global absence because one search found no match. Do not borrow
addresses, defaults, timings, labels or types from another project. Reference
identity checks cannot prove that the explanation's reasoning is correct.

## 5. Teach the method through actual adapter training

Source-derived records contain an informal question, the exact source/help
context and an authored answer following the method above. They do not require
manual approval for the development run. Preserve their origin, source digest,
project family, coverage and truthful review status.

The CPU trainer masks system/user tokens, optimizes an adapter on complete
answers and holds out another project family. Its manifest records real steps,
loss, skipped rows and saved artifacts. Dataset preparation and downloads are
separate from weight optimization; a saved adapter is separate from an installed
serving model. See [CHOPPER_TRAINING.md](CHOPPER_TRAINING.md).

At inference time, keep the source decoder, selected-project retrieval, B&R help,
task guide, citation checks and deterministic validators. Training complements
that pipeline; it does not make a small model an Automation Studio compiler or
a live PLC diagnostic connection.
