# Fixed data models

DataInspect uses one fixed database model per service and department. The source JSON format is preserved:

```json
{
  "controleCode": "CARDING",
  "keysList": {
    "pms_CARDING_live": [
      {
        "tagName": "Delivery Speed",
        "dataType": "FLOAT",
        "groupCode": "20",
        "tdEngineKey": "delivery_speed",
        "mongoKey": "deliverySpeed",
        "formula": null,
        "type": "Live",
        "isRequired": true
      }
    ]
  }
}
```

The example illustrates the schema. Each generated file preserves its supplied database keys, formulas and flags; absent database keys remain null rather than being invented.

## Folder layout

- `PMS/<DEPARTMENT>.json`: Production monitoring service, nine departments/variants.
- `QMS/<DEPARTMENT>.json`: Quality monitoring service, seven departments.
- `CMS/<DEPARTMENT>.json`: Condition monitoring service, seven departments.
- `reference_sources/`: Original JSON Key and Excel files, copied without changing the development-team sources.
- `catalog.json`: Parsed fixed references used by the app, including Excel worksheet/row evidence.
- `source_manifest.json`: Source hashes, selection and source discrepancies.
- `legacy_catalog.json`: Earlier reference IDs retained for historical results.

`DRAWFRAMEFINISHER` means **Finisher**; `DRAWFRAMEBREAKER` means **Breaker**. The two departments remain separate. `RINGFRAME_YBS` is a separate supplied variant, not merged into `RINGFRAME`.

## Reference selection

1. Prefer a database JSON from the matching service's JSON Key folder.
2. Otherwise use that service's collections embedded in another department JSON, such as `qms_` or `cms_` collections inside PMS V5.
3. Supplement missing requirements from the department Excel workbook, with workbook/sheet/row evidence.

Excel supplies omitted requirements and source locations. Existing database keys and equations are retained. If matching Excel rows consistently identify a numeric output type where legacy JSON declared a conflicting nonnumeric type, the generated knowledge applies the Excel clarification and records both values in `reference_corrections.json`. Original files under `reference_sources` remain unchanged. Other source conflicts remain explicit.

**Source discrepancy:** `QMS/JSON Keys V1/DRAWFRAMEBREAKER.json` declares `DRAWFRAMEFINISHER` and contains Finisher collections. It is archived but excluded from fixed Breaker requirements. QMS Breaker uses the correctly labeled `qms_DRAWFRAMEBREAKER` collections from `PMS/JSON Key V5/DRAWFRAMEBREAKER.json`. The warning is retained in the model and manifest.

## Checks and display

Names ignore letter case. The configured policy also accepts space/underscore formatting and explicit aliases scoped to service, department and Group Code. Ambiguous matches remain errors. Database FLOAT/REAL output types can map to numeric integer PLC inputs; this checks value compatibility, not independent wire-type conformance. Machine metadata determines decoding widths and signedness. Explicit `plcDataType` requirements remain strict.

The Data model column shows the reference name, matching services and result. Repeated collections are grouped only when they have the same outcome. Source details retain every collection/entry and Excel location. Expected parameters absent from metadata are listed above the table and in the complete requirements view. Wrong-group requirements remain separate with their expected and actual groups.

An unmatched metadata name is labeled **No matching reference for this department**. Configured aliases, such as the supplied Finisher `Delivery Hanks` / `Hanks` mapping, are shown in source details. Missing requirements for another Group Code do not turn a valid current-group row into a failure.

Database-only types such as `TIMESTAMP`, `INTEGER` and `SMALLINT UNSIGNED` do not define a PLC wire representation. These PLC requirements are **UNRESOLVED**, rather than incorrectly compared to a guessed wire type. A source may declare `plcDataType` explicitly when its wire representation is known. A consistent numeric Excel clarification is applied with a correction record; remaining conflicts stay visible for review.

Current table and exported evaluations are recalculated from the loaded metadata. Saved validation outcomes cannot override newer metadata or reference rules. Archived runs retain their saved reference snapshots, labeled separately from the current department catalog. Historical results remain available as original saved evidence.

Server IDs and timestamps are skipped, as are host fields (`isHost`). Formulas, `groupCode: "formula"` and `isAutoCalc` fields are shown as calculated. Missing required PLC parameters fail; unavailable optional parameters remain optional; incomplete definitions remain unresolved. The check compares loaded metadata and does not claim to evaluate formulas or verify live PLC values.

Automatic checks appear immediately. **Save check to history** records a validation with the current user's test identity. Collected verification Excel/JSON includes all fixed requirements and missing fields; older saved results retain their original evidence.

## Rebuild after an approved reference update

Update the original development-team JSON/Excel sources, then rebuild the bundled references:

```powershell
.venv\Scripts\python.exe scripts\build_data_model_knowledge.py --source "..\Data Modelling"
```

On Ubuntu with the same source folder beside the app:

```bash
.venv-ubuntu/bin/python scripts/build_data_model_knowledge.py --source "../Data Modelling"
```

The builder writes canonical JSON and the parsed catalog together. Copy the complete `knowledge/data_models` folder to the deployed app. This release also changes backend and frontend code: rebuild and restart as described in `UBUNTU_DEMO.md`. Current private user imports and test history are not overwritten by this operation.

## Editable knowledge rules and dashboard equations

`knowledge/master/data_model_rules.json` holds numeric value-type policy, scoped
name aliases, optional explicit PLC wire requirements and formula overrides.
Admin can edit it through DataInspect → Data model requirements → Review and
edit reference configuration. Shared knowledge export includes this file.

Dashboard starters in `knowledge/dashboard_layouts` resolve named workbook
functions using concrete equations from the same department/service/period of
the supplied JSON. Missing inputs stay unavailable; source instructions do not
become invented calculations or default pass conditions.
