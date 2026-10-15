from __future__ import annotations

import base64
import re
from io import BytesIO
from backend.core.compare_screen_preview import screen_previews, preview_progress
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


DARK_BLUE = "#173b68"
BASE_COLOR = "#00c6b5"
DEVELOPED_COLOR = "#b5718f"
BASE_TINT = "#e8fbf8"
DEVELOPED_TINT = "#f8edf2"
MUTED = "#64748b"
CATEGORY_ORDER = (
    ("logic", "Logical View"),
    ("screen", "Screen View"),
    ("config", "Project View / Configuration"),
    ("hardware", "Hardware View"),
)


def report_progress(message):
    callback = preview_progress.get()
    if callback:
        callback(message)


def _relative_file(diff: dict, side: str) -> str:
    value = diff.get("base_relative_path" if side == "base" else "new_relative_path")
    if value:
        return str(value)
    return "Not present in Base project" if side == "base" else "Not present in Developed project"


def _line_text(value: Any) -> tuple[str, str]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[0]), str(value[1])
    return "", str(value)


def _display(value: Any, missing: str = "Not configured") -> str:
    if value is None:
        return "Not present"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value) or missing
    text = str(value).replace("â€”", "Not present").replace("\x00", "").strip()
    return text if text else missing


def _row(
    label: str,
    base: Any,
    developed: Any,
    *,
    group: str = "Details",
    base_ref: str = "",
    developed_ref: str = "",
    state: str | None = None,
) -> dict:
    if state is None:
        if base is None and developed is not None:
            state = "added"
        elif developed is None and base is not None:
            state = "removed"
        elif _display(base) != _display(developed):
            state = "modified"
        else:
            state = "unchanged"
    return {
        "label": str(label),
        "base": (str(base) if base is not None else "") if group == "PLC source" else _display(base),
        "developed": (str(developed) if developed is not None else "") if group == "PLC source" else _display(developed),
        "group": str(group),
        "base_ref": str(base_ref),
        "developed_ref": str(developed_ref),
        "state": state,
    }


def _property_group(name: str) -> str:
    key = name.casefold().replace(" ", "").replace("_", "")
    if 'bitmap' in key:
        return 'Bitmap / ' + ('Pressed' if 'pressed' in key else 'Released')
    if key in {"name", "id", "controltype", "class", "classid"}:
        return "Identity"
    if key in {"left", "top", "width", "height", "zorder", "x", "y", "position"}:
        return "Position"
    if "text" in key or "language" in key or "description" in key:
        return "Text Group"
    if "value" in key or "min" in key or "max" in key or "format" in key:
        return "Value"
    if "runtime" in key or "status" in key or "event" in key or "controlid" in key:
        return "Runtime"
    if "input" in key or "touch" in key or "confirm" in key or "cancel" in key:
        return "Input"
    if "complete" in key:
        return "Completion"
    if "lock" in key or "password" in key or "level" in key:
        return "Locking"
    if any(word in key for word in ("color", "font", "style", "border", "bitmap", "appearance")):
        return "Appearance"
    if key in {"station", "order", "objectname", "moduletype", "module", "channel", "direction", "address", "plctag"}:
        return "Hardware mapping"
    return "Other"


def _record_properties(record: dict | None) -> dict:
    if not record:
        return {}
    properties = record.get("properties")
    if isinstance(properties, dict):
        return dict(properties)
    return {
        key: value
        for key, value in record.items()
        if key not in {"name", "class", "class_id", "properties", "elements"}
    }


def _control_blocks(parsed: dict, category: str) -> list[dict]:
    blocks: list[dict] = []
    base_page = parsed.get("base_page_properties") or {}
    developed_page = parsed.get("new_page_properties") or {}
    page_keys = sorted(set(base_page) | set(developed_page), key=str.casefold)
    if page_keys:
        page_rows = [
            _row(key, base_page.get(key), developed_page.get(key), group=_property_group(key))
            for key in page_keys
        ]
        blocks.append(
            {
                "title": "Page properties",
                "subtitle": str(parsed.get("object_name") or parsed.get("entity_label") or "HMI object"),
                "status": "modified" if any(row.get("state") != "unchanged" for row in page_rows) else "unchanged",
                "rows": page_rows,
            }
        )

    # Text snippets are separate from indexed values in the UI, but must also
    # retain their complete binding/configuration evidence in every report.
    controls = list(parsed.get("controls") or [])
    # Page properties are already emitted once above; parsed HMI data also
    # carries a synthetic Screen properties record for the interactive view.
    controls = [control for control in controls if str(control.get("name") or "").casefold() != "screen properties"]
    for snippet in (parsed.get("text_group") or {}).get("snippets") or []:
        controls.append({**snippet, "name": "Text snippet: " + str(snippet.get("name") or "Unnamed")})
    for control in controls:
        if category=="hardware" and any(_support_module(_record_properties(control.get(side))) for side in ("base","new")): continue
        status = str(control.get("status") or "modified").casefold()
        base_record = control.get("base")
        developed_record = control.get("new")
        base_props = _record_properties(base_record)
        developed_props = _record_properties(developed_record)
        base_type = (base_record or {}).get("class_id") or (base_record or {}).get("class")
        developed_type = (developed_record or {}).get("class_id") or (developed_record or {}).get("class")
        if base_type is not None or developed_type is not None:
            type_label = "Control Type" if category == "screen" else "Record Type"
            base_props = {type_label: base_type, **base_props}
            developed_props = {type_label: developed_type, **developed_props}
        change_groups = {
            str(change.get("prop", change.get("field", ""))): str(change.get("group") or "")
            for change in control.get("changes") or []
        }
        keys = list(dict.fromkeys([*base_props.keys(), *developed_props.keys()]))
        rows = [
            _row(
                key,
                base_props.get(key) if base_record else None,
                developed_props.get(key) if developed_record else None,
                group=change_groups.get(key) or _property_group(key),
            )
            for key in keys
        ]
        if not rows:
            rows = [_row("Presence", "Available" if base_record else None, "Available" if developed_record else None)]
        blocks.append(
            {
                "title": str(control.get("name") or "Unnamed item"),
                "subtitle": str(control.get("class") or parsed.get("entity_label") or "Structured record"),
                "status": status,
                "rows": rows,
            }
        )
    return blocks


def _ladder_element(element: dict | None) -> str | None:
    if element is None:
        return None
    identity = element.get("name") or element.get("type") or "Unnamed"
    parts = [f"{element.get('kind', 'Element')}: {identity}"]
    if element.get("name") and element.get("type"):
        parts.append(f"Type {element['type']}")
    if element.get("position"):
        parts.append(f"Position {element['position']}")
    if element.get("branch"):
        parts.append(f"Branch {element['branch']}")
    if element.get("pins"):
        parts.append("Pins " + ", ".join(str(pin) for pin in element["pins"]))
    return " | ".join(parts)


