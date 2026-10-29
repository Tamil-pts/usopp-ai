# Shared Database JSON Keys

The active dataset contains only the **3,509 shortlisted records** from
`Data_model_29102026.csv` (23 service/department groups and
94 collections). KnowHub, DataInspect and metadata
comparison use this same catalog. Existing fixed model IDs are retained.

The input CSV is retained byte-for-byte under `reference_sources`. The JSON
files are the server-compatible representation of its rows. Old workbook
supplements and legacy catalogs are outside the active dataset in the backup.
No missing parameters, aliases or corrected values are invented during import.
Explicit interpretation rules in `knowledge/master/data_model_rules.json`
remain separate from the source definitions.

To apply a new shortlist, first preview it and then apply it with a backup:

```powershell
python scripts/replace_data_model_json_keys.py --csv "C:/path/shortlist.csv"
python scripts/replace_data_model_json_keys.py --csv "C:/path/shortlist.csv" --apply
```

An administrator can edit an individual collection in KnowHub. Refresh the
source table to load edits from another session. Historical reports keep their
recorded definitions; they do not repopulate this active catalog.
