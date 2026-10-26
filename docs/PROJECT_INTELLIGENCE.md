# WorkHub Project Intelligence

## Location and scope

Open an existing WorkHub project and choose **Project Intelligence**. The eight sections are Overview, Discussions, MOM & FRD, Flowcharts, Timeline, Roadmap, Documents and Review & Approvals. Existing project tabs and engineering tools retain their own routes and records.

This module extends the existing Python/FastAPI backend and React/TypeScript frontend. It does not introduce PHP, a second user directory, a separate project database or a replacement task system.

### Typical use

1. Upload a Teams recording/transcript, or record a physical meeting with the browser microphone. Teams application consent is not required for file uploads.
2. Save, then choose **Process meeting**. Processing uses saved jobs and continues after navigation. Browser recording needs HTTPS over a VPN, or localhost during development. Keep the recording page open until the recording has been stopped and saved.
3. Correct the original-language transcript, replay timestamped speech and review the separate English interpretation. Unknown speakers, responsibilities and dates remain unknown.
4. Review the generated MOM, choose an enabled reviewer by name and submit the exact revision. The assigned reviewer approves or requests corrections. Approving a MOM queues an FRD proposal when its author still has project contribution access.
5. Compare proposed requirements with the approved FRD. Approve a new revision after reviewing changes and unresolved questions.
6. Generate or draw an editable flowchart. Generate a plan proposal, adjust its activities, owners, dates, estimates and dependencies, then submit it for review.
7. A project manager reviews the approved plan preview and explicitly confirms **Apply to WorkHub**. Only then are activities created or updated through the existing WorkHub task functions. Existing project stage rules still apply.

Development, quality review and release remain separate delivery phases. Document approval does not mark a project released.

## Implemented components

| Area | Implementation |
| --- | --- |
| Capture | MP3, WAV, M4A, MP4, VTT, DOCX; browser WebM/OGG/M4A recording with pause/resume, duration, consent and microphone state |
| Speech | Offline Faster-Whisper model folder; Tamil, English and automatic detection; timestamps, word probabilities and uncertainty flags |
| Meeting analysis | Local LLM, original text retained, separate English interpretation, referenced MOM draft and clarification questions |
| MOM/FRD | Immutable content revisions, optimistic version checks, named reviewers, retained approved baseline, requirement change classes and source references |
| Clarifications | Choices, short answers, attachments, Not decided / Ask later, normalized duplicate questions and remembered confirmed decisions |
| Flowcharts | React Flow nodes/connections, decisions/start/end, requirements, drag/pan/zoom, layout, fullscreen, revision saves and PNG/SVG/PDF export |
| Planning | Proposed activities and risks; approved revision plus explicit Apply; mappings to existing WorkHub tasks; existing Gantt for dates, owners, progress, milestones and dependencies |
| Roadmap | Official phases and activities, editable phase names/owners, dates, completion, milestones, dependencies, approved proposal risks and existing issues |
| Documents | Preserved originals; PDF.js page/text/zoom/search; source references; version-specific page notes; PDF rotate/merge/extract/OCR; native TXT/CSV editing |
| Office | Self-hosted ONLYOFFICE DOCX/XLSX editing, signed document links/config/callbacks, new draft revision on save; LibreOffice conversion/export |
| Document assistant | Source-cited questions, summaries, FRD comparison, earlier revision comparison, and approved-source flowchart/plan proposals |
| Processing | Durable SQLite job ledger, atomic leases and heartbeat, cancellation/retry, Redis wakeups and separate local workers |

Manual drafts, document storage and review do not require a language model. Automatic speech recognition and AI drafting require the local services below.

## Data, permissions and history

- Project Intelligence tables are additive `pi_*` tables inside the existing `.usopp_workhub/projects.sqlite3` database. Original recordings and document files use the existing WorkHub SHA-256 blob store and upload quota.
- Enabled personal accounts retain existing project visibility. Existing project contributors can add evidence/drafts; project managers control planning and preferences. Only the named reviewer can approve a submitted document revision.
- Saving creates a new content revision. Earlier content and approved revisions remain stored. Approval status, reviewer identity, decisions and comments are recorded separately in the WorkHub activity history.
- Transcript history retains original ASR text, corrected text, English interpretations, supplied speaker information and author/version timestamps.
- Applying a plan calls the existing WorkHub create/edit functions in one transaction. Proposal IDs map to official task IDs so reapplication does not create duplicate activities. Removed proposal rows do not silently delete official tasks.
- Office links authorize one editing session, expire after 12 hours and recheck the account. Callbacks require both a scoped capability and the configured JWT signature; edited files must come from the configured local office server.
- Confirmed answers are provided to later local processing. Matching normalized questions are retained once. Semantically rephrased questions can still require an engineer to recognize an existing decision; there is no claim of perfect semantic deduplication.

