# WorkHub backend reliability — 4.87.0

## Scope

This extends the existing SQLite Project Intelligence queue, WorkHub database,
project access checks, controlled documents and Docker overlay. It preserves the
existing document numbering, revision, review, approval, FAT execution and project
workflow implementations. No PLC validation or Virtual PLC engine source changed.

## Execution and recovery

- The API commits a job and returns its ID. The existing project panels show
  Processing, Completed, Failed or Cancelled, stage progress, permitted actions
  and generated downloads. Engineers can navigate and keep working.
- One supervisor runs one isolated child by default. Speech, document and PDF
  lanes share a configurable global admission budget. A worker accepts all kinds,
  including FRD, FAT, ISO and exports. Heavy libraries leave memory when the child
  exits; API threads do not execute those jobs.
- SQLite leases survive app/container restarts. A supervisor renews its job lease,
  stops its owned process tree on cancellation/deadline/memory pressure, and
  requeues unfinished work on shutdown. Crashed children receive bounded recovery
  with backoff; expired leases can be reclaimed. The default attempt cap is three.
- Missing local services remain blocked for an explicit retry. Correctable model
  output failures may be retried, while changed sources, invalid input,
  permissions and memory-budget failures require correction or a fresh job.
- Payload canonicalization plus source snapshots deduplicates repeated requests.
  Revision recovery, durable file output slots and package records prevent retry
  duplication. Transactional number allocation still uses the administrator's
  existing PTPL / ES / PLC configuration. No new approval is synthesized.

## Reuse and source traceability

- Extraction results, text, metadata, page/row references and notices are stored
  in a project-scoped, compressed, integrity-checked cache in the existing database.
  The key includes immutable file bytes, format, processor/library version and
  relevant options. Original blob integrity and project identity are checked on
  reads; cached source IDs and names are rebound only within the same project.
- Concurrent misses use persistent leases. Unchanged files reuse a complete
  extraction. Changed PDFs reuse matching standalone pages, including fonts and
  resources; other changed formats are parsed again. Chunk fingerprints are
  retained. The cache never claims that a partly read document was fully covered.
- Transcription is reused by recording bytes, language, terminology and offline
  speech-model revision. Conversion outputs, structured model responses and
  document exports are also reusable. Model responses must still pass existing
  engineering schemas and citation checks on every use; invalid responses are
  removed from the reusable cache.
- Source snapshots include relevant native/controlled revision identities and
  draft edit versions. New source revisions invalidate cached retrieval identities
  and derived preparation. The existing closure checks additionally flag changed
  sources for newly generated controlled revisions. Upstream dependency tracking
  does not treat downstream FAT preparation as an FRD source change. Historical
  approved documents and previous results are retained, never rewritten.
- A crash before a compute checkpoint commits can require repeating that compute.
  Committed document/file/package identities remain idempotent.

## Qwen and resource controls

Chopper and WorkHub share a persistent FIFO inference admission queue. The default
concurrency is one. Queue length, wait deadlines, model HTTP deadlines, memory
reserves and orphan lease expiry are bounded. A cancelled/failed request retains
a short reservation while the private model unwinds. WorkHub has no cloud fallback
or model download path. Existing private model credentials and transport remain in
use; no prompt or credential is written to inference telemetry.

Important environment settings (prefix all with `USOPP_PI_`):

| Setting | Default | Purpose |
| --- | ---: | --- |
| `WORKER_CONCURRENCY` | 1 | Global active jobs across processes |
| `SPEECH_CONCURRENCY`, `DOCUMENT_CONCURRENCY`, `PDF_CONCURRENCY` | 1 each | Lane budgets |
| `JOB_TIMEOUT`, `SPEECH_TIMEOUT` | 1800 / 3600 s | Hard child deadlines |
| `JOB_MAX_MEMORY_MB` | 2048 | Child process tree RSS ceiling |
| `NATIVE_THREADS` | 2 | Native math thread budget |
| `JOB_MAX_ATTEMPTS` | 3 | Recovery/manual attempt ceiling |
| `MAX_PENDING`, `MAX_PROJECT_PENDING` | 100 / 20 | Global/project backpressure |
| `AI_CONCURRENCY`, `AI_MAX_PENDING` | 1 / 32 | Private inference admission |
| `AI_QUEUE_TIMEOUT`, `LLM_TIMEOUT` | 120 / 240 s | Inference wait/HTTP deadline |
| `MEMORY_RESERVE_MB`, `AI_REQUEST_MEMORY_MB`, `JOB_MEMORY_MB` | 256 each | Memory admission |
| `DISK_RESERVE_MB` | 512 | Keep capacity for durable writes |
| `MAX_DOCUMENT_MB`, `MAX_OUTPUT_MB` | 100 / 256 | Processing limits; originals remain available |
| `CACHE_MAX_MB`, `CACHE_WAIT_SECONDS` | 1024 / 120 s | Cache storage and contention limit |

