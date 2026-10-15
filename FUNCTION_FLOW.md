# Function flow

## Chopper chat

Open **AI Assistant → Chat → Routine function flow**. Chopper lists the PLC implementation files in the selected ByteMap / LogicScan project or a project attached through the paperclip. Search by name or path, then choose a routine. The reply shows numbered working steps and explanations of the selected step’s functions, blocks, inputs, outputs and status handling. **Expand flow** opens the complete view; **Flow HTML** downloads its report. Chopper and its exports omit the PLC source column and raw source listing. Ladder connections remain available in a collapsed diagram.

You can also ask **“Show the step-by-step function flow for ip_addCyclic.ab”**. A uniquely named source opens directly. If several files share the name, Chopper presents the matching files for selection. With “Follow-up questions use MatchView” selected, flows use the saved Base / Developed comparison sources and keep both sides separate.

Flows are built locally from the complete selected routine and work without a running model. Generated answers and exports use a source snapshot, so an earlier reply retains its original evidence after later edits. Project and export ownership use the existing account checks. Temporary and generated folders follow the project's common exclusions.

### Call explanations

**How this subroutine works** connects the complete program section into sentences, in source order. Each paragraph links to its corresponding step, including the correct sequence tab when read, write and scan checks are grouped separately. It describes conditions, actions, documented calls, status outcomes, timer feedback and reset order. Called project routines also receive their own written explanation. **Copy explanation** copies the prose, and **Flow HTML** includes it with step links. The same explanation is passed to Chopper as context for follow-up questions.

The prose is generated locally from the parsed steps and resolved help evidence. It preserves conditional branches and does not turn the routine into an unconditional machine timeline. Older saved chat snapshots retain their original content; reopen a routine to generate the written explanation.

The backend reads local `.var`, `.fun`, `.typ` and inline declarations to resolve named instances such as `TON_hide_ping_state : TON`. It retrieves exact function topics from the existing B&R help index and reads their parameter and status tables. Each explanation pairs documented meanings with the actual values supplied by the selected routine. Functions inside assignments and conditions are included too, such as `memset`, `atoi`, `ADR` and type conversions.

An unambiguous project-defined function or block expands into its own numbered sequence, including its nested calls and source conditions. Recursion, ambiguous bindings, unavailable topics and expansion limits are reported explicitly. Expansion is bounded to five levels, 32 implementations and approximately 1,500 steps; open a called routine separately for remaining detail. Different library topics sharing a name are not silently treated as equivalent. Saved comparison sources receive available documentation explanations; complete-project context is required to resolve external declarations and expand project implementations.

The supplied help set is reference evidence, not proof that its library version matches the PLC runtime. No routine is executed, no project code is edited, and library internals are not invented. The existing MatchView source view stays available.

For `Logical/Libraries/GENERAL/LUB.ab`, the sequence includes hours-to-seconds conversion, the `TICK1SEC` / `TON` call and second increment, the elapsed-time comparison and both `ENABLED` outcomes, the `RESET` branch, and the final `UINT` conversion. The timer explanation includes `IN = START AND NOT TICK1SEC.Q`, `PT = T#1S`, its `Q` / `ET` outputs, the feedback reset on a later executing call, and the effect of skipping the call when `START` is false.

## MatchView

In MatchView, select a PLC implementation file in the Logic tree and click **Function flow**. Choose Base or Developed, then the program section. The main view shows **numbered working steps joined by arrows**, with their triggers, actions and status outcomes already visible. The source or ladder appears on the left; the selected step's data path, block inputs and variables appear on the right. Click a step's source icon to inspect its evidence.

**Flow HTML** downloads a portable report in the same three-column style. Each step has its source or rung alongside it. The full variable list, call list and complete source are available below the working steps.

The flow is generated from the source saved with the comparison, without requiring Chopper or a running LLM. It does not edit the selected projects. Source order describes a program or function invocation; it does not simulate a machine cycle or the internal behavior of a library function.

Supported source formats:

