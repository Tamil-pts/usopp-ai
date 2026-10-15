# DataInspect reference review

Reviewed in development on 15 October 2026. No physical PLC was contacted.

## Screenshot: Production in kg

The Finisher CMS database JSON declares `Production in kg` as `TIMESTAMP` in
`cms_DRAWFRAMEFINISHER_hours`, entry 142, Group Code 40. Its corresponding Excel
source declares `FLOAT` in all three matching locations:

| Workbook | Worksheet | Row | Type | Group Code |
|---|---|---:|---|---:|
| CMS/05 CMS_DrawFrameFinisher_Key_Definitions_and_Source_Mapping.xlsx | cms_DFFinisher_shift_live | 54 | FLOAT | 40 |
| Same workbook | cms_DFFinisher_hourwise | 98 | FLOAT | 40 |
| Same workbook | cms_DFFinisher_shift | 121 | FLOAT | 40 |

The screenshot's metadata is `REAL`, GC 40. The old check treated the database
storage type as a PLC type and reported a PLC datatype failure. The current
result is **Reference conflict - review required** (`UNRESOLVED`). Source details
retain the JSON type, Excel types and original worksheet locations. `REAL` is
shown as the Excel-derived suggestion; the source definition is not rewritten.

The separate JSON requirement for the same name in GC 50 remains a requirement
for GC 50. Its absence cannot mark the GC 40 row as a failure.

## Complete bundled reference scan

All 23 fixed service/department models were rebuilt from `../Data Modelling`.
The scan found:

- 63 PLC requirement entries with conflicting normalized JSON/Excel datatypes,
  across 41 distinct service/department/name/database-type combinations.
- 17 additional PLC requirement entries using database-only types without a
  declared PLC wire datatype: 13 `INTEGER`, three `TIMESTAMP` and one
  `SMALLINT UNSIGNED`.
- The existing mislabeled QMS Breaker JSON remains excluded. Its filename says
  Breaker, but its declared department is Finisher. The correct Breaker source
  remains selected.

Conflicting or undefined wire types require reference review. Ordinary mapped
types such as `FLOAT` to `REAL` still pass, and genuine `REAL` versus `INT`
mismatches still fail. JSON originals, archived workbooks and database export
keys remain unchanged.

## Other screenshot names

| Metadata name | Available Finisher reference | Result |
|---|---|---|
| Powerfail_Time_Minute | Power Fail Time Minutes; Power Fail Time Minute is a calculated field | Different punctuation/wording; no implicit alias |
| Delivery Hanks | Hanks | Different wording; no implicit alias |
| Feed Roller Stoppage | Feed Roller Stops | Different wording; no implicit alias |

Only capitalization and surrounding whitespace are ignored. The interface now
says **No matching reference for this department**, rather than implying that
the parameter is absent from every data model.

## Display and saved-result fixes

- Table evaluations always use the loaded metadata. An old saved PASS or FAIL
  cannot replace the current evaluation.
- A saved check for another department cannot join current department models.
- Archived reference snapshots stay preserved and are labeled separately from
  current department references. Evaluation uses current validation rules.
- Database types and expected PLC wire types are labeled separately in exports.
- Calculated fields are identified as calculated outputs.
- Hovering a row in light mode uses a subtle background rather than dark gray.

## Focused verification

```powershell
python -m unittest discover -s tests -p test_data_models.py -v
```

Ten tests passed, including a synthetic builder fixture that checks unchanged
original source bytes and a regression using the actual Finisher catalog.

From `nami`, using the configured Node runtime:

```powershell
node --import tsx --test ../tests/nami_data_model_checks.test.ts
node node_modules/typescript/bin/tsc --noEmit
```

Seven TypeScript tests passed and TypeScript checking passed. These checks cover
source conflicts, valid and invalid wire types, capitalization, separate Group
Codes, stale saved results and department scope. They do not validate live PLC
values or execute stored formulas.
