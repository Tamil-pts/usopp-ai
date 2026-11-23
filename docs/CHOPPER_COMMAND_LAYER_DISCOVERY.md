# Chopper Command Layer — Phase 0 Discovery

**Status:** DRAFT — awaiting engineer review and approval  
**Date:** 2026-11-23  
**Repo root:** `C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp_ai_2.0`

---

## 1. Hook Point in `_assist()`

**File:** [`backend/api/assist.py`](../backend/api/assist.py) lines 291–300

```python
def _assist(payload:dict):
    # line 294-296 — log decoder early-return
    from backend.core.log_diagnostics import reply_if_invalid_ybs
    frame_reply = reply_if_invalid_ybs(context, question)
    if frame_reply is not None: return frame_reply

    # line 297-300 — report analysis early-return
    from backend.core.report_analysis import reply_if_report
    report_reply = reply_if_report(payload)
    if report_reply is not None: return report_reply

    # ← COMMAND LAYER HOOK GOES HERE (line ~301, before line 301 `application_help` check)
```

**Pattern:** The command layer inserts a third early-return hook immediately after line 300 and before line 301:

```python
# chopper_actions hook (additive, flag-gated)
if os.environ.get('USOPP_CHOPPER_ACTIONS'):
    from backend.core.chopper_actions.router import reply_if_action
    if (card := reply_if_action(payload)): return card
```

The return value shape must match what `assist_start` already wraps into a job result: a plain `dict`. The front end receives it as `result` in the `status` poll response.

---

## 2. ByteMap Validation — Request / Response

### Local path (project already on server)

**Endpoint:** `POST /api/local/validate`  
**File:** [`backend/api/validation.py`](../backend/api/validation.py) lines 118–124

```json
{
  "project_path": "C:/path/to/Project.apj",
  "metadata_path": "C:/path/to/Metadata.xlsx",
  "machine_department": "Spinning",
  "bool_metadata_mode": "BOOL",
  "project_name": "MachineX"
}
```

**What it does:**
1. `_local_session()` → `(sid, work)` where `work = WORK / sid`  
2. `_execute_project(sid, root, ...)` → calls `run_engine(args, BASE)` (synchronous)  
3. Engine writes `work/validation_results.json`; `find_json(work, 'validation_results.json')` loads it  
4. `begin_run` / `record_run` write history  

**Response shape** (from `_execute_project`, file line 104):

```json
{
  "sessionId": "<uuid>",
  "projectName": "MachineX",
  "machineDepartment": "Spinning",
  "testId": "<testId>",
  "version": "4.99.x",
  "engineVersion": "1.71",
  "projectPath": "C:/...",
  "localMode": true,
  "downloadExcelUrl": "/api/download/<sid>/...",
  "boolMetadataMode": "BOOL",
  "counts": {"fail": 3, "warning": 7, "pass": 120, "error": 0, "groups": 15},
  "results": [
    {
      "group_code": 10,
      "issues": [
        {"severity": "FAIL", "parameter": "GC10_Param1", "message": "...", "file": "mms_nw_rCyclic.st", "line": 42}
      ]
    }
  ],
  "score": 94.2
}
```

> `counts` and `results[].issues` are the fields the **action's `summarize_validation()`** function reads from.  
> `sessionId` is the deep-link token for opening results in ByteMap.

### Upload path

**Endpoint:** `POST /api/validate` (multipart form)  
**File:** [`backend/api/validation.py`](../backend/api/validation.py) lines 147–154  
Accepts: `project_files` (folder zip), `metadata` (xlsx), `machine_department`, `project_name`, `bool_metadata_mode`  
Response: same shape as local path.

---

## 3. MatchView Comparison — Request / Response

### Start (async, background thread)

**Endpoint:** `POST /api/local/compare/start`  
**File:** [`backend/api/comparison.py`](../backend/api/comparison.py) lines 122–133

```json
{
  "base_path": "C:/path/to/BaseProject.apj",
  "new_path":  "C:/path/to/DevelopedProject.apj",
  "base_name": "Machine_Base",
  "new_name":  "Machine_Dev",
  "base_hmi":  "",
  "new_hmi":   ""
}
```

**Response:**

