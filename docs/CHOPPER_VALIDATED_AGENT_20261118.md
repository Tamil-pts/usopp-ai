# Chopper: validated agent workspace, guided prompts and reviewed learning

Implemented and checked on 18 November 2026 in the current checkout. UI/API
remain 4.99.3. These are additive tools under AI Assist; existing engineering
validation, approvals, projects and model weights were preserved.

## Review and implementation

| Area | Finding and resulting behavior |
|---|---|
| Local neural model | Existing Qwen GGUF inference retained. No replacement download or weight update. |
| Hybrid RAG | Existing exact-symbol / FTS retrieval, engineering graph and optional local semantic retrieval retained. Dense retrieval depends on installed local embedding assets; it is not silently downloaded. |
| Agent orchestration | Added LangChain Runnable stages: retrieve, select, second review pass, verify sources, publish literal checked records. At most two evidence model calls and two concurrent tool runs. No LangGraph installation or arbitrary tool execution. |
| Structured output | Strict Pydantic fact-ID and SQL-plan schemas. Unknown IDs, extra claims, inconsistent abstention and changed project sources are rejected. |
| Text to SQL | Owned CSV/XLS/XLSX worksheet -> schema -> SELECT dry-run -> user review -> publish result/CSV. A temporary in-memory SQLite database contains only this worksheet. No access to accounts, approvals or application databases. |
| Internet references | Exact-domain approved HTTPS retrieval with public-IP validation, pinned TCP destination, verified TLS, bounded downloads and no scripts/cookies/proxy. Web access is off by default and requires explicit per-run selection. |
| Multiple models | Planner, researcher and reviewer roles can reference the existing local model or configured OpenAI, Anthropic or compatible HTTPS profiles. Both global privacy policy and per-run consent apply. |
| Learning | Private run diagnostics and proposed lessons with independent administrator review. Approved lessons are guidance, never new PLC facts. Separate existing source-backed Q&A export supports offline adapter training. |
| Evaluation | Executable installation guard fixtures required before the new tools run. A code revision change invalidates the report. Engineer-labeled model-quality evaluation is still required. |
| Chat UX | Chat & files, Checked agent and Learning & training shortcuts; a goal/scope/context/output prompt builder fills an editable draft without sending it. New modes support browser history and direct refresh. |

The two model review roles can use the same local model. This is a second model
pass, not independent engineering verification. Ordinary chat has its existing
publication boundaries; it has not been silently replaced by the new agent.
The existing engineering harness still controls which static facts it can
establish. Missing timer/scan/vendor semantics remain unresolved.

## Use the new workspace

Open **AI Assist -> Agent workspace**. An administrator runs **Run safety checks**
once for the installed engine revision. Choose Evidence agent or Text to SQL.
For project facts, select an owned project and explicitly build its engineering
graph. Changed sources require a current index and graph.

For SQL, upload a worksheet, choose sheet/header, and ask a precise question such
as `What is the total Hours?` or `How many rows?`. Review the prepared SELECT and
column mapping before publishing. The deterministic fallback supports only these
narrow aggregate forms; it rejects implied filters/grouping rather than guessing.
The optional planner handles richer proposals, which still require SQL validation
and user review. Syntactic SQL safety does not establish that a query captures
business intent. Saved formula results are used; unknown/error cells are NULL.
SQLite numeric aggregation uses floating-point arithmetic. Input is capped at
50,000 data rows, result at 200 rows, with VM/time and allocation limits.

## Public references and optional providers

In **Connections & policy**, the administrator chooses exact public domains and
may enable web references. Each run must also request fetching its URLs. Pages
are stored as external untrusted excerpts with retrieval time and SHA-256, not
as validated engineering knowledge. Private, loopback and metadata-service IPs
are rejected. This tool is for public sources, not authenticated sites or LAN
services. It does not crawl or execute downloaded code.

Optional search needs the server environment variable `USOPP_BRAVE_SEARCH_KEY`.
Only the separately entered public search query goes to search; project source
is not automatically used as a search query. Approved URLs work without a search
key. Search results are restricted to the approved domain list.