def _ladder_blocks(parsed: dict) -> list[dict]:
    blocks: list[dict] = []
    for control in parsed.get("controls") or []:
        status = str(control.get("status") or "modified").casefold()
        base = control.get("base")
        developed = control.get("new")
        rows = [
            _row("Network index", (base or {}).get("index") if base else None, (developed or {}).get("index") if developed else None, group="Ladder network"),
            _row("Label", (base or {}).get("label") if base else None, (developed or {}).get("label") if developed else None, group="Ladder network"),
            _row("Comment", (base or {}).get("comment") if base else None, (developed or {}).get("comment") if developed else None, group="Ladder network"),
            _row("Commented", (base or {}).get("commented") if base else None, (developed or {}).get("commented") if developed else None, group="Ladder network"),
            _row("Rows", (base or {}).get("rows") if base else None, (developed or {}).get("rows") if developed else None, group="Ladder network"),
            _row("Logic summary", (base or {}).get("summary") if base else None, (developed or {}).get("summary") if developed else None, group="Ladder network"),
            _row("Network layout", (base or {}).get("layout") if base else None, (developed or {}).get("layout") if developed else None, group="Ladder network"),
        ]
        base_elements = (base or {}).get("elements") or []
        developed_elements = (developed or {}).get("elements") or []
        for index in range(max(len(base_elements), len(developed_elements))):
            base_element = base_elements[index] if index < len(base_elements) else None
            developed_element = developed_elements[index] if index < len(developed_elements) else None
            rows.append(_row(f"Element {index + 1}", _ladder_element(base_element), _ladder_element(developed_element), group="Contacts, coils and functions"))
        blocks.append(
            {
                "title": str(control.get("name") or "Ladder network"),
                "subtitle": "Structured ladder logic",
                "status": status,
                "rows": rows,
            }
        )
    return blocks


def _logic_blocks(diff: dict) -> list[dict]:
    if diff.get('source_rows'):
        rows=[_row('Source line',r.get('base'),r.get('new'),group='PLC source',
                   base_ref=f"L{r['base_line']}" if r.get('base_line') else '',
                   developed_ref=f"L{r['new_line']}" if r.get('new_line') else '',state=r['status']) for r in diff['source_rows']]
        return [{'title':'Changed source lines','subtitle':'Whitespace-only changes ignored','status':diff.get('status','unchanged'),'rows':rows}]
    blocks: list[dict] = []
    for number, hunk in enumerate(diff.get("hunks") or [], start=1):
        rows = []
        for source in hunk.get("lines") or []:
            kind = str(source.get("t") or "ctx")
            text = source.get("text", "")
            base_value = text if kind in {"ctx", "del"} else None
            developed_value = text if kind in {"ctx", "add"} else None
            rows.append(
                _row(
                    "Source line",
                    base_value,
                    developed_value,
                    group="PLC source",
                    base_ref=f"L{source.get('bl')}" if source.get("bl") is not None else "",
                    developed_ref=f"L{source.get('nl')}" if source.get("nl") is not None else "",
                    state="removed" if kind == "del" else "added" if kind == "add" else "unchanged",
                )
            )
        blocks.append(
            {
                "title": f"Difference {number}",
                "subtitle": f"Base line {hunk.get('base_start', '—')} | Developed line {hunk.get('new_start', '—')}",
                "status": "modified",
                "rows": rows,
            }
        )
    if blocks:
        return blocks

    rows = []
    for value in diff.get("removed_lines") or []:
        line_number, text = _line_text(value)
        rows.append(_row("Source line", text, None, group="PLC source", base_ref=f"L{line_number}" if line_number else "", state="removed"))
    for value in diff.get("added_lines") or []:
        line_number, text = _line_text(value)
        rows.append(_row("Source line", None, text, group="PLC source", developed_ref=f"L{line_number}" if line_number else "", state="added"))
    if diff.get("diff_note"):
        rows.insert(0, _row("Comparison note", diff["diff_note"], diff["diff_note"], group="Report note", state="unchanged"))
    return [
        {
            "title": "Source changes",
            "subtitle": "Line-numbered PLC logic",
            "status": str(diff.get("status") or "modified"),
            "rows": rows or [_row("Result", "No changed lines recorded", "No changed lines recorded")],
        }
    ]


def _all_blocks_for_diff(diff: dict) -> list[dict]:
    if diff.get("parsed_ladder"):
        blocks = _ladder_blocks(diff["parsed_ladder"])
        if blocks:
            return blocks
    if diff.get("category")=="logic" and diff.get("source_rows"): return _logic_blocks(diff)
    category = str(diff.get("category") or "config")
    parsed = diff.get("parsed_screen") or diff.get("parsed_hardware")
    if parsed:
        blocks = _control_blocks(parsed, category)
        if blocks:
            return blocks
    if category in {"logic", "config"}:
        return _logic_blocks(diff)
    return [
        {
            "title": "Structured comparison summary",
            "subtitle": "The engineering object changed but no readable structured records were returned.",
            "status": str(diff.get("status") or "modified"),
            "rows": [
                _row("File", _relative_file(diff, "base"), _relative_file(diff, "developed"),state=diff.get('status','modified')),
                _row("Change status", diff.get("status"), diff.get("status")),
            ],
        }
    ]


def split_change_lines(diff: dict, limit: int = 120) -> tuple[list[str], list[str]]:
    """Compatibility helper returning structured report rows as readable text."""
    base_lines: list[str] = []
    developed_lines: list[str] = []
    for block in _blocks_for_diff(diff):
        title = f"{block['title']} — {block.get('subtitle', '')}".strip(" —")
        base_lines.append(title)
        developed_lines.append(title)
        for row in block.get("rows") or []:
            base_label = row.get("base_ref") or row.get("label")
            developed_label = row.get("developed_ref") or row.get("label")
            base_lines.append(f"{base_label}: {row.get('base', '')}")
            developed_lines.append(f"{developed_label}: {row.get('developed', '')}")
    return base_lines[:limit], developed_lines[:limit]


def change_lines(diff: dict, limit: int = 120) -> list[str]:
    base, developed = split_change_lines(diff, limit)
    return ["BASE PROJECT", *base, "DEVELOPED PROJECT", *developed]


def _summary_values(result: dict) -> tuple[str, str, dict]:
    return (
        str(result.get("baseName", "Base")),
        str(result.get("newName", "Developed")),
        result.get("summary") or {},
    )


def _identity_rows(result: dict) -> list[dict]:
    projects = result.get("projects") or {}
    base = projects.get("base") or (result.get("knowledge") or {}).get("base") or {}
    developed = projects.get("developed") or (result.get("knowledge") or {}).get("developed") or {}
    fields = (
        ("Automation Studio", "automation_studio_version"),
        ("Active configuration", "active_configuration"),
        ("PLC type", "plc_type"),
        ("Screen folder", "active_hmi"),
        ("Configured HMI objects", "configured_hmi_objects"),
        ("Available screen folders", "screen_folders"),
    )
    return [_row(label, base.get(key), developed.get(key), group="Project identity") for label, key in fields]


def _knowledge_value(record: dict, fields: tuple[tuple[str, str], ...]) -> str:
    lines = []
    for label, key in fields:
        value = record.get(key)
        if value not in (None, "", []):
            lines.append(f"{label}: {_display(value)}")
    return "\n".join(lines) or "Available"


def _record_map(records: list[dict], key_fields: tuple[str, ...] = ("name",)) -> dict[str, dict]:
    mapped: dict[str, dict] = {}
    for index, record in enumerate(records or []):
        key = next((str(record.get(field)) for field in key_fields if record.get(field) not in (None, "")), f"Record {index + 1}")
        mapped[key] = record
    return mapped


def _aligned_record_rows(
    base_records: list[dict],
    developed_records: list[dict],
    fields: tuple[tuple[str, str], ...],
    *,
    group: str,
    key_fields: tuple[str, ...] = ("name",),
) -> list[dict]:
    base_map = _record_map(base_records, key_fields)
    developed_map = _record_map(developed_records, key_fields)
    rows = []
    for key in sorted(set(base_map) | set(developed_map), key=lambda value: value.casefold()):
        base_record = base_map.get(key)
        developed_record = developed_map.get(key)
        rows.append(
            _row(
                key,
                _knowledge_value(base_record, fields) if base_record else None,
                _knowledge_value(developed_record, fields) if developed_record else None,
                group=group,
            )
        )
    return rows


