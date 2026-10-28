# SpinConnect write ST in ByteMap

## Packet direction and source of the generated code

`mms_nw_r` serializes PLC values for the server. ByteMap validates those outgoing
groups and their byte layouts. Write ST now discovers group codes and external
field order from this same routine.

The settings service in `mms_nw_w` supports function 1 to read current settings
and function 2 to receive settings from the server. The generated function 1
response and function 2 request use the selected `mms_nw_r` payload layout.
The response has a five-byte prefix; the write request adds the two-byte group
code before its values. Both frames also include the existing two-byte trailer.

Existing `mms_nw_w` code supplies the transport and setting policies. Where its
internal field order differs, a generated frame adapter supplies those policies
their original order. The original write blocks retain `memcpy` into typed
temporary variables, `nw_i` byte advances, `nw_j` field increments, limits,
assignments, password-level updates, and per-parameter error code 16. For
example, the Motor pulley UINT block and its 0..310 limit remain intact.

Read-only context fields retain their outgoing packet slots. A read group with
no setting-write policy is visible with a finding; the generator does not
invent an assignment or an interlock for it. Conflicting byte widths, read
copies that exceed their cursor span, and unsupported layouts block generation.
Existing source files are never rewritten by analysis or draft generation.

## Use the feature

1. Select or upload the complete Automation Studio project in ByteMap.
2. Open the **Write ST** tab and choose **Generate ST** inside the generator
   panel. This starts source and HMI analysis for the selected project.
3. Confirm the `mms_nw_r` and `mms_nw_w` cyclic sources and one HMI target.
4. Select the group codes to include. Inspect their original machine conditions,
   wire types, conditional byte positions, readonly fields and source findings.
5. Review the selected HMI input controls, displayed limits, unit conversions
   and limits in native PLC units. Additional limits retain the original HMI
   and write-source checks.
6. Resolve any **Required choices** for HMI controls. Confirm that the selected
   mappings were reviewed, then choose **Generate ST** at the top of this panel.
   The view moves to the generated files. Analysis and draft remain available
   when switching tabs for this selected project.
7. Copy individual files or download the complete ZIP. It contains the cyclic
   ST, matching existing variable/type/init files, `write_mapping.json` and
   integration instructions.
8. Back up the project, integrate the reviewed files into the original
   `mms_nw_w` program, and compile in Automation Studio for the selected CPU.
9. Read current settings using function 1 on the write port. Build function 2
   from the generated **write** field map and active conditional variant.
   Check the response and read back the values.

The generator reads source files. It does not connect to a PLC or change the
selected project. Existing packet validation and metadata generation remain
separate ByteMap actions.

## Edit one parameter in DataInspect

1. Compile the reviewed generated writer in Automation Studio for the selected
   CPU. Confirm that this is the program installed on the selected target.
2. Load matching SpinConnect metadata in DataInspect. A pencil appears beside
   rows whose `IS_WRITABLE` value is `YES`. Historical tests remain read only.
3. Click the pencil and load the generated `write_mapping.json`. Existing 4.73
   downloads must be regenerated to include the DataInspect layout.
4. Confirm the settings service port (21011 in both reference projects), target,
   Machine ID, byte order and active machine configuration / conditional layout.
5. Choose **Read current settings**. This sends function 1 to the write service.
   A mismatched length or unresolved source mapping blocks the edit.
6. Enter the new **raw PLC value**. For example, Project 5 roller diameter uses
   a factor of 10: enter 350 for 35.0 displayed units. Source limits are already
   in PLC units. Datatype bounds and literal limits are checked on the server;
   dynamic HMI limits and original checks remain enforced by the PLC code.
7. Choose **Send to PLC and verify**. The application reads the complete settings
   group again. If it differs from the preview, nothing is written. Otherwise it
   preserves the full source-mapped group, patches the selected field, sends
   function 2 once, and performs a function 1 readback.
8. Review the acknowledgement, observed value and saved test ID. A nonzero result
   or an unconfirmed value is reported as failure. Read again before another
   attempt, especially after a timeout or a partial parameter rejection.

