# Chopper 4.97.2: question-relevant engineering traces

Verified locally on 29 October 2026 against the existing Project 2 index. This correction fixes output identification and unsupported answer publication. It does **not** establish a complete machine execution model.

## Root cause and correction

| Failure | Correction |
|---|---|
| Natural-language motor questions used broad source retrieval; exact writer seeding required an exact PLC tag. | Separate output, troubleshooting, function-sequence, whole-machine and mapping plans. Resolve writer-backed symbols; prefer a unique physical `%Q` mapping in the active configuration. Return ambiguity when identity is not established. |
| A signal occurrence or HMI page was treated as a start-condition proof. | Named outputs use deterministic writer proofs. Read the complete Ladder network or common ST/AB/C control-flow representation; HMI bindings remain supporting references. |
| Parallel Ladder contacts could not be combined reliably. | Reuse the existing shared Ladder geometry. Join right-boundary OR junctions, trace connected power to the coil, and preserve AND/OR/NOT. Disconnected timer branches do not become coil conditions. Unsupported instructions remain explicit gaps. |
| Multiple writes on one C source line could collapse together. | Keep writer identity by symbol, file, line, network, value and guards. Re-establish each assignment against whole-file parser output. Include preceding IF/ELSIF conditions in ELSE evidence. |
| Project-wide USB sequences appeared ahead of a motor trace. | Return a focused Machine Analysis containing the selected writer, relevant routines and upstream proofs. Function-sequence queues prioritize matching routine roots and resolved callees. Whole-machine analysis retains its independent work queue. |
| Citations were accepted as proof of the model's PLC conclusions. | Named-output answers publish only deterministic traces. Whole-machine model summaries remain diagnostic and are omitted from the answer until semantically verified; source-parsed transitions/calls and incomplete coverage remain visible. |
| Files and source sections were mixed in coverage labels. | Separate file counts, section counts, relevant functions, writer proofs and unresolved dependency checks. A deterministic trace supplies zero sections to the LLM; it does not pretend to have run model inference. |
| Partial engineering answers created training drafts automatically. | Gate training capture before any training-database access. Partial, unresolved or rejected engineering results are ineligible. Manual review and existing approved knowledge are preserved. |

The 4.97.1 retrieval adapter, pagination and actual-token prompt fitter remain in use. No Transformer/NCM or model configuration changes were introduced.

## Actual Project 2 answer check

Question: **What conditions are required before the can changer motor starts?**

Before, the user-reported answer cited `DI_FEED_SENSOR`, `DI_MAIN_MOTOR_SLOW` and an unrelated HMI screen without proving the controlling coil or logical relationship. The reported duration was 310.8 seconds. That answer is rejected; it is not the expected reference answer.

After, Chopper identifies:

- Output: `DO_CAN_CHANGER_MOTOR`.
- Active physical mapping: `%QX."105_X20DO9322".DigitalOutput03`, configuration `LDF3S_WO_SUCTION`.
- Writer: `Logical/doffing/doffingCyclic.ld`, network 23, coil line 458.
- Active task assignment: `doffing.prg` / `doffing`, with separate scheduling uncertainty.
- `DO_CAN_CHANGER_MOTOR_V` is another name match; it is not substituted for the mapped physical output.

The source-derived Boolean condition, factored here for readability, is:

```text
M501
AND (hmi_sliver_cutting_device_toggle
     OR (NOT hmi_sliver_cutting_device_toggle AND NOT SLIVER_CUTTING_ENABLE))
AND DI_EMERGENCY_OFF_LHS
AND DI_EMERGENCY_OFF_RHS
AND DELAY
AND NOT M1236
AND NOT EMERGENCY_PB_PRESSED
AND NOT ALARM_BIT_SAFETY_SWITCH_OFF
AND NOT TEMP
AND NOT SLOW_SPEED_FOR_DOFF_SCD
```

This is rung power for an ordinary open coil when that network executes. It is not an observation that inputs are active, a diagnosis of the present stop, or proof of physical motor motion. The displayed answer retains the fully parenthesized expression produced by the topology tracer.

Latest measured focused run: **4.30 seconds**, using the existing cached project model and index, **zero LLM requests**. Its scope differs from the earlier broad model response; this is not an equal-work model throughput comparison.

| Measurement | Focused result |
|---|---:|
| Eligible / indexed files | 887 / 887 |
| Statically parsed executable files, including partial parses | 163 |
| Parsed files carrying semantic notices | 12 |
| Retrieved source files / sections | 10 / 36 |
| Files with established writer or supporting mapping/task proofs | 10 |
| Relevant logic routine files with at least one parsed writer proof | 8 |
| Distinct resolved source sections | 21 |
| Resolved writer proofs | 78 |
| Source sections containing unresolved writer logic | 15 |
| Reported unresolved dependency/execution checks | 90 |
| Model-supplied files / sections | 0 / 0 |