def _hardware_knowledge_rows(base: dict, developed: dict) -> list[dict]:
    def module_map(knowledge: dict) -> dict[str, dict]:
        mapped = {}
        mappings = knowledge.get("io_mappings") or []
        for module in knowledge.get("hardware_modules") or []:
            if _support_module(module): continue
            name = str(module.get("Object name") or module.get("name") or "Unknown module")
            station = str(module.get("Station") or "")
            related = [
                item
                for item in mappings
                if str(item.get("Module") or "").casefold() == name.casefold()
                or (station and str(item.get("Station") or "") == station)
            ]
            module = dict(module)
            module["_mappings"] = related
            key = f"Station {station}" if station else name
            mapped[key] = module
        return mapped

    def describe(module: dict) -> str:
        return (
            f"Object: {_display(module.get('Object name') or module.get('name'))}\n"
            f"Module type: {_display(module.get('Module type'))}\n"
            f"Order: {_display(module.get('Order'))}\n"
            f"Mapped channels: {len(module.get('_mappings') or [])}"
        )

    def mapping_map(module: dict | None) -> dict[str, dict]:
        if not module:
            return {}
        return {
            str(item.get("Channel") or item.get("name") or f"Channel {index + 1}"): item
            for index, item in enumerate(module.get("_mappings") or [])
        }

    def mapping_text(mapping: dict) -> str:
        return (
            f"PLC tag: {_display(mapping.get('PLC tag'))}\n"
            f"Direction: {_display(mapping.get('Direction'))}\n"
            f"Address: {_display(mapping.get('Address'))}"
        )

    base_map = module_map(base)
    developed_map = module_map(developed)
    rows = []
    for key in sorted(set(base_map) | set(developed_map), key=str.casefold):
        base_module = base_map.get(key)
        developed_module = developed_map.get(key)
        rows.append(
            _row(
                f"{key} — Module",
                describe(base_module) if base_module else None,
                describe(developed_module) if developed_module else None,
                group="Hardware modules",
            )
        )
        base_mappings = mapping_map(base_module)
        developed_mappings = mapping_map(developed_module)
        for channel in sorted(set(base_mappings) | set(developed_mappings), key=str.casefold):
            rows.append(
                _row(
                    f"{key} — {channel}",
                    mapping_text(base_mappings[channel]) if channel in base_mappings else None,
                    mapping_text(developed_mappings[channel]) if channel in developed_mappings else None,
                    group="Mapped PLC tags",
                )
            )
    return rows


def _all_knowledge_blocks(result: dict) -> list[dict]:
    knowledge = result.get("knowledge") or {}
    base = knowledge.get("base") or {}
    developed = knowledge.get("developed") or {}
    blocks = [
        {
            "title": "Project identity",
            "subtitle": "Automation Studio project and active target",
            "status": "information",
            "rows": _identity_rows(result),
        },
        {
            "title": "Project inventory",
            "subtitle": "Engineering files detected in each project",
            "status": "information",
            "rows": [
                _row("Total files", base.get("total_files", 0), developed.get("total_files", 0), group="Inventory"),
                _row("Logic files", base.get("logic_files", 0), developed.get("logic_files", 0), group="Inventory"),
                _row("Screens", base.get("screen_count", 0), developed.get("screen_count", 0), group="Inventory"),
                _row("Hardware files", base.get("hardware_files", 0), developed.get("hardware_files", 0), group="Inventory"),
                _row("Variable sections", base.get("variable_sections", 0), developed.get("variable_sections", 0), group="Inventory"),
            ],
        },
    ]

    record_specs = (
        (
            "Cyclic task assignments",
            "CPU task class, program source and execution settings",
            "task_assignments",
            (("Task class", "Task class"), ("Source", "Source"), ("Language", "Language"), ("Memory", "Memory"), ("Version", "Version"), ("Disabled", "Disabled")),
        ),
        (
            "Active software objects",
            "Objects enabled in the active software list",
            "active_objects",
            (("Enabled", "Enabled"), ("Memory", "Memory")),
        ),
        (
            "Permanent variables",
            "Configured retained variable addresses",
            "permanent_variables",
            (("Address", "Address"),),
        ),
        (
            "Logical subroutines",
            "Subroutine folders and their source files",
            "subroutines",
            (("Files", "files"),),
        ),
    )
    for title, subtitle, key, fields in record_specs:
        rows = _aligned_record_rows(base.get(key) or [], developed.get(key) or [], fields, group=title, key_fields=("name", "path"))
        if rows:
            blocks.append({"title": title, "subtitle": subtitle, "status": "information", "rows": rows})

    hardware_rows = _hardware_knowledge_rows(base, developed)
    if hardware_rows:
        blocks.append(
            {
                "title": "Hardware and I/O mappings",
                "subtitle": "Modules by station with channel-level mapped PLC tags",
                "status": "information",
                "rows": hardware_rows,
            }
        )

    screen_rows = _aligned_record_rows(
        [{"name": name} for name in base.get("screens") or []],
        [{"name": name} for name in developed.get("screens") or []],
        (),
        group="HMI screens",
    )
    if screen_rows:
        blocks.append({"title": "HMI screen inventory", "subtitle": "Screens in the selected visualization folder", "status": "information", "rows": screen_rows})
    return blocks


CHANGED_STATES = {'added', 'removed', 'modified'}


def _support_module(record):
    values=[record.get('Module type'),record.get('Object name'),record.get('name')]
    return any(re.search(r'(?i)(?:^|[^a-z0-9])X20(?:TB|BM)',str(value or '')) for value in values)


def _changed_blocks(blocks):
    return [{**block,'rows':rows} for block in blocks
            if (rows := [row for row in block.get('rows',[]) if row.get('state') in CHANGED_STATES])]


def _blocks_for_diff(diff):
    blocks=_all_blocks_for_diff(diff)
    return blocks if diff.get('report_include_same') else _changed_blocks(blocks)


def _knowledge_blocks(result):
    if not (result.get('reportSelection') or {}).get('includeKnowledge',True):return []
    return _selected_blocks(result,[b for b in _all_knowledge_blocks(result) if b['title']!='Hardware and I/O mappings'])


def _hardware_blocks(result):
    if 'hardware' not in (result.get('reportSelection') or {}).get('categories',['hardware']):return []
    kb=result.get('knowledge') or {}
    rows=_hardware_knowledge_rows(kb.get('base') or {},kb.get('developed') or {})
    return _selected_blocks(result,[{'title':'Hardware and mapped datapoints','subtitle':'Modules and channel-level PLC mappings','status':'modified','rows':rows}])


def _selected_blocks(result,blocks):
    states=set((result.get('reportSelection') or {}).get('statuses',CHANGED_STATES))
    return [{**block,'rows':rows} for block in blocks if (rows:=[row for row in block.get('rows',[]) if row.get('state') in states])]


def _changed_diffs(result):
    states=set((result.get('reportSelection') or {}).get('statuses',CHANGED_STATES))
    return [d for d in result.get('diffs') or [] if d.get('status') in states and d.get('category') in {'logic','screen','hardware','config'} and not str(d.get('path','')).casefold().endswith(('.pkg', '.prg')) and (_blocks_for_diff(d) or (d.get('parsed_ladder') or {}).get('changes'))]


