# Engineering knowledge layout

- `br_help/` contains the supplied B&R Automation Studio reference material (HTML, XML, images and related help files).
- `master/` contains reusable engineering mappings.
- `projects/` contains project-specific knowledge and mappings.
- `model_data/` is reserved for a future separately installed local language model and its weights.
- `../rules/features/` stores feature-level validation configuration. Each feature has its own JSON file.
- `../rules/modules/` stores individual reviewed rules; `../rules/learning/` stores engineer observations and approved examples.

The current Chopper assistant uses retrieval over approved observations and reference material. It does not train or store LLM weights. Only engineer-approved feedback is eligible for a future training dataset.
