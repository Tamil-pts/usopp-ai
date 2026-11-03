# Parameter mapping replacement and viewport checks - 2-3 November 2026

The supplied `uSOPp_parameter_mappings (4).csv` replaces the old master parameter
mapping rows. The old table contained 1,263 rows; the replacement contains exactly
1,129 rows. Duplicate rows and their source order are preserved as supplied.

| Machine / department | Rows |
|---|---:|
| Finisher | 326 |
| Ringframe | 443 |
| Lap Former | 294 |
| Blow Room | 60 |
| Carding | 5 |
| All | 1 |

Every CSV field was checked after import: PLC parameter, PLC tag, metadata name,
machine/department, units, minimum, maximum, offset factor, scale factor,
visibility, writability and status. Blank optional values remain unset and zero
values remain zero. No mapping is borrowed from a different department.
Dropdown mappings, minimum/maximum fallback rules and the packet validation
engine were not rewritten.

Source SHA-256:
`132c2d365007bb840d6390fe7342edc2a9e9a5fbb63cde414d2b4a59470bae07`.

Backup: `.build/parameter-mappings-20261102/parameter_mappings.before.json`.
The source CSV snapshot and import verification are retained beside the backup.

Parameter mappings now provide per-row Delete, page selection and Delete selected.
Deletion changes the editable draft; Save changes persists it and Cancel edits
restores the saved rows. Existing optimistic revision checks prevent stale saves.
CSV import offers Merge rows and Replace all rows. Replacement requires the
current table revision and an explicit UI confirmation. Empty or malformed
replacement data leaves the previous table intact. Existing account restrictions
remain in force.

The shared workspace keeps wide tables inside their own scroll area and wraps
knowledge controls at narrow browser widths. Browser zoom remains under the
user's control. Layout checks use CSS widths equivalent to 80, 100, 125, 150 and
200 percent zoom on a 1600-pixel screen, plus a 390-pixel mobile viewport.
These check responsive reflow, rather than forcing or resetting browser zoom.

Verification:

- 51 local workflow and metadata tests, plus 11 subtests, passed. These include
  replacement, stale/invalid import rejection, persistent deletion, machine
  scopes, metadata editing, generated workbook behavior and report checks.
- Production builds passed for the main interface, comparison report,
  DataInspect and Virtual PLC.
- Browser checks passed for draft deletion/cancel, persistent selected deletion,
  reload and exact CSV replacement. All 162 tested workspace layouts fit the
  available width, including standalone DataInspect and Virtual PLC.
- Docker source-bundle checks confirmed the updated 1,129 mappings, required
  build scripts, valid checksum and exclusion of private databases and secrets.
  Docker is unavailable here, so no Linux image build was executed.
- The restarted local installation passed eight live API read checks and
  serves the verified 1,129-row master.
- Browser and final packaging results are retained under
  `.build/parameter-mappings-20261102/`.

Existing historical reports and project approval records remain historical;
rerun metadata validation to use the replacement mapping table.
