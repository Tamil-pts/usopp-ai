# WorkHub FRD workflow acceptance review

Release: **4.89.0** · Review date: **2026-10-26**

## Build and navigation

The main WorkHub, Nami and Virtual PLC production builds pass, with their TypeScript checks. All 129 backend Python files compile. The checked bundles are published locally; `/api/health` and the served interface manifest both identify 4.89.0, and the served entry matches its SHA-256. Docker/Linux deployment and a Windows installer were not built or tested in this review.

From **WorkHub → Overview**, use **Create FRD / Reports**, beside **New project**. Select a project and a document. In its workspace, choose **Generate draft**. The four project sections remain:

| Document | Project section |
| --- | --- |
| FRD and its flowchart | Meetings & Requirements |
| Test Report, Correction Notes | Engineering Documents |
| FAT, Quality Approval, Project Closure | Quality & Closure |

The shortcut also opens portfolio reports. Document creation still enforces existing project permissions and prerequisites; opening a tool does not generate or approve a document.

The fictional example is at **Help → Engineering Documentation → FRD Sample**, also accessible through **Help · FRD Sample** in the WorkHub header.

## Test methods and isolation

- `tests/test_workhub_frd_workflow.py`: 7 acceptance tests using actual authenticated APIs, isolated SQLite databases, real supervised job subprocesses, and Chromium PDF generation. Its local HTTP model fixture deliberately tests valid and malformed model responses. These tests establish integration behavior, not model accuracy.
- `tests/test_workhub_reliability.py`: 25 passing checks for durable jobs, restart recovery, cancellation, timeouts, source changes, caches, admission limits, permissions and related controls.
- `tests/workhub_frd_browser.py`: 15 passing Chromium checks against the published bundle. It uses an isolated copy of saved Admin dashboard preferences and project records. A simulated microphone tests browser recording controls; it does not test real microphones or speech recognition.
- Additional live checks used the existing private Chopper model with fictional, isolated meeting data. Actual MOM generation, FRD generation and an editable flowchart proposal completed. Earlier failed model responses remain in the artifacts to document fixes and limitations.
- 79 protected PLC and validation source files match the starting hashes. Existing items, files, issues, updates, engineering runs and saved project revisions match the starting database copies. Test and practice records are not production projects or performance contributions.

## Feature classification

“Working” refers to the specific checks below, with their stated limits. It is not certification of generated machine behavior or of every possible input.

| Feature | Expected result | Actual result and evidence | Classification |
| --- | --- | --- | --- |
| Saved dashboard rendering | Returning users can open their dashboard | Reproduced the previous raw-record widget crash with saved Admin preferences; chart-only transforms and a widget error boundary prevent the crash. Published-bundle browser check passes. | Working |
| FRD/report discovery | Visible entry from Overview | All six document shortcuts open the intended section and document heading in Chromium. | Working |
| Browser recording consent | Capture requires consent and microphone access | Consent prevents starting; simulated Chromium microphone capture, pause, resume, stop and authenticated upload pass. Real hardware/denial prompts are not acceptance tested. | Partially Implemented |
| Recording and transcript uploads | Preserve source files and support supplied transcripts | Browser WebM and WAV storage/integrity checks pass; VTT, SRT and TXT imports pass. Real MP3/M4A/MP4/Teams audio decoding is not tested without the speech model and recordings. | Partially Implemented |
| Tamil/English/mixed speech recognition | Local multilingual transcription with reviewable uncertainty | Faster-Whisper integration and uncertainty fields exist, but no installed local Whisper model or user recordings are available. Missing-service behavior is tested. Clear/noisy/multiple-speaker/mixed/technical audio accuracy is unverified. | Partially Implemented |
| Voice-based speaker identification | Identify speakers only when supported | No voice diarization model is installed. Explicit VTT voice labels and manually supplied speakers are retained; unknown speakers remain unknown. | Missing |
| Transcript timestamps and editing | Preserve originals, validate time ranges and retain history | VTT/SRT times retained, reverse times rejected, text originals retained after corrections. Current-version review is required before a separate MOM job. | Working |
| English interpretation | Separate original and interpretation | Separate fields and revision history pass. Live English-source generation passes. Tamil translation fidelity is not tested. | Partially Implemented |
| MOM structure and source links | Editable, timestamp-linked sections with unknown owners/dates preserved | Required sections, including engineering requirements, pass fixture integration and a real local-model run. Unsupported fixture owners/dates are cleared. Human review is still required for semantic correctness. | Working |
| MOM approval | Only reviewed approved content becomes a derivation source | Unreviewed transcript is rejected; outsider approval returns 403; assigned reviewer approval queues FRD derivation. | Working |
| Structured FRD | Unique IDs, reviewed source revisions, context and clarifications | Fixture flow yields two unique requirements from repeated source statements; actual local model produces a draft from the approved MOM. Purpose/scope/machine fields use recorded information and remain unconfirmed when absent. | Working |
| Chopper flowchart proposal | Valid source-linked proposal, no automatic edits | Actual local Chopper proposal completes after schema/citation validation. Applying is a separate authenticated action. Invalid IDs, sources, tags and values are rejected. Model accuracy still requires engineering review. | Working |
| Chopper explain/rewrite/clarify | Reviewable answers and changes for selected requirements | Existing actions and review controls are retained. This acceptance run exercises flowchart proposal/apply; live behavior of every other assistance action is not separately certified. | Partially Implemented |
| Editable FRD diagram | Nodes, branches, I/O refs, manual edits and persistence | Embedded editor renders; manual practice editing/save/reopen passes. Alarm/interlock/I/O types are accepted. PDF return paths and loops are routed separately. | Working |
| Diagram review after requirement changes | Changed requirements invalidate diagram review | Requirement edits set `needs_review`; document confirmation is blocked until explicit current-diagram review. | Working |
| Draft PDF | Company template, metadata, diagram, repeated footer and watermark | Chromium exports pass; each page has document/project/revision and Page X of Y. Company logo, selected header color, layout, Unicode text and revision history are checked; representative pages are visually reviewed. | Working |
| Customer PDF branding | Customer identity and optional logo | Customer master/project association and separate logo rendering are checked with fictional assets. | Working |
| Approved PDF integrity | No silent overwrite after approval/template changes | Assigned reviewer approves; approved source/layout are frozen. Export bytes remain identical after organization branding changes; editing the approved revision returns 409. Actual reviewer identity is printed. | Working |
| Alternative PDF renderer | Export where Chromium is absent | ReportLab fallback is retained. This review exercises Chromium; it does not certify fallback Unicode/layout parity. | Partially Implemented |
| FAT/test report preparation | Trace approved requirements without inventing test results | Background report preparation creates linked cases with no executions. Five built-in training FAT cases remain Not Tested. No physical FAT is performed. | Working |
| Read-only Help sample | Complete fictional learning material | Project, original/English transcript, MOM, FRD, linked diagram, five FAT cases and draft PDF are available through View Sample. | Working |
| Private practice copies | Edit and reopen without affecting company records | Try Sample, save/history, reviewed proposal application and PDF pass; another user gets 404. Production project/document/approval/sequence/event counts do not change. | Working |
| Background recovery and protection | Retry safely, preserve originals and scope access | Existing reliability suite passes; missing speech service gives an actionable Failed display, safe retry/cancel, and unchanged original recording hash. | Working |
| Complete live audio-to-approval acceptance | Real representative audio through the full workflow | Supplied-transcript-to-approval is exercised with the controlled model fixture; live local AI MOM/FRD/flowchart calls are separately exercised. Complete real-audio acceptance remains unavailable without the recordings and offline speech model. | Partially Implemented |

