# Lapformer source reference rules

These are three separate, editable reference profiles for the supplied
LH20S_PV2042, LH20_3390_REV1 and LH2014050 projects. They are source regression
requirements, saved as drafts for engineering review. They do not establish
that a reference project's machine operation or safety design is correct.

| Reference project | Source program checks |
| --- | ---: |
| LH20S_PV2042 | 85 |
| LH20_3390_REV1 | 75 |
| LH2014050 | 84 |
| Total | 244 |

## Use in the application

1. Open **KnowHub → Rule library** and select the matching **Lapformer / project**
   feature. Select Lapformer as the department.
2. Inspect a rule to see the complete reference logic or exact ladder networks.
   Active networks retain their branches, contact types, pins and relative order.
3. Expand **Cross references**. Each link identifies a declaration, producing
   source block, function block definition, HMI control/datasource or physical
   I/O channel, with a source path and reference line.
   **Function calls and definitions** lists call sites, their resolved files,
   and any implementation/signature that is not supplied as readable source.
4. **Inspect referenced logic** loads the saved expected check. **Create editable
   copy in this rule** makes an independent copy inside that rule's configuration;
   other rules retain their saved references.
5. Review source findings and adapt requirements to the selected machine, then
   use the existing configure/validate/enable workflow and add its feature to a
   LogicScan pipeline. Select one project profile; do not combine the three
   implementations into one acceptance baseline.

The profiles cover nonempty INIT, CYCLIC and EXIT programs in readable .st, .ab
and .ld files outside vendor libraries. Every active read/write packet branch is
included in its communication program's complete expected logic. Comments and
disabled ladder networks are excluded from executable requirements. Missing
producers, ambiguous declarations and unresolved datasource links are listed for
review, rather than assigned guessed bindings. For legacy syntax that the flow
parser cannot fully enclose, a cross reference uses the complete producing
program instead of inferring its branch.

HMI references check a control and its exact datasource folder/point, preserving
separate visualization files. I/O references preserve each physical configuration
path and channel address. These bindings are reference expectations; they do not
independently certify configured HMI limits or physical hardware suitability.
Shared datasource checks use their configured `.dso` paths, including VCShared;
they do not require the datasource file to live under an HMI Pages folder.
Function/library interface files establish the supplied signature. A signature
alone does not establish the behavior of a compiled library implementation.

## Files and rebuilding

- `rules/modules/LAPFORMER-*_v1.0.json`: account-visible Rule Library drafts.
- `rules/references/LAPFORMER-*_v1.0.json`: deduplicated expected checks. Keep these
  files with the rule modules when transferring the profiles.
- `knowledge/lapformer/catalog.json` and each profile JSON: coverage, source file
  to rule mapping, Group Codes, parser notices and source concerns.

Saved checks carry a content hash. Validation loads expected definitions from
the application's reference folder, independently of the project under review.
A missing or changed definition fails explicitly. Referenced source blocks are
not replaced with the current project's implementation.

Create or rebuild a profile using:

```powershell
.\.venv\Scripts\python.exe scripts/build_lapformer_rules.py --reference PROFILE_ID=C:\path\to\LapformerProject
```

The authoring tool refuses to overwrite hand-edited modules or saved definitions. Rule IDs
remain stable for the same profile ID and source path. Reference source projects
are read only. Existing rules and saved pipelines are preserved.
