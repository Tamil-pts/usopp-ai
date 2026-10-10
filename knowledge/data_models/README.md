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
3. Use the department Excel workbook only if no matching database JSON collections exist.

Excel clarifies names, types and groups and supplies original worksheet/row locations. It does not overwrite an available JSON definition. The supplied Carding attachment matches the archived QMS Carding JSON. Default references are fixed; the app does not combine every workbook/JSON version.

**Source discrepancy:** `QMS/JSON Keys V1/DRAWFRAMEBREAKER.json` declares `DRAWFRAMEFINISHER` and contains Finisher collections. It is archived but excluded from fixed Breaker requirements. QMS Breaker uses the correctly labeled `qms_DRAWFRAMEBREAKER` collections from `PMS/JSON Key V5/DRAWFRAMEBREAKER.json`. The warning is retained in the model and manifest.

## Checks and display

Names ignore letter case and surrounding whitespace. Different words, punctuation or internal spacing still differ. A similar spelling may be attached to a metadata row to explain a failure; it is never accepted as a match. The parameter must exist in its specified Group Code and have the mapped PLC datatype: FLOAT → REAL, NCHAR/NVARCHAR/VARCHAR/CHAR → STRING, USINT → BYTE.

The Data model column shows the reference name, matching services and result. Repeated collections are grouped only when they have the same outcome. Source details retain every collection/entry and Excel location. Parameters absent from the model are labeled **Not in data model**; expected parameters absent from metadata are listed above the table and in the complete requirements view. Wrong-group parameters stay visible with the expected/actual groups.

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