All parsed writers of the selected output are shown. The trace also follows upstream writers through two dependency expansion levels, bounded at 128 writer records. A routine/file being counted as analyzed does not mean every branch in that routine was resolved. Same-spelled local symbols and case-distinct names are not silently merged.

Evidence artifact: `.build/chopper-pipeline-correction/project2-can-changer-verified.json` contains the actual answer, complete source references, focused Machine Analysis and verification result. Status is **partial**, with direct conditions established and training ineligible.

## Whole-machine check and context budget

Also ran **Explain the complete machine working sequence** against Project 2 using the actual installed local model, tokenizer and production answer orchestration.

- First run: 3 engineering batches plus synthesis, 189.36 seconds, maximum actual prompt 2,106 tokens.
- Continued run: one additional batch plus synthesis, 82.50 seconds, maximum actual prompt 2,030 tokens for those two requests.
- Across the saved run: 10 model-supplied files / 10 sections; 9 sections passed source-reference checking; 4,378 retrieved sections and 154 routine files remained unvisited or incomplete.
- Each captured request satisfied `actual prompt tokens + reserved answer tokens + fitting margin <= 4096`; the local context setting was not increased.
- Whole-machine result remains **partial**. Unverified calibration summaries from the model were removed from the displayed answer. The answer reports source-parsed transitions and unresolved coverage rather than claiming a full operating timeline.

Artifacts: `.build/chopper-pipeline-correction/project2-whole-machine-question-correction.json` and `project2-whole-machine-question-correction-final.json`. The first artifact preserves the rejected intermediate model interpretation for diagnostic comparison; it is not approved knowledge. The latter demonstrates the semantic publication gate. Source-reference checking alone is not engineering entailment verification.

Reproduce with `scripts/verify_chopper_pipeline.py --index <existing-key> --question "..." --batches 3 --inference --label <name>`. This uses existing indexes without rebuilding them, records real inference and tokens, and verifies that indexed file counts remain unchanged. It writes local analysis caches and diagnostic artifacts.

## Modified files for this correction

- `backend/core/engineering_question.py`: plans, identification, complete-source proofs, scope-aware dependency traversal, focused answer and verification metadata.
- `python_engine/ladder_model.py`: Boolean coil tracing using the existing geometry model.
- `backend/core/project_assistant.py`: focused dispatch and deterministic publication gate for whole-machine results.
- `backend/core/engineering_analysis.py`: function-specific queue priority and separate coverage units.
- `backend/core/assist_training.py`: block automatic capture of unverified engineering answers.
- `src/features/assist/MachineFunctionAnalysis.tsx`: focused writer/dependency panel.
- `src/features/assist/ProjectIntelligence.tsx`: explicit files, sections, functions and dependency counts.
- `scripts/verify_chopper_pipeline.py`: retain actual verification and focused view in QA artifacts.
- `tests/test_chopper_question_trace.py`: real chat route, Project 2 reference, parallel-rung truth table, ambiguity, stale source, C writers, ELSE proof, local scope, training gate and unverified-summary rejection.
- `tests/test_chopper_retrieval_compatibility.py`: exercise retrieval compatibility through a general-source chat question now that named outputs intentionally use the focused path.
- `package.json`, `package-lock.json`: synchronized 4.97.2 version.
- This report. Earlier pipeline files remain described in the audit and the 4.97.1 retrieval report.

## Regression and browser verification

Target suite: **79 passed, 2 skipped**. Includes project intelligence, machine function engine, function flow/API, runtime controls, actual chat retrieval compatibility, prompt overflow, question traces, machine summary and shared Ladder diagrams/exports. Two environment-dependent Ladder checks skipped. Installed the already-declared `svglib` and `pypdf` dependencies to run PDF export regression checks; no dependency declarations changed.

Production build passed for the main UI, DataInspect and Virtual PLC. Existing bundle-size/dynamic-import warnings remain.

Playwright mounted the actual React components with intercepted API fixtures. Confirmed focused motor title/condition, absence of `ah_open_stage`, separate coverage units, source counts, token display and 390px coverage layout. Confirmed that an in-flight validation completes while its window is hidden, retains the selected project/result and does not rerun or fail on reopening. This fixture test is separate from actual local-model inference above.

Local server restarted successfully. `/api/health` and served JavaScript confirm **UI 4.97.2 / API 4.97.2**, matching build integrity.

The v1.71 validator is unchanged: current and HEAD Git blob both `80bc7904a5c2b083c50e0fdc6334a9496767fe20`. No PLC project source, workbook schema, user permission, model setting or project workflow was edited.

## Remaining limitations

Edge contacts, unsupported block pin behavior, pointer aliasing, external library implementations and actual scheduler/runtime state can leave upstream behavior unresolved. These gaps are shown, not replaced with guessed prerequisites. The bounded focused trace does not claim a transitive proof of every machine dependency. Whole-machine interpretation still needs additional verified function summaries and connected execution analysis; it is not complete merely because indexing, batching or unit tests succeed.