```json
{"status": "started", "sessionId": "<pid>_<token>", "baseName": "Machine_Base", "newName": "Machine_Dev"}
```

### Poll status

**Endpoint:** `GET /api/local/compare/status/{sid}`  
**File:** [`backend/api/comparison.py`](../backend/api/comparison.py) lines 140–146

```json
{
  "status": "complete",
  "phase": "complete",
  "percent": 100,
  "result": { ... }
}
```

Statuses: `starting` → `running` (phase `comparing`) → `saving` → `complete` | `error`

### Result shape (from `compare_results.json`)

**File:** [`backend/api/comparison.py`](../backend/api/comparison.py) lines 102–115

```json
{
  "sessionId": "<sid>",
  "baseName":  "Machine_Base",
  "newName":   "Machine_Dev",
  "localMode": true,
  "summary": {"added": 2, "removed": 0, "modified": 14, "unchanged": 320},
  "diffs": [
    {
      "path":     "Logical/Global/mms_nw_rCyclic.st",
      "category": "logic",
      "status":   "modified",
      "hunks":    [...]
    }
  ],
  "projects": {
    "base":      {"project_name": "Machine_Base"},
    "developed": {"project_name": "Machine_Dev"}
  }
}
```

> `summary` total counts and `diffs[].category` breakdown are the fields `summarize_compare()` reads.  
> `sessionId` is the deep-link token for opening results in MatchView.

---

## 4. Opening Saved Results in ByteMap / MatchView

**File:** [`src/app/App.tsx`](../src/app/App.tsx) lines 94–95 (`RunHistory onOpen` handler)

```tsx
onOpen={(kind, data) => {
  if (kind === 'data-model' || data.runStatus === 'interrupted' || ...) {
    setHistoryDetail(data)
  } else if (kind === 'datainspect') {
    setDataInspectHistoryId(data.historyId); setPage('plc')
  } else if (kind === 'compare') {
    compare.openHistory(data); setPage('compare')   // ← MatchView deep link
  } else if (kind === 'rules') {
    setRuleResults(data); setPage('rules')
  } else {
    validation.openHistory(kind, data); setPage('validation')  // ← ByteMap deep link
  }
}}
```

**How the front end opens results from Chopper summary card:**

The Chopper summary card's "View details" button must dispatch:
- **ByteMap:** `window.dispatchEvent(new CustomEvent('usopp-open-result', {detail: {kind: 'validation', data}}))` — OR — call `onOpenFeature('validation')` from `AssistWorkspace`'s prop (file: [`src/app/App.tsx`](../src/app/App.tsx) line 103, `onOpenFeature={feature => setPage(feature)}`)
- **MatchView:** `compare.openHistory(data); setPage('compare')` — requires passing the compare result object

The cleanest path for the Phase 3 card is to emit `window.dispatchEvent(new CustomEvent('chopper-open-feature', {detail: {page, data}}))` from `Chatbot.tsx`, caught in `AssistWorkspace` and forwarded up via `onOpenFeature`.

---

## 5. WorkHub Project Creation and Document Jobs

### Create project

**Endpoint:** `POST /api/workhub/projects`  
**File:** [`backend/api/workhub.py`](../backend/api/workhub.py) line 84–85

```python
@router.post('/projects')
def create(request, payload): return workspace.create(actor(request), payload)
```

**Payload** (inferred from `SimpleProjectDialog.tsx` and `workspace.create`):

```json
{
  "name": "MachineX Project",
  "customer": "Acme Ltd",
  "machine_department": "Spinning",
  "template_id": null
}
```

### Queue a document job (FRD, MoM, flowchart, etc.)

**Endpoint:** `POST /api/workhub/projects/{project_id}/intelligence/jobs`  
**File:** [`backend/api/workhub_intelligence.py`](../backend/api/workhub_intelligence.py) line 59–60

```python
@router.post('/jobs')
def queue(project_id, payload, request):
    return jobs.enqueue(request.state.user, project_id, payload.get('kind'), payload.get('payload', {}))
```

**Payload** (`kind` examples):

| `kind`       | Purpose                              |
|-------------|--------------------------------------|
| `frd`       | FRD document draft                   |
| `mom`       | Minutes of meeting draft             |
| `flowchart` | Flowchart / infographic generation   |
| `q_generate`| Quality-controlled FRD (after MOM approve) |

