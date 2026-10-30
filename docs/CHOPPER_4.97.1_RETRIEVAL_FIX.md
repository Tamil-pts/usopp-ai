# Chopper 4.97.1 — retrieval interface regression

Date: 29 October 2026. Previous application version: 4.97.0.

## Root cause

The recent multi-batch work queue introduced calls to
`Index.retrieve(question, characters=..., passes=3, limit=48)` and a subsequent
page using `offset=...`. The original loaded class supported only
`retrieve(question, characters=18000, passes=3)`.

The updated source file already defined the backward-compatible optional
`offset=0, limit=14` arguments, but the long-running combined application server
still held the old imported `Index` class. The newly imported orchestration
module therefore called the old class with a new keyword. The backend log at
22:19:32 records the failure at `engineering_analysis.build_queue` before model
inference. This was an interface/deployment mismatch, not an indexing failure
or a context-window failure.

The separate `python_engine.project_knowledge.retrieve` function also has a
`limit` argument; it is a different API and does not define the class interface.

## Correction

`backend/core/project_retrieval.py` provides one explicit retrieval adapter.
It inspects the bound method's actual signature and supplies only supported
options. It does not catch and retry internal `TypeError` exceptions.

| Loaded interface | Behavior |
|---|---|
| Current `Index` with `offset` and `limit` | Uses real pagination and the requested bounded section count. |
| Older `Index` | Uses its supported character/pass arguments, caps returned items, and reports legacy pagination availability explicitly. |
| Older `Index` requested at a nonzero offset | Returns no further page with a restart notice; never repeats page one as though it were a new page. |

Both the Chopper work queue and the public retrieval endpoint use the adapter.
Existing calls with only the question or character/pass budgets remain valid.
Auto and Deep retain their 16,000/28,000-character initial retrieval budgets.
Graph evidence and additional pages feed separate bounded analysis batches;
those character budgets are not model token limits.

The adapter bounds limits to 1–200, offsets to 0–100,000, and passes to 1–4.
It rejects malformed numeric options. Unknown adapter keyword arguments remain
errors. The existing tokenizer-based complete-prompt fitter still reserves the
response budget plus a 32-token fitting margin within the actual 4,096-token
model context.

The application server must be restarted after upgrading Python modules. Hot
replacement of individual module files is not a supported deployment method.
The compatibility adapter is an additional safeguard, not a replacement for
restarting a consistent installation.

## Files for this runtime fix

- `backend/core/project_retrieval.py`: new interface adapter.
- `backend/core/engineering_analysis.py`: seed and continuation retrieval use the adapter.
- `backend/api/project_intelligence.py`: retrieval API uses the same adapter.
- `tests/test_chopper_retrieval_compatibility.py`: real chat dispatch, real SQLite retrieval, legacy/current signatures, pagination, numeric bounds, internal-error transparency and model-budget regression tests.
- `tests/test_chopper_workbench_prompts.py`: replace its incomplete index stub with a real indexed project behind a legacy-signature wrapper; retain Auto/Deep budget assertions.
- `package.json`, `package-lock.json`: synchronized application version 4.97.1.

These changes sit on top of the ongoing engineering-analysis correction. They
do not establish complete machine understanding or remove the explicitly
reported semantic and unvisited-source limitations of that larger change.

## Verification

The regression suite invokes the production `/api/assist` route and its normal
project dispatch. Project retrieval and machine parsing use real temporary
projects and SQLite indexes. The budget test uses the real chat transport and
fitting code with a deterministic tokenizer/model response fixture; it checks
every resulting request satisfies `prompt + reserved answer + 32 <= 4096`.
Live model answers are a separate quality check, not implied by these tests.

```text
python -m pytest -q tests/test_chopper_retrieval_compatibility.py tests/test_chopper_pipeline_correction.py tests/test_project_intelligence.py tests/test_machine_function_engine.py tests/test_chopper_workbench_prompts.py tests/test_chopper_runtime_controls.py tests/test_function_flow.py tests/test_function_flow_api.py tests/test_machine_summary.py
57 passed
```

The chat regression also verifies the input project bytes and indexed-file
count remain unchanged. Browser verification of the ongoing pipeline change
confirmed that validation finishes while its window is collapsed, preserves
the project/result on reopening, and does not trigger a second validation.

The Python v1.71 packet-validation file is unchanged. No model settings, PLC
source, production metadata rows or workbook columns are changed by this fix.

The full production build passed for the main interface, DataInspect and Virtual
PLC. After restarting the combined server on port 8200, the live health response
and served frontend bundle both report 4.97.1. The existing Project 2 and
SC_PV5046 indexes still contain 887 and 597 successfully indexed files,
respectively. The browser validation-collapse check passed again after the fix.
