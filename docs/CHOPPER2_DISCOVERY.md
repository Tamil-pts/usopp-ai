# Chopper 2.0 — Phase 0 Discovery Document

**Status:** Completed  
**Repository:** `uSOPp.ai` (v4.99.3)  
**Date:** 2026-11-23  

---

## 1. MatchView Decode and Storage Architecture

MatchView performs structural, textual, AST, ladder, and HMI visual comparison between two B&R Automation Studio projects (*Base* vs *Developed*).

### 1.1 Modules and Engine Entry Points
- **Comparison Engine CLI:** [python_engine/compare.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/python_engine/compare.py#L1-L28)
  - Invoked as: `python compare.py --base <path> --new <path> --output <compare_results.json> [--base-hmi ...] [--new-hmi ...]`
  - Defined as constant `COMPARE_ENGINE` in [backend/core/runtime.py#L56](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/runtime.py#L56).
- **FastAPI Router & Worker:** [backend/api/comparison.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/api/comparison.py#L5-L37)
  - Endpoint `POST /api/local/compare/start` ([backend/api/comparison.py#L122-L134](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/api/comparison.py#L122-L134)) spawns `_compare_worker` in a background daemon thread.
  - Progress tracked via job dict `COMPARE_JOBS[sid]` ([backend/api/comparison.py#L68-L98](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/api/comparison.py#L68-L98)).
- **Subroutines & Source Diffs:**
  - [python_engine/source_compare.py#L1-L80](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/python_engine/source_compare.py#L1-L80) (`source_diff` generates line hunks and line-by-line status).
  - [python_engine/ladder_model.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/python_engine/ladder_model.py) and [backend/core/plc_ladder_structure.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/plc_ladder_structure.py) (ladder rung and network parsing).

### 1.2 File Classification
In [python_engine/compare.py#L32-L43](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/python_engine/compare.py#L32-L43):
- **Logic:** `.st`, `.src`, `.var`, `.typ`, `.fun`, `.fb`, `.prg`, `.idc`, `.ab`, `.c`, `.h`
- **Ladder:** `.ld`
- **Screen / HMI:** `.page`, `.pages`, `.layer`, `.txtgrp`, `.algrp`, `.tpr`, `.dso`
- **Hardware:** `.hwl`, `.iom`, `.sw`, `.per`, `.osl`, `hw.cfg`

### 1.3 Disk Storage and Result Schema
- **Work Session Directory:** `WORK / 'compare' / <sid>` ([backend/api/comparison.py#L39-L51](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/api/comparison.py#L39-L51)), where `WORK = BASE / '.usopp_workspaces'` ([backend/core/runtime.py#L70](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/runtime.py#L70)).
- **Output File:** `compare_results.json` ([backend/api/comparison.py#L66](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/api/comparison.py#L66)).
- **Result Data Shape:**
  ```json
  {
    "projects": {
      "base": { "project_name": "...", "automation_studio_version": "...", "active_configuration": "..." },
      "developed": { "project_name": "...", "automation_studio_version": "...", "active_configuration": "..." }
    },
    "summary": { "added": 12, "removed": 3, "modified": 25, "unchanged": 140 },
    "categories": { "logic": 15, "screen": 8, "hardware": 2, "config": 3 },
    "diffs": [
      {
        "path": "Logical/MainTask/Cyclic.st",
        "category": "logic",
        "status": "modified",
        "subroutine": "Logical/MainTask",
        "base_relative_path": "Logical/MainTask/Cyclic.st",
        "new_relative_path": "Logical/MainTask/Cyclic.st",
        "hunks": [...],
        "source_rows": [...],
        "logic_added": [...],
        "logic_removed": [...]
      }
    ],
    "same_project_files": [...]
  }
  ```

---

## 2. Project Intelligence Index (`backend/core/project_intelligence.py`)

### 2.1 Index Location and Database Schema
- **File Location:** [backend/core/project_intelligence.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/project_intelligence.py)
- **Database Path:** `WORK / 'intelligence' / <project_key> / 'index.sqlite3'` ([backend/core/project_intelligence.py#L36](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/project_intelligence.py#L36)).
- **Tables and Schema** ([backend/core/project_intelligence.py#L51-L73](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/project_intelligence.py#L51-L73)):
  - `meta(key TEXT PRIMARY KEY, value TEXT)`: Tracks `schema`, `parser_revision`, `state`, `identity`.
  - `files(path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, sha TEXT, category TEXT, status TEXT, error TEXT)`
  - `sections(id INTEGER PRIMARY KEY, file TEXT, first INTEGER, last INTEGER, text TEXT, kind TEXT, label TEXT, complete INTEGER, enabled INTEGER, scope TEXT)`
  - `section_search USING fts5(text, tokenize='unicode61 tokenchars ''_''')`: Full-text search virtual table.
  - `symbols(name TEXT, display TEXT, kind TEXT, datatype TEXT, file TEXT, line INTEGER, scope TEXT)`: Declared variables, functions, programs.
  - `refs(name TEXT, file TEXT, line INTEGER, kind TEXT, scope TEXT)`: Usages (`read`, `write`, `condition`, `call`).
  - `edges(a TEXT, b TEXT, kind TEXT, file TEXT, line INTEGER, scope TEXT, detail TEXT)`: Call graph and dependency edges.
  - `tasks(name TEXT, source TEXT, file TEXT, line INTEGER, enabled INTEGER, configuration TEXT)`: PLC cyclic/init tasks.

### 2.2 Incremental Freshness
- In `Index.build(mode='refresh')` (and internal `Index.sync()`, [backend/core/project_intelligence.py#L300-L407](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/project_intelligence.py#L300-L407)), files are discovered and compared against stored `stat.st_size` and `stat.st_mtime_ns`.
- Unmodified files are retained without re-parsing; added/changed files are incrementally reparsed and re-indexed into SQLite and FTS5. Projects should always be accessed via the public `opened(key, owner)` lifecycle.

### 2.3 Retrieval Interface
- Invoked via `Index.retrieve(question, characters=18000, passes=3, offset=0, limit=14)` ([backend/core/project_intelligence.py#L409-L510](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/project_intelligence.py#L409-L510)):
  - **Pass 1:** Exact symbol matches, file name mentions, FTS5 BM25 matches (`section_search MATCH ?`), and dense semantic candidate IDs from `backend/core/semantic_retrieval.py`.
  - **Passes 2–3:** Follows graph edges (`edges` table) for callers, callees, condition drivers, and related type declarations.

---

## 3. WorkHub Intelligence: FRD, Flowchart, and MoM

### 3.1 Durable Job Queue
- **Module:** [backend/core/workhub_intelligence/jobs.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/jobs.py)
- **Supported Job Kinds:** Defined in [backend/core/workhub_intelligence/jobs.py#L17](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/jobs.py#L17):
  `{'meeting', 'transcribe', 'frd', 'flowchart', 'plan', 'extract', 'ocr', 'pdf', 'convert', 'document_answer', ...}`
- **Queue Table:** `pi_jobs` inside WorkHub's central SQLite database `application.sqlite3` ([backend/core/workhub_intelligence/jobs.py#L72-L79](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/jobs.py#L72-L79)).

### 3.2 Document Workflows and Schemas
- **MoM (Minutes of Meeting):**
  - Handled by `meeting_job` ([backend/core/workhub_intelligence/processing.py#L122-L189](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/processing.py#L122-L189)).
  - Requires reviewed transcript (`pi_transcript_reviews`), extracts discussion summary, decisions, engineering requirements, and action items with owners.
- **FRD (Functional Requirements Document):**
  - Handled by `requirement_job` ([backend/core/workhub_intelligence/processing.py#L231-L297](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/processing.py#L231-L297)).
  - Content schema:
    ```json
    {
      "project_name": "...",
      "requirements": [
        {
          "id": "FR-001",
          "title": "Concise title",
          "description": "Functional description",
          "trigger": null,
          "expected_behavior": null,
          "subsystem": null,
          "acceptance_criteria": null,
          "change": "new|modified|confirmed|removed_proposed|unresolved",
          "source_ids": ["..."],
          "status": "draft"
        }
      ],
      "purpose": "...",
      "scope": "...",
      "sections": [...]
    }
    ```
- **Flowchart:**
  - Handled by `generation_job` ([backend/core/workhub_intelligence/processing.py#L312-L344](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/processing.py#L312-L344)).
  - Layout graph coordinates via `layout_graph` ([backend/core/workhub_intelligence/processing.py#L299-L310](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/processing.py#L299-L310)).
  - Verified by `validate_drawing` in [backend/core/workhub_drawing.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_drawing.py):
    - `nodes`: `[{ "id": "n1", "position": { "x": 0, "y": 0 }, "data": { "label": "...", "kind": "start|process|decision|end|alarm|interlock", "source_ids": [...] } }]`
    - `edges`: `[{ "id": "e1", "source": "n1", "target": "n2", "label": "..." }]`

### 3.3 Approval Workflow
- In [backend/core/workhub_intelligence/store.py#L101-L140](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/store.py#L101-L140):
  - Documents created in `pi_documents` with revisions in `pi_revisions`.
  - Revisions are initially created in `status='draft'` or `review`.
  - An approved revision is recorded in `pi_documents.approved_revision`. Only approved revisions are picked up as ground truth for downstream stages ([backend/core/workhub_intelligence/processing.py#L195-L228](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/workhub_intelligence/processing.py#L195-L228)).

---

## 4. Old Chopper Calling Mechanism & Coexistence Strategy

### 4.1 How Old Chopper Works Today
1. **Configuration:**
   - Saved in `BASE / '.usopp_assist_model.json'` ([backend/core/assist_model.py#L18](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/assist_model.py#L18)).
   - Defaults: provider `embedded`, baseUrl `http://127.0.0.1:8202/v1`, model `chopper-local`, localPort `8202` ([backend/core/assist_model.py#L55-L60](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/assist_model.py#L55-L60)).
2. **Local Model Runtime:**
   - Manages an owned subprocess running `local_ai/runtime/llama-server` on loopback port 8202 ([backend/core/local_model_runtime.py#L45-L80](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/local_model_runtime.py#L45-L80)).
   - Model weights: single GGUF model `local_ai/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`.
3. **Retrieval Runtime:**
   - [backend/core/semantic_runtime.py#L20-L24](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/semantic_runtime.py#L20-L24) launches `bge-small-en-v1.5-q8_0.gguf` on port 8204 for embeddings and `jina-reranker-v1-tiny-en-Q8_0.gguf` on port 8205 for reranking.
4. **Invocation:**
   - Chat requests flow through `backend/api/assist.py` and `backend/core/assist_model.py:chat_model()`.

### 4.2 Coexistence Architecture for Chopper 2.0
- **Feature Flag:** Controlled by environment variable `USOPP_CHOPPER2=1` (disabled by default). When off, all Chopper 2.0 endpoints return 404 and the UI tab is hidden.
- **Separate Package & API:**
  - New package: `chopper2/` at the repository root.
  - New thin router: `backend/api/chopper2.py` with prefix `/api/chopper2`.
  - Registered additively in `backend/app.py`.
- **Separate Config File:**
  - Stored in `BASE / '.usopp_chopper2' / 'config.json'` (does not touch or overwrite `.usopp_assist_model.json`). Added to `.gitignore` to prevent committing local credentials or configs.
- **Separate Ports & Gateways:**
  - Connects to an external OpenAI-compatible model server (e.g. vLLM, Ollama, or LAN server on ports like 8000, 11434, or 8206).
  - Enforces network allowlist inside `chopper2/gateway/`.
- **Fallback Chain:**
  - If Chopper 2.0 gateway models are unavailable or time out, it can automatically route through old Chopper's fallback transport ([backend/core/assist_model.py](file:///C:/Users/PTPL0241/Projects/AI_QC/uaopp.ai/usopp_ai_2.0/backend/core/assist_model.py)).

---

## 5. "Do Not Touch" Verification

The following files and paths are confirmed to exist, remain untouched, and are treated as strictly **read-only**:

| Path / Module | Purpose | Status in Repo |
| :--- | :--- | :--- |
| `backend/api/assist.py` | Old Chopper API endpoints | Exists, untouched |
| `backend/core/assist_model.py` | Old Chopper transport & client | Exists, untouched |
| `backend/core/local_model_runtime.py` | Embedded llama-server process manager | Exists, untouched |
| `backend/core/model_policy.py` | Model network host restrictions | Exists, untouched |
| `backend/core/chopper_*.py` | Old Chopper agent, speech, sql, chain | All 8 files exist, untouched |
| `backend/core/project_assistant.py` | Context builder for old Chopper | Exists, untouched |
| `backend/core/project_intelligence.py` | Project index & symbol store | Exists, untouched (read-only reference) |
| `backend/core/log_diagnostics.py` | PLC log decoder | Exists, untouched |
| `backend/core/report_analysis.py` | Validation & comparison report analytics | Exists, untouched |
| `src/features/assist/**` | Old Chopper frontend UI | Exists, untouched |
| `src/features/settings/AssistModelSettings.tsx` | Old Chopper settings panel | Exists, untouched |

---

## 6. Python Environment & Dependency Analysis

Inspected `.venv/Lib/site-packages` in the local project environment:

| Package | Status | Version / Note |
| :--- | :--- | :--- |
| `langchain-core` | **Installed** | `>=1.8, <2` in backend requirements |
| `pydantic` | **Installed** | `2.13+` |
| `httpx` | **Installed** | Available in environment |
| `requests` | **Installed** | `2.32+` |
| `numpy` | **Installed** | `2.4+` |
| `duckdb` | **Installed** | `2.0.0` |
| `langgraph` | **Missing** | To be added in `chopper2/requirements.txt` |
| `pyyaml` | **Installed** | Available in environment (needed for eval suites) |
| Embeddings library | **Pluggable** | Can use OpenAI-compatible `/v1/embeddings` endpoint or local port 8204 |

### Dependencies to add to `chopper2/requirements.txt`:
```txt
# Chopper 2.0 Dependencies (isolated from main project requirements)
langgraph>=1.0,<2
```
*(Backend requires `langchain-core>=1.8,<2`. Verify in a clean venv with `pip check`. Adding Chopper 2.0 dependencies to container build is planned for Phase 8. No existing requirements files will be modified).*

---

## 7. Proposed Analysis Tools Specification (Phase 3)

Chopper 2.0 wraps read-only engine capabilities as typed LangChain / Pydantic tools. Every returned fact includes `file` and `line`.
**Critical Architecture Constraint:** Tools must call `Index` public methods and resolve projects via `opened(key, owner)` from `backend.core.project_intelligence`, **never raw SQL** directly on the SQLite database. This maintains strict per-user tenant isolation and ensures compatibility if database or parser internals evolve.

| Tool Name | Input Schema | Output Schema | Backing Engine Function / Public Method |
| :--- | :--- | :--- | :--- |
| `list_routines` | `{ project_id: str, owner: str }` | `List[{ name, file, line, kind, scope }]` | `index = opened(key, owner); index.routines()` / symbol lookup |
| `get_routine` | `{ project_id: str, name: str, owner: str }` | `{ name, file, first_line, last_line, text, scope }` | `index.section_for_routine(name)` |
| `call_graph` | `{ project_id: str, routine: str, owner: str }` | `{ routine, callees: List[{ name, file, line, kind }] }` | `index.calls_from(routine)` |
| `callers` | `{ project_id: str, routine: str, owner: str }` | `{ routine, callers: List[{ name, file, line, kind }] }` | `index.calls_to(routine)` |
| `trace_variable` | `{ project_id: str, name: str, owner: str }` | `{ symbol, datatype, declarations: List[...], writers: List[...], readers: List[...] }` | `index.trace(variable_name)` |
| `io_map` | `{ project_id: str }` | `List[{ channel, variable, module, datatype, file, line }]` | `python_engine/module_serial_mapping.py` |
| `alarms` | `{ project_id: str }` | `List[{ code, message, group, trigger_var, file, line }]` | `python_engine/packet_validation_report_uSOPp_v1.71_final.py` |
| `modes_and_states` | `{ project_id: str }` | `{ modes: List[str], states: List[{ name, code, routine, file, line }] }` | `python_engine/working_sequence.py` |
| `communication_blocks`| `{ project_id: str }`| `List[{ protocol, task, packet_type, payload_bytes, file, line }]` | `python_engine/packet_validation_report_uSOPp_v1.71_final.py` |
| `hmi_objects` | `{ project_id: str, screen: str }` | `List[{ object_id, type, tag_binding, position, file }]` | `python_engine/compare.py:parse_structured_hmi_diff` |
| `compare_summary` | `{ session_id: str }` | `{ base_project, new_project, summary, categories }` | `WORK / 'compare' / <sid> / 'compare_results.json'` |
| `changed_items` | `{ session_id: str, filter?: str }` | `List[{ path, category, status, hunks, logic_added, logic_removed }]` | `compare_results.json:diffs` |
| `read_source` | `{ project_id: str, file: str, start: int, end: int }` | `{ file, start_line, end_line, content }` | Bounded read via `python_engine/source_operations.py` |
