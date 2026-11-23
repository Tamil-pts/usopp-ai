"""
Chopper quick-task endpoints.

Each endpoint accepts files directly (browser-upload), runs the
appropriate engine, and returns a compact chat-ready summary so
Chopper can display fails/warnings inline without opening a full window.
The session ID is returned so the UI can deep-link to ByteMap or MatchView.
"""
from __future__ import annotations
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.core.runtime import (
    BASE, WORK, ENGINE, COMPARE_ENGINE, log,
    run_engine, engine_command, engine_creation_flags,
    stage_project, start_project_upload, append_project_upload,
    finish_project_upload, project_kb_file, locate_root, find_json,
)

router = APIRouter(tags=["Chopper Tasks"])

# ---------------------------------------------------------------------------
# Task job store (in-memory, keyed by task_id)
# ---------------------------------------------------------------------------
TASK_JOBS: dict = {}
TASK_LOCK = threading.Lock()


def _new_task(kind: str) -> str:
    task_id = uuid.uuid4().hex
    with TASK_LOCK:
        TASK_JOBS[task_id] = {"status": "running", "kind": kind, "startedAt": time.time()}
    return task_id


def _finish_task(task_id: str, result: dict):
    with TASK_LOCK:
        if task_id in TASK_JOBS:
            TASK_JOBS[task_id].update(status="complete", **result)


def _fail_task(task_id: str, error: str):
    with TASK_LOCK:
        if task_id in TASK_JOBS:
            TASK_JOBS[task_id].update(status="error", error=error)


@router.get("/api/assist/task/{task_id}")
def get_task(task_id: str):
    with TASK_LOCK:
        job = TASK_JOBS.get(task_id)
    if not job:
        raise HTTPException(404, "Task not found.")
    return JSONResponse(job)


# ---------------------------------------------------------------------------
# ByteCheck summary helpers
# ---------------------------------------------------------------------------

def _bytecheck_summary(result: dict) -> dict:
    """
    Distil a validation_results.json into a small chat-ready summary.
    Returns: {pass, fail, warning, error, groups, score, snippet, sessionId}
    """
    counts: dict = result.get("counts") or {}
    score = result.get("score")
    session_id = result.get("sessionId", "")
    project_name = result.get("projectName", "")

    fail_count = counts.get("fail", 0)
    warn_count = counts.get("warning", 0)
    pass_count = counts.get("pass", 0)
    error_count = counts.get("error", 0)
    groups = counts.get("groups", 0)

    # Collect the first few failures for the chat snippet
    snippets: list[str] = []
    for group in (result.get("results") or [])[:60]:
        gcode = group.get("group_code", "")
        for issue in (group.get("issues") or [])[:3]:
            sev = str(issue.get("severity") or "").upper()
            if sev in ("FAIL", "ERROR", "WARNING"):
                param = issue.get("parameter") or issue.get("offset") or ""
                msg = issue.get("message") or issue.get("check") or ""
                snippets.append(f"- **GC {gcode}** {param}: {msg[:120]}")
            if len(snippets) >= 8:
                break
        if len(snippets) >= 8:
            break

    if snippets:
        snippet_text = "\n".join(snippets[:8])
        if fail_count + warn_count > len(snippets):
            snippet_text += f"\n- … and {fail_count + warn_count - len(snippets)} more issue(s)."
    else:
        snippet_text = "No issues found in the first check."

    return {
        "projectName": project_name,
        "sessionId": session_id,
        "pass": pass_count,
        "fail": fail_count,
        "warning": warn_count,
        "error": error_count,
        "groups": groups,
        "score": score,
        "snippet": snippet_text,
    }


# ---------------------------------------------------------------------------
# ByteCheck task endpoint
# ---------------------------------------------------------------------------

@router.post("/api/assist/task/bytecheck")
async def chopper_bytecheck_task(
    project_files: Optional[List[UploadFile]] = File(None),
    metadata: Optional[UploadFile] = File(None),
    project_name: str = Form(""),
    bool_metadata_mode: str = Form("BOOL"),
    machine_department: str = Form("All"),
):
    """
    Upload a project (folder of files) + optional metadata workbook.
    Runs the ByteCheck (validation) engine synchronously (runs in threadpool)
    and returns a chat-ready summary with fail/warning counts and snippets.
    The sessionId can be used to open the full ByteMap window.
    """
    if not project_files:
        raise HTTPException(400, "Upload at least one project file.")

    # Stage project files using the existing upload pipeline
    try:
        sid, root = await stage_project(project_files, project_name)
    except Exception as exc:
        raise HTTPException(400, f"Project upload failed: {exc}") from exc

    work = WORK / sid

    # Store metadata workbook if provided
    meta_path: Optional[Path] = None
    if metadata and metadata.filename:
        suffix = (metadata.filename or "").rsplit(".", 1)[-1].lower()
        if suffix not in {"xlsx", "xls"}:
            raise HTTPException(400, "Metadata must be an .xlsx or .xls workbook.")
        meta_path = work / f"uploaded_metadata.{suffix}"
        meta_path.write_bytes(await metadata.read())

    def _run_bytecheck():
        from backend.core.identifiers import run_identity
        run_identity(work)
        json_name = "validation_results.json"
        out_excel = work / f"bytecheck_report.xlsx"
        args = [
            str(ENGINE),
            "--project", str(root),
            "--output-excel", str(out_excel),
            "--output-json", str(work / json_name),
            "--project-kb", str(project_kb_file(project_name or root.name)),
            "--machine-department", machine_department or "All",
            "--bool-metadata-mode", bool_metadata_mode or "BOOL",
        ]
        if meta_path:
            args += ["--metadata", str(meta_path)]
        try:
            run_engine(args, BASE)
        except RuntimeError as exc:
            raise HTTPException(500, str(exc)) from exc
        result = find_json(work, json_name)
        result["sessionId"] = sid
        return result

    try:
        raw = await run_in_threadpool(_run_bytecheck)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("CHOPPER_BYTECHECK_TASK_ERROR session=%s", sid)
        raise HTTPException(500, f"ByteCheck failed: {exc}") from exc

    summary = _bytecheck_summary(raw)
    return JSONResponse({"taskKind": "bytecheck", "summary": summary})