## Failures fixed during review

1. Saved raw-record dashboard widgets incorrectly passed table/Gantt rows into chart transforms and could blank the app. Only chart widgets build chart options; failures are isolated per widget.
2. FRD/report controls were buried below the dashboard. A visible project/document shortcut opens the existing tools.
3. Meeting processing previously combined transcription and MOM generation. They are now separate jobs with an explicit saved-transcript review gate.
4. FRD assistant requests omitted their native document ID and failed queue validation. Requests now carry the controlled and native revision references.
5. Small local-model responses failed JSON/citation validation. First-draft prompts use concise schemas and short prompt references mapped back to canonical IDs. Repeated approved MOM statements are grouped into one coherent, revision-specific source, retaining upstream transcript references. One bounded citation correction is validated before anything is saved.
6. A live model supplied the graph in the explanation field as well as the correct flowchart field. The valid graph still undergoes full schema/citation checks; the UI receives an explicit system notice that a separate explanation was not supplied. Non-text explanations for other actions are rejected.
7. Optional null edge labels are treated as empty. Invalid graph structure and unsupported technical values still fail validation.
8. Diagram changes were not linked to requirements review. Semantic requirement hashes now invalidate diagram confirmation after a requirement edit.
9. PDF exports lacked some repeated project/header details and overlapping return paths. Footer/header fields, revision history and flow routing were corrected.

An earlier live flowchart run was cancelled after a worker lease expired during a long execution pause. It is recorded as a failed attempt, not as successful generation. The later live flowchart job completed.

## Operational limits

- Speech recognition requires an offline multilingual model configured by `USOPP_PI_WHISPER_MODEL`, the speech worker dependencies and representative recordings. None were downloaded or synthesized to claim speech accuracy. The user stated that the recordings/model were not available.
- Model output remains an engineering draft. Literal value/tag guards cannot prove all narrative semantics, decisions or engineering correctness. An engineer and the assigned reviewer must verify them.
- Private practice assistant calls are authenticated request/response operations. Production transcription, MOM, FRD, flowchart and export jobs use the existing durable queue.
- Real microphone/audio accuracy, Tamil interpretation accuracy, every assistance action, Linux/Docker runtime deployment and installer creation are not signed off by these tests.

## Artifacts

Local artifacts are under `.build/workhub-frd-validation/`:

- `release-build-results.json`, build logs, `live-release-results.json`.
- `workflow-tests.log`, `workflow-results.json`, `reliability-after.log`.
- `browser-results.json`, `browser-live-dist.log`, dashboard/settings/sample screenshots.
- `local-model-results.json`, `local-model-native-success.json`, `local-model-recheck.json` document actual local-model attempts and the later successful stages.
- `acceptance-draft-frd.pdf`, `acceptance-approved-frd.pdf`, `training-sample-frd.pdf`, branded/Unicode PDF examples and rendered inspection pages.

Every generated document and identity in those test artifacts is fictional. They do not constitute company project approval or physical test evidence.