## Local services and deployment

The Compose overlay is [deploy/intelligence/compose.yaml](../deploy/intelligence/compose.yaml). It extends [distribution/compose.yaml](../distribution/compose.yaml) and reuses the existing external data volume. It does not replace the existing installer or reverse proxy.

| Service | Role |
| --- | --- |
| `app` | Existing WorkHub application image extended with local document export tools; same routes/authentication/data volume |
| `project-meeting-worker` | Speech, MOM/FRD, diagram/plan generation and document questions |
| `project-document-worker` | Text extraction, image/PDF OCR and document conversion |
| `project-pdf-worker` | Local PDF page transformations through the same authenticated project job queue |
| `project-llm` | Existing llama.cpp server binary with an operator-provided engineering GGUF model |
| `project-redis` | Password-protected internal wakeup queue; SQLite remains authoritative |
| `project-office` | Optional `office` profile for a reviewed self-hosted ONLYOFFICE Docs image |

PDF operations use local pypdf/OCRmyPDF in the PDF/document workers. A separate Stirling-PDF server is not required for the implemented operations. No external PDF API is used.

### Prepare the server

Use the existing Linux Docker server and deployment environment. Build the normal application image from this checkout first, with its version matched to `package.json`, as described by the existing container deployment instructions.

1. Back up the existing application volume using the existing deployment backup procedure. For SQLite, use its backup API or stop writers; copying only a live database file can omit WAL contents.
2. Provide the external data volume name and normal `USOPP_IMAGE`/admin secret environment from the existing installation.
3. Copy `deploy/intelligence/local.env.example` to a private `local.env` on the server. Supply company HTTPS origins, private-network DNS, random Redis/JWT secrets and a reviewed ONLYOFFICE image tag or digest. Keep secrets outside source control.
4. Place models under the configured absolute directory:

   ```text
   /srv/usopp/intelligence-models/
     engineering.gguf
     whisper/
       model.bin
       config.json
       tokenizer.json
       vocabulary.*
       ...complete multilingual Faster-Whisper model files...
   ```

   Obtain model files separately under their licenses. Workers use `local_files_only=True`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; jobs do not download a missing model or fall back to a cloud provider.

5. From the repository root, combine the existing deployment environment and the new overlay:

   ```sh
   docker compose --env-file /srv/usopp/deployment.env \
     --env-file deploy/intelligence/local.env \
     -f distribution/compose.yaml -f deploy/intelligence/compose.yaml \
     --profile office build

   docker compose --env-file /srv/usopp/deployment.env \
     --env-file deploy/intelligence/local.env \
     -f distribution/compose.yaml -f deploy/intelligence/compose.yaml \
     --profile office up -d
   ```

   Omit `--profile office` when Office editing is not yet configured. The file upload/download workflow remains available. Do not run `down -v` against the application data volume.

6. Reuse the existing HTTPS reverse proxy for WorkHub. Proxy a second company HTTPS hostname to `127.0.0.1:8202` for the office server, preserving Host, Upgrade and forwarded protocol headers as described by ONLYOFFICE deployment documentation. The browser must reach this URL; the office server must reach `http://app:8200`. Do not publish Redis, model or worker ports.
7. Trust forwarded HTTPS headers only from the existing selected proxy using `USOPP_FORWARDED_ALLOW_IPS`. Install the company CA in containers if private TLS endpoints need it. `USOPP_PI_CA_BUNDLE` can identify a local CA bundle for outbound local service requests.
8. Restrict service egress at the company network/container layer according to local policy. LLM URL checks reject public-network endpoints, redirects and proxy environment forwarding; originals and meeting content are not sent to external AI.

### Resource and model configuration