# ---------------------------------------------------------------------------
# MatchView summary helpers
# ---------------------------------------------------------------------------

def _matchview_summary(result: dict) -> dict:
    """
    Distil a compare_results.json into a compact chat-ready summary.
    Returns: {baseName, newName, summary{added,removed,modified,unchanged},
              categories, topChanges, sessionId}
    """
    session_id = result.get("sessionId", "")
    base_name = result.get("baseName") or result.get("projectName", "Base")
    new_name = result.get("newName") or "Developed"
    summary_counts: dict = result.get("summary") or {}
    categories: dict = result.get("categories") or {}

    # Pick top changed files for snippet
    diffs: list = result.get("diffs") or []
    modified = [d for d in diffs if d.get("status") in ("modified", "added", "removed")]
    top: list[str] = []
    for diff in modified[:8]:
        status = str(diff.get("status") or "").capitalize()
        path = diff.get("path") or diff.get("base_relative_path") or ""
        cat = str(diff.get("category") or "").capitalize()
        hunks = len(diff.get("hunks") or [])
        top.append(f"- **{status}** `{Path(path).name}` ({cat}{', '+str(hunks)+' hunk(s)' if hunks else ''})")

    if modified and len(modified) > 8:
        top.append(f"- … and {len(modified) - 8} more changed file(s).")

    snippet_text = "\n".join(top) if top else "No differences detected."

    return {
        "baseName": base_name,
        "newName": new_name,
        "sessionId": session_id,
        "added": summary_counts.get("added", 0),
        "removed": summary_counts.get("removed", 0),
        "modified": summary_counts.get("modified", 0),
        "unchanged": summary_counts.get("unchanged", 0),
        "categories": categories,
        "snippet": snippet_text,
    }


# ---------------------------------------------------------------------------
# MatchView task endpoint
# ---------------------------------------------------------------------------

@router.post("/api/assist/task/matchview")
async def chopper_matchview_task(
    base_files: Optional[List[UploadFile]] = File(None),
    new_files: Optional[List[UploadFile]] = File(None),
    base_name: str = Form(""),
    new_name: str = Form(""),
):
    """
    Upload Base and Developed project folders.
    Runs MatchView comparison engine and returns a chat-ready summary
    with added/removed/modified counts and top changed files.
    The sessionId can be used to open the full MatchView window.
    """
    if not base_files or not new_files:
        raise HTTPException(400, "Upload both a Base project and a Developed project.")

    import subprocess

    try:
        base_sid, base_root = await stage_project(base_files, base_name or "Base")
        new_sid, new_root = await stage_project(new_files, new_name or "Developed")
    except Exception as exc:
        raise HTTPException(400, f"Project upload failed: {exc}") from exc

    # Use base session as the compare session
    from backend.core.runtime import COMPARE_JOBS, COMPARE_JOBS_LOCK
    compare_sid = uuid.uuid4().hex
    work = WORK / compare_sid
    work.mkdir(parents=True, exist_ok=True)
    from backend.core.access import claim_resource
    claim_resource(work)

    def _run_matchview():
        out = work / "compare_results.json"
        b_root = locate_root(base_root)
        n_root = locate_root(new_root)
        args = engine_command(COMPARE_ENGINE,
                              "--base", str(b_root),
                              "--new", str(n_root),
                              "--output", str(out))
        try:
            proc = subprocess.run(
                args, cwd=str(BASE), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
                creationflags=engine_creation_flags(),
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or "Compare engine failed").strip()[-8000:])
            if not out.exists():
                raise RuntimeError("Compare engine finished but produced no result file.")
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("MatchView comparison timed out (600 s).") from exc

        result = json.loads(out.read_text(encoding="utf-8"))
        result["sessionId"] = compare_sid
        return result

    try:
        raw = await run_in_threadpool(_run_matchview)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("CHOPPER_MATCHVIEW_TASK_ERROR session=%s", compare_sid)
        raise HTTPException(500, f"MatchView comparison failed: {exc}") from exc

    summary = _matchview_summary(raw)
    return JSONResponse({"taskKind": "matchview", "summary": summary})