Optional remote profiles contain provider/model IDs and a **key variable name**,
for example `USOPP_AGENT_CLAUDE_KEY`; never paste a secret into the profile.
Configure its value outside the app in the server environment. Enter a model ID
available to your provider account. Remote execution remains blocked while the
shared local-only policy is enabled, and requires per-run evidence-sharing
consent after that policy is explicitly changed. No cloud calls were made in
verification; provider transport formats and consent guards were mocked.

## Training and learning boundary

The live reviewed-Q&A summary currently contains **5 approved and 14 pending**
examples. The existing offline pilot trainer requires at least **50 distinct
reviewed Q&A examples**, **two project groups**, and at least **20 training
examples after a project-held-out split**. The new readiness panel mirrors these
checks, deduplicates examples, and does not start training.

Use **Chat -> Learning & training** to inspect and correct source-backed examples,
export the approved dataset, and follow the existing training instructions and
`scripts/train_chopper_adapter.py`. Select a compatible base model explicitly;
the trainer's default is not proof of compatibility with the installed GGUF.
Train a separate adapter in an isolated environment, evaluate held-out projects,
compare against the serving baseline, review deployment, then activate explicitly.
No adapter was trained or activated in this change. Pending chats, web pages and
model suggestions are not automatically promoted into training or approvals.

Agent lessons and training Q&A are separate records: approving a retrieval lesson
does not automatically add it to the weight-training export. Automatic weight
self-modification and unrestricted autonomous agents are not implemented.

## API and storage

New account-bound endpoints under `/api/assist/agent`:

- `GET /status`, administrator `PUT /settings`, administrator `POST /evaluate`.
- `POST /runs`, `GET /runs/{id}`.
- `POST /queries`, `POST /queries/{id}/execute`.
- `GET /examples`, `POST /runs/{id}/examples`, `POST /examples/{id}/review`.

The new tools reject demo/unauthorized accounts. Runs are private even between
administrators. Example review is restricted to a different administrator.
Settings, runs and lessons are in `chopper_agent.sqlite3`, separate from the
engineering graph, project data and approval records. The installation guard
report is `chopper_agent_evaluation.json`. Both are local runtime artifacts;
these are not trained weights. Existing engineering MCP tools remain available;
new agent endpoints are REST only in this change.

## Verification

- **78 targeted Python tests passed**, covering the new agent, engineering
  harness, local speech interfaces, semantic retrieval and compatibility.
  A pre-existing speech worker timing failure appeared during one concurrent
  run; the final full targeted run passed. No speech implementation was changed.
- **20 executable installation guard fixtures passed**: strict selections,
  fabricated claims, SQL isolation/limits, changed source and public-network
  boundaries. These are guard tests, not model-accuracy certification.
- Actual installed local GGUF selected the relevant supplied fact ID in a
  synthetic two-fact question. No general accuracy or training claim follows.
- Actual public HTTPS retrieval of Python's sqlite3 documentation succeeded;
  the snapshot hash and explicit shortening were retained. No confidential
  source was sent. Search and cloud model calls need configured keys.
- Browser: authenticated API evaluation, CSV upload, SQL dry-run, review/publish,
  CSV download, guided prompt drafting, internal Back and direct-refresh checks.
  New agent layout checked at 1440, 760 and 390 px with no horizontal overflow
  or page errors. Training page checked at desktop/mobile widths.
- Main TypeScript and Vite production builds passed. This turn did not execute
  Windows packaging or a Docker runtime build. Frozen-module code hashing has
  a loader fallback; packaged deployment still needs its normal smoke checks.

Artifacts: `.build/chopper-agent-regression.log`, `chopper-agent-local-model.json`,
`chopper-agent-web-smoke.json`, `chopper-agent-browser/`, and build logs.
Reproduce with `.venv/Scripts/python.exe -m pytest tests/test_chopper_agent.py
 tests/test_engineering_harness.py tests/test_chopper_speech.py
 tests/test_chopper_semantic.py tests/test_chopper_retrieval_compatibility.py -q`
(on one command line) and `.venv/Scripts/python.exe tests/chopper_agent_browser.py`.
Browser fixtures use a temporary data root and do not rewrite live records.

Primary implementation references: [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html),
[LangChain](https://www.langchain.com/oss-overview),
[Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create),
[Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get).
