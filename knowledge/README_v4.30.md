# uSOPp.ai Engineering Knowledge Base v4.30

Master knowledge is reusable across projects. Project knowledge is kept separately under `knowledge/projects/<project>/`.

`parameter_mappings.json` stores `plc_parameter`, `plc_tag`, `metadata_parameter`, and approval status.

Dropdown validation is activated by metadata `IS_SHOWN_VALUE_DIFFERENT = YES`, then Sheet2 is used by `TAG_CODE` to compare individual `PLCVAL` and `SHOWNVAL` mappings.