The supplied worker image is a CPU configuration. Faster-Whisper defaults to CPU/int8 and four threads. Configure `USOPP_PI_WHISPER_THREADS` and `USOPP_PI_LLM_THREADS` for the server, and choose model size/context according to measured RAM and latency. No throughput or transcription accuracy benchmark is claimed by this implementation.

For GPU speech processing, supply a compatible CUDA/CTranslate2 worker image and explicitly configure `USOPP_PI_WHISPER_DEVICE`, `USOPP_PI_WHISPER_COMPUTE` and Docker GPU access. The CPU image is not presented as a verified CUDA deployment.

On a workstation, the default embedded worker supports operations whose local dependencies are installed. To use separately launched workers:

```sh
USOPP_PI_WORKER_MODE=external python -m backend.core.workhub_intelligence.worker \
  --kinds meeting,frd,flowchart,plan,document_answer,clarifications
```

All processes must use the same `USOPP_DATA_ROOT`, accounts and writable WorkHub storage. Use a local Docker volume/filesystem for SQLite WAL, not a network-mounted SQLite database.

## Explicit processing limits

- Existing WorkHub upload limits still apply: resumable large engineering files remain stored/downloadable. Automatic document extraction/conversion is limited to **100 MiB per input**, **500 extracted PDF pages**, **1.5 million extracted characters**, bounded Office ZIP expansion and image dimensions. Coverage notices identify partial extraction.
- The text editor refuses to save a truncated extraction preview over a complete TXT/CSV document. Download the original or split it before native editing.
- PDF transformations accept at most 20 inputs and 2,000 pages. Notes remain full Unicode PDF text annotations; they are not flattened pictures of shortened text.
- Meeting transcription is limited to 20,000 segments. Browser recording stops at 250 MiB so it can be saved and continued as another recording. Uploaded larger recordings remain subject to available worker resources.
- The flow editor supports 500 nodes/1,500 connections. Complete labels are preserved in SVG/PDF; oversized PNG exports ask for vector export.
- Generated proposal context is bounded. Long transcripts are chunked. Large document question/proposal contexts fail with a selection/splitting instruction rather than silently omitting the specification tail.
- Local model responses require recognized source references. This verifies citation identity, not the truth of every interpretation. Engineers must inspect the evidence and approve drafts. Generated control sequences are not validated PLC logic.
- Speaker diarization/voice identity is not inferred. VTT voice labels and explicitly supplied participants are retained; other speaker fields remain unassigned/editable.
- Complex drawings are preserved; OCR does not claim to reconstruct editable CAD, electrical schematics or a validated machine design.
- Link exports use `USOPP_PI_PUBLIC_ORIGIN`. Without it, exports retain source IDs/page/timestamps but cannot form company-accessible hyperlinks. Users opening a source link still need their normal WorkHub account.
- Tamil PDF export needs the local LibreOffice/Noto font installation. DOCX and browser SVG/PNG remain available when that dependency is missing.

## Availability and rollout evidence

The frontend production build and Python module compilation are recorded during implementation. Docker is not available in the current Windows shell, and no Linux server address or model files were supplied. Therefore container builds/startup, Tamil speech accuracy, local LLM generation quality, microphone/browser compatibility, PDF rendering and Office callbacks have **not been verified live** by those build checks. Activate and review these on the target server before treating them as production capabilities.

The supplied request ended at `Redis | Backg`; no unseen requirements after that text are assumed implemented.

## Primary integration references

- [Faster-Whisper: local models, multilingual transcription and runtime requirements](https://github.com/SYSTRAN/faster-whisper)
- [React Flow interactive editor](https://reactflow.dev/learn) and [serialization](https://reactflow.dev/examples/interaction/save-and-restore)
- [PDF.js official examples](https://github.com/mozilla/pdf.js/blob/master/docs/contents/examples/index.md)
- [ONLYOFFICE JWT security](https://api.onlyoffice.com/docs/docs-api/get-started/how-it-works/security/) and [save callback statuses](https://api.onlyoffice.com/docs/docs-api/usage-api/callback-handler/)
- [OCRmyPDF cookbook](https://ocrmypdf.readthedocs.io/en/latest/cookbook.html)

ONLYOFFICE distribution, licensing, supported concurrent editing capacity and model licenses must match the chosen company deployment.
