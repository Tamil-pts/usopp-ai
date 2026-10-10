# Engineering knowledge layout

- `br_help/` contains the supplied B&R Automation Studio reference material (HTML, XML, images and related help files).
- `help_index/BR_PROJECT_HELP.md` is the single readable guide to source formats, syntax and uSOPp decoding. `project_guide.json` contains its structured topics.
- `help_index/br_help.sqlite3` is the generated offline full-text manual index. It is persistent local data, excluded from Git and distributable packages.
- `master/` contains reusable engineering mappings.
- `projects/` contains project-specific knowledge and mappings.
- `../local_ai/models/` stores separately installed GGUF model weights; it is not an engineering knowledge database.
- `../rules/features/` stores feature-level validation configuration. Each feature has its own JSON file.
- `../rules/modules/` stores individual reviewed rules; `../rules/learning/` stores engineer observations and approved examples.

Chopper retrieves approved observations, project evidence and bounded B&R guide/manual excerpts into its model context. References use `[H1]` citations; project evidence uses `[S1]`. Documentation does not prove project execution and must match the installed runtime/library version. This retrieval does not train model weights. Only engineer-approved feedback is eligible for a future training dataset.

Open **AI Assistant → KnowHub → B&R help index** to search manuals, open guide topics or download the complete Markdown guide. Admin can rebuild the index after changing help files. The previous index remains readable during a rebuild. A missing index is built in the background at server startup.

From a source installation: `python scripts/build_br_help_index.py` (or use `--data-root` for a separate persistent directory). Supported source topics are scanned with a 5 MiB per-file limit and a 100,000-character extraction limit. Skipped and truncated counts are reported. Linked files outside the supplied corpus are not followed. Binary assets and images remain in the original manuals.

Packages include the compact guide. Copy the supplied vendor manuals to `<USOPP_DATA_ROOT>/knowledge/br_help` on another server and rebuild there. Back up the persistent knowledge directory with users, mappings, rules and results. Project exclusions prune Temp/AS/Binaries/build/cache folders; those names are not excluded from vendor manuals, where they may be valid topics.