**Response:** `{job_id, status, kind, ...}`

---

## 6. Role / Module Permission Map

**File:** [`src/shared/workspaceModules.ts`](../src/shared/workspaceModules.ts) lines 1–17

```ts
export const PAGE_MODULES = {
  home:       'workhub',
  validation: 'bytemap',
  plc:        'datainspect',
  compare:    'matchview',
  circuit:    'edesign',
  electrical: 'edesign',
  rules:      'logicscan',
  edesign:    'edesign',
  chatbot:    'assistant',
} as const;

export function visibleModules(user): WorkspaceModule[] {
  return user.role === 'admin'
    ? ALL_WORKSPACE_MODULES
    : (user.workspaceModules ?? ALL_WORKSPACE_MODULES);
}
```

**Consequence for the action layer:**  
Before offering or running a ByteMap action, check the user has `bytemap` module.  
Before offering or running a MatchView action, check the user has `matchview` module.  
Backend enforces `personal_account` dep on WorkHub routes; `require_session` on compare status.  
The action layer must enforce module access server-side, not only in the UI.

---

## 7. Existing Tests Relevant to the Command Layer

From `tests/` directory listing, the most relevant files:

| Test file | Coverage |
|-----------|---------|
| `tests/test_local_workflows.py` | Local validate / compare flows |
| `tests/test_compare_live_progress.py` | Compare session polling |
| `tests/test_workhub_workflow.py` | WorkHub job queue |
| `tests/test_chopper_agent.py` | Chopper reply pipeline |
| `tests/test_chopper_answer_workspace.py` | _assist routing |
| `tests/test_chopper_runtime_controls.py` | Early-return hooks |
| `tests/chopper_tasks_browser.py` | UI task flow (browser) |
| `tests/test_workhub_frd_workflow.py` | FRD job pipeline |
| `tests/test_workhub_mom_signoff.py` | MoM approve → FRD trigger |

**None of these test the new command-layer package** — `tests/test_chopper_actions.py` does not yet exist and must be created in Phase 1.

---

## 8. Existing New Files (created previous session, not yet registered)

| File | Status | Issue |
|------|--------|-------|
| `backend/api/chopper_tasks.py` | ✅ Syntax OK | Not registered in `backend/app.py` |
| `backend/api/chopper_guided_task.py` | ✅ Syntax OK | Not registered in `backend/app.py`; has `.padStart()` Python bug (see §9) |
| `src/features/assist/ChopperGuidedTask.tsx` | Created | Not wired into `ChopperQuickHelp.tsx` |

---

## 9. Known Bug: `.padStart()` in `chopper_guided_task.py`

**File:** [`backend/api/chopper_guided_task.py`](../backend/api/chopper_guided_task.py)

The file uses JavaScript's `.padStart()` method in Python string formatting. The pattern
`str(i+1).padStart(3,'0') if False else str(i+1).zfill(3)` appears as a no-op today,
but calling `.padStart()` on a Python `str` will raise `AttributeError` at import time
if the `if False` branch is ever removed or the guard fails.

**Fix:** Replace every occurrence of `.padStart(...)` with `.zfill(3)` before the file is registered.

---

## 10. Proposed Tool Functions for Phase 1+

### `backend/core/chopper_actions/`

```
__init__.py
registry.py        — ActionEntry dataclass; register_action(); get_action(id)
router.py          — reply_if_action(payload) → dict | None
audit.py           — write_audit(user_id, action_id, input_files, result_id)
actions/
  bytecheck.py     — run_bytecheck(slots, user) → result; summarize_validation(result) → chat card
  matchview.py     — run_matchview(slots, user) → {sid}; summarize_compare(result) → chat card
```

### Tool function signatures

