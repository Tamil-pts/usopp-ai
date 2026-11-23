# Chopper Command Layer — Operator & Developer Guide

## 1. Overview
The **Chopper Command Layer** adds an actionable execution capability to the top-bar Chopper assistant in uSOPp.ai without modifying the legacy Chopper conversational pipelines.

Unlike open-ended generation, the Command Layer operates on a deterministic principle:
> **Code finds the facts and computes results; the model only provides human-readable explanations; the engineer confirms before any execution occurs.**

---

## 2. Supported Actions & Commands

| Action ID | Name | Trigger Verbs / Patterns | Window Module | Description |
|-----------|------|--------------------------|---------------|-------------|
| `bytecheck` | **ByteMap Validation** | `run bytecheck`, `validate this project`, `check plc project`, `execute validation` | `bytemap` | Validates an Automation Studio project against rule sets. Shows pass/fail/warn counters and top issues with `file:line` locations. |
| `matchview` | **MatchView Comparison** | `run matchview`, `compare base project and developed project`, `start comparison`, `diff between base and new` | `matchview` | Compares base and developed PLC projects. Shows added/removed/modified counts, category breakdown, and top changed files with a one-click **Swap** option. |
| `project_pack` | **Project Pack Creation** | `create a project`, `new project pack`, `setup project pack`, `build project with frd` | `workhub` | Creates a WorkHub project and drafts FRD, Flowchart, and Kickoff MoM in draft status for engineer review. |

---

## 3. Interaction Lifecycle

```
[User Message]
       │
       ▼
[Question Filter] ──(Looks like a question?)──► [Old Chopper Pipeline (Unchanged)]
       │ (No, command verb matched)
       ▼
[Module & Permission Check] ──(Denied)──► [Access Error Card]
       │ (Permitted)
       ▼
[Slot Collection Flow] ◄───► [Question Card: Slot Input / Choices / Skip]
       │ (All required slots filled)
       ▼
[HMAC Server Signing] ──► [Action Plan Card with 'Confirm', 'Cancel', 'Swap']
       │
  (User clicks 'Confirm' / 'Cancel')
       │
       ▼
[Server Plan Verification] ──► HMAC valid? Not expired? Not already used? Paths safe?
       │ (Verified)
       ▼
[Execution & Computed Summary] ──► [Result Summary Card + Deep Link Button]
```

### Plan Security Model
1. **Stateless HMAC-SHA256 Signing:** When all slots are collected, the backend signs a canonical payload of `(user_id, action_id, slots, expiry)`.
2. **15-Minute Expiry (TTL):** Plans automatically expire after 900 seconds.
3. **Single-Use Replay Protection:** When a plan is confirmed, its hash is recorded in an in-memory cache until expiry. Re-submitting or replaying the same plan is rejected.
4. **Server-Side Path Validation:** Client-supplied paths are never trusted. All project folders are re-validated through `_local_path` and `locate_root`.
5. **Tamper Prevention:** Modifying any slot value in the client payload breaks the HMAC signature and triggers a security warning in the server log.

---

## 4. Administration & Pilot Rollout

### Feature Flag
The Command Layer is gated by the environment variable:
```bash
USOPP_CHOPPER_ACTIONS=1
```
If this variable is not set, all messages fall through directly to the standard Chopper assistant.

### Pilot User Configuration
By default, **only Administrators** have access to the Command Layer. Administrators can grant access to specific users (e.g. Lead Engineers) or specific roles via:

**API Endpoints:**
- `GET /api/admin/settings/chopper-actions` — View pilot list
- `PUT /api/admin/settings/chopper-actions` — Save pilot list:
```json
{
  "pilot_users": ["lead_dev", "qa_lead"],
  "pilot_roles": ["lead_engineer"]
}
```
Configuration is stored persistently at:
`BASE/.usopp_chopper2/chopper_actions_config.json`

---

## 5. Audit Logging
Every action execution is recorded in an append-only daily audit log:
`BASE/logs/chopper_actions_YYYYMMDD.log`

Each line contains a JSON record:
```json
{
  "ts": "2026-11-23T15:20:00Z",
  "user": "alice",
  "action": "bytecheck",
  "input": {"project_path": "C:/Projects/Machine_A", "machine_department": "Spinning"},
  "result_id": "4a71b29e...",
  "status": "ok"
}
```
*Note: Audit logs never store raw project code or proprietary file contents; only paths and execution metrics are logged.*

---

## 6. Rollback Procedure
If any unexpected behavior occurs:
1. Set `USOPP_CHOPPER_ACTIONS=0` or remove the environment variable.
2. Restart the backend process.
3. The system immediately reverts to standard Chopper behavior with zero side effects on existing features.
