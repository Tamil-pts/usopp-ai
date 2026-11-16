# MatchView progress and performance - 16 November 2026

The processing timer now appears in the page flow below navigation. It cannot
cover the account menu, notification bell, inbox or logo. Mobile layouts wrap
its labels. A remaining-time approximation appears only after measurable file
progress; the unsupported fixed 45-second promise is removed.

Uploaded project folders now use `/api/compare/start` and poll the existing
account-protected comparison status endpoint. The synchronous `/api/compare`
endpoint remains compatible. The UI reports upload, queue, scanning and current
file progress instead of holding at 0 percent until the whole response arrives.
Worker setup failures become failed jobs instead of leaving a starting job.

Metadata inspection resolves an enclosing upload directory using the actual
project descriptor. This fixes missing Automation Studio/configuration details
when an uploaded project has an extra outer folder.

Performance work preserves source comparison semantics:

- Exact identical source text retains every original line without running a
  repeated-line sequence search.
- HMI resource references, text lookups and bitmap records are reused within
  one comparison. Cache keys retain their visualization path; shared assets
  remain present in every screen that references them.
- Ladder declarations are cached per source file within a run. Global and
  private program declarations retain their existing override/scoping rules.
- Caches are recreated for each comparison so a later run reads source edits.

The observed original uploaded run compared 1,403 base and 1,404 developed
files: engine 222.56 seconds, backend comparison 276.59 seconds, plus about
42 seconds staging uploads. Duration depends on project content and server
load; file percentage is not a guarantee of remaining wall time.

Verification artifacts are in `.build/matchview-performance-20261116/`.
Browser checks cover nested-folder metadata, upload progress, current file
labels, and inline timer placement at 1440, 760 and 390 pixels. Production
TypeScript and Vite checks passed. Targeted regression tests cover source
context, exports, HMI resources, declaration scope and asynchronous progress.

PLC source, the packet validator and saved project records are unchanged.

Final real-project check: 253.96 engine seconds. All 20 changed-file records,
391 unchanged logic records, 506 unchanged HMI records, 488 unchanged project
records and every non-timing summary field match the saved original result
exactly. This run overlapped maintenance checks; no end-to-end speedup is claimed.
Large-project runtime remains a limitation. The primary fixes are responsive
progress, accurate stages and unobstructed header controls.

Validation: 34 targeted tests, production TypeScript/Vite build and responsive
browser checks. Live UI/API version 4.99.3; frontend build integrity verified.
