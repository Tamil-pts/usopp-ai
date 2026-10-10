# B&R project decoding and engineering help

A compact uSOPp reference for engineers and Chopper. Original vendor manuals remain under `knowledge/br_help/`. Examples below illustrate syntax and record shapes; they are not extracted project source.

## Contents

- [How uSOPp transforms source files into structured evidence](#decoding-pipeline)
- [Project tree and source inventory](#project-layout)
- [Active configuration, CPU and HMI scope](#active-target)
- [Automation Studio 2.x / 2.7 legacy layout](#as27)
- [.st — Structured Text](#structured-text)
- [.ab — B&R Automation Basic](#automation-basic)
- [.c / .h — ANSI C source and declarations](#ansi-c)
- [.ld — Ladder networks and graphical topology](#ladder)
- [Global variables and Global.var](#global-variables)
- [Local variables and function-block instances](#local-variables)
- [.typ — Primitive types, aliases and type declarations](#datatypes)
- [Arrays, lower/upper bounds and indexed access](#arrays)
- [Structures, enums, strings and qualified members](#structures-strings)
- [RETAIN / remanent variables](#retain)
- [.per — Permanent variables and memory mapping](#permanent)
- [Tasks, subroutines, actions and execution order](#tasks-subroutines)
- [Functions versus stateful function blocks](#function-blocks)
- [Predefined B&R and user libraries](#libraries)
- [AsIcmp / IcmpPing — documentation lookup example](#icmp-library)
- [Hardware tree, .hw / .hwl and hw.cfg](#hardware)
- [.iom — I/O mappings and process variables](#io-map)
- [.page / .pages / .layer — HMI controls and layout](#hmi-pages)
- [.dso — HMI data sources and PLC aliases](#hmi-datapoints)
- [.txtgrp — Text indexes and language values](#text-groups)
- [Text snippets and formatted datapoint text](#text-snippets)
- [.bmgrp — Bitmaps, TouchPads and released/pressed states](#bitmaps-touchpads)
- [.algrp — Alarm groups and VCShared resources](#alarms)
- [Wrapped legacy source, unknown .ad and source encoding](#source-encoding)
- [Review checklist before editing B&R code](#editing)
- [Excluded temporary, cache and compiled folders](#temporary-folders)
- [Evidence chain, documentation and limits](#traceability)

## How the help reaches Chopper

KnowHub → **B&R help index** provides the topic tree, search and this guide download. On startup, the server builds a missing reference index in the background. Admin can rebuild it after replacing or adding help files. The last completed index remains readable while a new one is prepared.

`knowledge/help_index/br_help.sqlite3` is a derived full-text index in the persistent data directory. Each readable source topic records its original path, title, category, library, help-set label and SHA-256 digest. Images stay in the original help folder. Search retrieves bounded excerpts and supplies them to the configured model alongside project evidence. This changes the model context; it does not train or modify model weights.

The scanner inventories supported `.html`, `.htm`, `.xml`, `.txt`, `.st`, `.ab`, `.c`, `.h`, `.var`, `.typ` and `.ld` files. Files larger than 5 MiB, unreadable files and topics without extracted text are counted as skipped; extracted text beyond 100,000 characters is flagged as truncated. Other assets are not converted into language lessons. The UI reports coverage and indexing progress. A help-set folder label alone does not establish project compatibility.

The compact JSON and this guide ship with application releases. The large vendor help installation and derived index are local reference data and stay in the server’s persistent knowledge folder. Keep that folder in backups. Rebuild on the shared server with Admin’s button, or in a source checkout run `python scripts/build_br_help_index.py --data-root <persistent-data-root>`.

## Syntax and standards scope

Structured Text (ST) and Ladder Diagram (LD) are IEC 61131-3 language families. Automation Basic and B&R project wrappers/tooling require B&R documentation for the installed Automation Studio/runtime version. C entry-point conventions are B&R-specific. This guide is an engineering reference, not an IEC compliance assessment or a replacement for the full language/compiler manuals. Every edit needs review against actual declarations, target configuration and library versions.

<a id="decoding-pipeline"></a>
## How uSOPp transforms source files into structured evidence

Read bytes, resolve the active target, parse each format, preserve source locations, then render or retrieve the structured records.

- Discovery: compare.project_identity/project_info resolve project descriptors, active Physical configuration, task sources and HMI package. AS 2.7 may use pgm/<program>/<CPU>/*.src and Logical/HMI/Pages. Ambiguous target selection remains unresolved. project_paths.project_files prunes temporary/generated directories before reading files; it does not apply those exclusions to vendor manuals.
- Ladder: compare._ladder_networks extracts the <networks> XML section from an .ld source, retaining network order, labels, comments and commented state. ladder_model.network_model records cells with kind, row, logical column, original XML column, span, name, type, attributes, pins and IDs. Functions/function blocks span two logical columns. Header/top/middle/bottom pieces are joined by logical column and type, retaining the instance and block ID. Series wires join adjacent conducting endpoints; OR markers connect the right boundary to the preceding upper junction. Unknown elements, unmatched segments and missing junctions produce warnings. Do not flatten parallel branches into an AND list.
- Ladder enrichment/rendering: declaration_symbols/apply_symbols attach declared types, descriptions and source/declaration locations. normalized_model upgrades older saved geometry. primitives creates rails, contact/coil symbols, wires and function blocks for SVG and PNG rendering; diagram_panels splits large networks for reports. Comparison aligns ordered networks and checks cell/pin/geometry signatures. Drawing is a source view, not a PLC simulator. project_knowledge.ladder_behaviour explains only supported simple-series semantics; complex networks keep topology and unresolved block internals.
- HMI: compare._xml_controls reads named XML controls, ClassId and direct Property names/values; _page_properties reads screen properties. parse_screen_diff compares control identities and grouped properties. hmi_screen_layout separately resolves layers/references, inherited styles, scoped layer/control IDs, z-order, text/font/bitmap/virtual-key references and preview geometry. The plain control diff is not a complete HMI runtime parser; keep source text chunks for original file/line evidence. Text groups retain numeric text/value IDs and language strings; snippets retain datapoint/type/format details. Preview resolves local datapoints, text/bitmap groups, palette/font references and position. Nested property paths distinguish released/pressed bitmap states. Missing assets remain unresolved; a rendered preview is not a live HMI. Overlapping controls must remain independently selectable in the control/property list.
- Structured Text/Automation Basic: decode_bytes handles source encoding; project_knowledge.declarations records names, declaration expressions, inclusive array bounds and lines. Chunking retains original file/line and task ownership. source_calls extracts literal calls; conditional_behaviour extracts a small set of direct IF-branch assignments with comments removed without shifting lines. Deterministic rule engines separately check configured patterns and cross-source requirements. This is bounded static extraction, not a complete ST compiler, execution trace or proof that every statement runs. Preserve language-specific assignment and END_IF/ENDIF syntax.
- C: retain _INIT/_CYCLIC/_EXIT entry points, declarations/includes, literal expressions and line references. Resolve B&R generated headers and library declarations before interpreting a pointer or function-block call. Static project retrieval does not execute C or infer the body of an external function.
- Evidence: project records use [S1] IDs plus actual source file/line or ladder network and selected target/task ownership. Retrieved help uses [H1] IDs plus document title, local path, help set and digest. Guide examples are labeled illustrative. Vendor documentation can explain syntax or a block contract; project source is required for claims about implementation. Reading limits, unsupported formats and truncation remain visible.
- Future editing: keep original files, encoding, comments, namespaces, object IDs, ordering and project wrappers. Propose a patch with exact file/line/network and declarations, review the full affected scope, and build/download using the matching Automation Studio and runtime. The assistant does not automatically write PLC source. Never reconstruct or overwrite a whole project from a bounded retrieval excerpt.

**Illustrative example**

```text
{"network":1,"commented":false,"cells":[{"id":"1:0:0","kind":"contact","name":"Start","type":"open","row":0,"column":0,"span":1}],"connections":[],"warnings":[]}

{"name":"Numeric_4","properties":{"Left":"296","Top":"158","Datapoint":"Local.DOFFER[2]"}}

{"name":"ShiftValue","declaration":"ARRAY[0..9] OF REAL","file":"Logical/Global.var","line":12}
```

**Source pointers**

- `python_engine/compare.py`
- `python_engine/ladder_model.py`
- `python_engine/project_knowledge.py`
- `python_engine/project_info.py`
- `python_engine/hmi_bitmaps.py`
- `backend/core/compare_screen_preview.py`
- `AS27_PROJECT_LAYOUT.md`
- `LADDER_REFERENCE_REVIEW.md`

<a id="project-layout"></a>
## Project tree and source inventory

Read the project descriptor and selected configuration before interpreting its files.

- Modern project sources normally sit under Logical/; selected PLC/HMI hardware and task configuration sit under Physical/<configuration>/. Read the actual descriptor and file content; folder names are not runtime evidence.
- Logical/Libraries can contain user libraries and declarations. Keep a library version, its declarations and its call sites together. Package.prg/.pkg metadata may resolve ownership but is omitted from comparison results.
- Use uSOPp's project identity reader and scoped source inventory; preserve source-relative paths and line/network numbers.

**Illustrative example**

```text
Machine.apj
LastUser.set
Logical/Global.var
Logical/Global.typ
Logical/<program>/<program>Cyclic.st
Logical/<HMI>/Pages/<screen>.page
Logical/VCShared/AlarmGroups/<group>.algrp
Physical/<active>/<PLC>/Cpu.sw
```

<a id="active-target"></a>
## Active configuration, CPU and HMI scope

A source file's presence does not prove it executes on the selected controller.

- Use LastUser.set and the project configuration metadata to choose the active Physical configuration. Use Cpu.sw task Source/Name and task class to link a logical program to that CPU.
- Resolve the visualization mapped to that controller and retain HMI target identity. Multiple HMI/CPU results must stay separate.
- Missing or ambiguous mappings remain unresolved; do not combine targets or assume Config1 is always active.

**Source pointers**

- `AS27_PROJECT_LAYOUT.md`
- `python_engine/project_info.py`

<a id="as27"></a>
## Automation Studio 2.x / 2.7 legacy layout

Legacy projects can place program sources under pgm/<project>/CPU instead of modern Logical subroutine folders.

- The supplied layout uses Logical/HMI/Pages for HMI, pgm/TRIAL_01/CPU for logic, Physical/Config1 for its selected configuration and Physical/Config1/PCC1/HMI/hw.cfg for panel type.
- These names are examples. Select a legacy CPU only when scope is uniquely resolved. CPU.txt can supply exported declarations.
- Alarm and referenced HMI resources may reside under Logical/VCShared. A resource's XML version does not override the project version.

**Source pointers**

- `AS27_PROJECT_LAYOUT.md`

<a id="structured-text"></a>
## .st — Structured Text

Structured Text uses IEC declarations and statements such as :=, IF/THEN/END_IF and CASE/OF/END_CASE.

- B&R programs can contain _INIT, _CYCLIC and _EXIT sections, or separate source objects for those lifecycle parts. Determine task assignment from configuration.
- Strip comments while preserving line positions before analyzing executable statements. An extracted IF assignment is partial static evidence, not a full execution trace.
- Function-block instances must be declared; evaluate the enable, arguments, returned status and lifecycle at their call sites.

**Illustrative example**

```iecst
PROGRAM _CYCLIC
    IF Start AND NOT Stop THEN
        Run := TRUE;
    END_IF;
    Delay(IN := Run, PT := T#5s);
END_PROGRAM
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/programs/structuredtext/programmingmodel_programs_structuredtext.html`

<a id="automation-basic"></a>
## .ab — B&R Automation Basic

Automation Basic is a B&R text language. Its syntax differs from Structured Text.

- Statements are separated by line endings; a continuation uses the backslash described in the supplied help. Assignment syntax and block terminators must be read as AB, not converted by replacing text blindly.
- Use the language identified in the program/configuration and the source header. A .ad suffix is not established as Automation Basic by the supplied guide; inspect it rather than assuming .ab semantics.
- Preserve the original wrapper/header when preparing a reviewable edit.

**Illustrative example**

```text
IF Start = TRUE THEN
    Run = TRUE
ENDIF
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/programs/automationbasic/programmingmodel_programs_automationbasic.html`

<a id="ansi-c"></a>
## .c / .h — ANSI C source and declarations

C source uses C expressions, declarations, functions and header includes; it is not IEC Structured Text.

- Typical B&R lifecycle entry points include _INIT, _CYCLIC and _EXIT. Inspect the project's real build/language configuration and included headers.
- Function-block use can require the corresponding library headers and structures. Pointer, sizeof, signedness, alignment and memory-copy size need source and target evidence.
- Do not assume IEC array-bound checking or ST := assignments apply to C.

**Illustrative example**

```c
#include <bur/plctypes.h>
void _CYCLIC ProgramCyclic(void)
{
    if (Start && !Stop) Run = 1;
}
```

<a id="ladder"></a>
## .ld — Ladder networks and graphical topology

A B&R ladder source can contain a PROGRAM wrapper and XML describing networks, rows and cells. Render the electrical topology instead of treating it as XML prose.

- Read network numbers/comments, contacts, coils, connecting lines, branches and function/function-block pins. Reconstruct multi-row blocks from header/top/bottom positions and preserve parallel paths.
- Normally open contacts conduct for TRUE; normally closed contacts conduct for FALSE. A normal coil follows rung continuity; set/reset coils latch/reset. Parallel paths cannot be flattened into an AND sequence.
- Commented networks do not execute. Show unknown symbols as unsupported rather than inventing a rung meaning. Use the existing ladder model and SVG renderer for geometry and source links.

**Illustrative example**

```xml
<network comment="Illustrative series rung">
  <row><contact name="Start" type="open"/>
    <contact name="Stop" type="closed"/>
    <coil name="Run" type="open"/></row>
</network>
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/programs/ladder/programmingmodel_programs_ladder_symbols.html`
- `python_engine/ladder_model.py`
- `LADDER_REFERENCE_REVIEW.md`

<a id="global-variables"></a>
## Global variables and Global.var

Variable visibility comes from its declaration scope and package settings, not just a filename.

- A global declaration is available according to the project's visibility rules. A variable file can also be restricted to a package.
- Local variables can shadow global variables. Resolve a fully qualified HMI/datapoint name to the correct declaration instead of matching only the final label.
- Keep declaration file, type, qualifier, initialization and scope in the evidence.

**Illustrative example**

```text
VAR
    MachineSpeed : REAL;
    ProductName : STRING[50];
END_VAR
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/variables/programmingmodel_variables_scope.html`

<a id="local-variables"></a>
## Local variables and function-block instances

Task-local variables belong to their program/task instance; identically named variables in other tasks are separate.

- Inspect the program's .var declaration, task assignment and qualified reference. A local variable can shadow a global variable.
- Multiple mappings of one program can create separate local data instances. Retain the CPU/task context.
- HMI references such as Local.<package>.<program>.<variable> must be resolved through their data-source mapping; Local in an HMI name is not sufficient declaration proof.

**Illustrative example**

```text
VAR
    Ping : IcmpPing;
    StartPing : BOOL;
    Host : STRING[15];
END_VAR
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/variables/programmingmodel_variables_scope.html`

<a id="datatypes"></a>
## .typ — Primitive types, aliases and type declarations

Resolve named types through .typ declarations; do not infer a datatype from a variable's name or displayed value.

- Common PLC types include BOOL, signed/unsigned integers, REAL/LREAL, STRING, TIME, DATE and date/time types. Keep target/version-specific sizes and encodings distinct from packet schema rules.
- Follow type aliases, structures, enums and arrays to their declarations. Packet offsets must come from actual packing code and metadata, not from a generic layout guess.
- FLOAT→REAL and NCHAR/VARCHAR→STRING are this application's database-model comparison conventions, not a universal PLC memory conversion.

**Illustrative example**

```text
TYPE
    SpeedType : REAL;
    StateType : (Idle, Running, Fault);
END_TYPE
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/datatypes/programmingmodel_datatypes_simple.html`

<a id="arrays"></a>
## Arrays, lower/upper bounds and indexed access

ARRAY [lower..upper] OF Type defines inclusive index bounds. The lower bound need not be zero.

- An ARRAY [1..8] has eight elements. Retain all dimensions and resolve the element datatype before interpreting a copy or offset.
- Trace variable indexes, FOR loop bounds and byte-copy lengths. C and IEC/AB bounds behavior differ; runtime checks depend on configuration and available functions.
- Do not assume an array byte count equals its element count. Structures and strings require declared sizes plus the target's storage/packing rules.

**Illustrative example**

```text
VAR
    Samples : ARRAY[1..8] OF REAL;
    Grid : ARRAY[0..2, 1..4] OF INT;
END_VAR
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/datatypes/programmingmodel_datatypes_derived_arrays.html`

<a id="structures-strings"></a>
## Structures, enums, strings and qualified members

Composite fields and string lengths are declared data; preserve that structure when tracing HMI and packet mappings.

- Resolve SomeRecord.Field through its STRUCT definition. Follow type aliases instead of stopping at the first named type.
- STRING[n] and a packet's fixed string field are different declarations; inspect terminator handling, memcpy/strlen/memset and metadata length.
- An enum's numeric values and text-group labels need an explicit mapping; a label alone does not prove the PLC value.

**Illustrative example**

```text
TYPE ReportType : STRUCT
    Speed : REAL;
    Lot : STRING[50];
END_STRUCT; END_TYPE
```

<a id="retain"></a>
## RETAIN / remanent variables

RETAIN is a declaration qualifier. Retention depends on restart type, target generation and runtime configuration.

- In the supplied B&R help, RETAIN values are preserved for a warm restart but initialized for a cold restart; older system generations have additional behavior.
- Do not describe RETAIN as permanent across every download or restart. Inspect the selected CPU/runtime and applicable version's help.
- The qualifier applies to its declaration section until END_VAR; keep qualifiers with each extracted declaration.

**Illustrative example**

```text
VAR RETAIN
    TotalCount : UDINT;
END_VAR
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/variables/programmingmodel_variables_remanent.html`

<a id="permanent"></a>
## .per — Permanent variables and memory mapping

Permanent mapping is configured per CPU. In the supplied B&R programming model, .per uses VAR_CONFIG to map global RETAIN variables into permanent memory.

- Resolve the variable to its RETAIN declaration in .var and its address/size in the active .per file. A .per entry alone does not declare its PLC datatype.
- Check configured permanent memory size, address overlap and target/runtime support. Do not add permanent storage by changing only a variable name.
- Preserve existing values and migration intent when reviewing a datatype, address or array-size change.

**Illustrative example**

```text
VAR_CONFIG
    TotalCount AT %MD4;
END_VAR
```

**Source pointers**

- `br_help/AS12/Help-en/Data/programming/variables/programmingmodel_variables_permanent.html`

<a id="tasks-subroutines"></a>
## Tasks, subroutines, actions and execution order

Follow configured task assignments and actual call sites to reconstruct execution; file order in a tree is not execution order.

- Initialization, cyclic and exit code have different lifecycle roles. Task classes/priorities and scheduler configuration matter.
- A called action/subroutine/function must be traced from its caller. Name similarity and shared declarations do not establish that it runs.
- Separate disabled/commented code, shared ownership, active task mappings and unresolved block internals. Use source references for every claimed transition.

<a id="function-blocks"></a>
## Functions versus stateful function blocks

A function-block call uses an instance with retained internal state across calls. Resolve its type and installed library before explaining it.

- Read the instance declaration, parameter assignment, enable behavior, returned status and how outputs are consumed.
- For asynchronous library blocks, busy, success and error states require the applicable library help. A nonzero status is not automatically the same error for every block.
- A timer preset's units and a communication timeout's units can differ. Read the specific parameter documentation rather than guessing seconds.

**Illustrative example**

```text
VAR Delay : TON; END_VAR
Delay(IN := Start, PT := T#5s);
IF Delay.Q THEN Run := TRUE; END_IF;
```

<a id="libraries"></a>
## Predefined B&R and user libraries

Pair each function/block with its declaration, installed library version and supplied help.

- The indexed local manual includes library functions, parameters, datatypes, examples, status/error codes and version history. Search the exact block or numeric error.
- User libraries can contain .fun interfaces and ST/AB/C implementations. A library's help does not prove that a selected project installs or calls it.
- The local help set label AS12 is recorded as provenance, not assumed to be the project's Automation Studio or runtime version.

<a id="icmp-library"></a>
## AsIcmp / IcmpPing — documentation lookup example

The supplied AsIcmp help documents IcmpPing as an asynchronous ping function block.

- The help identifies enable, pHost, timeout and status. Its documented timeout unit is 10 ms steps; confirm compatibility with the installed library/version.
- Use an instance declaration and an actual call to establish source implementation. Use Cpu.sw to establish active task ownership and HMI data-source bindings to establish the UI connection.
- This guide does not send a network ping or assert a live host is reachable.

**Source pointers**

- `br_help/AS12/Help-en/Data/libraries/asicmp/fbks/icmpping.html`

<a id="hardware"></a>
## Hardware tree, .hw / .hwl and hw.cfg

Read hardware objects from the selected Physical configuration and keep PLC CPU type separate from HMI panel type.

- Hardware descriptions can contain module hierarchies, slots, interfaces and properties. Formats vary by Automation Studio generation.
- In the supplied legacy layout, HMI/hw.cfg uses MasterPanel/Type for panel identification. Do not infer the panel from a program name.
- Referenced modules and library/runtime requirements need installed-version evidence.

**Source pointers**

- `AS27_PROJECT_LAYOUT.md`

<a id="io-map"></a>
## .iom — I/O mappings and process variables

An I/O mapping binds an explicit process variable to an identified hardware channel/address.

- Keep module/channel, direction, datatype and selected CPU configuration in the trace. A declaration or channel-like name is not proof of a mapped I/O.
- Legacy IOMap.iom can reside under the selected pgm/<project>/CPU. Modern I/O mappings live in the selected physical configuration.
- Trace mapping→declaration→logic use and keep missing mappings visible.

<a id="hmi-pages"></a>
## .page / .pages / .layer — HMI controls and layout

Visual Components files describe pages, layers and controls with properties; parse them as a control tree and draw the resulting geometry.

- Read the XML namespace and object hierarchy, control Name/Type/ClassId, Left/Top/Width/Height, colors, fonts and referenced resources.
- Control properties, value/status/index datapoints, actions and visibility are separate from visual position. Nested controls and overlapping HotSpots require selectable object/layer identity.
- Render actual referenced bitmap assets where available. If unresolved, show bitmap group/index/name and a missing-asset notice rather than inventing an image.

**Illustrative example**

```text
<Page Name="Example">
  <!-- Illustrative structure; use the actual file namespace/control schema. -->
  <Property Name="Width" Value="640"/>
  <Property Name="Height" Value="480"/>
</Page>
```

**Source pointers**

- `br_help/AS12/Help-en/Data/visualization/viscompvc4/pages/pages_management.html`

<a id="hmi-datapoints"></a>
## .dso — HMI data sources and PLC aliases

Resolve an HMI property through its data source and alias to an exact scoped PLC declaration and its runtime assignments.

- Follow Source[...].Variable[...] rather than matching a screen label to a variable name. Resolve global/local data sources and shared VCShared resources.
- Value, minimum, maximum, status, color, index and action datapoints have distinct roles. Preserve the target and control name in each result.
- If a mapping, declaration or assignment is absent, state the unresolved link; do not treat the visible numeric label as proof.

<a id="text-groups"></a>
## .txtgrp — Text indexes and language values

A text group maps stable indexes/text IDs to localized values. Index values and source identity should survive comparison.

- Read all language values for each numeric index. Preserve missing/added/removed entries and unknown references.
- IndexDatapoint plus TextGroup/TextIndexOffset selects text at runtime. Do not match only on an English label or reorder indexes lexically.
- Display an index/language table and a separate snippet table; keep calculated/snippet placeholders visible.

<a id="text-snippets"></a>
## Text snippets and formatted datapoint text

Text snippets can inject formatted data or references into text. Their definition is separate from the localized text group's entries.

- Keep snippet name, type, style, referenced datapoint, format/unit and description. A brace placeholder is not an ordinary fixed string.
- Resolve the named snippet and its data-source mapping before reporting the displayed value.
- Do not substitute or remove placeholders while comparing source definitions.

**Source pointers**

- `br_help/AS12/Help-en/Data/visualization/viscompvc4/common/textsnippets.html`

<a id="bitmaps-touchpads"></a>
## .bmgrp — Bitmaps, TouchPads and released/pressed states

A control can select different bitmaps from a bitmap group for released, pressed or runtime-indexed states.

- Resolve BitmapGroup and BitmapIndexOffset to the actual bitmap entry and asset; keep released and pressed mappings separate.
- TouchPad dimensions, number of levels and the selected bitmap index describe the keypad UI. Show the resolved bitmap name in properties even when an asset cannot be rendered.
- Do not confuse a shared bitmap group with a missing local asset folder; check referenced VCShared resources.

<a id="alarms"></a>
## .algrp — Alarm groups and VCShared resources

Alarm definitions can be shared under Logical/VCShared/AlarmGroups even when the active HMI's local AlarmGroups folder is empty.

- Read actual .algrp definitions, alarm IDs, datapoints/bit positions, text references, severity and acknowledgment settings. Resolve shared text resources in the active target's scope.
- For generated metadata Sheet2, trace packet tag/bit→alarm definition→localized shown text. Placeholder NA labels are not proof that an alarm description is unavailable.
- Do not let an empty local folder hide a referenced shared alarm group. Retain the alarm's source file and stable numeric identity.

**Source pointers**

- `AS27_PROJECT_LAYOUT.md`

<a id="source-encoding"></a>
## Wrapped legacy source, unknown .ad and source encoding

Inspect the actual content before choosing a decoder. Extension and editor screenshots alone do not establish a source grammar.

- A legacy B&R container may hold headers/binary data plus readable declarations or code. Retain wrapper bytes and decoded-source offsets; a text preview can be incomplete.
- A .ad file is not assigned ST/AB/ladder semantics by this index. .ab is the documented Automation Basic format in the supplied reference; unknown formats remain unresolved.
- Read XML namespaces/attributes without executing content or external entities. Keep source encoding, comments and original line references.

<a id="editing"></a>
## Review checklist before editing B&R code

Prepare a reviewable source edit using the correct language, target, declarations and library help.

- Record expected behavior and original source/version; trace callers, task lifecycle, variable scope/type, arrays, enable/status handling, I/O and HMI effects.
- Preserve ladder topology, XML/control IDs, source encoding and wrappers. Review RETAIN/permanent changes and packet layout/memory-copy lengths before changing a declaration.
- Use the app's source editor/backups and the engineer's save action. Compile in the matching Automation Studio environment and run the requested validations; this help index does not change code or verdicts automatically.

<a id="temporary-folders"></a>
## Excluded temporary, cache and compiled folders

Generated project output must be excluded before walking engineering sources.

- Skip Temp, tmp, AS build output, Binaries/CompiledBinaries, Diagnosis, bin/obj/build, version-control and application cache folders case-insensitively. The shared scanner prunes them before descent and does not follow linked folders.
- Keep Logical/VCShared, Libraries, Physical and the selected legacy pgm CPU; these are engineering sources or references, not temporary data.
- A vendor manual can contain a genuine topic under a directory named as/temp. Project exclusions apply to projects, not to the separate B&R documentation corpus.

**Source pointers**

- `python_engine/project_paths.py`

<a id="traceability"></a>
## Evidence chain, documentation and limits

Separate what the selected project does from what a help page says a library can do.

- Project evidence uses source IDs [S1] and file/line or ladder network. Reference documentation uses help IDs [H1], title, help set, source path and content fingerprint.
- Help names a format, parameter or block behavior; it does not establish that a project uses it or a host is reachable. Version compatibility must be checked.
- Retrieved snippets are bounded. Large/unsupported files and unresolved sources remain visible in index coverage. This is retrieval for an existing model, not model training.

## Quick syntax examples

These examples are authored illustrations. Declare the variables in the actual program scope and use the matching compiler/library documentation.

| Construct | Structured Text | Automation Basic / ladder |
| --- | --- | --- |
| Assignment | `Run := TRUE;` | AB: `Run = TRUE` on its own line |
| Conditional block | `IF condition THEN ... END_IF;` | AB: `IF condition THEN` followed by statement lines and `ENDIF` |
| Statement boundary | Semicolon | AB normally uses a new line; do not translate ST punctuation blindly |
| Boolean condition | `Start AND NOT Stop` | Ladder: normally open Start in series with normally closed Stop |
| Parallel paths | Preserve the full Boolean expression | LD: follow branch junctions and block pins; do not flatten branches |
| Timer | Declared `TON` instance; named `IN`, `PT`, `Q`, `ET` fields | LD: actual timer block and connected pins; AB calls follow the installed library interface |
| Cyclic behavior | Task executes configured program repeatedly | A file name alone does not identify scheduling or task priority |

### Structured Text CASE and bounded FOR

```iecst
CASE State OF
    0: Ready := FALSE;
    10: Ready := TRUE;
    ELSE Ready := FALSE;
END_CASE;

FOR i := 1 TO 8 DO
    Samples[i] := 0.0;
END_FOR;
```

Here `State` and `i` need appropriate integer declarations, `Ready` is BOOL, and `Samples` is `ARRAY[1..8] OF REAL`. Array bounds are inclusive. Loops execute within a task invocation; check execution time and bounds rather than treating each loop iteration as a separate PLC cycle.

### Automation Basic conditional layout

```text
IF Start THEN
    Run = TRUE
ELSE
    Run = FALSE
ENDIF
```

The supplied B&R AB help requires IF and THEN on the same line, body statements on following lines, and ELSE/ENDIF on their own lines. Keep AB and ST syntax separate.

**Local vendor references:**

- `br_help/AS12/Help-en/Data/programming/programs/structuredtext/programmingmodel_programs_structuredtext_case.html`
- `br_help/AS12/Help-en/Data/programming/programs/structuredtext/programmingmodel_programs_structuredtext_for.html`
- `br_help/AS12/Help-en/Data/programming/programs/automationbasic/programmingmodel_programs_automationbasic_if.html`

## Supplied collection coverage

Local index snapshot: 2026-10-10T10:51:21.371605+00:00. Scanned **135,466** supported source files; indexed **127,120** vendor topics plus **31** authored guide topics. **8,346** source files were skipped; **27** indexed topics have truncated text.

Skipped reasons: file-size-limit: 2, no-extracted-text: 8,344.

The source inventory table records paths and status for every scanned source file. Navigation XML without extracted text and files beyond the size limit remain recorded rather than silently counted as indexed. Images and binary assets remain in the original corpus. This is a local snapshot; another server reports its own installed collection and index counts.
