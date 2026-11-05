# Required Sheet2 references and decoder CSV export

Implemented and checked on 4–5 November 2026. Correct data remains the requirement:
missing labels do not become guessed mappings or successful validation results.

Generated metadata now preserves every transmitted TAG_CODE occurrence for the
same PLC variable. HMI/approved mappings are attached to each actual occurrence;
matching friendly captions alone cannot establish a PLC identity. Generation
checks every `IS_SHOWN_VALUE_DIFFERENT=YES` record against real nonempty
`PLCVAL`/`SHOWNVAL` rows before publishing either workbook or JSON. A missing
reference blocks publication with the tag, group, parameter and row. Previously
published valid output is retained.

Uploaded/edited metadata is checked by exact TAG_CODE and applicable machine
variant. A missing reference opens the MetaWorks error dialog and fails metadata
validation; save/export of the inconsistent copy is rejected. DataInspect and chat
do not activate the inconsistent workbook. Cached metadata without a required
reference retains raw readings and a failed data-quality finding. The canonical
Sheet2 columns remain `TAG_CODE, PLCVAL, SHOWNVAL, MACHINE VARIANT, IS_ALARM`.

Both the chat log decoder and DataInspect export CSV with these exact headers:

| Tag | Parameter | Offset | Type | Raw decimal bytes | Decoded value | Finding |
| --- | --- | --- | --- | --- | --- | --- |

Chat offers current-capture and filtered-capture exports. DataInspect exports its
existing decoded response, including manual/offline, live and saved captures.
SpinConnect and YBS use their existing protocol decoder results. Error frames
without decoded fields export actual received bytes and failure findings without
inventing parameter readings. CSV quoting, UTF-8 BOM and formula escaping preserve
text safely; signed numeric readings remain numeric.

Verification includes 73 Python regressions, nine focused TypeScript checks and
an actual read-only regeneration of saved `BLBP_1329`: 1,050 parameters, 204
Sheet2 rows and 83 tags requiring references, with every required tag covered.
The explicit TAG_CODE 653 regression reproduces a repeated PLC variable and
verifies both occurrences receive their real source mapping. The historical
screenshot's exact workbook was not supplied, so the sample regeneration is not
claimed to be that screenshot's workbook. Existing generated files require
regeneration or correction; they were not silently rewritten.

Five browser checks passed: the MetaWorks popup, save/export rejection with the
source workbook retained, chat rejection of missing references, current/filtered
chat CSV downloads, and DataInspect's missing/valid mapping plus offline CSV export.
Attachment notices now remain visible before the first chat question; the welcome
screen no longer hides these validation errors.

An additional existing data-model test fails independently of these changes:
`Finisher screenshot keeps conflicting JSON and Excel evidence without failing
the PLC REAL row` expects a suggested PLC type which is currently undefined.
The data-model implementation, catalog and that test match HEAD. No guessed
datatype was added to hide that separate failure.

Artifacts: `.build/sheet2-decoder-20261104/`.
