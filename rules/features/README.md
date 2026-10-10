# Feature rule pipeline

Each feature has a separate JSON file. `ruleIds` links the feature to reviewed rules in `rules/modules/`. `pipeline.json` stores drag-and-drop execution order and execution mode. Rule files remain independently reviewable and can be opened in the Learning Center.

Rules are deterministic. Engineer feedback and approved learning observations are stored in `rules/learning/`; they are retrieval/training data and are not an LLM model or model weights. B&R reference material is stored separately under `knowledge/br_help/`.