def _navigation_entries(result):
    entries=[]
    if _knowledge_blocks(result):entries.append(('knowledge','Project Knowledge Base',0))
    numbered=list(enumerate(_changed_diffs(result),start=1))
    for category,label in CATEGORY_ORDER:
        changes=[(number,diff) for number,diff in numbered if diff.get('category')==category]
        if not changes:continue
        entries.append(('category-'+category,label,0))
        entries.extend((f'change-{number}',f'{diff.get("status","").upper()} · {diff.get("path","")}',1) for number,diff in changes)
    if _hardware_blocks(result):entries.append(('hardware-mappings','Hardware and mapped datapoints',0))
    return entries


def _report_blocks(diff):
    """Ladder graphics are the human report; retain full evidence in JSON."""
    if not diff.get('parsed_ladder'): return _blocks_for_diff(diff)
    blocks=[]
    for control in diff['parsed_ladder'].get('controls',[]):
        if control.get('status')=='unchanged' and not diff.get('report_include_same'): continue
        rows=[]
        for key,label in [('label','Label'),('comment','Comment'),('commented','Commented')]:
            a=(control.get('base') or {}).get(key)
            b=(control.get('new') or {}).get(key)
            if a!=b and (a or b): rows.append(_row(label,a,b,group='Ladder network'))
        if rows: blocks.append({'title':control['name'],'subtitle':'Network annotations','status':control['status'],'rows':rows})
    return blocks


def _ladder_records(control):
    return {key:({**control[key],'comparisonStatus':control.get('status','')} if control.get(key) else None)
            for key in ('base','new')}


def _ladder_report_panels(control):
    from python_engine.ladder_model import diagram_panels
    records=_ladder_records(control)
    panels={key:diagram_panels(record,records['new' if key=='base' else 'base'],
                              'base' if key=='base' else 'developed') if record else []
            for key,record in records.items()}
    return records,panels


def export_data(result):
    sections=[{'category':'knowledge','title':'Project Knowledge Base','blocks':_knowledge_blocks(result)}] if _knowledge_blocks(result) else []
    for category,title in CATEGORY_ORDER:
        entries=[]
        for diff in _changed_diffs(result):
            if diff['category']!=category: continue
            report_progress(f'Preparing JSON: {diff.get("path",category)}')
            entry={k:diff.get(k) for k in ['path','status','category','base_relative_path','new_relative_path']}
            entry['blocks']=_blocks_for_diff(diff)
            if category=='screen':
                entry['previews']={side:'data:image/png;base64,'+base64.b64encode(data).decode('ascii') for side,data in screen_previews(diff).items() if data}
            entries.append(entry)
        sections.append({'category':category,'title':title,'changes':entries,'blocks':_hardware_blocks(result) if category=='hardware' else []})
    from python_engine.ladder_model import normalized_model,render_svg,RENDER_VERSION
    ladder=[]
    for diff in _changed_diffs(result):
        if not diff.get('parsed_ladder'): continue
        parsed={**diff['parsed_ladder'],'controls':[]}
        for control in diff['parsed_ladder'].get('controls',[]):
            records=_ladder_records(control)
            for key,record in records.items():
                if record: record['diagram']=normalized_model(record)
            updated={**control,**records}
            if control.get('status')!='unchanged':
                updated['diagrams']={key:render_svg(record,records['new' if key=='base' else 'base'],'base' if key=='base' else 'developed')
                                     for key,record in records.items() if record}
            parsed['controls'].append(updated)
        ladder.append({'path':diff.get('path'),'parsedLadder':parsed})
    project_trees = {side: (result.get('knowledge', {}).get(side, {}) or {}).get('project_tree')
                     for side in ('base', 'developed')} if (result.get('reportSelection') or {}).get('includeKnowledge',True) else {}
    return {'testId':result.get('testId'),'machineDepartment':result.get('machineDepartment'),'baseName':result.get('baseName'),'newName':result.get('newName'),'sections':sections,'ladderNetworks':ladder,'ladderRenderVersion':RENDER_VERSION,'projectTrees':project_trees,'reportSelection':result.get('reportSelection'),'summary':result.get('summary'),'comparisonSummary':result.get('comparisonSummary',result.get('summary')),'previewNote':'Static screen context; runtime values and visibility are not simulated. Selected file statuses are listed. Project trees, when requested, retain the complete scoped inventory.'}


def _preview_html(diff):
    if diff.get('category')!='screen': return ''
    previews=screen_previews(diff)
    if not any(previews.values()): return ''
    panes=''.join('<div><b>'+side.title()+'</b>'+('<img style="width:100%;height:auto;max-height:140mm;object-fit:contain" alt="'+side+' static HMI preview" src="data:image/png;base64,'+base64.b64encode(data).decode('ascii')+'">' if data else '<p>Screen not present</p>')+'</div>' for side,data in previews.items())
    return '<div class="file-split">'+panes+'</div><p>Static screen context: configured bitmap files are shown in Released state at level 0; live values, bitmap indexes and visibility are not simulated. Missing images retain their references.</p>'


def _html_value(value: Any) -> str:
    return escape(_display(value)).replace("\n", "<br>")


def _project_identity_html(result: dict, side: str) -> str:
    identity = ((result.get("projects") or {}).get(side) or (result.get("knowledge") or {}).get(side) or {})
    fields = (
        ("Automation Studio", "automation_studio_version"),
        ("Active configuration", "active_configuration"),
        ("PLC type", "plc_type"),
        ("Screen folder", "active_hmi"),
    )
    return "".join(f"<dt>{escape(label)}</dt><dd>{_html_value(identity.get(key))}</dd>" for label, key in fields)


def _html_block(block: dict, base_name: str, developed_name: str) -> str:
    rows = block.get("rows") or []

    def pane(side: str, title: str) -> str:
        rendered = []
        last_group = None
        value_key = "base" if side == "base" else "developed"
        ref_key = "base_ref" if side == "base" else "developed_ref"
        for row in rows:
            group = row.get("group") or "Details"
            if group != last_group:
                rendered.append(f'<div class="detail-group">{escape(str(group))}</div>')
                last_group = group
            reference = row.get(ref_key) or row.get("label") or "Detail"
            rendered.append(
                f'<div class="detail-row {escape(str(row.get("state") or "unchanged"))}">'
                f'<span>{escape(str(reference))}</span><code>{_html_value(row.get(value_key))}</code></div>'
            )
        return (
            f'<article class="side {side}"><h4>{"BASE / REFERENCE" if side == "base" else "DEVELOPED / COMPARE"}</h4>'
            f'<div class="side-project">{escape(title)}</div><div class="detail-list">{"".join(rendered)}</div></article>'
        )

    status = escape(str(block.get("status") or "modified"))
    return (
        f'<div class="record"><div class="record-title"><div><span class="status {status}">{status.upper()}</span>'
        f'<b>{escape(str(block.get("title") or "Details"))}</b></div><small>{escape(str(block.get("subtitle") or ""))}</small></div>'
        f'<div class="file-split">{pane("base", base_name)}{pane("developed", developed_name)}</div></div>'
    )