| Format | Flow evidence |
| --- | --- |
| `.st` | IF / ELSIF / ELSE, CASE arms, loops, assignments and calls |
| `.ab` | Automation Basic IF / ELSE IF / ENDIF, LOOP / ENDLOOP, EXITIF, assignments and FUB calls |
| `.src` | Saved decoded AS 2.7 text; ST, Automation Basic or instruction-list view according to its content |
| `.ld` | XML networks with contact types, coil actions, function blocks and the existing rung diagram |

Parallel ladder contacts retain their wiring; they are not flattened into a guessed AND expression. Commented networks remain visible but are excluded from active variable reads and writes. Legacy ladder instruction text is shown as instruction groups when XML rung geometry is unavailable. Malformed or unclosed control structures produce a notice.

Variable names are taken from source and show read/write line references. Case variations are combined. Library internals, indirect pointer writes and physical I/O addresses absent from the source are not inferred.

## IP address sample

Reference: `../project 1/Logical/ip_add/ip_addCyclic.ab`, from project `LDF3S_6361`. This is Automation Basic. The generated local sample is [ip_add_function_flow.html](artifacts/logic-flow/ip_add_function_flow.html).

The sample groups the actual source into three working sequences:

- **Read addresses:** read IP address → read subnet mask → read default gateway. Each card shows its request flags, status branches, parsed destination and handoff flags.
- **Apply addresses:** apply IP address → apply subnet mask → apply gateway. The next call is reached only through the displayed status `0` conditions. The final call's status `0` sets `getip = 1` and clears `setip`.
- **Checks every scan:** two gateway preparation checks and three status timers. The timers are shown separately from the read/write route because they update indicator flags at their own source positions.

Its main source actions are:

| Source lines | Condition / function call | Source effect |
| --- | --- | --- |
| 6–16 | `setip = 1` and gateway prefix differences; `GatewayAddress[3] = 0` | Copy the first three `IPAddress` octets to `GatewayAddress` when required; replace zero in the last gateway octet with `1`. |
| 21–55 | `getip = 1 AND setip = 0`; `CfgGetIPAddr` at line 28 | Read interface `IF5`. On status `0`, parse dotted bytes into `IPAddress` and set `getsubnet = 1`; on the other branch keep `getip = 1` and set `getip_status = 1`. |
| 56–65 | `IP_Address_status_tmr` / `TON` | Assign the timer input from the source flags, set `PT = T#3S`, and set `getip_status_v = 1` when its `Q` is true. |
| 67–109 | `CfgGetSubnetMask` at line 72; `Subnet_Address_status_tmr` | Parse the subnet on status `0`, request the gateway, and run the subnet status timer. |
| 113–169 | `CfgGetDefaultGateway` at line 120; `Gateway_Address_status_tmr` | Separate the explicit status `29009`, status `0`, and other-status branches. Parse `GatewayAddress` on status `0` and run the gateway status timer. |
| 173–225 | `setip = 1`; `CfgSetIPAddr`, `CfgSetSubnetMask`, `CfgSetDefaultGateway` | Build address strings with `itoa` / `strcat`, use `cfgOPTION_NON_VOLATILE`, and call each setter after the previous call reports status `0`. After the final status `0`, set `getip = 1` and clear `setip`. |

Address parsing loops are summarized as splitting dotted bytes and converting each part with `atoi`; the complete loop remains in the adjacent source evidence. All status and retry conditions come from source. The original parsed syntax tree remains in the API for detailed tools, while the main view presents the working actions.

Additional local examples: [doffing ladder](artifacts/logic-flow/doffing_function_flow.html) and [IP ping Structured Text](artifacts/logic-flow/ip_ping_function_flow.html). The ladder report pairs each numbered rung action with its actual drawing. Series conditions follow the connected symbols; parallel paths remain visible in the diagram. Block input rows are not mistaken for parallel contact branches.

## Development validation

The parser checks cover nested ST branches, Automation Basic loops/FUB calls, comments and quoted strings, CASE arms, REPEAT / UNTIL, variable casing, disabled ladder networks, parallel connections and legacy instruction text. API checks cover saved-source paths, lazy source details, missing sides, invalid selections and HTML export. The sample project inputs are read-only.
