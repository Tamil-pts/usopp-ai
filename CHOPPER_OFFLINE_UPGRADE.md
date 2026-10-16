# Chopper offline upgrade — 4.66.0

## Use it

1. Open Settings. The local CPU connection defaults to the bundled llama.cpp runtime. Install or select **3B primary**, activate it and wait for **Ready**. Keep **1.5B fallback** installed. Startup does not download weights. Saved connection choices remain editable.
2. Open AI Assistant → Chat. Your selected ByteMap/LogicScan project is reused; alternatively attach a complete project folder or ZIP using the existing paperclip.
3. Project Intelligence indexes that project locally. Its status line stays compact. Click to expand counts, progress, failed files, refresh, rebuild, retry and cancel. Refresh after editing sources. A cancelled or partly failed index is explicitly incomplete.
4. Ask a focused variable, routine, block or machine question. Source citations expand to the retrieved code. Context details show measured tokens and each retrieval pass. The model sees selected evidence, not the entire project.
5. Choose **Guide me step by step** for conversational app coaching. Select a workflow, perform one step, ask a question or continue to the next step. General chat remains available.
6. Ask for proposed Structured Text changes with before/after code. Review declarations, conditions, target scope and library compatibility. Chopper has no source-write tool; existing manual source editing remains a separate engineer action.

## Local model

Primary: `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF`, `qwen2.5-coder-3b-instruct-q4_k_m.gguf`, pinned revision `f74adce6aa16316c625447af059dbebe4983757c`.

SHA256: `724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7`.

The 3B model uses the **Qwen Research License**. The retained 1.5B model uses **Apache-2.0**. The existing `local_ai/MODEL_LICENSE.txt` and `MODEL_CARD.md` describe the 1.5B fallback; do not apply that license to 3B. See the [official 3B repository](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF) for its model card and license.

The 8 GB profile uses 4096 context tokens, at most four default CPU threads, 128-token inference batches, no GPU layers and one llama slot. RAM is measured for the owned model process, not an estimate of total laptop memory. An 8 GB physical device was not available as a separate constrained benchmark; performance depends on CPU and other applications. Increase context only after checking available memory. Installed weights and runtime files remain ignored by Git.

The installed 1.5B can be selected manually. An eligible failed primary startup or missing primary file can fall back to it automatically, with a visible reason. It never loads both models concurrently. A port occupied by an unrelated process is reported, not terminated. Windows cleanup checks the exact runtime executable, Chopper alias, loopback binding and parent identity before stopping a model.

## Index and retrieval

Per-user databases live in `.usopp_workspaces/chopper_intelligence/<owner-and-project-hash>/project.sqlite3` under the application's data directory. SQLite uses WAL, a 4 MB page cache, disk temporary storage and one index worker. Each source transaction replaces its sections and relationships; deleting a source cascades into FTS, symbols and dependencies. Source bytes are never rewritten.

The index retains one file at a time, with an 8 MB per-file bound and bounded reference extraction. Large or unreadable sources are reported. Excluded folders are counted without processing their content. Symlinks are not followed. Reindexing uses file modification time and size to detect changes; **Rebuild index** reparses all eligible files. Chat history and model context do not own the persistent index.

Retrieval combines explicit source filenames, exact symbol references/declarations, SQLite FTS5 ranking, callers/callees, block types, variable producers/consumers and conditions over up to three dependency passes. A fourth type lookup may follow. Complex machine questions can analyze two evidence batches before synthesis; only citation-checked intermediate findings are retained in the request. Source excerpts stay bounded and duplicate sections are removed. Small complete functions/blocks are preferred where available.

Physical configuration and task assignment are evidence distinct from source presence. Same-named local variables are scoped separately; ambiguity is reported. A ladder network keeps its full topology; a list of contacts is not treated as an AND expression. Conditions are interlock candidates, not proof of a safety function. Vendor manuals explain contracts and syntax, not the machine's implementation.

The runtime's `/apply-template` and `/tokenize` endpoints measure the complete prompt. Older history is trimmed before low-ranked code; answer tokens and framing have a separate reserve. Returned completion usage updates the visible meter. Omitted evidence, bounded sections, output limits and indexing errors are reported as incomplete analysis. Answers use a constrained source-ID response schema. Direct questions about enclosing conditions use parsed control-flow facts without inference. Source citations are mechanically checked; they do not establish that every generated interpretation is semantically correct. Engineer review remains necessary.

New Project Intelligence inference uses the bundled model only. Main and corner chat carry an offline-only flag. Other pre-existing optional external provider settings remain available for separately configured legacy integrations. No source is sent externally by this upgrade's project reasoning path. AI errors do not alter validation verdicts or prior results. No changes to the v1.71 validator or validation/offset windows are required by this Chopper upgrade; earlier authorized metadata work in this development batch remains separate.

## Verification

Run from the repository with `.venv/Scripts/python.exe`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_project_intelligence.py tests/test_chopper_setup_and_references.py tests/test_chopper_runtime_controls.py
.\.venv\Scripts\python.exe tests/chopper_index_benchmark.py
.\.venv\Scripts\python.exe tests/chopper_ui_browser_check.py
# Optional: requires the app-owned local model already loaded on loopback.
.\.venv\Scripts\python.exe tests/chopper_offline_inference_check.py
```

The index benchmark distinguishes a **synthetic 10,000-file PLC fixture** from supplied real project 2 and Project 3. It verifies unchanged PLC source hashes, incremental refresh and bounded retrieval. Results are local in `.build/chopper-intelligence-qa/results.json`. The browser check isolates accounts/storage, blocks PLC network operations and covers manual frame decode, coaching, project upload, indexing and ownership. It does not test physical machine operation.

Build both frontends before launching. UI and API versions read `package.json`. Container/image generation and updating the existing server are deferred release operations, not effects of a source push.