The editor currently supports scalar numeric and Boolean settings. It does not
infer a write protocol for YBS or add a settings service to the built-in
measurement simulator. The mapping and settings port are remembered per user
and target in this browser. A preview expires after two minutes and is consumed
by a send attempt. The full group is transmitted because that is the project
protocol; existing PLC completion actions and per-parameter commits still run.

The source fingerprint identifies the reviewed files. It is not a live
fingerprint of the running PLC program; confirm the installed revision and the
selected conditional layout before writing.

## How limits and source behavior are retained

- Group identities and external packet fields come from the `mms_nw_r`
  `CASE nw_group_code` branches. Original setting policies come from
  `mms_nw_w`; a compatible writer template is required.
- The selected target's `.page` input controls are linked to exact `.dso`
  datapoints and `.vcug` unit definitions. Controls with `Input=False` are
  excluded. Different HMI targets are never merged.
- Numeric literal limits are converted to PLC units using explicit unit
  factors. Dynamic limit datapoints already reference native PLC values.
  Unresolved conversions require reviewed limits rather than guessed scaling.
- Additional HMI checks run before the original write branch. They cannot
  remove its machine-state conditions, original value checks, readonly positions,
  recipe/completion actions or error responses.
- Original parameter commits remain per parameter. An original source check
  can reject a later parameter after an earlier parameter was accepted. Check
  the response and read the resulting values back.
- Conditional cursor positions are followed through IF/ELSE branches. The
  mapping records each byte position, error position and condition. Draft read
  response lengths are computed from the final cursor, including variants.
- Copy widths, temporary declarations and actual receive/send/error buffer
  capacities are checked before generation. Unsupported or unsafe mappings
  block generation for that group.
- A source fingerprint prevents generation from a stale analysis. Analyze
  again after changing PLC, declaration, HMI or unit files.

## Reference-project findings

With the read-derived layout, Project 5 GC 130 uses a 115-byte external payload;
the adapter handles its original 110/115-byte setting-policy variants. GC 140
uses 211 bytes. Project 2 GC 130 uses 112 bytes.

Project 1 GC 140 copies four bytes for `mms_HMI_ActSliverWght_ALOFF` but advances
the read cursor by one. Project 2 GC 140 sends `ED_Break_Draft` in four bytes
while its existing setting handler consumes one byte. These groups now require
a source correction and review before a draft can be generated.

### Original writer layouts retained inside the adapter

The supplied **project 2** and **project 5** were inspected independently.

| Property | Project 2 | Project 5 |
|---|---|---|
| Active configuration | LDF3S_WO_SUCTION | C70_Config06_REG_MCMT_CTL_HPM_8400 |
| Selected HMI | T30_5 | C70_7 |
| Original setting-write machine condition | MACHINE_STATUS = 0 | MACHINE_STATUS = 1 |
| Example HMI conversion | Suction delay 1–15 becomes 1000–15000 | Roller diameter 0–40 becomes 0–400 |
| GC 130 write payload | 112 bytes | 110 / 115 bytes, conditional |
| GC 140 write payload | 89 bytes | 211 bytes |

Findings exposed by the study include:

- Project 2's GC 130 write-port read header declares 110 bytes while its
  sequential field copies advance 112 bytes. The draft derives the length
  from the actual cursor.
- Project 2's GC 140 read-port and write-port layouts differ: the read routine's
  cursor totals 92 bytes, whereas the write-port read/write layout totals 89.
- Project 5's GC 130 read payload has 115 bytes; its writer consumes 110 or 115
  according to the 2Q selector. Some trailing fields are not consumed in one
  write branch. Use the write map for request construction.
- Project 2 GC 250 copies four bytes into UINT temporary variables declared
  with two-byte width. Project 5 GC 160 includes a four-byte copy into a SINT
  temporary declared with one-byte width. These groups are blocked until the
  source mapping is corrected and reviewed.

These are source findings and generated drafts. They are not Automation Studio
compiler results or evidence of physical machine operation.
