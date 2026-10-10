# Persistent storage and Chopper CPU model

Implemented in 4.65.9. One shared server supports five regular accounts plus Admin. Users connect through the existing LAN/VPN and sign in; the server administrator installs releases.

## What goes in a database

| Data | Storage | Why |
| --- | --- | --- |
| Accounts, password hashes, sessions and resource ownership | `accounts.sqlite3` | Stable user identity and access checks |
| Saved PLC targets, custom metadata, manual frame templates, report cover details and UI settings | `application.sqlite3` | Per-user records with revisions; available from another browser |
| Full test results, test IDs, owner IDs and history records | `application.sqlite3`, with compatible JSON archives | Searchable durable records; earlier file history is adopted when history is opened |
| Rule configuration and Knowledge Hub mappings | Existing `rules/` and `knowledge/` JSON files | Keep the current validation schemas and editing workflow |
| Approved engineering observations | Existing `rules/learning/` JSONL | Evidence retrieval; no automatic model training |
| XLSX/PDF/HTML reports, project snapshots and captured input files | `.usopp_exports/` and `.usopp_workspaces/history/` | Large files remain tied to their test IDs |
| LLM configuration | `.usopp_assist_model.json` | Small private server configuration |
| Model weights and approved checksum manifest | `local_ai/models/` GGUF + JSON | A model is a large binary file; it does not belong in SQLite |

All of these paths are under **`USOPP_DATA_ROOT`**. Docker uses `/data` in a named persistent volume. Application updates replace the image and retain that volume. Edited knowledge and rules are not overwritten by bundled defaults. Imported data models remain user-owned; bundled reference models are supplied with each application release.

SQLite uses WAL and short transactions on the server's local disk. Run one backend process; existing validation workers remain independent. JSON is still appropriate for rules and reference data. A vector database is not required for the current approved-evidence retrieval.

## Browser migration and conflicts

On first sign-in to the updated app, surviving browser-only settings are imported into that user's server records. Existing server values take priority. Earlier unscoped browser data is adopted only by Admin. Deleted settings have tombstones, so another old browser cannot restore them accidentally.

The UI waits for server settings before opening the workspace. Changes are saved automatically. A save notice remains visible until the server acknowledges them; connection failures offer retry and an unsaved-settings download. Revision checks reject different stale edits from another tab/device. Reloading server settings retains a browser recovery copy. Browser data already deleted before migration cannot be recovered.

## Small CPU model without Ollama

The selected model is [Qwen2.5-Coder 1.5B Instruct, Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF), Apache 2.0, **1,117,320,768 bytes**. Its pinned revision and SHA256 are in `backend/core/cpu_model.py`. The model card and license are included in packages.

1. Install/start uSOPp and sign in as Admin.
2. Open **Settings → Chopper · AI connection**.
3. Click **Set up small CPU model**. This downloads the fixed approved model into the server's persistent data folder and verifies its size and SHA256.
4. Continue validation while setup runs in the background. Setup selects Chopper local model mode, starts the included runtime, and enables restart startup.
5. Wait for **Ready**. The model uses localhost internally; users talk to it through authenticated uSOPp requests.

Windows packages include llama.cpp CPU binaries. The Dockerfile builds a Linux CPU runtime from the same pinned llama.cpp release, b11475 / `7e8324f5feba1d8be3f966e1791e84107e40cdd7`. No Ollama service is needed or modified. Model weights are downloaded once into the persistent volume and are excluded from Git and application images.

Defaults: 8,192 context tokens, up to four CPU threads, 512 answer tokens, one model generation at a time. The model response window defaults to 30 minutes; Admin can select 0.5-30 minutes. Up to five independent Chopper requests may enter the queue; queue waiting and generation share that window. Project indexing happens before it. Each request supplies its own messages and source evidence. CPU model queuing does not use the validation worker lock. Ready means the model is loaded; Save & check requests a short answer with a separate 30-second limit. Allow approximately 4 GB free RAM for this starting model and at least 1.4 GB disk for its download; total server RAM/disk must also cover simultaneous validations and retained projects. Actual speed depends on the server and is not established by compilation.

For an offline server, place the exact approved GGUF at `/data/local_ai/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`, then use the same setup button: it verifies the file without downloading it. The existing custom-GGUF selection remains available for another compatible licensed model. Keep custom weights under `USOPP_DATA_ROOT/local_ai/models` to include them in server backups.

## Updates, backup and restore

Use [the shared server instructions](distribution/LAN_SERVER.md). An update stops the app, backs up the entire data volume and starts the selected image on the same volume. Backup includes both databases, rule/knowledge JSON, private results, inputs, reports and model weights. Restore writes to a new empty volume and retains the original volume.

GitHub stores application releases, not private server data. Keep backups separately from the server. Finish active tests and wait for settings to save before stopping. Model/runtime packages and database changes need destination verification before production use.

## Build evidence and remaining verification

Python compilation, both TypeScript compilations, PowerShell/shell syntax and both frontend production builds passed. The Windows EXE and release ZIPs built; archive audits and checksums passed. The development copy of the selected model was downloaded, size/SHA256 verified and configured for loading on the next application restart. Docker is unavailable on the development laptop, so Linux image build/run, five-user load, live PLC routing and destination backup/restore are pending. No inference or runtime tests were run as part of this implementation.