PDF/conversion input groups are capped at 256 MiB. Existing page/text/ZIP expansion
limits remain. Linux children also have file-size and descriptor limits. A full
cache safely bypasses reuse rather than deleting originals or approved revisions.

## Durable files and cleanup

Generated blobs are flushed, verified by SHA-256 and atomically placed before
their database records commit. Existing blobs are verified before reuse. Job
temporary files live in `processing-tmp/<job>-<lease>` in the WorkHub data volume.
The supervisor cleans them after its child stops; orphan directories are cleaned
only after age/active-lease checks. Blob originals, approved document revisions,
cached results and controlled packages are not targets of temporary cleanup.

## APIs and frontend

Existing API shapes and direct download routes remain compatible. Additional APIs:

- `POST .../intelligence/jobs`: existing queue, now also accepts `export` and
  `q_export` with a selected document/control, revision and format.
- `GET .../intelligence/jobs?limit=50&cursor=<last-id>`: project-scoped keyset
  pagination, bounded to 100 jobs. Existing overview responses still contain jobs.
- `GET .../intelligence/jobs/<id>`: detailed progress, permitted controls and source
  freshness. Cancel and Retry endpoints remain at their existing paths.
- `GET .../intelligence/jobs/<id>/download`: completed exports with renewed project
  authorization, integrity verification and controlled download audit.
- `GET /api/admin/settings/workhub-health`: administrator-only operational metrics.

The existing document editor queues PDF/DOCX exports; Quality & Closure queues
controlled PDFs. Completed exports appear in their existing background job panel.
Other download formats and legacy direct export URLs retain their behavior. A
legacy direct export request can still do first-time rendering synchronously;
the updated frontend uses the asynchronous paths for heavy exports. Existing
readers retain export access without gaining project contribution rights.

Operational health includes bounded API latency samples by route template, queue
counts, persistent processing times/peaks, worker heartbeat/failure counts, disk
capacity, cache hits, inference reservations and memory availability. Owned local
model RSS is reported when available. Remote inference memory is not fabricated;
its service uses its configured container memory limit. API latency samples are
per API process since startup, not a durable company-wide monitoring history.

## Docker and activation

`deploy/intelligence/compose.yaml` now starts one all-purpose document worker.
Redis is optional (`queue-wakeup`); additional workers require `extra-workers` and
an explicit larger global concurrency budget. A separate local model is optional
(`local-inference`); use the existing private service or set the corresponding
internal URL. The model directory mount contains operator-provided offline models.
No new configuration screen or mandatory service has been added.

Workers have CPU, memory, process and shutdown limits, and a persistent heartbeat
healthcheck. Worker and API volumes must be on the same Docker host with a local
filesystem: [SQLite WAL does not support a network filesystem](https://www.sqlite.org/wal.html).
Process-tree controls and RSS sampling use [psutil](https://psutil.io/).

The Linux/Docker rollout and real model activation were not performed from this
Windows workspace. These deployment files are prepared for the existing server;
the user's earlier decision to skip Linux/model activation remains respected.

## Verification

- `python tests/test_workhub_reliability.py`: isolated database/accounts/files,
  real worker subprocesses, cancellation including native descendants, timeouts,
  expired leases, cache contention/integrity, changed-page reuse, atomic numbering,
  controlled draft generation, ISO replay, export reader permissions and structured
  model/citation rejection. A loopback model fixture checks private HTTP transport;
  it is not a real Qwen quality/latency benchmark. Speech reuse uses a fixture.
- Existing WorkHub activity and growth tests are run alongside the new checks.
- Production frontend builds/type checks, database integrity and protected module
  hashes are checked separately.
- [Local before/after benchmark](WORKHUB_PERFORMANCE_BENCHMARK.md): repeatable
  synthetic data, no company records, and explicitly limited Windows measurements.