def _html_change(diff: dict, number: int, base_name: str, developed_name: str) -> str:
    report_progress(f'Preparing HTML: {diff.get("path", "comparison")}')
    status = escape(str(diff.get("status") or "modified"))
    category = escape(str(diff.get("category") or "config").title())
    subroutine = escape(str(diff.get("subroutine") or "Project level"))
    blocks = "".join(_html_block(block, base_name, developed_name) for block in _report_blocks(diff))
    from python_engine.ladder_model import render_svg
    diagrams=''
    for control in (diff.get('parsed_ladder') or {}).get('controls',[]):
        if control.get('status')=='unchanged' and not diff.get('report_include_same'):continue
        records=_ladder_records(control)
        panes=[]
        for side,key,other in [('base','base','new'),('developed','new','base')]:
            record=records[key]
            svg=render_svg(record,records[other],side) if record and record.get('diagram') else '<p>Network not present</p>'
            panes.append(f'<div style="min-width:0;padding:8px"><b>{escape(base_name if side=="base" else developed_name)} / {side.title()}</b><div style="overflow:auto"><div style="min-width:100%;width:max-content">{svg}</div></div></div>')
        diagrams+=f'<h3>{escape(control.get("name","Network"))}</h3><div class="file-split">{"".join(panes)}</div>'
    return (
        f'<section class="change" id="change-{number}"><div class="change-title"><div><span class="status {status}">{status.upper()}</span>'
        f'<b>Change {number}: {escape(str(diff.get("path") or ""))}</b></div><small>{category} / {subroutine}</small></div>'
        f'<div class="file-paths"><div><b>Base file</b>{escape(_relative_file(diff, "base"))}</div>'
        f'<div><b>Developed file</b>{escape(_relative_file(diff, "developed"))}</div></div>{_preview_html(diff)}{diagrams}{blocks}</section>'
    )