```python
# registry.py
@dataclass
class ActionEntry:
    id: str
    title: str
    window: str                      # 'bytemap' | 'matchview' | 'workhub'
    patterns: list[re.Pattern]       # command-verb regexes
    required_slots: list[str]        # slot keys that must be filled
    optional_slots: list[str]
    permissions: list[str]           # module ids, e.g. ['bytemap']
    run: Callable                    # (slots, user) → result dict
    summarize: Callable              # (result) → chat card dict

# router.py
def reply_if_action(payload: dict) -> dict | None:
    """
    Returns None  → question phrase, old Chopper path runs.
    Returns dict  → one of:
      {type: 'action-question', actionId, question, slot, choices}
      {type: 'action-plan',    actionId, title, description, planHash, slotSummary}
      {type: 'action-summary', actionId, counts, topIssues, deepLink}
    State (pending slots, planHash) travels in the payload['_actionState'] dict.
    """

# actions/bytecheck.py
def run_bytecheck(slots: dict, user: dict) -> dict:
    """Calls _execute_project() from backend.api.validation and returns raw result."""

def summarize_validation(result: dict) -> dict:
    """
    Computes: total counts, top 5 fails, top 3 warnings.
    All values from result dict — never from the model.
    Returns: {counts, topFails, topWarnings, sessionId, deepLink}
    """

# actions/matchview.py
def start_matchview(slots: dict, user: dict) -> str:
    """Starts compare thread, returns sessionId."""

def poll_matchview(sid: str) -> dict:
    """Polls COMPARE_JOBS[sid] until complete or error."""

def summarize_compare(result: dict) -> dict:
    """
    Computes: summary counts, per-category breakdown, top N changed paths.
    All values from result dict — never from the model.
    Returns: {summary, byCategory, topChanged, sessionId, deepLink}
    """
```

---

## 11. Dependency / Environment Check

All packages needed for Phase 1 (`backend/core/chopper_actions/`) are already available in `.venv`:

| Package | Required | Status |
|---------|---------|--------|
| `fastapi` | router, HTTPException | ✅ Present |
| `pydantic` | slot validation | ✅ Present (v2 via langchain-core) |
| `re` (stdlib) | pattern matching | ✅ stdlib |
| `hashlib` (stdlib) | plan hash | ✅ stdlib |
| `threading` (stdlib) | compare polling | ✅ stdlib |
| `backend.api.validation._execute_project` | bytecheck action | ✅ importable (additive) |
| `backend.api.comparison._compare_worker`, `COMPARE_JOBS` | matchview action | ✅ importable |
| `backend.core.runtime` (BASE, WORK, log, etc.) | shared infra | ✅ Present |

**No new packages needed for Phase 1.**

---

## 12. What Could NOT Be Verified

| Item | Reason |
|------|--------|
| Exact `counts` key names in `validation_results.json` | Engine runs only with a real project; shape inferred from `_execute_project` return and existing test fixtures |
| Exact `diffs[].category` values in `compare_results.json` | Compare engine runs only with two real projects; shape inferred from `_compare_project` logging and `comparison_knowledge()` usage |
| `workspace.create()` payload schema | `backend/core/workhub_workspace.py` not read in this phase; inferred from `SimpleProjectDialog.tsx` draft keys |
| `ChopperGuidedTask.tsx` CSS class list | Not verified against rendered UI; CSS file not yet created |

---

## 13. Open Questions (answered by user, Phase 0 approved)

1. **`USOPP_CHOPPER_ACTIONS` default:** Admin-only until Phase 5 sign-off.
2. **State transport:** `_actionState` dict travels inside the existing `payload` dict (no new DB table for MVP).
3. **Plan hash algorithm:** `hashlib.sha256` over canonical JSON of slots + action ID + timestamp-epoch-minute.
4. **Deep-link mechanism for summary card:** Dispatch `window.dispatchEvent(new CustomEvent('chopper-open-feature', {detail: {page, data}}))` from `Chatbot.tsx`; `AssistWorkspace` catches it and calls `onOpenFeature`.

---

## 14. Files Created / Changed in Phase 0

| Action | File |
|--------|------|
| **Created** | `docs/CHOPPER_COMMAND_LAYER_DISCOVERY.md` (this file) |
| No other files changed | — |

Previous-session files verified:
- `backend/api/chopper_tasks.py` — syntax OK (`py_compile`)
- `backend/api/chopper_guided_task.py` — syntax OK (`py_compile`); `.padStart()` bug identified, fix pending Phase 1
- `src/features/assist/ChopperGuidedTask.tsx` — present, not wired
