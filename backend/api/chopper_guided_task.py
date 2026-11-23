"""
Chopper Guided Task â€” backend endpoint.

Chopper asks the user one question at a time, collects the answers,
then returns a "pre-fill brief" that the frontend passes to the
WorkHub task dialog (project, FRD, MoM, task, etc.) to auto-populate fields.

No model is required: the question/answer flow is deterministic (config-driven).
When the user enables Chopper 2.0, the brief can optionally be refined by an LLM.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Chopper Guided Task"])

# ---------------------------------------------------------------------------
# Task question scripts
# Each task has an ordered list of questions.
# 'key' maps the answer into the brief dict (matches WorkHub draft fields).
# 'optional' tasks can be skipped by answering "skip" or leaving blank.
# ---------------------------------------------------------------------------

TASK_SCRIPTS: dict[str, dict] = {
    "project": {
        "label": "Create Project",
        "destination": "project",
        "intro": "I'll help you create a new project. Answer a few quick questions and I'll fill in the form for you.",
        "questions": [
            {"key": "title",           "q": "What is the project name?",                       "placeholder": "e.g. Ring Frame PLC Upgrade"},
            {"key": "customer",        "q": "Who is the customer?",                             "placeholder": "e.g. LMW / Rieter / Internal"},
            {"key": "kind",            "q": "What type of project is this?",                    "placeholder": "e.g. PLC Upgrade / New Machine / Electrical Design"},
            {"key": "objective",       "q": "What is the main objective? (1â€“3 sentences)",      "placeholder": "Describe the scope and expected outcome"},
            {"key": "requirements",    "q": "List the top requirements, one per line.",          "placeholder": "e.g.\nData collection via SpinConnect\nHMI alarm screen\nFAT documentation", "multiline": True},
            {"key": "due",             "q": "What is the target delivery date? (optional)",     "placeholder": "e.g. 2026-03-31 or leave blank", "optional": True},
            {"key": "customerReference","q": "Customer reference / PO number? (optional)",      "placeholder": "e.g. LMW-2026-01 or leave blank", "optional": True},
        ],
    },
    "frd": {
        "label": "Create FRD",
        "destination": "frd",
        "intro": "I'll help you create a Functional Requirements Document. Answer a few questions and I'll prefill the FRD for you.",
        "questions": [
            {"key": "title",          "q": "Project name for this FRD?",                       "placeholder": "e.g. Ring Frame PLC Upgrade"},
            {"key": "purpose",        "q": "What is the purpose / scope of this document?",    "placeholder": "e.g. Document functional requirements for the upgraded PLC program"},
            {"key": "requirements",   "q": "List the functional requirements, one per line.",   "placeholder": "REQ-001: SpinConnect data collection\nREQ-002: HMI alarm screen\nREQ-003: FAT documentation", "multiline": True},
            {"key": "acceptance",     "q": "List acceptance criteria, one per line. (optional)","placeholder": "e.g. All alarms visible on HMI\nFAT passed without open defects", "multiline": True, "optional": True},
            {"key": "background",     "q": "Any background or context? (optional)",            "placeholder": "Existing machine version, known issues, reference documents", "optional": True},
        ],
    },
    "mom": {
        "label": "Create Meeting Minutes",
        "destination": "mom",
        "intro": "I'll help you draft Minutes of Meeting. Answer a few quick questions.",
        "questions": [
            {"key": "title",        "q": "Meeting title?",                                    "placeholder": "e.g. Ring Frame PLC Kick-off Meeting"},
            {"key": "customer",     "q": "Customer / attendee organisation?",                 "placeholder": "e.g. LMW Ltd"},
            {"key": "attendees",    "q": "List attendees, one per line. (optional)",           "placeholder": "e.g. John (LMW)\nAnil (uSOPp)\nRaj (Electrical)", "multiline": True, "optional": True},
            {"key": "agenda",       "q": "List agenda items or discussion topics, one per line.","placeholder": "e.g. Project scope review\nTimeline agreement\nAction items", "multiline": True},
            {"key": "decisions",    "q": "Key decisions made? (optional)",                    "placeholder": "e.g. FAT planned for March 2026\nElectrical team to provide wiring diagram", "optional": True},
            {"key": "actions",      "q": "Action items and owners? (optional)",               "placeholder": "e.g. John: Share BOM by 2026-01-10\nAnil: Send PLC draft by 2026-01-15", "optional": True},
        ],
    },
    "task": {
        "label": "Create Task / Work Item",
        "destination": "task",
        "intro": "I'll help you create a task. Answer a few quick questions.",
        "questions": [
            {"key": "title",       "q": "Task title?",                                      "placeholder": "e.g. Update HMI alarm screen for Ring Frame"},
            {"key": "description", "q": "Describe the task. What needs to be done?",         "placeholder": "e.g. Update the alarm list on the HMI to match the new PLC variables"},
            {"key": "objective",   "q": "What is the expected outcome / acceptance?",        "placeholder": "e.g. All alarms visible and correctly labelled"},
            {"key": "due",         "q": "Target completion date? (optional)",               "placeholder": "e.g. 2026-02-28 or leave blank", "optional": True},
        ],
    },
    "fat": {
        "label": "Create FAT Document",
        "destination": "fat",
        "intro": "I'll help you set up a Factory Acceptance Test document.",
        "questions": [
            {"key": "title",       "q": "Project / machine name for this FAT?",              "placeholder": "e.g. Ring Frame PLC v2.1"},
            {"key": "customer",    "q": "Customer name?",                                    "placeholder": "e.g. LMW Ltd"},
            {"key": "objective",   "q": "FAT scope â€” what will be tested?",                  "placeholder": "e.g. Full functional test of SpinConnect data collection and HMI alarms"},
            {"key": "requirements","q": "List the test items / requirements, one per line.",  "placeholder": "e.g. Alarm screen test\nData collection accuracy\nManual/Auto mode switch", "multiline": True},
        ],
    },
    "closure": {
        "label": "Create Closure Report",
        "destination": "closure",
        "intro": "I'll help you create a project closure report.",
        "questions": [
            {"key": "title",          "q": "Project name?",                                      "placeholder": "e.g. Ring Frame PLC Upgrade"},
            {"key": "customer",       "q": "Customer?",                                          "placeholder": "e.g. LMW Ltd"},
            {"key": "objective",      "q": "What was delivered? (brief summary)",                "placeholder": "e.g. Upgraded PLC program, new HMI screens, FAT passed"},
            {"key": "requirements",   "q": "List any outstanding items or known issues. (optional)","placeholder": "Leave blank if none", "optional": True, "multiline": True},
        ],
    },
    "test": {
        "label": "Create Validation Report",
        "destination": "test",
        "intro": "I'll help you create a validation / test report.",
        "questions": [
            {"key": "title",       "q": "Project / machine being validated?",                "placeholder": "e.g. Ring Frame PLC v2.1"},
            {"key": "customer",    "q": "Customer?",                                         "placeholder": "e.g. LMW Ltd"},
            {"key": "objective",   "q": "What is the validation scope?",                     "placeholder": "e.g. Verify SpinConnect data collection against metadata workbook"},
            {"key": "requirements","q": "List test cases or validation checks, one per line.","placeholder": "e.g. GC-01 data matches metadata\nAlarm state validated\nAuto mode cycle test", "multiline": True},
        ],
    },
}


@router.get("/api/assist/guided-task/scripts")
def list_scripts():
    """Return available task scripts for the frontend task picker."""
    return JSONResponse([
        {"id": task_id, "label": script["label"], "destination": script["destination"], "intro": script["intro"]}
        for task_id, script in TASK_SCRIPTS.items()
    ])


@router.get("/api/assist/guided-task/{task_id}")
def get_script(task_id: str):
    """Return the full question script for a task."""
    script = TASK_SCRIPTS.get(task_id)
    if not script:
        raise HTTPException(404, f"No guided task script for '{task_id}'. Available: {', '.join(TASK_SCRIPTS)}")
    return JSONResponse(script)


@router.post("/api/assist/guided-task/{task_id}/brief")
def build_brief(task_id: str, payload: dict):
    """
    Given collected answers {key: answer_text}, build and return the
    pre-fill brief dict that the frontend passes to startAssistantTask().
    The brief is task-specific and maps directly to WorkHub draft fields.

    Example payload: {"title": "Ring Frame", "customer": "LMW", "requirements": "REQ-001...\nREQ-002..."}
    """
    script = TASK_SCRIPTS.get(task_id)
    if not script:
        raise HTTPException(404, f"No guided task script for '{task_id}'.")

    answers: dict = payload.get("answers") or {}

    # Build a human-readable brief string Chopper passes as the task prompt
    brief_lines: list[str] = []
    for q in script["questions"]:
        key = q["key"]
        value = str(answers.get(key) or "").strip()
        if not value and not q.get("optional"):
            # Silently continue â€” frontend validates required fields
            continue
        if value:
            brief_lines.append(f"{key.replace('_', ' ').title()}: {value}")

    brief_text = "\n".join(brief_lines)

    # Build the structured prefill dict (matches SimpleProjectDialog Draft shape)
    prefill: dict = {}
    for q in script["questions"]:
        key = q["key"]
        value = str(answers.get(key) or "").strip()
        if not value:
            continue
        if key == "requirements":
            # Split into requirementItems list
            prefill["requirements"] = value
            items = [line.strip() for line in value.splitlines() if line.strip()]
            prefill["requirementItems"] = [
                {"id": f"REQ-{str(i+1).zfill(3)}", "description": item, "category": "", "priority": "medium"}
                for i, item in enumerate(items)
            ]
        elif key == "acceptance":
            prefill["acceptance"] = value
            prefill["acceptanceItems"] = [line.strip() for line in value.splitlines() if line.strip()]
        elif key == "attendees":
            prefill["attendees"] = value
        elif key == "agenda":
            prefill["agenda"] = value
        elif key == "decisions":
            prefill["decisions"] = value
        elif key == "actions":
            prefill["actions"] = value
        elif key == "description":
            prefill["objective"] = value  # maps task description â†’ objective
        else:
            prefill[key] = value

    return JSONResponse({
        "taskId": task_id,
        "destination": script["destination"],
        "brief": brief_text,
        "prefill": prefill,
    })