def export_html(result: dict, path: Path, logo: Path):
    from backend.core.report_cover import COVER_CSS,cover_html
    cover_section=cover_html(result['reportCover'],'MatchView — Complete comparison result') if result.get('reportCover') else ''
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_name, developed_name, summary = _summary_values(result)
    logo_uri = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode("ascii") if logo.exists() else ""
    logo_html = f'<img src="{logo_uri}" alt="uSOPp.ai logo">' if logo_uri else ""
    numbered = list(enumerate(_changed_diffs(result), start=1))
    sections = []
    for category, title in CATEGORY_ORDER:
        changes = [(number, diff) for number, diff in numbered if diff.get("category") == category]
        if not changes:
            continue
        sections.append(
            f'<section class="report-section" id="category-{category}"><h2>{title}<small>{len(changes)} selected file(s)</small></h2>'
            + "".join(_html_change(diff, number, base_name, developed_name) for number, diff in changes)
            + "</section>"
        )
    if _hardware_blocks(result):sections.append('<section class="report-section" id="hardware-mappings"><h2>Hardware and mapped datapoints</h2>'+"".join(_html_block(block,base_name,developed_name) for block in _hardware_blocks(result))+"</section>")
    knowledge = "".join(_html_block(block, base_name, developed_name) for block in _knowledge_blocks(result))
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>uSOPp.ai Project Comparison</title><style>
{COVER_CSS}
svg{{width:100%;height:auto}}
@page{{size:A4 landscape;margin:22mm 10mm 17mm;@bottom-left{{content:"{escape(generated)}";color:{MUTED};font-size:8pt}}@bottom-right{{content:"Page " counter(page) " / " counter(pages);color:{MUTED};font-size:8pt}}}}
*{{box-sizing:border-box}}body{{margin:0;font:12px/1.45 Segoe UI,Arial,sans-serif;color:#172033;background:#fff}}header{{display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid {DARK_BLUE};padding-bottom:9px;margin-bottom:14px}}header h1{{margin:0;color:{DARK_BLUE};font-size:22px}}header img{{width:125px;max-height:58px;object-fit:contain}}.projects,.file-split,.file-paths{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}}.project,.summary div{{border:1px solid #cbd7e3;border-radius:7px;padding:9px}}.project.base{{border-top:5px solid {BASE_COLOR}}}.project.developed{{border-top:5px solid {DEVELOPED_COLOR}}}.project span,.summary span{{display:block;color:{MUTED};font-size:9px;text-transform:uppercase;letter-spacing:.06em}}.project b{{overflow-wrap:anywhere}}.project dl{{display:grid;grid-template-columns:max-content 1fr;gap:3px 8px;margin:7px 0 0;font-size:9px}}.project dt{{color:{MUTED}}}.project dd{{margin:0;font-weight:600}}.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0 15px}}.summary b{{font-size:18px;color:{DARK_BLUE}}}.report-section{{margin-top:18px}}.report-section>h2{{display:flex;justify-content:space-between;align-items:end;margin:0 0 8px;padding:7px 10px;color:{DARK_BLUE};background:#e8eef5;border-left:5px solid {DARK_BLUE};font-size:15px}}.report-section>h2 small{{color:{MUTED};font-size:9px}}.change{{border:1px solid #cad5e1;border-radius:7px;margin:10px 0;overflow:hidden}}.change-title,.record-title{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;background:#f1f5f9;border-bottom:1px solid #d9e2eb}}.change-title b,.record-title b{{font-size:11px;overflow-wrap:anywhere}}.change-title small,.record-title small{{color:{MUTED};text-align:right}}.status{{display:inline-block;margin-right:7px;border-radius:999px;padding:2px 7px;color:white;background:#64748b;font-size:8px;font-weight:700}}.status.added{{background:#16975f}}.status.removed{{background:#d34b55}}.status.modified{{background:#d18b16}}.status.information{{background:{DARK_BLUE}}}.file-paths{{gap:0;background:#f8fafc;border-bottom:1px solid #d9e2eb}}.file-paths>div{{padding:6px 9px;font:8px/1.35 Consolas,monospace;overflow-wrap:anywhere}}.file-paths>div+div{{border-left:1px solid #d9e2eb}}.file-paths b{{display:block;color:{MUTED};font:700 8px Segoe UI,Arial,sans-serif;text-transform:uppercase}}.record{{margin:8px;border:1px solid #d4dee8;border-radius:6px;overflow:hidden;break-inside:auto}}.record-title{{padding:5px 7px;background:#fff}}.file-split{{gap:0}}.side{{min-width:0}}.side+.side{{border-left:1px solid #c9d5df}}.side.base{{background:{BASE_TINT}}}.side.developed{{background:{DEVELOPED_TINT}}}.side h4{{margin:0;padding:6px 9px;color:#fff;font-size:9px;letter-spacing:.06em}}.side.base h4{{background:{BASE_COLOR}}}.side.developed h4{{background:{DEVELOPED_COLOR}}}.side-project{{padding:4px 9px;background:rgba(255,255,255,.66);font:700 8px Consolas,monospace;overflow-wrap:anywhere}}.detail-group{{padding:5px 8px 2px;color:{MUTED};font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}}.detail-row{{display:grid;grid-template-columns:minmax(80px,25%) minmax(0,1fr);border-top:1px solid rgba(148,163,184,.25);min-height:25px}}.detail-row>span{{padding:5px 7px;color:#52677a;font-size:8px;font-weight:700;overflow-wrap:anywhere}}.detail-row>code{{padding:5px 7px;border-left:1px solid rgba(148,163,184,.22);color:#1f3345;font:8px/1.4 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}.detail-row.added{{background:#dcfce7;box-shadow:inset 3px 0 #16975f}}.detail-row.removed{{background:#fee2e2;box-shadow:inset 3px 0 #d34b55}}.detail-row.modified{{background:#fef3c7;box-shadow:inset 3px 0 #d18b16}}footer{{display:flex;justify-content:space-between;color:{MUTED};font-size:9px;margin-top:20px;padding-top:8px;border-top:1px solid #d7e0e9}}footer .pages:after{{content:"Page 1 / 1"}}@media print{{footer{{display:none}}.record{{break-inside:auto}}}}@media screen{{body{{max-width:1500px;margin:24px auto;padding:0 24px}}}}
</style></head><body>{cover_section}<header><div><h1>uSOPp.ai</h1><b>Structured Project Comparison Report</b></div>{logo_html}</header>
<p><b>Test ID:</b> {escape(str(result.get("testId") or "Earlier run: not recorded"))} &nbsp; <b>Department:</b> {escape(str(result.get("machineDepartment") or "All"))}</p>
<div class="projects"><div class="project base"><span>Base project</span><b>{escape(base_name)}</b><dl>{_project_identity_html(result, 'base')}</dl></div><div class="project developed"><span>Developed project</span><b>{escape(developed_name)}</b><dl>{_project_identity_html(result, 'developed')}</dl></div></div>
<div class="summary"><div><span>Modified</span><b>{summary.get('modified',0)}</b></div><div><span>Added</span><b>{summary.get('added',0)}</b></div><div><span>Removed</span><b>{summary.get('removed',0)}</b></div><div><span>Unchanged</span><b>{summary.get('unchanged',0)}</b></div></div>
<section class="report-section knowledge"><h2>Project Knowledge Base<small>Changed project structure</small></h2>{knowledge}</section>{''.join(sections)}<footer><span>{escape(generated)}</span><span class="pages"></span></footer></body></html>'''
    if not knowledge:
        html=html.replace('<section class="report-section knowledge"><h2>Project Knowledge Base<small>Changed project structure</small></h2></section>','')
    html=html.replace('class="report-section knowledge"','class="report-section knowledge" id="knowledge"')
    links=''.join(f'<a class="toc-level-{level}" href="#{key}">{escape(title)}</a>' for key,title,level in _navigation_entries(result))
    navigation='<nav class="report-toc" aria-label="Table of contents"><h2>Table of contents</h2><a href="#report-top">Report overview</a>'+links+'</nav>'
    css='<style>.report-toc{position:sticky;top:12px;align-self:start;min-width:180px;max-width:50vw;width:270px;max-height:85vh;overflow:auto;resize:horizontal;padding:12px;border:1px solid #cbd7e3;background:#f3f7fb}.report-toc h2{font-size:15px}.report-toc a{display:block;padding:5px;color:#173b68;overflow-wrap:anywhere}.report-toc .toc-level-1{padding-left:18px;font-size:11px}.report-layout{display:flex;gap:18px}.report-layout main{min-width:0;flex:1}.change,.report-section{scroll-margin-top:12px}@media print{.report-layout{display:block}.report-toc{position:static;width:auto;max-width:none;max-height:none;resize:none;break-after:page}}@media(max-width:850px){.report-layout{display:block}.report-toc{position:static;width:auto;max-width:none;max-height:260px;resize:vertical}}</style>'
    html=html.replace('</head>',css+'</head>').replace('</header>','</header><div class="report-layout">'+navigation+'<main id="report-top">',1).replace('<footer>','</main></div><footer>',1)
    path.write_text(html, encoding="utf-8")


def export_pdf(result: dict, path: Path, logo: Path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    page_size = landscape(A4)

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._states = []

        def showPage(self):
            report_progress(f'Preparing PDF: laying out page {self._pageNumber}')
            self._states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._states)
            for state in self._states:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            width, height = page_size
            self.saveState()
            self.setStrokeColor(colors.HexColor(DARK_BLUE))
            self.setLineWidth(2)
            self.line(10 * mm, height - 18 * mm, width - 10 * mm, height - 18 * mm)
            self.setFillColor(colors.HexColor(DARK_BLUE))
            self.setFont("Helvetica-Bold", 14)
            self.drawString(10 * mm, height - 13 * mm, "uSOPp.ai  Structured Project Comparison Report")
            if logo.exists():
                self.drawImage(str(logo), width - 47 * mm, height - 17 * mm, width=36 * mm, height=13 * mm, preserveAspectRatio=True, anchor="ne", mask="auto")
            self.setFillColor(colors.HexColor(MUTED))
            self.setFont("Helvetica", 8)
            self.drawString(10 * mm, 7 * mm, generated)
            self.drawRightString(width - 10 * mm, 7 * mm, f"Page {self._pageNumber} / {total}")
            self.restoreState()

    def safe(value: Any) -> str:
        return escape(_display(value)).replace("\n", "<br/>")

    def source_value(row, side):
        value = row.get(side)
        if row.get('group') == 'PLC source':
            return escape(str(value or '').expandtabs(4)).replace(' ', '&#160;')
        return safe(value)

    styles = getSampleStyleSheet()
    project_style = ParagraphStyle("project", parent=styles["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#172033"))
    header_style = ParagraphStyle("side_header", parent=styles["BodyText"], fontSize=8, leading=10, textColor=colors.white)
    cell_style = ParagraphStyle("cell", parent=styles["BodyText"], fontName="Courier", fontSize=6.3, leading=8, wordWrap="CJK")
    title_style = ParagraphStyle("change", parent=styles["Heading3"], fontSize=9, leading=11, textColor=colors.HexColor(DARK_BLUE), spaceAfter=3)
    category_style = ParagraphStyle("category", parent=styles["Heading2"], fontSize=13, leading=15, textColor=colors.HexColor(DARK_BLUE), spaceBefore=6, spaceAfter=6)
    class NavigationDoc(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            bookmark=getattr(flowable,'report_bookmark',None)
            if bookmark:
                key,title,level=bookmark
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(title,key,level=level,closed=level>0)
    doc = NavigationDoc(str(path), pagesize=page_size, rightMargin=10 * mm, leftMargin=10 * mm, topMargin=22 * mm, bottomMargin=12 * mm)
    base_name, developed_name, summary = _summary_values(result)

    def project_text(side: str, name: str) -> str:
        identity = ((result.get("projects") or {}).get(side) or (result.get("knowledge") or {}).get(side) or {})
        return (
            f"Test ID: {safe(result.get('testId') or 'Earlier run')}<br/><b>{'BASE PROJECT' if side == 'base' else 'DEVELOPED PROJECT'}</b><br/>{safe(name)}<br/>"
            f"Automation Studio: {safe(identity.get('automation_studio_version'))}<br/>"
            f"Active configuration: {safe(identity.get('active_configuration'))}<br/>"
            f"PLC type: {safe(identity.get('plc_type'))}<br/>Screen folder: {safe(identity.get('active_hmi'))}"
        )

    story = [
        Table(
            [[Paragraph(project_text("base", base_name), project_style), Paragraph(project_text("developed", developed_name), project_style)]],
            colWidths=[135 * mm, 135 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#aab7c4")),
                    ("INNERGRID", (0, 0), (-1, -1), .4, colors.HexColor("#cbd5df")),
                    ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(BASE_TINT)),
                    ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(DEVELOPED_TINT)),
                    ("LINEABOVE", (0, 0), (0, 0), 4, colors.HexColor(BASE_COLOR)),
                    ("LINEABOVE", (1, 0), (1, 0), 4, colors.HexColor(DEVELOPED_COLOR)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        ),
        Spacer(1, 5),
        Table(
            [[f"Modified\n{summary.get('modified', 0)}", f"Added\n{summary.get('added', 0)}", f"Removed\n{summary.get('removed', 0)}", f"Unchanged\n{summary.get('unchanged', 0)}"]],
            colWidths=[67.5 * mm] * 4,
            style=TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#aab7c4")), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3f7")), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8)]),
        ),
        Spacer(1, 7),
    ]

    def add_block(block: dict):
        story.append(Paragraph(f"<b>{safe(block.get('title'))}</b> &nbsp; {safe(block.get('subtitle'))}", title_style))
        rows = block.get("rows") or []
        table_rows = [[Paragraph(f"<b>BASE / REFERENCE</b><br/>{safe(base_name)}", header_style), Paragraph(f"<b>DEVELOPED / COMPARE</b><br/>{safe(developed_name)}", header_style)]]
        for row in rows:
            left_label = row.get("base_ref") or row.get("label")
            right_label = row.get("developed_ref") or row.get("label")
            table_rows.append(
                [
                    Paragraph(f"<b>{safe(left_label)}</b><br/>{source_value(row, 'base')}", cell_style),
                    Paragraph(f"<b>{safe(right_label)}</b><br/>{source_value(row, 'developed')}", cell_style),
                ]
            )
        # Bound repeated table splitting/layout work without omitting rows.
        for offset in range(0, max(1, len(rows)), 80):
            table = Table([table_rows[0]] + table_rows[offset + 1:offset + 81], colWidths=[135 * mm, 135 * mm], repeatRows=1, splitByRow=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#bdc9d4")),
                        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(BASE_COLOR)),
                        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(DEVELOPED_COLOR)),
                        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor(BASE_TINT)),
                        ("BACKGROUND", (1, 1), (1, -1), colors.HexColor(DEVELOPED_TINT)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            for index, row in enumerate(rows[offset:offset + 80], start=1):
                tint = {"added":"#dcfce7", "removed":"#fee2e2", "modified":"#fef3c7"}.get(row.get("state"))
                if tint:
                    table.setStyle(TableStyle([("BACKGROUND", (0,index), (-1,index), colors.HexColor(tint))]))
            story.extend([table, Spacer(1, 5)])

    def heading(text,key,level=0,style=None):
        paragraph=Paragraph(text,style or category_style)
        paragraph.report_bookmark=(key,re.sub('<[^>]+>','',text),level)
        story.append(paragraph)
    story.append(Paragraph('Table of contents',category_style))
    for key,title,level in _navigation_entries(result):
        story.append(Paragraph(('&nbsp;&nbsp;&nbsp;' if level else '')+f'<link href="#{key}" color="{DARK_BLUE}">{escape(title)}</link>',project_style))
    story.append(PageBreak())
    if _knowledge_blocks(result):heading('Project Knowledge Base','knowledge')
    for block in _knowledge_blocks(result): add_block(block)
    numbered = list(enumerate(_changed_diffs(result), start=1))
    for category, label in CATEGORY_ORDER:
        changes = [(number, diff) for number, diff in numbered if diff.get("category") == category]
        if not changes:
            continue
        heading(f"{label} ({len(changes)} selected file(s))",'category-'+category)
        for number, diff in changes:
            heading(f"{safe(diff.get('status')).upper()} | Change {number}: {safe(diff.get('path'))}<br/><font size='7'>Base: {safe(_relative_file(diff, 'base'))} | Developed: {safe(_relative_file(diff, 'developed'))}</font>",f'change-{number}',1,title_style)
            from svglib.svglib import svg2rlg
            for control in (diff.get('parsed_ladder') or {}).get('controls',[]):
                if control.get('status')=='unchanged' and not diff.get('report_include_same'):continue
                records,panels=_ladder_report_panels(control)
                for panel_index in range(max(map(len,panels.values()),default=1)):
                    previews=[]
                    for side,key in [('base','base'),('developed','new')]:
                        project=base_name if side=='base' else developed_name
                        pane=[Paragraph(safe(project)+' / '+side.title()+' / '+safe(control.get('name')),project_style)]
                        if panel_index<len(panels[key]):
                            panel=panels[key][panel_index]
                            if panel['rows']*panel['columns']>1:
                                pane.append(Paragraph(f'Continuation tile {panel_index+1}/{len(panels[key])}: vertical {panel["row"]+1}, horizontal {panel["column"]+1}',project_style))
                            drawing=svg2rlg(BytesIO(panel['svg'].encode('utf-8')))
                            if drawing is None: raise ValueError('Ladder SVG could not be converted to PDF')
                            factor=min((doc.width/2-12)/drawing.width,doc.height*.72/drawing.height)
                            drawing.scale(factor,factor);drawing.width*=factor;drawing.height*=factor;pane.append(drawing)
                        else:pane.append(Paragraph('Network not present' if not records[key] else 'No continuation on this side',project_style))
                        previews.append(pane)
                    story.extend([Table([previews],colWidths=[doc.width/2]*2),Spacer(1,6)])
            if diff.get('category')=='screen':
                from reportlab.platypus import Image as ReportImage
                previews=[]
                for side,data in screen_previews(diff).items():
                    if data:
                        from PIL import Image as PillowImage
                        size=PillowImage.open(BytesIO(data)).size
                        factor=min((doc.width/2-12)/size[0],100*mm/size[1])
                        previews.append([Paragraph(side.title(),project_style),ReportImage(BytesIO(data),width=size[0]*factor,height=size[1]*factor)])
                    else: previews.append([Paragraph(side.title()+': screen not present',project_style)])
                if any(len(p)>1 for p in previews):
                    story.append(Table([previews],colWidths=[doc.width/2]*2))
                    story.append(Paragraph('Static screen context; configured bitmaps use Released state at level 0. Live values, bitmap indexes and visibility are not simulated. Missing images retain their references.',project_style))
            for block in _report_blocks(diff):
                add_block(block)

    if _hardware_blocks(result):heading('Hardware and mapped datapoints','hardware-mappings')
    for block in _hardware_blocks(result):
        add_block(block)
    if result.get('reportCover'):
        from backend.core.report_cover import cover_pdf_story
        story=cover_pdf_story(result['reportCover'],'MatchView - Complete comparison result')+story
    doc.build(story, canvasmaker=NumberedCanvas)


def export_docx(result: dict, path: Path, logo: Path):
    # B&R legacy containers can leave non-XML control characters in evidence.
    # Strip them recursively before passing any report text to python-docx.
    def xml_safe(value):
        if isinstance(value,str): return ''.join(c for c in value if c in '\t\n\r' or 0x20<=ord(c)<=0xD7FF or 0xE000<=ord(c)<=0xFFFD or 0x10000<=ord(c)<=0x10FFFF)
        if isinstance(value,dict): return {xml_safe(k):xml_safe(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)): return [xml_safe(v) for v in value]
        return value
    result=xml_safe(result)
    from docx import Document
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def field(paragraph, code):
        run = paragraph.add_run()
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instruction = OxmlElement("w:instrText")
        instruction.set(qn("xml:space"), "preserve")
        instruction.text = code
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        run._r.extend((begin, instruction, end))

    def shade(cell, fill):
        tc_pr = cell._tc.get_or_add_tcPr()
        element = tc_pr.find(qn("w:shd"))
        if element is None:
            element = OxmlElement("w:shd")
            tc_pr.append(element)
        element.set(qn("w:fill"), fill)

    def set_cell_color(cell, color):
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor.from_string(color)

    def add_cell_detail(cell, label, value):
        paragraph = cell.paragraphs[0]
        label_run = paragraph.add_run(_display(label))
        label_run.bold = True
        label_run.font.name = "Consolas"
        label_run.font.size = Pt(7.5)
        value_run = paragraph.add_run("\n" + _display(value))
        value_run.font.name = "Consolas"
        value_run.font.size = Pt(7.5)

    doc = Document()
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    doc.settings._element.append(update)
    section = doc.sections[0]
    section.orientation = 1
    section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = Inches(.45)
    section.right_margin = Inches(.45)
    header = section.header.add_table(rows=1, cols=2, width=Inches(10.5))
    header.alignment = WD_TABLE_ALIGNMENT.CENTER
    left, right = header.rows[0].cells
    title = left.paragraphs[0]
    run = title.add_run("uSOPp.ai\n")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(23, 59, 104)
    title.add_run("Structured Project Comparison Report").bold = True
    if logo.exists():
        right.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        right.paragraphs[0].add_run().add_picture(str(logo), width=Inches(1.25))
    footer = section.footer.add_table(rows=1, cols=2, width=Inches(10.5))
    footer.alignment = WD_TABLE_ALIGNMENT.CENTER
    footer.cell(0, 0).text = generated
    page = footer.cell(0, 1).paragraphs[0]
    page.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    page.add_run("Page ")
    field(page, "PAGE")
    page.add_run(" / ")
    field(page, "NUMPAGES")

    base_name, developed_name, summary = _summary_values(result)
    doc.add_heading("Project comparison", 0)
    doc.add_paragraph('Test ID: '+str(result.get('testId') or 'Earlier run: not recorded'))
    doc.add_paragraph('Department: '+str(result.get('machineDepartment') or 'All'))
    project_table = doc.add_table(rows=2, cols=2)
    project_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    project_table.style = "Table Grid"
    project_table.cell(0, 0).text = "BASE / REFERENCE"
    project_table.cell(0, 1).text = "DEVELOPED / COMPARE"
    shade(project_table.cell(0, 0), BASE_COLOR[1:])
    shade(project_table.cell(0, 1), DEVELOPED_COLOR[1:])
    set_cell_color(project_table.cell(0, 0), "FFFFFF")
    set_cell_color(project_table.cell(0, 1), "FFFFFF")
    identity_rows = _identity_rows(result)
    add_cell_detail(project_table.cell(1, 0), base_name, "\n".join(f"{row['label']}: {row['base']}" for row in identity_rows[:4]))
    add_cell_detail(project_table.cell(1, 1), developed_name, "\n".join(f"{row['label']}: {row['developed']}" for row in identity_rows[:4]))
    shade(project_table.cell(1, 0), BASE_TINT[1:])
    shade(project_table.cell(1, 1), DEVELOPED_TINT[1:])
    doc.add_paragraph(f"Modified: {summary.get('modified', 0)} | Added: {summary.get('added', 0)} | Removed: {summary.get('removed', 0)} | Unchanged: {summary.get('unchanged', 0)}")

    def add_block(block: dict):
        heading = doc.add_heading(str(block.get("title") or "Details"), 2)
        report_progress(f'Preparing Word: {block.get("title") or "comparison details"}')
        heading.paragraph_format.keep_with_next = True
        if block.get("subtitle"):
            paragraph = doc.add_paragraph(str(block["subtitle"]))
            paragraph.paragraph_format.keep_with_next = True
        rows = block.get("rows") or []
        table = doc.add_table(rows=len(rows) + 1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"
        # column.cells flattens the table once. Repeated table.cell() calls
        # traverse every cell again, causing quadratic work on large reports.
        left_cells, right_cells = table.columns[0].cells, table.columns[1].cells
        left_cells[0].text = f"BASE / REFERENCE — {base_name}"
        right_cells[0].text = f"DEVELOPED / COMPARE — {developed_name}"
        shade(left_cells[0], BASE_COLOR[1:])
        shade(right_cells[0], DEVELOPED_COLOR[1:])
        set_cell_color(left_cells[0], "FFFFFF")
        set_cell_color(right_cells[0], "FFFFFF")
        for index, row in enumerate(rows, start=1):
            left_cell, right_cell = left_cells[index], right_cells[index]
            add_cell_detail(left_cell, row.get("base_ref") or row.get("label"), row.get("base"))
            add_cell_detail(right_cell, row.get("developed_ref") or row.get("label"), row.get("developed"))
            shade(left_cell, BASE_TINT[1:])
            shade(right_cell, DEVELOPED_TINT[1:])
            tint = {"added":"dcfce7", "removed":"fee2e2", "modified":"fef3c7"}.get(row.get("state"))
            if tint:
                shade(left_cell, tint)
                shade(right_cell, tint)
        for cell in (*left_cells, *right_cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        doc.add_paragraph()

    if _knowledge_blocks(result):doc.add_heading("Project Knowledge Base", 1)
    for block in _knowledge_blocks(result): add_block(block)
    numbered = list(enumerate(_changed_diffs(result), start=1))
    for category, label in CATEGORY_ORDER:
        changes = [(number, diff) for number, diff in numbered if diff.get("category") == category]
        if not changes:
            continue
        doc.add_heading(f"{label} ({len(changes)} selected file(s))", 1)
        for number, diff in changes:
            doc.add_heading(f"{str(diff.get('status') or '').upper()} | Change {number}: {diff.get('path', '')}", 2)
            doc.add_paragraph(f"Base file: {_relative_file(diff, 'base')}\nDeveloped file: {_relative_file(diff, 'developed')}\nSubroutine / area: {diff.get('subroutine') or 'Project level'}")
            from python_engine.ladder_model import panel_png
            for control in (diff.get('parsed_ladder') or {}).get('controls',[]):
                if control.get('status')=='unchanged' and not diff.get('report_include_same'):continue
                doc.add_heading(str(control.get('name') or 'Ladder network'),3)
                records,panels=_ladder_report_panels(control)
                for panel_index in range(max(map(len,panels.values()),default=1)):
                    table=doc.add_table(rows=1,cols=2)
                    table.autofit=False
                    for index,(side,key,other) in enumerate([('base','base','new'),('developed','new','base')]):
                        cell=table.cell(0,index);cell.text=(base_name if side=='base' else developed_name)+' / '+side.title()
                        if panel_index<len(panels[key]):
                            panel=panels[key][panel_index]
                            if panel['rows']*panel['columns']>1:
                                cell.add_paragraph(f'Continuation tile {panel_index+1}/{len(panels[key])}: vertical {panel["row"]+1}, horizontal {panel["column"]+1}')
                            width=min(4.8,4.2*panel['width']/panel['height'])
                            cell.add_paragraph().add_run().add_picture(BytesIO(panel_png(records[key],panel,records[other],side)),width=Inches(width))
                        else:cell.add_paragraph('Network not present' if not records[key] else 'No continuation on this side')
            if diff.get('category')=='screen':
                previews=screen_previews(diff)
                if any(previews.values()):
                    table=doc.add_table(rows=1,cols=2)
                    for index,(side,data) in enumerate(previews.items()):
                        cell=table.cell(0,index);cell.text=side.title()
                        if data:
                            from PIL import Image as PillowImage
                            size=PillowImage.open(BytesIO(data)).size
                            width=min(4.8,3.7*size[0]/size[1])
                            cell.add_paragraph().add_run().add_picture(BytesIO(data),width=Inches(width))
                        else: cell.add_paragraph('Screen not present')
                    doc.add_paragraph('Static screen context; configured bitmaps use Released state at level 0. Live values, bitmap indexes and visibility are not simulated. Missing images retain their references.')
            for block in _report_blocks(diff):
                add_block(block)

    if _hardware_blocks(result):doc.add_heading("Hardware and mapped datapoints", 1)
    for block in _hardware_blocks(result):
        add_block(block)
    doc.save(path)
