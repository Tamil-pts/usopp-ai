# Engineering dashboard layouts

`catalog.json` indexes editable PMS, QMS and CMS starters, grouped by department
and original Excel sheet. Select them through DataInspect → My dashboard →
Layout library. The app binds parameters to the selected machine's metadata.
Unmatched fields and undefined formulas stay pending until configured.

Templates preserve all named non-server workbook parameters and their row
references. They also include JSON equation dependencies for the same service,
department and period. `widgets` select numeric/calculated parameters for presentation;
`excluded` records server/context rows and fields the numeric renderer cannot
display. Source files are in `knowledge/data_models/reference_sources`.

Personal “Save to knowledge” copies live in `users/{account-hash}/`, are ignored
by Git, and are excluded from shared Admin knowledge transfer. Download your
copies with Export layout and restore them with Import layout.

Generate starters with `scripts/build_dashboard_layouts.py`. Rebuilding updates
the shared starters and retains personal saved copies.

Shared name/type policies and formula overrides are in
`knowledge/master/data_model_rules.json`. Review them through DataInspect →
Data model requirements → Review and edit reference configuration. Database
numeric value compatibility and explicit PLC wire requirements are distinct.
Missing inputs and textual source instructions are reported as configuration
findings. Fixed source equations do not add acceptance limits.
