#!/usr/bin/env python3
# ============================================================================
# uSOPp - Industrial Automation AI Engine
# Proven Python v1.71 Engineering Validation Engine
# Adapted for Nami/React Web Integration (Data Model Validation removed per user directive)
# ============================================================================

import os
import sys
import re
import json
import argparse
from copy import copy, deepcopy
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import xml.etree.ElementTree as ET

from openpyxl import Workbook, load_workbook
try:
    from python_engine.workbook_bounds import value_rows
    from python_engine.metadata_cells import metadata_numeric_value, normalize_metadata_workbook
    from python_engine.metadata_names import resolve_name_collisions
except ModuleNotFoundError:
    from workbook_bounds import value_rows
    from metadata_cells import metadata_numeric_value, normalize_metadata_workbook
    from metadata_names import resolve_name_collisions
try:
    import xlrd
except ImportError:
    xlrd = None
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.formatting.rule import FormulaRule

# Global project variables
ROOT = Path.cwd()
LOGICAL_ROOT = ROOT / "Logical"
PROJECT_NAME = ROOT.name
OUTPUT_WORKBOOK = ROOT / "AI_QC" / f"{PROJECT_NAME}.xlsx"
SOURCE_PATTERNS = ("*.st", "*.var", "*.typ", "*.fun", "*.ab")
PLC_PACKET_FILE = LOGICAL_ROOT / "mms_nw_rCyclic.st"
PROJECT_APJ: Optional[Path] = None
PROJECT_GLOBAL_ROOTS: List[Path] = []
HMI_PAGE_ROOTS: List[Path] = []
HMI_TEXTGROUP_ROOTS: List[Path] = []
HMI_TARGET_NAME = "All discovered HMI targets"
SELECTED_METADATA_FILE: Optional[Path] = None
HAS_PROJECT_CONTEXT = True
STATUS_CALLBACK = None
LAST_REPORT_PATH: Optional[Path] = None
METADATA_CACHE: Dict[Tuple[str, int], Any] = {}
BOOL_METADATA_MODE = "BOOL"

DUPLICATE_PARAMETER_CHECK = True
DUPLICATE_PARAMETER_FILL = "E4D7FF"
DUPLICATE_PARAMETER_FORMULA = 'N("uSOPp duplicate row")=0'

DEFAULT_VALIDATION_OPTIONS = {
    "group_code": True,
    "offset_datatype": True,
    "metadata_compare": True,
    "duplicate_parameter": True,
    "dropdown": True,
    "alarm": True,
}

# Group controls are separate checks from individual payload fields. Count
# them in the report KPIs even when every copied field itself passes.
PACKET_CONTROL_CHECK_TYPES = {
    "Packet Size", "Packet Overflow", "Packet Underflow",
    "Response Length Missing", "Response Trigger Missing", "Packet Cursor Data Type",
    "Alarm Array Bounds", "Alarm Array Missing", "Alarm Loop Bounds", "Alarm Buffer Mismatch",
    "Alarm Packing Sequence", "Alarm Buffer Capacity", "Alarm Copy Start", "Alarm Copy Size",
    "Alarm Copy Missing", "Alarm Packing Ambiguous", "Alarm Bit Position", "Alarm Bit Collision",
}

PACKET_HEADER_BYTES = 5

BASE_TYPE_SIZES = {
    "BOOL": 1,
    "BYTE": 1,
    "USINT": 1,
    "SINT": 1,
    "CHAR": 1,
    "WORD": 2,
    "UINT": 2,
    "INT": 2,
    "DWORD": 4,
    "UDINT": 4,
    "DINT": 4,
    "REAL": 4,
    "TIME": 4,
    "DATE": 4,
    "TOD": 4,
    "DATE_AND_TIME": 4,
    "DT": 4,
    "LWORD": 8,
    "ULINT": 8,
    "LINT": 8,
    "LREAL": 8,
}

METADATA_HEADER_MAP = {
    "group code": "group_code",
    "groupcode": "group_code",
    "group": "group_code",
    "group id": "group_code",
    "sl no": "sequence",
    "slno": "sequence",
    "sl no.": "sequence",
    "tag code": "tag_code",
    "tag_code": "tag_code",
    "sequence": "sequence",
    "seq": "sequence",
    "order": "sequence",
    "parameters": "parameter",
    "parameter": "parameter",
    "parameter name": "parameter",
    "name": "parameter",
    "screen name": "description",
    "description": "description",
    "parameter description": "description",
    "tag_data_type": "datatype",
    "datatype": "datatype",
    "data type": "datatype",
    "type": "datatype",
    "offset_from_the_start_of_the_group_in_bytes": "offset",
    "offset": "offset",
    "expected offset": "offset",
    "size": "size",
    "memcpy size": "size",
    "expected size": "size",
    "packet size": "packet_size",
    "configured bytes": "packet_size",
    "expected bytes": "packet_size",
    "min": "min_value",
    "minimum": "min_value",
    "max": "max_value",
    "maximum": "max_value",
    "is shown value different": "shown_value_different",
    "is_shown_value_different": "shown_value_different",
}


@dataclass
class TypeInfo:
    name: str
    kind: str
    base: Optional[str] = None
    fields: Dict[str, "TypeInfo"] = field(default_factory=dict)
    array_range: Optional[Tuple[int, int]] = None
    string_len: Optional[int] = None


@dataclass
class SymbolInfo:
    name: str
    type_info: TypeInfo
    source_file: str


@dataclass
class ValidationIssue:
    group_code: str
    parameter: str
    description: str
    validation_type: str
    expected: str
    actual: str
    source_file: str
    line_number: str
    suggested_fix: str
    severity: str = "FAIL"
    condition: str = ""


@dataclass
class ParameterRow:
    group_code: int
    sequence: int
    parameter: str
    parameter_description: str
    data_type: str
    declared_data_type: str
    memcpy_size: Optional[int]
    declared_size: Optional[int]
    running_offset: Optional[int]
    offset_buffer: Optional[int]
    expected_offset: Optional[int]
    metadata_group_code: Optional[int]
    metadata_parameter: str
    metadata_description: str
    metadata_data_type: str
    metadata_size: Optional[int]
    metadata_offset: Optional[int]
    metadata_sequence: Optional[int]
    metadata_tag_code: Optional[int]
    metadata_min_value: Any
    metadata_max_value: Any
    metadata_shown_value_different: str
    metadata_sheet_name: str
    metadata_row_number: Optional[int]
    metadata_match_method: str
    increment_value: Optional[int]
    source_expression: str
    destination_expression: str
    offset_after_copy: Optional[int]
    status: str
    remarks: str
    validation_type: str
    expected_value: str
    actual_value: str
    severity: str
    source_file: str
    line_number: Optional[int]
    # Sequence evidence added by the offset-sequence fix. These fields are
    # populated from PacketParameter without changing the existing validation
    # decisions.
    increment_line_number: Optional[int] = None
    increment_relation: str = ""
    sequence_validation: str = "NOT FOUND"
    transfer_method: str = "memcpy"
    write_evidence: List[dict] = field(default_factory=list)
    condition_context: str = ""
    metadata_primary_path: bool = True


@dataclass
class PacketParameter:
    group_code: int
    group_description: str
    sequence: int
    parameter_expr: str
    parameter_name: str
    parameter_description: str
    src_expr: str
    dest_expr: str
    size_expr: str
    memcpy_size: Optional[int]
    expected_size: Optional[int]
    resolved_type_name: str
    source_exists: bool
    destination_valid: bool
    running_offset: Optional[int]
    expected_offset: Optional[int]
    offset_after_copy: Optional[int]
    increment_value: Optional[int]
    source_file: str
    line_number: int
    # Sequence-aware offset tracking. These fields only add evidence; the
    # existing memcpy/type/offset validation remains unchanged.
    increment_line_number: Optional[int] = None
    increment_relation: str = ""
    sequence_validation: str = "NOT FOUND"
    transfer_method: str = "memcpy"
    write_evidence: List[dict] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    remarks: List[str] = field(default_factory=list)
    condition_context: str = ""


@dataclass
class GroupResult:
    code: int
    description: str
    configured_bytes: Optional[int]
    configured_msb: Optional[int]
    configured_lsb: Optional[int]
    expected_bytes: Optional[int]
    calculated_bytes: int
    total_parameters: int
    pass_count: int
    fail_count: int
    warning_count: int
    overall_status: str
    calculated_offset_bytes: Optional[int] = None
    parameters: List[ParameterRow] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    packet_variants: List[dict] = field(default_factory=list)


@dataclass
class MetadataParameter:
    group_code: int
    sequence: Optional[int]
    tag_code: Optional[int]
    parameter: str
    description: str
    datatype: str
    offset: Optional[int]
    size: Optional[int]
    packet_size: Optional[int]
    min_value: Any
    max_value: Any
    shown_value_different: str
    sheet_name: str
    row_number: int
    units: str = ""
    screen_name: str = ""
    machine_variants: str = ""
    offset_factor: Any = ""
    scale_factor: Any = ""
    is_visible: Any = ""
    is_writable: Any = ""


@dataclass
class MetadataInfo:
    path: Optional[Path]
    rows: Dict[int, List[MetadataParameter]]
    issues: List[ValidationIssue]
    workbook: Optional[Workbook] = None


@dataclass
class DropdownRow:
    family: str
    page_file: str
    control_name: str
    index_datapoint: str
    logic_parameter: str
    group_code: Optional[int]
    sequence: Optional[int]
    text_group: str
    text_group_name: str
    text_index_offset: str
    text_group_source: str
    text_group_index: str
    text_group_values: str


@dataclass
class TextGroupRow:
    family: str
    text_group: str
    index: Optional[int]
    source_file: str
    values: str


def emit_status(message: str) -> None:
    if STATUS_CALLBACK is not None:
        try:
            STATUS_CALLBACK(message)
        except Exception:
            pass


def emit_progress(percent: int, message: str) -> None:
    emit_status(f"PROGRESS|{percent}|{message}")


def choose_preferred_path(candidates: List[Path], preferred_terms: Tuple[str, ...]) -> Optional[Path]:
    if not candidates:
        return None
    normalized = sorted(candidates)
    for term in preferred_terms:
        matched = [path for path in normalized if term in str(path).lower()]
        if len(matched) == 1:
            return matched[0]
    return normalized[0]


def safe_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except (ValueError, RuntimeError):
        return str(path)


IGNORED_PROJECT_DIRECTORIES = {"temp", "as", "binaries", "diagnosis"}


def is_ignored_project_path(path: Path) -> bool:
    """Exclude Automation Studio generated/diagnostic trees from source discovery."""
    try:
        parts = path.resolve().relative_to(ROOT.resolve()).parts
    except (ValueError, RuntimeError, OSError):
        parts = path.parts
    return any(part.casefold() in IGNORED_PROJECT_DIRECTORIES for part in parts)


def initialize_project_context(selected_root: Path, selected_metadata: Optional[Path] = None, selected_project_kb: Optional[Path] = None) -> None:
    global ROOT, LOGICAL_ROOT, PROJECT_NAME, OUTPUT_WORKBOOK, PLC_PACKET_FILE, PROJECT_APJ, PROJECT_GLOBAL_ROOTS, HMI_PAGE_ROOTS, HMI_TEXTGROUP_ROOTS, HMI_TARGET_NAME, VARIABLES, TYPES, SELECTED_METADATA_FILE, KNOWLEDGE_PROJECT_FILE

    ROOT = selected_root.resolve()

    if ROOT.name.lower() == "ai_qc" and (ROOT.parent / "Logical").is_dir():
        ROOT = ROOT.parent.resolve()
    elif not (ROOT / "Logical").is_dir() and (ROOT.parent / "Logical").is_dir():
        ROOT = ROOT.parent.resolve()

    SELECTED_METADATA_FILE = selected_metadata.resolve() if selected_metadata is not None and selected_metadata.exists() else None
    if selected_project_kb is not None and selected_project_kb.exists():
        KNOWLEDGE_PROJECT_FILE = selected_project_kb.resolve()
    else:
        KNOWLEDGE_PROJECT_FILE = None
    emit_status("Project uploaded")
    emit_status(f"Project root: {ROOT}")

    apj_candidates = sorted(path for path in ROOT.rglob("*.apj") if not is_ignored_project_path(path))
    PROJECT_APJ = choose_preferred_path(apj_candidates, (ROOT.name.lower(),))
    PROJECT_NAME = ROOT.name

    logical_candidates = [path for path in ROOT.rglob("*") if path.is_dir() and path.name.lower() == "logical" and not is_ignored_project_path(path)]
    LOGICAL_ROOT = choose_preferred_path(logical_candidates, ()) or (ROOT / "Logical")
    HMI_PAGE_ROOTS, HMI_TEXTGROUP_ROOTS, HMI_TARGET_NAME = discover_active_hmi_roots()
    emit_status(f"HMI target selected: {HMI_TARGET_NAME}")

    plc_candidates = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_ignored_project_path(path):
            continue
        name = path.name.lower()
        parent = path.parent.name.lower()
        if name == "mms_nw_rcyclic.st":
            plc_candidates.append(path)
        elif name == "cyclic.st" and parent == "mms_nw_r":
            plc_candidates.append(path)
        elif name == "mms_nw_r.st" and parent == "mms_nw_r":
            # Some Automation Studio projects use the task name as the cyclic
            # source filename. Confirm the packet CASE before selecting it so
            # an unrelated same-named file cannot become the packet source.
            try:
                source_head = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                source_head = ""
            if re.search(r"\bCASE\s+nw_group_code\s+OF\b", source_head, re.I):
                plc_candidates.append(path)
        elif name == "mms_nw_r.src":
            # Legacy project format used by paths such as *.pgp\pgm\TRIAL_01\CPU\mms_nw_r.src
            plc_candidates.append(path)

    PLC_PACKET_FILE = choose_preferred_path(plc_candidates, ("spinconnect", "spin connect", "mms_nw_r")) or (LOGICAL_ROOT / "mms_nw_rCyclic.st")
    emit_status("Project scan start")
    emit_status(f"Packet source selected: {PLC_PACKET_FILE}")

    PROJECT_GLOBAL_ROOTS = [path for path in ROOT.rglob("*") if path.is_dir() and path.name.lower() in {"logical", "global"} and not is_ignored_project_path(path)]
    if not PROJECT_GLOBAL_ROOTS:
        PROJECT_GLOBAL_ROOTS = [ROOT]

    output_dir = ROOT / "AI_QC"
    output_dir.mkdir(exist_ok=True)
    OUTPUT_WORKBOOK = output_dir / f"{PROJECT_NAME}.xlsx"

    VARIABLES, TYPES = parse_symbol_files()
    metadata_test = detect_metadata_workbook()

    if metadata_test is None:
        emit_status("Metadata workbook not found, skipping metadata comparison")
    else:
        emit_status(f"Metadata workbook selected: {metadata_test}")

    dereference_type_name.cache_clear()
    resolve_type_info.cache_clear()
    size_from_type_expr.cache_clear()


def discover_active_hmi_roots() -> Tuple[List[Path], List[Path], str]:
    """Select the display family indicated by the physical configuration.

    Shared VC resources remain available for TextGroups. If the project does
    not provide enough physical evidence, retain the conservative behaviour of
    scanning all logical display targets instead of silently excluding one.
    """
    if not LOGICAL_ROOT.exists():
        return [ROOT], [ROOT], "All discovered HMI targets"
    physical_text = ""
    physical = ROOT / "Physical"
    try:
        from python_engine.project_info import local_project_details
    except ModuleNotFoundError:
        from project_info import local_project_details
    identity = local_project_details(ROOT)
    active = identity.get("activeConfiguration")
    if active and (physical / active).is_dir():
        physical = physical / active
    screen = identity.get("screenFolder")
    if screen and (LOGICAL_ROOT / screen).is_dir():
        page_roots = [LOGICAL_ROOT / screen]
        shared = LOGICAL_ROOT / "VCShared"
        return page_roots, page_roots + ([shared] if shared.exists() else []), screen
    if physical.exists():
        for path in list(physical.rglob("*.pkg")) + list(physical.rglob("*.per")):
            try:
                physical_text += "\n" + path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
    target_terms = []
    low = physical_text.lower()
    if "4ppc70" in low or "c70_" in low or "c70config" in low:
        target_terms.append("c70")
    if "t30" in low or "4ppc30" in low or "t30_" in low:
        target_terms.append("t30")
    logical_dirs = [path for path in LOGICAL_ROOT.iterdir() if path.is_dir()]
    page_roots = [path for path in logical_dirs if any(path.name.lower().startswith(term) for term in target_terms)]
    if not page_roots:
        page_roots = [LOGICAL_ROOT]
        target_name = "All discovered HMI targets"
    else:
        target_name = ", ".join(path.name for path in page_roots)
    shared = LOGICAL_ROOT / "VCShared"
    text_roots = list(page_roots)
    if shared.exists() and shared not in text_roots:
        text_roots.append(shared)
    return page_roots, text_roots, target_name


def strip_comments(line: str) -> str:
    line = re.sub(r"\(\*.*?\*\)", "", line)
    if "//" in line:
        line = line.split("//", 1)[0]
    return line.rstrip()


def extract_comment(line: str) -> Optional[str]:
    match = re.search(r"\(\*(.*?)\*\)", line)
    return match.group(1).strip() if match else None


def packet_code_lines(text: str) -> List[str]:
    """Mask ST comments without shifting source lines.

    Automation Studio packet sources in the supported projects use non-nested
    ``(* ... *)`` comments. Some legacy comments contain a second ``(*`` as
    decoration before the first closing ``*)``. Treating that decoration as a
    nested comment masks the remainder of a large source file and drops later
    group codes, so the first closing marker always ends the comment.
    """
    depth = 0
    cursor = 0
    parts = []
    quote = ""
    while cursor < len(text):
        pair = text[cursor:cursor + 2]
        char = text[cursor]
        if depth:
            if pair != "*)":
                parts.append(char if char in "\r\n" else " ")
                cursor += 1
                continue
            depth = 0
            parts.append("  ")
            cursor += 2
        elif quote:
            parts.append(char)
            cursor += 1
            # IEC string literals do not continue across source lines. Reset
            # after a malformed/unmatched quote so comments on later lines are
            # still masked and cannot become packet parameters.
            if char in "\r\n":
                quote = ""
            elif char == quote:
                if cursor < len(text) and text[cursor] == quote:
                    parts.append(text[cursor])
                    cursor += 1
                else:
                    quote = ""
        elif pair == "(*":
            depth += 1
            parts.append("  ")
            cursor += 2
        elif pair == "//":
            end = text.find("\n", cursor)
            end = len(text) if end < 0 else end
            parts.append(" " * (end - cursor))
            cursor = end
        else:
            if char in "'\"":
                quote = char
            parts.append(char)
            cursor += 1
    return "".join(parts).split("\n")


def normalize_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


KNOWLEDGE_ROOT = Path(os.getenv('USOPP_DATA_ROOT') or Path(__file__).resolve().parent.parent) / "knowledge"
KNOWLEDGE_MASTER_FILE = KNOWLEDGE_ROOT / "master" / "parameter_mappings.json"
KNOWLEDGE_MASTER_DROPDOWN_FILE = KNOWLEDGE_ROOT / "master" / "dropdown_mappings.json"
KNOWLEDGE_MASTER_MIN_MAX_FILE = KNOWLEDGE_ROOT / "master" / "min_max_mappings.json"
KNOWLEDGE_PROJECT_FILE: Optional[Path] = None
ACTIVE_MACHINE_DEPARTMENT = 'All'

def _machine_mapping_scope(mapping: dict) -> bool:
    configured=str(mapping.get('machine_department') or mapping.get('MACHINE_DEPARTMENT') or 'All').strip() or 'All'
    if ACTIVE_MACHINE_DEPARTMENT.casefold()=='all':
        return configured.casefold()=='all'
    return configured.casefold() in ('all',ACTIVE_MACHINE_DEPARTMENT.casefold())

def load_parameter_mappings(path: Optional[Path]) -> List[dict]:
    try:
        if path is None or not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        mappings = data.get("mappings", []) if isinstance(data, dict) else []
        return [m for m in mappings if isinstance(m, dict) and m.get("plc_parameter") and m.get("metadata_parameter")]
    except Exception:
        return []

def load_project_parameter_mappings() -> List[dict]:
    return load_parameter_mappings(KNOWLEDGE_PROJECT_FILE)

def load_master_parameter_mappings() -> List[dict]:
    rows=load_parameter_mappings(KNOWLEDGE_MASTER_FILE)
    selected=[row for row in rows if _machine_mapping_scope(row)]
    if ACTIVE_MACHINE_DEPARTMENT.casefold()!='all':
        selected.sort(key=lambda row: str(row.get('machine_department') or 'All').casefold()=='all')
    return selected

def _master_value(mapping: dict, *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
        for candidate in (key.upper(), key.lower()):
            if candidate in mapping and mapping.get(candidate) not in (None, ""):
                return mapping.get(candidate)
    return default

def master_metadata_fields(metadata_parameter: str) -> Dict[str, Any]:
    """Return approved metadata field overrides keyed by generated metadata parameter."""
    target = normalize_name(metadata_parameter)
    if not target:
        return {}
    for mapping in load_master_parameter_mappings():
        candidates = (mapping.get("metadata_parameter"), mapping.get("parameter"), mapping.get("name"))
        if not any(target == normalize_name(str(v or "")) for v in candidates):
            continue
        return {
            "units": _master_value(mapping, "units", "UNITS", default=""),
            "offset_factor": _master_value(mapping, "offset_factor", "OFFSET_FACTOR", default=1),
            "scale_factor": _master_value(mapping, "scale_factor", "SCALE_FACTOR", default=1),
            "is_visible": _master_value(mapping, "is_visible", "IS_VISIBLE", default="YES"),
            "is_writable": _master_value(mapping, "is_writable", "IS_WRITABLE", default="NO"),
        }
    return {}

def metadata_output_type(value: str, group_code=None) -> str:
    """Normalize generated metadata datatype to the metadata standard."""
    raw = str(value or "").strip()
    # GC 30 alarm bytes must remain BYTE in the workbook as in the JSON.
    # Generic PLC alias normalization treats BYTE as USINT for size checks.
    if str(group_code).strip() in ("30", "30.0"):
        return "BYTE"
    # Targeted cleanup for the malformed legacy token seen in generated
    # metadata. It is a REAL datatype; do not expose the concatenated
    # REDUNDUNREPLICABLE token in the metadata workbook/view.
    upper = raw.upper()
    # Some legacy symbol/type exports can concatenate a non-datatype token
    # with REAL (for example REDUNDUNREPLICABLEREAL). Metadata must expose
    # only the engineering datatype. Keep this normalization deliberately
    # narrow so no unrelated PLC datatype is changed.
    if "REDUNDUNREPLICABLE" in upper and upper.endswith("REAL"):
        return "REAL"
    if upper == "REDUNDUNREPLICABLEREAL":
        return "REAL"
    if re.match(r"^(STRING|NCHAR|CHAR|VARCHAR)\s*(?:\[?\d+\]?|\(\d+\))?$", raw, re.IGNORECASE):
        return "STRING"
    normalized = normalize_type_name(raw)
    # Legacy AS 2.7 exports can flatten ARRAY [0..N] OF STRING(1) into tokens
    # such as ARRAY015OFSTRING1. Metadata uses STRING; its standard capacity is
    # 50 bytes while the packet copy size remains the authoritative wire size.
    if re.fullmatch(r"ARRAY\d+OFSTRING(?:1|\[1\])?", normalized):
        return "STRING"
    return "STRING" if normalized.startswith("STRING[") else normalized

def load_master_dropdown_mappings() -> List[dict]:
    """Load approved PLC comment/tag to Sheet2 value mappings."""
    try:
        if not KNOWLEDGE_MASTER_DROPDOWN_FILE.exists():
            return []
        data = json.loads(KNOWLEDGE_MASTER_DROPDOWN_FILE.read_text(encoding="utf-8"))
        mappings = data.get("mappings", []) if isinstance(data, dict) else []
        selected = [
            mapping for mapping in mappings
            if isinstance(mapping, dict)
            and mapping.get("plc_parameter")
            and mapping.get("plc_tag")
            and _machine_mapping_scope(mapping)
            and isinstance(mapping.get("mapping"), list)
        ]
        if ACTIVE_MACHINE_DEPARTMENT.casefold()!='all':
            selected.sort(key=lambda mapping: str(mapping.get('machine_department') or 'All').casefold()=='all')
        return selected
    except Exception:
        return []

def master_dropdown_pairs(plc_parameter: str, plc_tag: str) -> List[Tuple[str, str]]:
    """Get an approved dropdown only when its PLC comment and tag both match."""
    parameter_norm = normalize_name(plc_parameter)
    tag_norm = normalize_name(plc_tag)
    for mapping in load_master_dropdown_mappings():
        if (
            parameter_norm != normalize_name(str(mapping.get("plc_parameter", "")))
            or tag_norm != normalize_name(str(mapping.get("plc_tag", "")))
        ):
            continue
        pairs = []
        for item in mapping["mapping"]:
            if not isinstance(item, dict) or "PLCVAL" not in item or "SHOWNVAL" not in item:
                continue
            pairs.append((str(item["PLCVAL"]), str(item["SHOWNVAL"]).strip()))
        if pairs:
            return pairs
    return []


def master_min_max_values(plc_parameter: str, plc_tag: str) -> Tuple[Optional[Any], Optional[Any]]:
    """Return approved fallback limits only for an exact PLC comment/tag match."""
    try:
        if not KNOWLEDGE_MASTER_MIN_MAX_FILE.exists():
            return None, None
        data = json.loads(KNOWLEDGE_MASTER_MIN_MAX_FILE.read_text(encoding="utf-8"))
        mappings = data.get("mappings", []) if isinstance(data, dict) else []
    except Exception:
        return None, None
    parameter_norm = normalize_name(plc_parameter)
    tag_norm = normalize_name(plc_tag)
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        if (
            parameter_norm != normalize_name(str(mapping.get("plc_parameter", "")))
            or tag_norm != normalize_name(str(mapping.get("plc_tag", "")))
        ):
            continue
        minimum = mapping.get("min")
        maximum = mapping.get("max")
        return (None if minimum in (None, "") else minimum, None if maximum in (None, "") else maximum)
    return None, None


def resolved_min_max(plc_parameter: str, plc_tag: str, hmi_info: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any], str]:
    """Prefer explicit HMI limits; use approved master limits only as fallback."""
    def valid(value: Any) -> Optional[Any]:
        if value is None or str(value).strip().casefold() in {"", "none", "null", "<null>"}:
            return None
        return value
    hmi_min, hmi_max = valid(hmi_info.get("hmiMin")), valid(hmi_info.get("hmiMax"))
    master_min, master_max = master_min_max_values(plc_parameter, plc_tag)
    minimum, maximum = hmi_min if hmi_min is not None else master_min, hmi_max if hmi_max is not None else master_max
    source = "HMI" if hmi_min is not None or hmi_max is not None else ("Master MIN/MAX" if master_min is not None or master_max is not None else "Not configured")
    return minimum, maximum, source

def description_match(logic_description: str, metadata_description: str) -> bool:
    """Strict text identity comparison after case/separator normalization."""
    return metadata_text_exact(logic_description, metadata_description)

def metadata_text_exact(logic_comment: str, metadata_parameter: str) -> bool:
    """Exact metadata identity: PLC logic comment -> metadata Parameter.

    Case and separators are normalized, but partial/token-subset/fuzzy matches
    are intentionally rejected so similar names cannot silently be substituted.
    """
    logic = normalize_name(logic_comment)
    meta = normalize_name(metadata_parameter)
    return bool(logic and meta and logic == meta)

def plc_parameter_value(parameter) -> str:
    """User-facing PLC Parameter: logic comment, with PLC tag fallback."""
    comment = str(getattr(parameter, "parameter_description", "") or "").strip()
    tag = str(getattr(parameter, "parameter_name", getattr(parameter, "parameter", "")) or "").strip()
    if comment and normalize_name(comment) not in {"NODESCRIPTION", "NOTAVAILABLE", "NONE"}:
        return comment
    return tag


def generated_metadata_parameter(plc_parameter: str, plc_tag: str) -> Tuple[str, str]:
    """Return the approved metadata name only for an exact PLC comment/tag pair.

    A master mapping is an engineering-approved alias, such as
    ``Hank leveller`` / ``Autoleveller_ON_OFF`` -> ``Auto leveller``.
    Both the PLC logic comment and PLC tag must match; a match on only one
    field must not rename generated metadata.
    """
    parameter_norm = normalize_name(plc_parameter)
    tag_norm = normalize_name(plc_tag)
    if not parameter_norm or not tag_norm:
        return plc_parameter, "PLC name"

    for mapping in load_master_parameter_mappings():
        mapping_parameter = str(mapping.get("plc_parameter", "")).strip()
        mapping_tag = str(mapping.get("plc_tag", "")).strip()
        metadata_parameter = str(mapping.get("metadata_parameter", "")).strip()
        if (
            metadata_parameter
            and parameter_norm == normalize_name(mapping_parameter)
            and tag_norm == normalize_name(mapping_tag)
        ):
            return metadata_parameter, "Master Knowledge configured mapping"
    return plc_parameter, "PLC name"


def normalize_header(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9]+", " ", str(value or "").strip()).strip().lower()


def normalize_type_name(value: str) -> str:
    normalized = normalize_name(value)
    aliases = {
        "FLOAT": "REAL",
        "REAL": "REAL",
        "NCHAR": "STRING",
        "STRING": "STRING",
        "INTEGER": "INT",
        "INT": "INT",
        "UINT": "UINT",
        "UNSIGNED INT": "UINT",
        "UNSIGNED INTEGER": "UINT",
        "DINT": "DINT",
        "INT32": "DINT",
        "SIGNED INT32": "DINT",
        "SIGNED INTEGER 32": "DINT",
        "BIGINT": "DINT",
        "BOOL": "BOOL",
        "BOOLEAN": "BOOL",
        "USINT": "USINT",
        "BYTE": "USINT",
        "UINT8": "USINT",
        "UNSIGNED INT8": "USINT",
        "UNSIGNED INTEGER 8": "USINT",
    }
    return aliases.get(normalized, normalized)


def normalize_bool_metadata_mode(value: Any) -> str:
    """Return the supported metadata representation for a PLC BOOL tag."""
    return "USINT" if str(value or "").strip().upper() == "USINT" else "BOOL"


def metadata_type_compatibility(logic_type: str, metadata_type: str, group_code: Optional[int] = None) -> str:
    logic_raw = normalize_name(logic_type or "")
    meta_raw = normalize_name(metadata_type or "")
    logic_norm = normalize_type_name(logic_type or "")
    meta_norm = normalize_type_name(metadata_type or "")

    if not logic_raw or not meta_raw:
        return "MISMATCH"

    # Group 30 is the alarm/fault byte array. PLC code commonly declares the
    # temporary array as USINT, then packs individual alarm bits into it. Its
    # metadata contract is always BYTE; it must never be validated as USINT.
    if group_code == 30:
        return "EXACT" if meta_raw == "BYTE" else "MISMATCH"

    # Outside Group 30, PLC BOOL representation is an engineer-selected
    # metadata contract. Other PLC datatypes retain their declared type.
    if logic_norm == "BOOL":
        expected = normalize_bool_metadata_mode(BOOL_METADATA_MODE)
        return "EXACT" if meta_raw == expected else "MISMATCH"
    if logic_norm == meta_norm:
        return "EXACT"

    one_byte = {"BOOL", "BOOLEAN", "USINT", "BYTE", "UINT8", "UNSIGNED INT8", "UNSIGNED INTEGER 8"}
    if logic_raw in one_byte and meta_raw in one_byte:
        return "WARNING"

    two_byte = {"INT", "INTEGER", "UINT", "UNSIGNED INT", "UNSIGNED INTEGER", "INT16", "UINT16", "SIGNED INT16", "UNSIGNED INT16"}
    if logic_raw in two_byte and meta_raw in two_byte:
        return "WARNING"

    def is_string_family(value):
        return bool(re.match(r"^(STRING|NCHAR|CHAR|VARCHAR)(?:\s*\[?\d+\]?)?$", value))

    if is_string_family(logic_raw) and is_string_family(meta_raw):
        return "WARNING"

    four_byte = {"REAL", "FLOAT", "DINT", "INT32", "SIGNED INT32", "SIGNED INTEGER 32", "BIGINT"}
    if logic_raw in four_byte and meta_raw in four_byte:
        return "WARNING"

    return "MISMATCH"


def normalize_parameter_expr(expr: str) -> str:
    return re.sub(r"\s+", "", expr or "")


def to_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_last_bracket_value(value: str) -> str:
    matches = re.findall(r"\[(.*?)\]", value or "")
    return matches[-1].strip() if matches else ""


def normalize_compared_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def sanitize_sheet_title(title: str) -> str:
    safe = re.sub(r"[\[\]\*:/\\\?]", "_", title).strip()
    return safe[:31] if len(safe) > 31 else safe


def get_xml_property_value(node, property_name: str) -> str:
    for child in node.findall("./{*}Property"):
        if child.get("Name") == property_name:
            return child.get("Value") or ""
    return ""


def parse_type_expr(expr: str) -> TypeInfo:
    # B&R declaration attributes describe storage/compiler behaviour, not the
    # IEC datatype. Strip them before resolving sizes, arrays and report names.
    expr = re.sub(r"\{[^{}]*\}", " ", expr).strip().rstrip(";").strip()
    # Legacy compact array exports describe capacity as BOOL[0..400].
    # Resolve them as arrays rather than an unknown datatype alias.
    compact_array = re.fullmatch(r"([A-Za-z_]\w*)\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]", expr)
    if compact_array:
        base, start, end = compact_array.groups()
        expr = f"ARRAY[{start}..{end}] OF {base}"
    array_match = re.match(r"ARRAY\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s+OF\s+(.+)$", expr, re.IGNORECASE)
    if array_match:
        start, end, base_expr = array_match.groups()
        nested = parse_type_expr(base_expr)
        return TypeInfo(
            name=expr,
            kind="array",
            base=nested.name,
            fields=nested.fields,
            array_range=(int(start), int(end)),
            string_len=nested.string_len,
        )
    string_match = re.match(r"STRING\s*\[\s*(\d+)\s*\]$", expr, re.IGNORECASE)
    if string_match:
        return TypeInfo(name=expr, kind="string", string_len=int(string_match.group(1)))
    return TypeInfo(name=expr.strip(), kind="alias")


def parse_var_sections(text: str) -> Dict[str, TypeInfo]:
    symbols: Dict[str, TypeInfo] = {}
    in_var = False
    for raw_line in text.splitlines():
        line = strip_comments(raw_line).strip()
        upper = line.upper()
        if upper.startswith("VAR"):
            in_var = True
            continue
        if upper == "END_VAR":
            in_var = False
            continue
        if not in_var:
            continue
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)(?:\s*:=.+)?;$", line)
        if match:
            name, type_expr = match.groups()
            symbols[name] = parse_type_expr(type_expr)
    return symbols


def parse_as27_cpu_symbols(text: str) -> Dict[str, TypeInfo]:
    """Parse Automation Studio 2.7 global declarations exported in CPU.txt."""
    symbols: Dict[str, TypeInfo] = {}
    declaration = re.compile(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s+%[MC](?:B|W|L|X)(?:\d+)?\s*:\s*(.+?)\s*;\s*$",
        re.IGNORECASE,
    )
    for raw_line in text.splitlines():
        # AS 2.7 uses ``!`` for the trailing declaration comment in CPU.txt.
        line = raw_line.split("!", 1)[0].strip()
        match = declaration.match(line)
        if not match:
            continue
        name, type_expr = match.groups()
        type_expr = re.sub(r"\bSTRING\s*\(\s*(\d+)\s*\)", r"STRING[\1]", type_expr, flags=re.IGNORECASE)
        type_expr = re.sub(r"\s*:=.*$", "", type_expr).strip()
        symbols[name] = parse_type_expr(type_expr)
    return symbols


def parse_typedefs(text: str) -> Dict[str, TypeInfo]:
    types: Dict[str, TypeInfo] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = strip_comments(lines[i]).strip()
        struct_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*STRUCT$", line, re.IGNORECASE)
        alias_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+);$", line)
        if struct_match:
            type_name = struct_match.group(1)
            fields: Dict[str, TypeInfo] = {}
            i += 1
            while i < len(lines):
                inner = strip_comments(lines[i]).strip()
                if inner.upper() == "END_STRUCT;":
                    break
                field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)(?:\s*:=.+)?;$", inner)
                if field_match:
                    field_name, field_type = field_match.groups()
                    fields[field_name] = parse_type_expr(field_type)
                i += 1
            types[type_name] = TypeInfo(name=type_name, kind="struct", fields=fields)
        elif alias_match and alias_match.group(1).upper() not in {"TYPE", "END_TYPE"}:
            type_name, type_expr = alias_match.groups()
            parsed = parse_type_expr(type_expr)
            parsed.name = type_name
            types[type_name] = parsed
        i += 1
    return types


def parse_fun_blocks(text: str) -> Dict[str, TypeInfo]:
    blocks: Dict[str, TypeInfo] = {}
    chunks = re.split(r"(?=FUNCTION_BLOCK\s+)", text, flags=re.IGNORECASE)
    for chunk in chunks:
        header = re.match(r"FUNCTION_BLOCK\s+([A-Za-z_][A-Za-z0-9_]*)", chunk.strip(), re.IGNORECASE)
        if not header:
            continue
        block_name = header.group(1)
        fields = parse_var_sections(chunk)
        blocks[block_name] = TypeInfo(name=block_name, kind="struct", fields=fields)
    return blocks


def strip_c_comments(text: str) -> str:
    """Remove C comments while preserving newlines for source diagnostics."""
    text = re.sub(
        r"/\*.*?\*/",
        lambda match: re.sub(r"[^\r\n]", " ", match.group(0)),
        text,
        flags=re.DOTALL,
    )
    return re.sub(r"//[^\r\n]*", "", text)


def split_c_declarators(value: str) -> List[str]:
    """Split comma declarators without splitting a bracketed array suffix."""
    parts: List[str] = []
    start = 0
    bracket_depth = 0
    for index, char in enumerate(value):
        if char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        elif char == "," and bracket_depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def c_declaration_type(type_name: str, dimensions: List[int]) -> TypeInfo:
    """Translate a B&R C global declaration into the IEC type model."""
    base = re.sub(r"\s+", " ", type_name.strip())
    c_aliases = {
        "float": "REAL", "double": "LREAL", "char": "SINT", "signed char": "SINT",
        "unsigned char": "USINT", "short": "INT", "unsigned short": "UINT",
        "int": "DINT", "unsigned int": "UDINT", "long": "DINT",
        "unsigned long": "UDINT", "plcbit": "BOOL",
    }
    base = c_aliases.get(base.casefold(), base)
    dims = list(dimensions)
    # B&R C declares an array of STRING values as STRING names[count][length].
    # Preserve the final bracket as the string capacity and the earlier
    # bracket(s) as array dimensions.
    if base.upper() == "STRING" and dims:
        type_expr = f"STRING[{dims.pop()}]"
    else:
        type_expr = base
    for dimension in reversed(dims):
        if dimension <= 0:
            return TypeInfo(name=type_expr, kind="alias")
        type_expr = f"ARRAY[0..{dimension - 1}] OF {type_expr}"
    return parse_type_expr(type_expr)


def parse_as27_c_struct_types(text: str) -> Dict[str, TypeInfo]:
    """Recover legacy function-block and structure members exported in CPU.txt."""
    types: Dict[str, TypeInfo] = {}
    clean = strip_c_comments(text)
    struct_pattern = re.compile(
        r"\btypedef\s+struct\s+(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\s*"
        r"\{(?P<body>.*?)\}\s*(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    field_pattern = re.compile(
        r"^(?P<type>.+?)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
        r"(?P<dimensions>(?:\s*\[\s*\d+\s*\])*)$"
    )
    for match in struct_pattern.finditer(clean):
        fields: Dict[str, TypeInfo] = {}
        for statement in match.group("body").split(";"):
            statement = re.sub(r"\s+", " ", statement).strip()
            field = field_pattern.match(statement)
            if not field:
                continue
            type_name = re.sub(r"^struct\s+", "", field.group("type"), flags=re.IGNORECASE)
            dimensions = [int(value) for value in re.findall(r"\[\s*(\d+)\s*\]", field.group("dimensions"))]
            fields[field.group("name")] = c_declaration_type(type_name, dimensions)
        if not fields:
            continue
        tag = match.group("tag")
        alias = match.group("alias")
        struct_type = TypeInfo(name=alias, kind="struct", fields=fields)
        types[tag] = struct_type
        types[alias] = struct_type
        legacy_name = re.sub(r"_typ$", "", alias, flags=re.IGNORECASE)
        types[f"_${legacy_name}"] = struct_type
    return types


def parse_c_global_declarations(text: str) -> Dict[str, TypeInfo]:
    """Parse Automation Runtime ``_GLOBAL`` declarations from C modules."""
    symbols: Dict[str, TypeInfo] = {}
    clean = strip_c_comments(text)
    # Automation Studio accepts the storage qualifier on either side of
    # the datatype: _GLOBAL REAL value and REAL _GLOBAL value.
    # Anchor to declaration boundaries so a match cannot borrow a type from
    # the previous declaration, comment or preprocessor directive.
    c_type = r"(?:(?:unsigned|signed)\s+(?:char|short|int|long)|[A-Za-z_][A-Za-z0-9_]*)\s*\*?"
    declaration_pattern = re.compile(
        r"(?:^|(?<=[;{}]))\s*(?:"
        r"_GLOBAL(?:_RETAIN)?\s+(?P<prefix_type>" + c_type + r")"
        r"|(?P<suffix_type>" + c_type + r")\s+_GLOBAL(?:_RETAIN)?)\s+"
        r"(?P<variables>[^;]+);",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in declaration_pattern.finditer(clean):
        type_name = (match.group("prefix_type") or match.group("suffix_type")).strip()
        for raw_declarator in split_c_declarators(match.group("variables")):
            declarator = re.sub(r"\b_VAR_RETAIN\b", "", raw_declarator, flags=re.IGNORECASE)
            declarator = declarator.split("=", 1)[0].strip().lstrip("*").strip()
            parsed = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_]*)\s*((?:\[\s*\d+\s*\]\s*)*)",
                declarator,
            )
            if not parsed:
                continue
            name, suffix = parsed.groups()
            dimensions = [int(value) for value in re.findall(r"\[\s*(\d+)\s*\]", suffix)]
            symbols[name] = c_declaration_type(type_name, dimensions)
    return symbols


def parse_symbol_files() -> Tuple[Dict[str, SymbolInfo], Dict[str, TypeInfo]]:
    """Load declared PLC symbols from both supported Automation Studio eras.

    Automation Studio 4.x normally stores declarations in ``.var/.typ/.fun``.
    Automation Studio 2.7 program groups can instead keep IEC declarations in
    a ``.pgp`` program-group file (for example ``LD_22120.pgp``).  Scan those
    legacy text files as a fallback first; dedicated .var/.typ/.fun files are
    still loaded afterwards and therefore remain the higher-priority source.
    """
    variables: Dict[str, SymbolInfo] = {}
    types: Dict[str, TypeInfo] = {}
    search_roots = PROJECT_GLOBAL_ROOTS or [LOGICAL_ROOT] or [ROOT]

    # AS 2.7 exports declarations in CPU.txt and sometimes incpi.txt using
    # address markers such as ``%MB``, ``%MW``, ``%ML`` and ``%MX``.
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_ignored_project_path(path) or path.name.casefold() not in {"cpu.txt", "incpi.txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, type_info in parse_as27_cpu_symbols(text).items():
                variables[name] = SymbolInfo(name=name, type_info=type_info, source_file=str(safe_relative_path(path)))
            types.update(parse_typedefs(text))
            types.update(parse_as27_c_struct_types(text))
        except Exception:
            continue

    # AS 2.7: IEC VAR / TYPE / FUNCTION_BLOCK content can be embedded in a
    # program-group file. Binary or non-text PGP files are harmless: decoding
    # with errors ignored simply yields no declaration matches.
    scanned_legacy: set[Path] = set()
    for base_root in search_roots:
        if not base_root.exists():
            continue
        for path in base_root.rglob("*.pgp"):
            if is_ignored_project_path(path):
                continue
            resolved = path.resolve()
            if resolved in scanned_legacy:
                continue
            scanned_legacy.add(resolved)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for name, type_info in parse_var_sections(text).items():
                    variables[name] = SymbolInfo(name=name, type_info=type_info, source_file=str(safe_relative_path(path)))
                types.update(parse_typedefs(text))
                types.update(parse_fun_blocks(text))
            except Exception:
                continue

    # B&R C modules can publish Automation Runtime globals with declarations
    # such as ``_GLOBAL REAL value1,value2;``. Load these as another fallback
    # before IEC .var files, which remain authoritative on name collisions.
    scanned_c: set[Path] = set()
    for base_root in search_roots:
        if not base_root.exists():
            continue
        for path in base_root.rglob("*.c"):
            if is_ignored_project_path(path):
                continue
            resolved = path.resolve()
            if resolved in scanned_c:
                continue
            scanned_c.add(resolved)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for name, type_info in parse_c_global_declarations(text).items():
                    variables[name] = SymbolInfo(
                        name=name,
                        type_info=type_info,
                        source_file=str(safe_relative_path(path)),
                    )
            except Exception:
                continue

    # AS 4.2 / standard IEC declaration files. They intentionally overwrite a
    # fallback declaration recovered from a legacy .pgp or C source file.
    for pattern in ("*.var", "*.typ", "*.fun"):
        for base_root in search_roots:
            if not base_root.exists():
                continue
            for path in base_root.rglob(pattern):
                if is_ignored_project_path(path):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    if pattern == "*.var":
                        parsed = parse_var_sections(text)
                        for name, type_info in parsed.items():
                            variables[name] = SymbolInfo(name=name, type_info=type_info, source_file=str(safe_relative_path(path)))
                    elif pattern == "*.typ":
                        types.update(parse_typedefs(text))
                    elif pattern == "*.fun":
                        types.update(parse_fun_blocks(text))
                except Exception:
                    continue
    return variables, types


VARIABLES: Dict[str, SymbolInfo] = {}
TYPES: Dict[str, TypeInfo] = {}


@lru_cache(maxsize=None)
def dereference_type_name(type_name: str) -> TypeInfo:
    current = TYPES.get(type_name)
    if current is None:
        parsed = parse_type_expr(type_name)
        current = parsed if parsed.kind != "alias" or parsed.name != type_name else TypeInfo(name=type_name, kind="alias")
    seen = set()
    while current.kind == "alias" and current.name not in BASE_TYPE_SIZES and current.name in TYPES:
        if current.name in seen:
            break
        seen.add(current.name)
        current = TYPES[current.name]
    return current


def resolve_path_segments(expr: str) -> Tuple[str, List[int], List[str]]:
    clean = expr.strip()
    raw_segments = clean.split(".")
    names: List[str] = []
    indexes: List[int] = []
    for segment in raw_segments:
        name_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", segment)
        if not name_match:
            continue
        names.append(name_match.group(1))
        indexes.extend(int(idx) for idx in re.findall(r"\[\s*(-?\d+)\s*\]", segment))
    base = names[0] if names else clean
    return base, indexes, names


def format_type_info(type_info: Optional[TypeInfo]) -> str:
    if type_info is None:
        return "UNKNOWN"
    if type_info.kind == "string":
        return f"STRING[{type_info.string_len}]"
    if type_info.kind == "array":
        base_name = type_info.base or "UNKNOWN"
        bounds = ""
        if type_info.array_range is not None:
            bounds = f"[{type_info.array_range[0]}..{type_info.array_range[1]}]"
        return f"ARRAY{bounds} OF {base_name}"
    return type_info.name


def format_parameter_copy_type(parameter_expr: str, memcpy_size: Optional[int], resolved_type: Optional[TypeInfo]) -> str:
    base_name, indexes, _ = resolve_path_segments(parameter_expr)
    symbol = VARIABLES.get(base_name)
    if symbol is not None:
        base_type = dereference_type(symbol.type_info)
        if base_type.kind == "array" and base_type.array_range is not None and memcpy_size is not None:
            total_size = size_from_type_info(base_type)
            element_type = dereference_type_name(base_type.base) if base_type.base else None
            element_size = size_from_type_info(element_type) if element_type is not None else BASE_TYPE_SIZES.get(base_type.base or "")
            if total_size is not None and element_size:
                if memcpy_size == total_size:
                    return format_type_info(base_type)
                if indexes and memcpy_size > element_size and memcpy_size % element_size == 0:
                    count = memcpy_size // element_size
                    start_index = indexes[-1]
                    end_index = start_index + count - 1
                    return f"ARRAY[{start_index}..{end_index}] OF {base_type.base or 'UNKNOWN'}"
    return format_type_info(resolved_type)


def global_serial_map(results: List[GroupResult]) -> Dict[int, int]:
    serials: Dict[int, int] = {}
    serial = 1
    for result in results:
        for row in result.parameters:
            serials[id(row)] = serial
            serial += 1
    return serials


@lru_cache(maxsize=None)
def resolve_type_info(expr: str) -> Optional[TypeInfo]:
    base_name, indexes, names = resolve_path_segments(expr)
    symbol = VARIABLES.get(base_name)
    current = symbol.type_info if symbol else TYPES.get(base_name)
    if current is None:
        return None
    current = dereference_type(current)
    name_index = 1
    remaining_indexes = list(indexes)
    while remaining_indexes:
        if current.kind != "array":
            break
        remaining_indexes.pop(0)
        if current.base:
            current = dereference_type_name(current.base)
        else:
            break
    while name_index < len(names):
        if current.kind == "array" and current.base:
            current = dereference_type_name(current.base)
            continue
        if current.kind != "struct":
            return None
        field = current.fields.get(names[name_index])
        if field is None:
            return None
        current = dereference_type(field)
        name_index += 1
        while remaining_indexes and current.kind == "array":
            remaining_indexes.pop(0)
            if current.base:
                current = dereference_type_name(current.base)
            else:
                break
    if remaining_indexes and current.kind == "array" and current.base:
        current = dereference_type_name(current.base)
    return current


def dereference_type(type_info: TypeInfo) -> TypeInfo:
    current = type_info
    seen = set()
    while current.kind == "alias" and current.name not in BASE_TYPE_SIZES and current.name in TYPES:
        if current.name in seen:
            break
        seen.add(current.name)
        current = TYPES[current.name]
    return current


@lru_cache(maxsize=None)
def size_from_type_expr(expr: str) -> Optional[int]:
    return size_from_type_info(resolve_type_info(expr))


def size_from_type_info(type_info: Optional[TypeInfo]) -> Optional[int]:
    if type_info is None:
        return None
    current = dereference_type(type_info)
    if current.kind == "string":
        return current.string_len
    if current.kind == "array":
        if current.array_range is None:
            return None
        base = dereference_type_name(current.base) if current.base and current.base in TYPES else TypeInfo(name=current.base or "", kind="alias")
        base_size = size_from_type_info(base if base.name else None)
        if base_size is None:
            base_size = BASE_TYPE_SIZES.get(current.base or "")
        if base_size is None:
            return None
        element_count = current.array_range[1] - current.array_range[0] + 1
        return base_size * element_count
    if current.name in BASE_TYPE_SIZES:
        return BASE_TYPE_SIZES[current.name]
    if current.kind == "struct":
        total = 0
        for field in current.fields.values():
            field_size = size_from_type_info(field)
            if field_size is None:
                return None
            total += field_size
        return total
    if current.name in TYPES:
        return size_from_type_info(TYPES[current.name])
    return None


def datatype_index() -> List[dict]:
    """Expose the declarations used by this validation for read-only browsing."""
    rows = []
    for symbol in sorted(VARIABLES.values(), key=lambda item: (item.name.casefold(), item.source_file)):
        try:
            size = size_from_type_info(symbol.type_info)
        except (RecursionError, ValueError, TypeError):
            size = None
        rows.append({"name": symbol.name, "dataType": format_type_info(symbol.type_info),
                     "size": size, "sourceFile": symbol.source_file})
    return rows


def element_size(expr: str) -> Optional[int]:
    base_name, indexes, names = resolve_path_segments(expr)
    symbol = VARIABLES.get(base_name)
    current = symbol.type_info if symbol else TYPES.get(base_name)
    if current is None:
        return None
    current = dereference_type(current)
    remaining_indexes = list(indexes)
    name_index = 1
    while True:
        if remaining_indexes and current.kind == "array":
            remaining_indexes.pop(0)
            if current.base:
                current = dereference_type_name(current.base)
                continue
        if name_index < len(names):
            if current.kind != "struct":
                return None
            field = current.fields.get(names[name_index])
            if field is None:
                return None
            current = dereference_type(field)
            name_index += 1
            continue
        break
    return size_from_type_info(current)


def expected_memcpy_size(parameter_expr: str, memcpy_size: Optional[int]) -> Optional[int]:
    resolved = resolve_type_info(parameter_expr)
    if resolved is None:
        return None

    resolved_base = dereference_type(resolved)
    if resolved_base.kind == "string":
        return 50

    base_name, _, _ = resolve_path_segments(parameter_expr)
    symbol = VARIABLES.get(base_name)
    base_type = symbol.type_info if symbol is not None else TYPES.get(base_name)
    base_type = dereference_type(base_type) if base_type is not None else None
    if base_type is not None and base_type.kind == "array" and memcpy_size is not None:
        capacity = size_from_type_info(base_type)
        element = dereference_type_name(base_type.base) if base_type.base and base_type.base in TYPES else None
        element_size = size_from_type_info(element) if element is not None else BASE_TYPE_SIZES.get(base_type.base or "")
        if capacity is not None and memcpy_size <= capacity:
            if element_size is None or element_size == 1 or memcpy_size % element_size == 0:
                return memcpy_size

    return size_from_type_info(resolved)


def evaluate_size_expr(size_expr: str, parameter_expr: str) -> Optional[int]:
    size_expr = size_expr.strip()
    if re.fullmatch(r"\d+", size_expr):
        return int(size_expr)
    sizeof_match = re.match(r"SIZEOF\((.+)\)$", size_expr, re.IGNORECASE)
    if sizeof_match:
        target = sizeof_match.group(1).strip()
        return size_from_type_expr(target)
    return element_size(parameter_expr)


def detect_metadata_workbook() -> Optional[Path]:
    if SELECTED_METADATA_FILE is not None and SELECTED_METADATA_FILE.exists():
        return SELECTED_METADATA_FILE
    return None


def _metadata_rows_from_values(sheet_name: str, rows, hidden_rows=None) -> List[MetadataParameter]:
    hidden_rows = hidden_rows or set()
    if not rows:
        return []
    headers = [normalize_header(cell) for cell in rows[0]]
    mapped: Dict[int, str] = {}
    for idx, header in enumerate(headers):
        if header in METADATA_HEADER_MAP:
            mapped[idx] = METADATA_HEADER_MAP[header]
    if not {"group_code", "parameter"}.issubset(set(mapped.values())):
        return []
    output=[]
    for row_number,row in enumerate(rows[1:],start=2):
        if row_number in hidden_rows or all(cell is None or str(cell).strip()=="" for cell in row):
            continue
        values={mapped[idx]:row[idx] for idx in mapped if idx < len(row)}
        # Reference 7.170 workbook columns: A=S NO., D=Parameters, E=UNITS,
        # F=MIN, G=MAX, H=TAG_CODE, I=GROUP_CODE, J=OFFSET, M=TAG_DATA_TYPE, X=IS_SHOWN_VALUE_DIFFERENT.
        fixed_sequence=row[0] if len(row)>0 else None
        fixed_parameter=row[3] if len(row)>3 else None
        fixed_tag_code=row[7] if len(row)>7 else None
        fixed_group_code=row[8] if len(row)>8 else None
        fixed_offset=row[9] if len(row)>9 else None
        fixed_datatype=row[12] if len(row)>12 else None
        fixed_min=row[5] if len(row)>5 else None
        fixed_max=row[6] if len(row)>6 else None
        fixed_shown=row[23] if len(row)>23 else None
        if fixed_parameter not in (None,"") and fixed_group_code not in (None,""):
            parameter=str(fixed_parameter).strip()
            group_code=to_int(fixed_group_code)
            sequence_value=to_int(fixed_sequence)
            tag_code_value=to_int(fixed_tag_code)
            offset_value=to_int(fixed_offset)
            datatype_value=str(fixed_datatype or "").strip()
            description_value=parameter
            min_value=fixed_min
            max_value=fixed_max
            shown_value=str(fixed_shown or "").strip()
        else:
            group_code=to_int(values.get("group_code"))
            sequence_value=to_int(values.get("sequence"))
            tag_code_value=to_int(values.get("tag_code")) or sequence_value
            parameter=str(values.get("parameter") or "").strip()
            offset_value=to_int(values.get("offset"))
            datatype_value=str(values.get("datatype") or "").strip()
            description_value=str(values.get("description") or "").strip() or "No Description"
            min_value=values.get("min_value")
            max_value=values.get("max_value")
            shown_value=str(values.get("shown_value_different") or "").strip()
        if group_code is None or not parameter:
            continue
        item = MetadataParameter(group_code, sequence_value, tag_code_value, parameter, description_value, datatype_value, offset_value,
                                 to_int(values.get("size")), to_int(values.get("packet_size")), min_value, max_value, shown_value, sheet_name, row_number)
        item.units = str(row[4] if len(row)>4 and row[4] is not None else "").strip()
        item.screen_name = str(row[1] if len(row)>1 and row[1] is not None else "").strip()
        item.machine_variants = str(row[2] if len(row)>2 and row[2] is not None else "").strip()
        item.offset_factor = row[13] if len(row)>13 else ""
        item.scale_factor = row[14] if len(row)>14 else ""
        item.is_visible = row[15] if len(row)>15 else ""
        item.is_writable = row[16] if len(row)>16 else ""
        output.append(item)
    return output

def load_metadata() -> MetadataInfo:
    metadata_path=detect_metadata_workbook()
    metadata: Dict[int,List[MetadataParameter]]=defaultdict(list); issues=[]
    if metadata_path is None:
        return MetadataInfo(path=None,rows=metadata,issues=issues)
    if metadata_path.suffix.lower()==".xls":
        if xlrd is None:
            raise RuntimeError("Legacy .xls metadata requires xlrd. Run the v4.30 setup to install the dependency.")
        book=xlrd.open_workbook(str(metadata_path),on_demand=True)
        for i in range(book.nsheets):
            try:
                if book.sheet_visibility()[i] != 0: continue
            except Exception: pass
            sh=book.sheet_by_index(i)
            for item in _metadata_rows_from_values(sh.name,[sh.row_values(r) for r in range(sh.nrows)]):
                metadata[item.group_code].append(item)
        book.release_resources()
        return MetadataInfo(path=metadata_path,rows=metadata,issues=issues,workbook=None)
    workbook=load_workbook(metadata_path,data_only=True)
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible": continue
        rows=value_rows(sheet)
        hidden={r for r, dimension in sheet.row_dimensions.items() if dimension.hidden}
        for item in _metadata_rows_from_values(sheet.title,rows,hidden):
            metadata[item.group_code].append(item)
    return MetadataInfo(path=metadata_path,rows=metadata,issues=issues,workbook=workbook)

def english_text_values(node) -> Dict[str, str]:
    """Read one English layer, including regional AS language IDs such as en-US.

    Prefer legacy en, then en-US, then another English region. Do not merge
    translations: the same text ID can have different values in each layer.
    """
    layers = []
    for layer in node.findall(".//{*}TextLayer"):
        language = (layer.get("LanguageId") or "").strip().lower().replace("_", "-")
        if language == "en" or language.startswith("en-"):
            priority = 0 if language == "en" else 1 if language == "en-us" else 2
            layers.append((priority, language, layer))
    if not layers:
        return {}
    layer = min(layers, key=lambda item: (item[0], item[1]))[2]
    return {
        text.get("ID") or "": (text.get("Value") or "").strip()
        for text in layer.findall("./{*}Text")
    }


def summarize_textgroup_node(node) -> Tuple[Optional[int], str]:
    text_values = english_text_values(node)

    index_map: List[Tuple[int, str]] = []
    for index_entry in node.findall(".//{*}IndexMap/{*}Index"):
        text_id = index_entry.get("ID") or ""
        index_value = to_int(index_entry.get("Value"))
        if index_value is None:
            continue
        index_map.append((index_value, text_values.get(text_id, "")))

    index_map.sort(key=lambda item: item[0])
    summary = "; ".join(f"{index}:{value}" for index, value in index_map if value != "")
    return to_int(get_xml_property_value(node, "Index")), summary


def parse_textgroup_file(path: Path) -> Dict[str, object]:
    tree = ET.parse(path)
    root = tree.getroot()
    name = root.get("Name") or path.stem
    index, summary = summarize_textgroup_node(root)
    relative_parts = path.relative_to(LOGICAL_ROOT).parts if LOGICAL_ROOT.exists() else path.parts
    family = relative_parts[0] if relative_parts else path.stem
    return {
        "name": name,
        "index": index,
        "summary": summary,
        "family": family,
        "source_file": str(safe_relative_path(path)),
    }


def build_textgroup_catalog() -> Dict[str, Dict[str, object]]:
    catalog: Dict[str, Dict[str, object]] = {}
    search_roots = HMI_TEXTGROUP_ROOTS or [LOGICAL_ROOT if LOGICAL_ROOT.exists() else ROOT]
    seen_paths = set()
    for search_root in search_roots:
        for path in search_root.rglob("*.txtgrp"):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                info = parse_textgroup_file(path)
                catalog[normalize_name(str(info["name"]))] = info
            except Exception:
                continue
    return catalog


def extract_page_embedded_textgroup(page_root) -> Tuple[Optional[int], str]:
    embedded_groups = []
    for node in page_root.findall(".//{*}TextGroup"):
        if node.get("Name"):
            continue
        if node.find(".//{*}IndexMap/{*}Index") is None:
            continue
        embedded_groups.append(summarize_textgroup_node(node))
    if not embedded_groups:
        return None, ""
    return embedded_groups[0]


def extract_dropdown_rows() -> Dict[str, List[DropdownRow]]:
    rows_by_family: Dict[str, List[DropdownRow]] = defaultdict(list)
    search_roots = HMI_PAGE_ROOTS or [LOGICAL_ROOT if LOGICAL_ROOT.exists() else ROOT]

    textgroup_catalog = build_textgroup_catalog()
    seen_pages = set()
    for search_root in search_roots:
      for page_path in search_root.rglob("*.page"):
        if page_path in seen_pages:
            continue
        seen_pages.add(page_path)
        try:
            tree = ET.parse(page_path)
        except Exception:
            continue
        page_root = tree.getroot()
        relative_parts = page_path.relative_to(search_root).parts
        family = relative_parts[0] if relative_parts else search_root.name
        embedded_index, embedded_summary = extract_page_embedded_textgroup(page_root)

        for control in page_root.findall(".//{*}Controls/{*}Control"):
            control_name = control.get("Name") or ""
            properties = {child.get("Name"): child.get("Value") for child in control.findall("./{*}Property") if child.get("Name")}
            index_datapoint = (properties.get("IndexDatapoint") or "").strip()
            text_group = (properties.get("TextGroup") or "").strip()
            text_index_offset = (properties.get("TextIndexOffset") or "").strip()

            if not index_datapoint or index_datapoint.upper() == "NONE":
                continue
            # Only B&R dropdown controls are validated here. A generic HMI
            # control may also expose IndexDatapoint but is not a dropdown.
            class_id = (control.get("ClassId") or control.get("ClassID") or "").strip().lower()
            if class_id not in {"0x00001018", "0x1018", "1018"}:
                continue

            resolved_source = ""
            resolved_index = ""
            resolved_summary = ""
            external_group_name = extract_last_bracket_value(text_group)
            logic_parameter = extract_last_bracket_value(index_datapoint) or index_datapoint.split(".")[-1].strip()
            if external_group_name:
                catalog_item = textgroup_catalog.get(normalize_name(external_group_name))
                if catalog_item is not None:
                    resolved_source = str(catalog_item["source_file"])
                    resolved_index = "" if catalog_item["index"] is None else str(catalog_item["index"])
                    resolved_summary = str(catalog_item["summary"])
                else:
                    resolved_source = "NOT FOUND"
            elif "embedded" in text_group.lower():
                resolved_source = str(safe_relative_path(page_path))
                resolved_index = "" if embedded_index is None else str(embedded_index)
                resolved_summary = embedded_summary
            else:
                resolved_source = "NOT FOUND"

            rows_by_family[family].append(
                DropdownRow(
                    family=family,
                    page_file=str(safe_relative_path(page_path)),
                    control_name=control_name,
                    index_datapoint=index_datapoint,
                    logic_parameter=logic_parameter,
                    group_code=None,
                    sequence=None,
                    text_group=text_group,
                    text_group_name=external_group_name or ("EMBEDDED" if "embedded" in text_group.lower() else ""),
                    text_index_offset=text_index_offset,
                    text_group_source=resolved_source,
                    text_group_index=resolved_index,
                    # TextSource (for example MultipleTexts) selects an HMI
                    # display mode; it is never a PLC value or display label.
                    text_group_values=resolved_summary,
                )
            )

    for family in rows_by_family:
        rows_by_family[family].sort(key=lambda item: (item.page_file, item.control_name))
    return rows_by_family


def extract_case_blocks(path: Path) -> List[Tuple[int, str, int, int]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    code_lines = packet_code_lines("\n".join(lines))
    blocks: List[Tuple[int, str, int, int]] = []
    idx = 0
    while idx < len(lines):
        if re.search(r"\bCASE\s+nw_group_code\s+OF\b", code_lines[idx], re.IGNORECASE):
            nesting = 1
            idx += 1
            current_code = None
            current_desc = "No Description"
            start_line = idx + 1
            while idx < len(lines) and nesting > 0:
                raw = lines[idx]
                cleaned = code_lines[idx]
                if re.search(r"\bCASE\b", cleaned):
                    nesting += 1
                if re.search(r"\bEND_CASE\b", cleaned):
                    nesting -= 1
                    if nesting == 0:
                        if current_code is not None:
                            blocks.append((current_code, current_desc, start_line, idx))
                        break
                if nesting == 1:
                    label = re.match(r"^\s*(\d+)\s*:", cleaned)
                    if label:
                        if current_code is not None:
                            blocks.append((current_code, current_desc, start_line, idx - 1))
                        current_code = int(label.group(1))
                        current_desc = extract_comment(raw) or "No Description"
                        start_line = idx + 1
                idx += 1
            continue
        idx += 1
    return blocks


def packet_source_diagnostics(path: Path) -> List[ValidationIssue]:
    """Report recoverable packet-source structure defects with source lines.

    The packet reader deliberately recovers from a second ``(*`` inside an
    open ST comment by ending at the first ``*)``. Without an explicit warning,
    that malformed/decorative marker can make an older nested-comment parser
    hide every group that follows it. An unterminated outer packet CASE is a
    separate hard failure because its final group boundary is unknowable.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    source_file = str(safe_relative_path(path))
    diagnostics: List[ValidationIssue] = []

    in_block_comment = False
    in_line_comment = False
    quote = ""
    line_number = 1
    cursor = 0
    nested_comment_lines: set[int] = set()
    while cursor < len(text):
        pair = text[cursor:cursor + 2]
        char = text[cursor]
        if char == "\n":
            line_number += 1
            in_line_comment = False
            cursor += 1
            continue
        if in_line_comment:
            cursor += 1
            continue
        if in_block_comment:
            if pair == "(*":
                nested_comment_lines.add(line_number)
                cursor += 2
                continue
            if pair == "*)":
                in_block_comment = False
                cursor += 2
                continue
            cursor += 1
            continue
        if quote:
            if char == quote:
                if cursor + 1 < len(text) and text[cursor + 1] == quote:
                    cursor += 2
                    continue
                quote = ""
            cursor += 1
            continue
        if pair == "//":
            in_line_comment = True
            cursor += 2
            continue
        if pair == "(*":
            in_block_comment = True
            cursor += 2
            continue
        if char in "'\"":
            quote = char
        cursor += 1

    for diagnostic_line in sorted(nested_comment_lines):
        diagnostics.append(create_issue(
            "GLOBAL", "", "PLC packet source", "Recovered Nested Comment Marker",
            "ST comments contain one opening (* marker", "Found another (* before the first closing *)",
            source_file, diagnostic_line,
            "Remove the extra (* marker from this comment. uSOPp recovered at the first closing *) and continued scanning later group codes.",
            severity="WARNING",
        ))

    code_lines = packet_code_lines(text)
    case_depth = 0
    outer_start: Optional[int] = None
    for index, line in enumerate(code_lines, start=1):
        outer_match = bool(re.search(r"\bCASE\s+nw_group_code\s+OF\b", line, re.IGNORECASE))
        case_starts = len(re.findall(r"\bCASE\b", line, re.IGNORECASE))
        case_ends = len(re.findall(r"\bEND_CASE\b", line, re.IGNORECASE))
        if case_depth == 0:
            if not outer_match:
                continue
            outer_start = index
            case_depth = max(case_starts, 1) - case_ends
        else:
            case_depth += case_starts - case_ends
        if case_depth <= 0:
            case_depth = 0
            outer_start = None

    if outer_start is not None:
        diagnostics.append(create_issue(
            "GLOBAL", "", "PLC packet source", "CASE Block Termination",
            "END_CASE for CASE nw_group_code OF", "NOT FOUND",
            source_file, outer_start,
            "Add the missing END_CASE before validating or generating metadata so the final group boundary is explicit.",
            severity="FAIL",
        ))
    return diagnostics


def is_buffer_expr(expr: str, name: str) -> bool:
    return normalize_parameter_expr(expr).startswith(name + "[")


def parse_buffer_index(expr: str, buffer_name: str) -> Optional[int]:
    match = re.search(rf"{buffer_name}\[\s*(\d+)\s*\]", normalize_parameter_expr(expr))
    return int(match.group(1)) if match else None


def parse_cursor_buffer_index(expr: str, buffer_name: str, current_offset: int) -> Optional[int]:
    """Resolve buffer[nw_i], buffer[nw_i+N], and buffer[nw_i-N]."""
    normalized = normalize_parameter_expr(expr)
    match = re.search(
        rf"{buffer_name}\[nw_i(?:(?P<sign>[+-])(?P<amount>\d+))?\]",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    amount = int(match.group("amount") or 0)
    return current_offset - amount if match.group("sign") == "-" else current_offset + amount


def create_issue(group_code: int, parameter: str, description: str, validation_type: str, expected: object, actual: object, source_file: str, line_number: Optional[int], suggested_fix: str, severity: str = "FAIL", condition: str = "") -> ValidationIssue:
    return ValidationIssue(
        group_code=str(group_code),
        parameter=parameter,
        description=description,
        validation_type=validation_type,
        expected="" if expected is None else str(expected),
        actual="" if actual is None else str(actual),
        source_file=source_file,
        line_number="" if line_number is None else str(line_number),
        suggested_fix=suggested_fix,
        severity=severity,
        condition=condition or "",
    )


def branch_payload_size(parameters: List[PacketParameter]) -> int:
    return sum(parameter.memcpy_size or 0 for parameter in parameters)


def _parse_group_legacy(path: Path, code: int, description: str, start_line: int, end_line: int) -> Tuple[List[PacketParameter], Optional[int], Optional[int], Optional[int], List[ValidationIssue]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    block = lines[start_line - 1 : end_line + 1]
    clean_block = packet_code_lines("\n".join(lines))[start_line - 1 : end_line + 1]
    source_file = str(safe_relative_path(path))
    configured_msb = None
    configured_lsb = None
    configured_msb_group_size = None
    configured_lsb_group_size = None

    main_state = {"current_offset": PACKET_HEADER_BYTES, "expected_offset": PACKET_HEADER_BYTES, "parameters": []}
    conditional_stack: List[dict] = []
    issues: List[ValidationIssue] = []
    sequence = 0
    # Tracks the most recently closed IF/ELSIF/ELSE block. A common B&R
    # pattern is: conditional memcpy -> END_IF -> nw_i := nw_i + N -> next
    # memcpy. The increment belongs to the preceding conditional packet
    # field and must advance the sequence for the next parameter.
    last_closed_conditional_line: Optional[int] = None
    last_closed_conditional_parameter: Optional[PacketParameter] = None

    def active_state() -> dict:
        return conditional_stack[-1]["active_state"] if conditional_stack else main_state

    def add_parameter(parameter: PacketParameter) -> None:
        active_state()["parameters"].append(parameter)

    def condition_context() -> str:
        labels = []
        for context in conditional_stack:
            active = context.get("active_state") or {}
            label = active.get("label") or context.get("label") or ""
            if label:
                labels.append(str(label).strip())
        return " -> ".join(labels)

    def update_increment(increment: int, rel_idx: int) -> None:
        nonlocal last_closed_conditional_line, last_closed_conditional_parameter
        state = active_state()
        parameters = state["parameters"]
        if not parameters:
            return

        # A shared increment immediately after END_IF/END_CASE belongs to the
        # packet field emitted by the conditional branch, not to the next
        # memcpy. Keep an explicit reference so the sequence cannot shift by
        # one parameter.
        post_conditional = (
            last_closed_conditional_parameter is not None
            and last_closed_conditional_line is not None
            and 0 < (rel_idx - last_closed_conditional_line) <= 3
        )
        parameter = last_closed_conditional_parameter if post_conditional else parameters[-1]
        parameter.increment_value = increment
        parameter.increment_line_number = rel_idx
        # If the increment is immediately after END_IF, explicitly record it
        # as a post-conditional sequence increment. This is evidence only;
        # it does not change the existing increment validation rule.
        if last_closed_conditional_line is not None and 0 < (rel_idx - last_closed_conditional_line) <= 3:
            parameter.increment_relation = "POST-CONDITIONAL"
        elif conditional_stack:
            parameter.increment_relation = "CONDITIONAL-BRANCH"
        else:
            parameter.increment_relation = "DIRECT"
        parameter.sequence_validation = "PASS" if parameter.memcpy_size is not None and increment == parameter.memcpy_size else "FAIL"
        condition = condition_context()

        if parameter.memcpy_size is not None and increment != parameter.memcpy_size:
            parameter.issues.append(create_issue(
                code,
                parameter.parameter_name,
                parameter.parameter_description,
                "Offset Increment",
                parameter.memcpy_size,
                increment,
                source_file,
                rel_idx,
                (
                    f"FAIL: packet field requires {parameter.memcpy_size} bytes, but "
                    f"nw_i is incremented by {increment} bytes"
                    + (f" under {condition}" if condition else "")
                    + f". Expected nw_i increment = +{parameter.memcpy_size}; actual = +{increment}."
                ),
                condition=condition
            ))

        if parameter.offset_after_copy is not None:
            actual_after_increment = (parameter.running_offset or 0) + increment
            if parameter.offset_after_copy != actual_after_increment:
                parameter.issues.append(create_issue(
                    code,
                    parameter.parameter_name,
                    parameter.parameter_description,
                    "Offset After Copy",
                    parameter.offset_after_copy,
                    actual_after_increment,
                    source_file,
                    rel_idx,
                    (
                        f"FAIL: packet field ends at offset {parameter.offset_after_copy}, "
                        f"but nw_i advances from {parameter.running_offset} by +{increment} "
                        f"to {actual_after_increment}"
                        + (f" under {condition}" if condition else "")
                        + f". Correct nw_i increment to match the {parameter.memcpy_size}-byte field."
                    ),
                    condition=condition
                ))

        if parameter.running_offset is not None:
            next_offset = parameter.running_offset + increment
            state["current_offset"] = next_offset
            if post_conditional:
                # Explicitly commit the shared post-END_IF/END_CASE cursor to
                # the main packet sequence before the next memcpy is parsed.
                main_state["current_offset"] = next_offset
        if state["expected_offset"] is not None and parameter.memcpy_size is not None:
            next_expected = state["expected_offset"] + parameter.memcpy_size
            state["expected_offset"] = next_expected
            if post_conditional:
                main_state["expected_offset"] = next_expected
        # The post-conditional marker belongs only to the first increment
        # following END_IF/END_CASE. Do not leak it to later parameters.
        if last_closed_conditional_line is not None and rel_idx >= last_closed_conditional_line:
            last_closed_conditional_line = None
            last_closed_conditional_parameter = None

    def open_conditional(rel_idx: int, condition_text: str, comment: str = "") -> None:
        state = active_state()
        base_offset = state["current_offset"]
        base_expected = state["expected_offset"]
        first_branch = {
            "current_offset": base_offset,
            "expected_offset": base_expected,
            "parameters": [],
            "label": condition_text.strip(),
        }
        conditional_stack.append(
            {
                "base_offset": base_offset,
                "base_expected": base_expected,
                "branches": [first_branch],
                "active_state": first_branch,
                "source_line": rel_idx,
                "label": condition_text.strip(),
                "comment": comment,
            }
        )

    def switch_branch(branch_text: str = "ELSE") -> None:
        if not conditional_stack:
            return
        context = conditional_stack[-1]
        next_branch = {
            "current_offset": context["base_offset"],
            "expected_offset": context["base_expected"],
            "parameters": [],
            "label": branch_text.strip(),
        }
        context["branches"].append(next_branch)
        context["active_state"] = next_branch

    def close_conditional(rel_idx: int) -> None:
        nonlocal last_closed_conditional_line, last_closed_conditional_parameter
        if not conditional_stack:
            return
        context = conditional_stack.pop()
        last_closed_conditional_line = rel_idx
        branches = context["branches"]
        branch_sizes = [branch_payload_size(branch["parameters"]) for branch in branches]
        if (not any(str(branch.get("label", "")).upper() == "ELSE" for branch in branches)
                and any(p.transfer_method == "direct-byte" for branch in branches for p in branch["parameters"])):
            branch_sizes.append(0)  # No ELSE: the false path leaves this byte unwritten.
        representative = max(branches, key=lambda branch: len(branch["parameters"])) if branches else {"parameters": []}
        selected_parameters = representative["parameters"]
        # IF/ELSE assigns alternative values to the same byte. Keep one field
        # per packet slot and retain every branch assignment as source evidence.
        for selected in selected_parameters:
            if selected.transfer_method != "direct-byte":
                continue
            for branch in branches:
                for alternative in branch["parameters"]:
                    if (alternative is not selected
                            and alternative.transfer_method == "direct-byte"
                            and alternative.running_offset == selected.running_offset):
                        selected.write_evidence.extend(alternative.write_evidence)
        # Preserve the branch parameter for a possible shared nw_i increment
        # immediately after END_IF/END_CASE.
        last_closed_conditional_parameter = selected_parameters[-1] if selected_parameters else None

        for branch in branches:
            branch_condition = str(branch.get("label") or "").strip()
            for branch_parameter in branch.get("parameters", []):
                for branch_issue in branch_parameter.issues:
                    if not getattr(branch_issue, "condition", "") and branch_condition:
                        branch_issue.condition = branch_condition

                    target_parameter = next(
                        (candidate for candidate in selected_parameters
                         if normalize_name(candidate.parameter_name) ==
                            normalize_name(branch_parameter.parameter_name)),
                        None
                    )
                    if target_parameter is not None:
                        if branch_issue not in target_parameter.issues:
                            target_parameter.issues.append(branch_issue)
                    else:
                        branch_copy = copy(branch_parameter)
                        setattr(branch_copy, "_branch_only", True)
                        if branch_issue not in branch_copy.issues:
                            branch_copy.issues.append(branch_issue)
                        if not any(
                            normalize_name(candidate.parameter_name) == normalize_name(branch_copy.parameter_name)
                            and getattr(candidate, "_branch_only", False)
                            for candidate in selected_parameters
                        ):
                            selected_parameters.append(branch_copy)
                        if branch_issue not in issues:
                            issues.append(branch_issue)

        target_state = active_state()
        target_state["parameters"].extend(selected_parameters)
        if branch_sizes:
            representative_actual = representative.get("current_offset")
            representative_expected = representative.get("expected_offset")
            target_state["current_offset"] = representative_actual
            if representative_expected is not None:
                target_state["expected_offset"] = representative_expected
            if len(set(branch_sizes)) > 1:
                issues.append(
                    create_issue(
                        code,
                        "",
                        description,
                        "Conditional Packet Size",
                        branch_sizes[0],
                        ", ".join(str(size) for size in branch_sizes),
                        source_file,
                        context["source_line"],
                        "Ensure all IF/ELSE packet branches contribute the same byte count.",
                    )
                )

    for rel_idx, raw_line in enumerate(block, start=start_line):
        line = clean_block[rel_idx - start_line].strip()
        upper = line.upper()
        msb_match = re.search(r"nw_snd_buffer\s*\[\s*3\s*\]\s*:=\s*(\d+)\s*;", line, re.IGNORECASE)
        lsb_match = re.search(r"nw_snd_buffer\s*\[\s*4\s*\]\s*:=\s*(\d+)\s*;", line, re.IGNORECASE)
        line_comment = (extract_comment(raw_line) or "").upper()
        is_group_size_assignment = "GROUP SIZE BYTES" in line_comment
        if msb_match:
            value = int(msb_match.group(1))
            configured_msb = value
            if is_group_size_assignment:
                configured_msb_group_size = value
        if lsb_match:
            value = int(lsb_match.group(1))
            configured_lsb = value
            if is_group_size_assignment:
                configured_lsb_group_size = value

        if re.match(r"^IF\b.*\bTHEN\s*;?$", upper):
            open_conditional(rel_idx, line, extract_comment(raw_line) or "")
            continue
        if upper.startswith("ELSE") or re.match(r"^ELSIF\b.*\bTHEN\s*;?$", upper):
            switch_branch(line)
            continue
        if upper.startswith("END_IF"):
            close_conditional(rel_idx)
            continue

        set_offset = re.match(r"nw_i\s*:=\s*(\d+)\s*(?:;\s*)+$", line)
        if set_offset:
            state = active_state()
            state["current_offset"] = int(set_offset.group(1))
            if state["expected_offset"] is None:
                state["expected_offset"] = int(set_offset.group(1))
            continue

        memcpy_match = re.search(r"memcpy\s*\(\s*ADR\((.+?)\)\s*,\s*ADR\((.+?)\)\s*,\s*(.+?)\s*\)\s*;", line, re.IGNORECASE)
        if memcpy_match:
            # Before parsing the next memcpy, synchronize the packet cursor
            # from the actual PLC sequence between the previous parameter and
            # this memcpy. This is important when the previous increment is
            # after END_IF/ELSE/CASE or otherwise not adjacent to the memcpy.
            # It only repairs the cursor/evidence; it does not change the
            # existing datatype, packet-size, metadata, or increment checks.
            state = active_state()
            params_before = state.get("parameters", [])
            previous_parameter = params_before[-1] if params_before else None
            if previous_parameter is not None and previous_parameter.line_number < rel_idx:
                scan_start = previous_parameter.line_number - start_line + 1
                scan_end = rel_idx - start_line
                if scan_start <= scan_end:
                    between = clean_block[scan_start:scan_end]
                    increment_values = []
                    for between_raw in between:
                        between_line = between_raw.strip()
                        inc = re.match(r"nw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*(?:;\s*)+$", between_line)
                        if inc:
                            increment_values.append(int(inc.group(1)))
                    if increment_values and previous_parameter.running_offset is not None:
                        state["current_offset"] = previous_parameter.running_offset + increment_values[-1]
                        if previous_parameter.expected_offset is not None and previous_parameter.memcpy_size is not None:
                            state["expected_offset"] = previous_parameter.expected_offset + previous_parameter.memcpy_size

            dest_expr, src_expr, size_expr = [part.strip() for part in memcpy_match.groups()]
            comment = extract_comment(raw_line) or "No Description"
            sequence += 1
            state = active_state()
            destination_valid = is_buffer_expr(dest_expr, "nw_snd_buffer")
            if destination_valid:
                running_offset = state["current_offset"] if "[nw_i]" in normalize_parameter_expr(dest_expr) else parse_buffer_index(dest_expr, "nw_snd_buffer")
                parameter_expr = src_expr
            elif is_buffer_expr(src_expr, "nw_rcv_buffer"):
                running_offset = state["current_offset"] if "[nw_i]" in normalize_parameter_expr(src_expr) else parse_buffer_index(src_expr, "nw_rcv_buffer")
                parameter_expr = dest_expr
                destination_valid = True
            else:
                running_offset = state["current_offset"]
                parameter_expr = src_expr
                destination_valid = False

            raw_memcpy_size = evaluate_size_expr(size_expr, parameter_expr)
            resolved_type = resolve_type_info(parameter_expr)

            memcpy_size = raw_memcpy_size
            resolved_packet_type = dereference_type(resolved_type) if resolved_type is not None else None
            is_string_packet_field = (
                resolved_packet_type is not None
                and resolved_packet_type.kind == "string"
            )
            is_bool_packet_field = (
                resolved_packet_type is not None
                and resolved_packet_type.kind == "bool"
            )

            if is_string_packet_field:
                memcpy_size = 50
            elif is_bool_packet_field:
                memcpy_size = 1

            resolved_type_name = format_parameter_copy_type(parameter_expr, memcpy_size, resolved_type)
            expected_size = expected_memcpy_size(parameter_expr, memcpy_size)
            parameter_name = parameter_expr.strip()
            source_exists = resolve_type_info(parameter_expr) is not None
            offset_after_copy = None if running_offset is None or memcpy_size is None else running_offset + memcpy_size

            parameter = PacketParameter(
                group_code=code,
                group_description=description,
                sequence=sequence,
                parameter_expr=parameter_expr,
                parameter_name=parameter_name,
                parameter_description=comment,
                src_expr=src_expr,
                dest_expr=dest_expr,
                size_expr=size_expr,
                memcpy_size=memcpy_size,
                expected_size=expected_size,
                resolved_type_name=resolved_type_name,
                source_exists=source_exists,
                destination_valid=destination_valid,
                running_offset=running_offset,
                expected_offset=state["expected_offset"],
                offset_after_copy=offset_after_copy,
                increment_value=None,
                source_file=source_file,
                line_number=rel_idx,
            )
            parameter.condition_context = condition_context()

            if not source_exists:
                parameter.issues.append(create_issue(code, parameter_name, comment, "Variable Resolution", "Resolvable variable", "UNRESOLVED", source_file, rel_idx, "Declare the source variable or correct the memcpy source reference."))
            if not destination_valid:
                parameter.issues.append(create_issue(code, parameter_name, comment, "memcpy Destination", "nw_snd_buffer[nw_i] or nw_rcv_buffer[nw_i]", dest_expr, source_file, rel_idx, "Copy packet data to the packet buffer destination."))
            if expected_size is None:
                parameter.issues.append(create_issue(code, parameter_name, comment, "Data Type Resolution", "Resolvable datatype", resolved_type_name, source_file, rel_idx, "Define the datatype or correct the parameter expression.", severity="WARNING"))
            if memcpy_size is None:
                parameter.issues.append(create_issue(code, parameter_name, comment, "memcpy Size", "Resolvable memcpy size", size_expr, source_file, rel_idx, "Use a literal size or SIZEOF() that resolves to the parameter datatype size."))

            if expected_size is not None and memcpy_size is not None and expected_size != memcpy_size:
                resolved_kind = dereference_type(resolved_type).kind if resolved_type is not None else None
                if resolved_kind == "string":
                    parameter.issues.append(create_issue(
                        code, parameter_name, comment,
                        "String Packet Size", 50, memcpy_size,
                        source_file, rel_idx,
                        "STRING packet fields are fixed at 50 bytes for packet offset calculation.",
                        severity="WARNING"
                    ))
                elif resolved_kind == "bool":
                    parameter.issues.append(create_issue(
                        code, parameter_name, comment,
                        "BOOL Packet Size", 1, memcpy_size,
                        source_file, rel_idx,
                        "BOOL packet fields occupy 1 byte; validate nw_i increment against +1.",
                        severity="WARNING"
                    ))
                else:
                    parameter.issues.append(create_issue(code, parameter_name, comment, "Data Type Size", expected_size, memcpy_size, source_file, rel_idx, "Match the memcpy size to the resolved datatype size."))

            if running_offset is not None and state["expected_offset"] is not None and running_offset != state["expected_offset"]:
                offset_severity = "WARNING" if any(
                    issue.validation_type == "String Packet Size" for issue in parameter.issues
                ) else "FAIL"
                parameter.issues.append(create_issue(
                    code, parameter_name, comment, "Offset",
                    state["expected_offset"], running_offset, source_file, rel_idx,
                    "Start the memcpy at the expected running offset.",
                    severity=offset_severity
                ))
            add_parameter(parameter)
            continue

        direct_match = re.fullmatch(
            r"(nw_snd_buffer\s*\[\s*nw_i\s*\])\s*:=\s*(.+?)\s*;", line, re.IGNORECASE
        )
        if direct_match:
            dest_expr, src_expr = direct_match.groups()
            state = active_state()
            running_offset = state["current_offset"]
            sequence += 1
            # A numeric result in IF/ELSE represents the condition's status.
            # The serialized value is a BYTE, regardless of condition datatype.
            context = conditional_stack[-1] if conditional_stack else {}
            condition = condition_context()
            condition_expr = re.sub(r"^IF\s+|\s+THEN\s*;?$", "", context.get("label", ""), flags=re.I)
            identifiers = re.findall(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", condition_expr)
            identifiers = [name for name in identifiers if name.upper() not in {"NOT", "AND", "OR", "XOR", "TRUE", "FALSE"}]
            literal = bool(re.fullmatch(r"(?:\d+|TRUE|FALSE)", src_expr.strip(), re.I))
            parameter_name = identifiers[0] if literal and identifiers else (
                f"nw_snd_buffer[{running_offset}]" if literal else src_expr.strip()
            )
            comment = extract_comment(raw_line) or context.get("comment") or "Direct packet byte"
            parameter = PacketParameter(
                group_code=code, group_description=description, sequence=sequence,
                parameter_expr=parameter_name, parameter_name=parameter_name,
                parameter_description=comment, src_expr=src_expr, dest_expr=dest_expr,
                size_expr="1", memcpy_size=1, expected_size=1, resolved_type_name="BYTE",
                source_exists=True, destination_valid=True, running_offset=running_offset,
                expected_offset=state["expected_offset"],
                offset_after_copy=None if running_offset is None else running_offset + 1,
                increment_value=None, source_file=source_file, line_number=rel_idx,
                transfer_method="direct-byte", write_evidence=[{
                    "sourceExpression": src_expr, "destinationExpression": dest_expr,
                    "condition": condition, "sourceFile": source_file, "lineNumber": rel_idx,
                "sourceText": lines[rel_idx - 1].strip() if 1 <= rel_idx <= len(lines) else "",
                }],
            )
            parameter.condition_context = condition
            if running_offset is not None and state["expected_offset"] is not None and running_offset != state["expected_offset"]:
                parameter.issues.append(create_issue(
                    code, parameter_name, comment, "Offset", state["expected_offset"], running_offset,
                    source_file, rel_idx, "Write the packet byte at the expected running offset.", condition=condition,
                ))
            add_parameter(parameter)
            continue

        increment_match = re.match(r"nw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*(?:;\s*)+$", line)
        if increment_match:
            increment = int(increment_match.group(1))
            state = active_state()
            parameters = state["parameters"]
            last_parameter = parameters[-1] if parameters else None

            if last_parameter is not None:
                distance = rel_idx - last_parameter.line_number
                post_conditional_increment = (
                    last_closed_conditional_parameter is not None
                    and last_closed_conditional_parameter is last_parameter
                    and last_closed_conditional_line is not None
                    and 0 < (rel_idx - last_closed_conditional_line) <= 3
                )
                immediate = distance == 1
                last_type = None
                if last_parameter.resolved_type_name:
                    try:
                        resolved_last = resolve_type_info(last_parameter.parameter_expr)
                        if resolved_last is not None:
                            last_type = dereference_type(resolved_last).kind
                    except Exception:
                        last_type = None

                if immediate or post_conditional_increment:
                    update_increment(increment, rel_idx)
                elif 1 < distance <= 12:
                    intervening = clean_block[
                        last_parameter.line_number - start_line + 1 :
                        rel_idx - start_line
                    ]
                    clean_intervening = "\n".join(intervening)
                    has_intervening_memcpy = bool(re.search(r"\bmemcpy\s*\(", clean_intervening, re.IGNORECASE))
                    has_string_helper = bool(
                        re.search(r"\bstringlength\s*:=", clean_intervening, re.IGNORECASE)
                        or re.search(r"\bstrlen\s*\(", clean_intervening, re.IGNORECASE)
                        or re.search(r"\bmemset\s*\(", clean_intervening, re.IGNORECASE)
                    )
                    direct_gap = last_parameter.transfer_method == "direct-byte" and not clean_intervening.strip()
                    if not has_intervening_memcpy and (direct_gap or last_type == "string" or has_string_helper or last_parameter.memcpy_size == 50):
                        update_increment(increment, rel_idx)
            continue

    if configured_msb_group_size is not None:
        configured_msb = configured_msb_group_size
    if configured_lsb_group_size is not None:
        configured_lsb = configured_lsb_group_size

    configured_bytes = None if configured_msb is None or configured_lsb is None else configured_msb * 256 + configured_lsb
    parameters = main_state["parameters"]
    if any(p.transfer_method == "direct-byte" for p in parameters):
        # Alternative assignments are one logical field, so metadata matching
        # must use the resulting packet sequence, not the count of statements.
        for field_sequence, parameter in enumerate(parameters, start=1):
            parameter.sequence = field_sequence

    # Sequence validation: validate the packet cursor between consecutive
    # parameters independently of the textual position of the nw_i increment.
    # This is intentionally separate from the Offset Increment check because
    # B&R code may place the increment after IF/ELSE/END_IF or other control
    # flow. The packet sequence itself must still advance by the memcpy byte
    # count. This catches cases such as:
    #   memcpy(..., Ring_center_sel..., 1);
    #   nw_i := nw_i + 1;
    #   memcpy(..., Traveller_Run..., 1);
    # where a parser accidentally fails to associate the increment with Ring.
    visible_parameters = [p for p in parameters if not getattr(p, "_branch_only", False)]
    for prev, current in zip(visible_parameters, visible_parameters[1:]):
        if prev.running_offset is None or current.running_offset is None:
            continue

        # The expected next packet position is based on the previous memcpy
        # size. Do not depend on increment_value being populated here. The
        # separate Offset Increment validation checks the actual nw_i := nw_i
        # + X statement when it is found.
        if prev.memcpy_size is None:
            continue

        expected_next = prev.running_offset + prev.memcpy_size
        if current.running_offset != expected_next:
            current.issues.append(create_issue(
                code, current.parameter_name, current.parameter_description,
                "Offset Sequence", expected_next, current.running_offset,
                source_file, current.line_number,
                (
                    f"The next parameter starts at {current.running_offset}, but the previous "
                    f"parameter is {prev.memcpy_size} bytes and the sequence requires the "
                    f"next nw_i position to be {expected_next}. Check the nw_i increment "
                    f"after the previous memcpy/IF/CASE sequence."
                ),
                severity="FAIL"
            ))
            current.sequence_validation = "FAIL"
        else:
            if current.sequence_validation in ("NOT FOUND", ""):
                current.sequence_validation = "PASS"

    used_offsets = []
    for parameter in parameters:
        if getattr(parameter, "_branch_only", False):
            continue
        if parameter.running_offset is not None and parameter.memcpy_size is not None:
            used_offsets.append((parameter.running_offset, parameter.running_offset + parameter.memcpy_size - 1, parameter))

    used_offsets.sort(key=lambda item: item[0])
    for idx, (start, end, parameter) in enumerate(used_offsets):
        if idx > 0:
            prev_start, prev_end, prev_parameter = used_offsets[idx - 1]
            if start == prev_start:
                parameter.issues.append(create_issue(code, parameter.parameter_name, parameter.parameter_description, "Duplicate Offset", prev_start, start, parameter.source_file, parameter.line_number, "Assign a unique start offset for this parameter."))
            if start <= prev_end:
                parameter.issues.append(create_issue(code, parameter.parameter_name, parameter.parameter_description, "Overlapping Offset", f">{prev_end}", start, parameter.source_file, parameter.line_number, "Move the parameter start offset after previous parameter ends."))
            if start > prev_end + 1:
                parameter.issues.append(create_issue(code, parameter.parameter_name, parameter.parameter_description, "Skipped Offset", prev_end + 1, start, parameter.source_file, parameter.line_number, "Align next parameter to immediate next offset.", severity="WARNING"))

    if configured_bytes is None and parameters:
        issues.append(create_issue(code, "", description, "Packet Size", "Configured bytes in nw_snd_buffer[3]/[4]", "NOT FOUND", source_file, start_line, "Populate nw_snd_buffer[3] and [4] with payload length."))

    for parameter in parameters:
        issues.extend(parameter.issues)

    return parameters, configured_bytes, configured_msb, configured_lsb, issues


@dataclass
class _PacketPathState:
    """One executable packet layout through an IF/ELSIF/ELSE tree."""

    current_offset: int = PACKET_HEADER_BYTES
    expected_offset: int = PACKET_HEADER_BYTES
    configured_msb: Optional[int] = None
    configured_lsb: Optional[int] = None
    parameters: List[PacketParameter] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    pending_index: Optional[int] = None
    branch_origins: Dict[int, int] = field(default_factory=dict)
    cursor_initialized: bool = False
    initialization_reported: bool = False
    configured_lsb_line: Optional[int] = None
    response_length_line: Optional[int] = None
    response_trigger_line: Optional[int] = None
    response_trigger_value: str = ""


def _validation_issue_key(issue: ValidationIssue, include_condition: bool = True) -> tuple:
    values = (
        issue.group_code,
        issue.parameter,
        issue.validation_type,
        issue.expected,
        issue.actual,
        issue.source_file,
        issue.line_number,
        issue.severity,
    )
    return values + ((issue.condition or ""),) if include_condition else values


def _append_unique_issue(target: List[ValidationIssue], issue: ValidationIssue) -> None:
    key = _validation_issue_key(issue)
    if not any(_validation_issue_key(existing) == key for existing in target):
        target.append(issue)


def packet_issue_json(issue: ValidationIssue, source_file: str = "", lines=()) -> dict:
    issue_line = to_int(issue.line_number)
    context = []
    if issue.source_file == source_file and issue_line and 1 <= issue_line <= len(lines):
        context = [{"lineNumber": number, "text": lines[number - 1], "highlight": number == issue_line}
                   for number in range(max(1, issue_line - 2), min(len(lines), issue_line + 2) + 1)]
    return {"sourceContext": context, "parameter": issue.parameter, "validationType": issue.validation_type,
            "expected": issue.expected, "actual": issue.actual, "severity": issue.severity,
            "sourceFile": issue.source_file, "lineNumber": issue_line, "condition": issue.condition,
            "suggestedFix": issue.suggested_fix}


@lru_cache(maxsize=32)
def legacy_packet_cursor_declaration(file_path: str, modified_ns: int, task_name: str) -> Optional[Tuple[SymbolInfo, Optional[int]]]:
    """Resolve an AS 2.7 local declaration inside its PROGRAM export section."""
    path = Path(file_path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    header = re.search(r"(?im)^[^\S\r\n]*PROGRAM\s+" + re.escape(task_name) + r"\s+\d+\b[^\n]*", text)
    if not header:
        return None
    next_program = re.search(r"(?im)^[^\S\r\n]*PROGRAM\s+[A-Za-z_]\w*\s+\d+\b", text[header.end():])
    section = text[header.end():header.end() + next_program.start()] if next_program else text[header.end():]
    symbols = parse_as27_cpu_symbols(section)
    name = next((name for name in symbols if name.casefold() == "nw_i"), None)
    if not name:
        return None
    declaration = re.search(r"(?im)^[^\S\r\n]*nw_i[^\S\r\n]+(?:%[A-Za-z]+\d*[^\S\r\n]*)?:\s*[^;]+;", section)
    line = text[:header.end() + declaration.start()].count("\n") + 1 if declaration else None
    return SymbolInfo(name, symbols[name], str(safe_relative_path(path))), line


def packet_cursor_declaration(path: Path) -> Optional[Tuple[SymbolInfo, Optional[int]]]:
    """Prefer task-local nw_i declarations over same-named symbols in other tasks."""
    candidates = []
    if isinstance(path, Path):
        candidates = sorted(path.parent.glob("*.var"), key=lambda item: (
            item.stem.casefold() not in {path.parent.name.casefold(), path.stem.casefold(), "variables", "local"},
            item.name.casefold(),
        ))
        candidates.append(path)
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        declarations = parse_var_sections(text)
        name = next((name for name in declarations if name.casefold() == "nw_i"), None)
        if name:
            line = next((index for index, content in enumerate(packet_code_lines(text), 1)
                         if re.search(r"\bnw_i\b[^;]*:(?!=)", content, re.I)), None)
            return SymbolInfo(name, declarations[name], str(safe_relative_path(candidate))), line
    symbol = next((item for name, item in VARIABLES.items() if name.casefold() == "nw_i"), None)
    if symbol is None:
        return None
    declaration_path = Path(symbol.source_file)
    if not declaration_path.is_absolute():
        declaration_path = ROOT / declaration_path
    if declaration_path.is_file() and declaration_path.name.casefold() == "cpu.txt":
        scoped = legacy_packet_cursor_declaration(str(declaration_path), declaration_path.stat().st_mtime_ns, path.stem)
        if scoped:
            return scoped
    line = None
    if declaration_path.is_file():
        line = next((index for index, content in enumerate(packet_code_lines(
            declaration_path.read_text(encoding="utf-8", errors="ignore")), 1)
            if re.search(r"\bnw_i\b[^;]*:(?!=)", content, re.I)), None)
    return symbol, line


def parse_group(
    path: Path,
    code: int,
    description: str,
    start_line: int,
    end_line: int,
    include_variants: bool = False,
    validate_response_setup: bool = False,
):
    """Parse a packet group with path-scoped cursor and packet-size state.

    Each IF/ELSIF/ELSE path retains its own ``nw_i`` value, configured packet
    length and write intervals until the group has been validated. Equivalent
    two-way branches are collapsed after their alternatives have been retained
    as write evidence; layouts with different sizes remain separate variants.
    """

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    block = lines[start_line - 1 : end_line + 1]
    clean_block = packet_code_lines("\n".join(lines))[start_line - 1 : end_line + 1]
    source_file = str(safe_relative_path(path))
    active_states: List[_PacketPathState] = [_PacketPathState()]
    conditional_stack: List[dict] = []
    operation_sequence = 0
    conditional_sequence = 0
    cursor_declaration = packet_cursor_declaration(path)

    def state_condition(state: _PacketPathState) -> str:
        return " -> ".join(part for part in state.conditions if part)

    def parameter_issue(
        state: _PacketPathState,
        parameter: PacketParameter,
        validation_type: str,
        expected: object,
        actual: object,
        line_number: int,
        suggested_fix: str,
        severity: str = "FAIL",
    ) -> ValidationIssue:
        issue = create_issue(
            code,
            parameter.parameter_name,
            parameter.parameter_description,
            validation_type,
            expected,
            actual,
            source_file,
            line_number,
            suggested_fix,
            severity=severity,
            condition=state_condition(state),
        )
        _append_unique_issue(parameter.issues, issue)
        return issue

    def add_parameter(state: _PacketPathState, parameter: PacketParameter) -> None:
        if state.pending_index is not None and state.pending_index < len(state.parameters):
            previous = state.parameters[state.pending_index]
            if previous.increment_value is None:
                parameter_issue(
                    state,
                    previous,
                    "Offset Increment Missing",
                    previous.memcpy_size,
                    "NOT FOUND",
                    parameter.line_number,
                    "Advance nw_i by the packet field size before writing the next field.",
                )
        state.parameters.append(parameter)
        state.pending_index = len(state.parameters) - 1

    def make_gap(state: _PacketPathState, increment: int, rel_idx: int, reason: str = "Standalone nw_i increment") -> None:
        nonlocal operation_sequence
        if increment <= 0:
            return
        operation_sequence += 1
        running_offset = state.current_offset
        condition = state_condition(state)
        parameter = PacketParameter(
            group_code=code,
            group_description=description,
            sequence=operation_sequence,
            parameter_expr=f"UNWRITTEN_GAP_{max(running_offset - PACKET_HEADER_BYTES, 0)}",
            parameter_name=f"UNWRITTEN_GAP_{max(running_offset - PACKET_HEADER_BYTES, 0)}",
            parameter_description=reason,
            src_expr="UNINITIALIZED",
            dest_expr=f"nw_snd_buffer[{running_offset}]",
            size_expr=str(increment),
            memcpy_size=increment,
            expected_size=increment,
            resolved_type_name="BYTE" if increment == 1 else f"BYTE[{increment}]",
            source_exists=True,
            destination_valid=True,
            running_offset=running_offset,
            expected_offset=state.expected_offset,
            offset_after_copy=running_offset + increment,
            increment_value=increment,
            source_file=source_file,
            line_number=rel_idx,
            increment_line_number=rel_idx,
            increment_relation="STANDALONE",
            sequence_validation="WARNING",
            transfer_method="unwritten-gap",
            write_evidence=[{
                "sourceExpression": "UNINITIALIZED",
                "destinationExpression": f"nw_snd_buffer[{running_offset}:{running_offset + increment - 1}]",
                "condition": condition,
                "sourceFile": source_file,
                "lineNumber": rel_idx,
                "sourceText": lines[rel_idx - 1].strip() if 1 <= rel_idx <= len(lines) else "",
                "transferMethod": "unwritten-gap",
            }],
            condition_context=condition,
        )
        setattr(parameter, "_skip_metadata", True)
        parameter_issue(
            state,
            parameter,
            "Unwritten Packet Gap",
            f"Initialized packet byte(s) {running_offset}..{running_offset + increment - 1}",
            "nw_i advanced without a packet write",
            rel_idx,
            "Remove the standalone nw_i increment, or initialize the reserved byte(s) and include them in metadata and configured packet size.",
            severity="WARNING",
        )
        state.parameters.append(parameter)
        state.current_offset += increment
        state.expected_offset += increment
        state.pending_index = None

    def apply_increment(state: _PacketPathState, increment: int, rel_idx: int) -> None:
        if state.pending_index is None or state.pending_index >= len(state.parameters):
            make_gap(state, increment, rel_idx)
            return
        parameter = state.parameters[state.pending_index]
        parameter.increment_value = increment
        parameter.increment_line_number = rel_idx
        parameter.increment_relation = "CONDITIONAL-BRANCH" if state.conditions else "DIRECT"
        parameter.sequence_validation = (
            "PASS" if parameter.memcpy_size is not None and increment == parameter.memcpy_size else "FAIL"
        )
        if parameter.memcpy_size is not None and increment != parameter.memcpy_size:
            parameter_issue(
                state,
                parameter,
                "Offset Increment",
                parameter.memcpy_size,
                increment,
                rel_idx,
                (
                    f"FAIL: packet field requires {parameter.memcpy_size} bytes, but nw_i is incremented "
                    f"by {increment} bytes under {state_condition(state) or 'the active packet path'}. "
                    f"Expected nw_i increment = +{parameter.memcpy_size}; actual = +{increment}."
                ),
            )
        if parameter.running_offset is not None and parameter.memcpy_size is not None:
            expected_after = parameter.running_offset + parameter.memcpy_size
            actual_after = parameter.running_offset + increment
            if expected_after != actual_after:
                parameter_issue(
                    state,
                    parameter,
                    "Offset After Copy",
                    expected_after,
                    actual_after,
                    rel_idx,
                    (
                        f"FAIL: packet field ends at offset {expected_after}, but nw_i advances from "
                        f"{parameter.running_offset} by +{increment} to {actual_after}. Correct nw_i "
                        f"increment to match the {parameter.memcpy_size}-byte field."
                    ),
                )
        state.current_offset += increment
        if parameter.memcpy_size is not None:
            state.expected_offset += parameter.memcpy_size
        state.pending_index = None

    def state_signature(state: _PacketPathState) -> tuple:
        parameter_layout = []
        for parameter in state.parameters:
            issue_signature = tuple(sorted(
                (
                    issue.validation_type,
                    issue.expected,
                    issue.actual,
                    issue.severity,
                )
                for issue in parameter.issues
            ))
            parameter_layout.append((
                parameter.running_offset,
                parameter.memcpy_size,
                parameter.increment_value,
                parameter.transfer_method == "unwritten-gap",
                issue_signature,
            ))
        state_issue_signature = tuple(sorted(
            (issue.validation_type, issue.expected, issue.actual, issue.severity)
            for issue in state.issues
        ))
        pending_size = None
        if state.pending_index is not None and state.pending_index < len(state.parameters):
            pending_size = state.parameters[state.pending_index].memcpy_size
        return (
            state.current_offset,
            state.expected_offset,
            state.configured_msb,
            state.configured_lsb,
            state.cursor_initialized,
            bool(state.response_length_line),
            state.response_trigger_value,
            pending_size,
            tuple(parameter_layout),
            state_issue_signature,
        )

    def merge_states(states: List[_PacketPathState], base_conditions: List[str], labels: List[str]) -> _PacketPathState:
        merged = deepcopy(states[0])
        merged.conditions = list(base_conditions)
        distinct_labels = list(dict.fromkeys(label for label in labels if label))
        if distinct_labels:
            merged.conditions.append("ANY OF (" + " | ".join(distinct_labels) + ")")
        merged_condition = state_condition(merged)
        for alternative in states[1:]:
            for index, other_parameter in enumerate(alternative.parameters):
                if index >= len(merged.parameters):
                    merged.parameters.append(deepcopy(other_parameter))
                    continue
                parameter = merged.parameters[index]
                for evidence in other_parameter.write_evidence:
                    if evidence not in parameter.write_evidence:
                        parameter.write_evidence.append(deepcopy(evidence))
                for issue in other_parameter.issues:
                    _append_unique_issue(parameter.issues, deepcopy(issue))
                if parameter.transfer_method != other_parameter.transfer_method:
                    parameter.transfer_method = "conditional"
            for issue in alternative.issues:
                _append_unique_issue(merged.issues, deepcopy(issue))
        if merged.pending_index is not None and merged.pending_index < len(merged.parameters):
            merged.parameters[merged.pending_index].condition_context = merged_condition
        return merged

    def validate_path(state: _PacketPathState) -> None:
        written = [
            parameter for parameter in state.parameters
            if parameter.transfer_method != "unwritten-gap"
            and parameter.running_offset is not None
            and parameter.memcpy_size is not None
        ]
        intervals = sorted(
            [(
                parameter.running_offset,
                parameter.running_offset + parameter.memcpy_size - 1,
                parameter,
            ) for parameter in written],
            key=lambda item: (
                item[0],
                item[1],
                item[2].sequence if item[2].sequence is not None else 10**9,
                item[2].line_number if item[2].line_number is not None else 10**9,
            ),
        )

        gap_ranges = [
            (parameter.running_offset, parameter.running_offset + (parameter.memcpy_size or 0) - 1)
            for parameter in state.parameters
            if parameter.transfer_method == "unwritten-gap" and parameter.running_offset is not None
        ]
        for index, (start, end, parameter) in enumerate(intervals):
            if index == 0:
                continue
            previous_start, previous_end, previous = intervals[index - 1]
            if start == previous_start:
                parameter_issue(
                    state,
                    parameter,
                    "Duplicate Offset",
                    f"> {previous_end}",
                    start,
                    parameter.line_number,
                    "Assign a unique packet offset within this condition path.",
                )
            if start <= previous_end:
                parameter_issue(
                    state,
                    parameter,
                    "Overlapping Offset",
                    f"> {previous_end}",
                    start,
                    parameter.line_number,
                    (
                        f"Move this field after {previous.parameter_name}; bytes {start}.."
                        f"{min(end, previous_end)} are written by both fields on this path."
                    ),
                )
            elif start > previous_end + 1:
                missing_start = previous_end + 1
                missing_end = start - 1
                explicitly_reported = any(
                    gap_start <= missing_start and gap_end >= missing_end
                    for gap_start, gap_end in gap_ranges
                )
                if not explicitly_reported:
                    parameter_issue(
                        state,
                        parameter,
                        "Skipped Offset",
                        missing_start,
                        start,
                        parameter.line_number,
                        "Initialize or remove the skipped packet byte(s) on this condition path.",
                        severity="WARNING",
                    )

    def issue_to_json(issue: ValidationIssue) -> dict:
        issue_line = to_int(issue.line_number)
        context = []
        if issue.source_file == source_file and issue_line and 1 <= issue_line <= len(lines):
            context = [{"lineNumber": number, "text": lines[number - 1], "highlight": number == issue_line}
                       for number in range(max(1, issue_line - 2), min(len(lines), issue_line + 2) + 1)]
        return {
            "sourceContext": context,
            "parameter": issue.parameter,
            "validationType": issue.validation_type,
            "expected": issue.expected,
            "actual": issue.actual,
            "severity": issue.severity,
            "sourceFile": issue.source_file,
            "lineNumber": to_int(issue.line_number),
            "condition": issue.condition,
            "suggestedFix": issue.suggested_fix,
        }

    def variant_parameter_json(parameter: PacketParameter) -> dict:
        severity = "FAIL" if any(i.severity == "FAIL" for i in parameter.issues) else (
            "WARNING" if any(i.severity == "WARNING" for i in parameter.issues) else "PASS"
        )
        return {
            "parameter": parameter.parameter_name,
            "description": parameter.parameter_description,
            "dataType": parameter.resolved_type_name,
            "size": parameter.memcpy_size,
            "runningOffset": parameter.running_offset,
            "offsetBuffer": None if parameter.running_offset is None else max(parameter.running_offset - PACKET_HEADER_BYTES, 0),
            "tcpOffset": None if parameter.running_offset is None else max(parameter.running_offset - PACKET_HEADER_BYTES, 0),
            "offsetAfterCopy": parameter.offset_after_copy,
            "incrementValue": parameter.increment_value,
            "transferMethod": parameter.transfer_method,
            "conditionContext": parameter.condition_context,
            "sourceFile": parameter.source_file,
            "lineNumber": parameter.line_number,
            "status": severity,
            "issues": [issue_to_json(issue) for issue in parameter.issues],
            "writeEvidence": parameter.write_evidence,
        }

    def finalize_variant(state: _PacketPathState, variant_index: int) -> dict:
        validate_path(state)
        if state.pending_index is not None and state.pending_index < len(state.parameters):
            parameter = state.parameters[state.pending_index]
            parameter_issue(
                state,
                parameter,
                "Offset Increment Missing",
                parameter.memcpy_size,
                "NOT FOUND",
                parameter.line_number,
                "Add the matching nw_i increment after this packet write.",
                severity="WARNING",
            )
            state.pending_index = None

        written_parameters = [
            parameter for parameter in state.parameters
            if parameter.transfer_method != "unwritten-gap" and parameter.memcpy_size is not None
        ]
        written_bytes = sum(parameter.memcpy_size or 0 for parameter in written_parameters)
        written_ends = [
            (parameter.running_offset - PACKET_HEADER_BYTES) + (parameter.memcpy_size or 0)
            for parameter in written_parameters
            if parameter.running_offset is not None
        ]
        max_written_end = max(written_ends) if written_ends else 0
        cursor_bytes = max(state.current_offset - PACKET_HEADER_BYTES, 0)
        calculated_by_offset = max(max_written_end, cursor_bytes)
        configured_bytes = (
            None
            if state.configured_msb is None or state.configured_lsb is None
            else state.configured_msb * 256 + state.configured_lsb
        )
        condition = state_condition(state) or "Unconditional"
        close_only = code == 11 and not written_parameters
        if validate_response_setup and not close_only:
            missing_line = min(end_line, len(lines))
            if state.response_length_line is None:
                _append_unique_issue(state.issues, create_issue(
                    code, "nw_snd_buffer_length", description, "Response Length Missing",
                    "nw_snd_buffer_length := ((nw_snd_buffer[3] * 256) + nw_snd_buffer[4] + 5);",
                    "NOT FOUND on this packet path", source_file, missing_line,
                    "Set nw_snd_buffer_length from the two payload-size header bytes plus the five-byte header, after the payload writes and before enabling the response.",
                    condition=condition,
                ))
            if state.response_trigger_value.upper() not in {"TRUE", "1"}:
                _append_unique_issue(state.issues, create_issue(
                    code, "nw_snd_response", description, "Response Trigger Missing",
                    "nw_snd_response := TRUE;", state.response_trigger_value or "NOT FOUND on this packet path",
                    source_file, state.response_trigger_line or missing_line,
                    "Add nw_snd_response := TRUE; after setting nw_snd_buffer_length so the PLC sends this group's response.",
                    condition=condition,
                ))
        if state.cursor_initialized and cursor_declaration:
            symbol, declaration_line = cursor_declaration
            cursor_type = dereference_type(symbol.type_info)
            cursor_name = normalize_type_name(format_type_info(cursor_type))
            if cursor_name in {"USINT", "SINT", "BYTE", "BOOL"}:
                _append_unique_issue(state.issues, create_issue(
                    code, "nw_i", "Packet cursor declaration", "Packet Cursor Data Type",
                    "UINT or another integer type with at least 16 bits", cursor_name,
                    symbol.source_file, declaration_line,
                    f"Declare nw_i : UINT; in the packet task. {cursor_name} is limited to one byte and can wrap when packet offsets exceed its range. This path needs offsets through {PACKET_HEADER_BYTES + calculated_by_offset}.",
                    condition=condition,
                ))
        if configured_bytes is None and not close_only:
            _append_unique_issue(state.issues, create_issue(
                code,
                "",
                description,
                "Packet Size",
                "Configured bytes in nw_snd_buffer[3]/[4]",
                "NOT FOUND",
                source_file,
                state.configured_lsb_line or start_line,
                "Populate nw_snd_buffer[3] and [4] on this packet path.",
                severity="WARNING",
                condition=condition,
            ))
        elif configured_bytes is not None and calculated_by_offset > configured_bytes:
            _append_unique_issue(state.issues, create_issue(
                code,
                "",
                description,
                "Packet Overflow",
                configured_bytes,
                calculated_by_offset,
                source_file,
                state.configured_lsb_line or start_line,
                (
                    f"This path reaches {calculated_by_offset} payload bytes but transmits only "
                    f"{configured_bytes}. If these fields are intended, set nw_snd_buffer[3] := {calculated_by_offset // 256}; "
                    f"nw_snd_buffer[4] := {calculated_by_offset % 256}; to include the full payload, then recalculate nw_snd_buffer_length."
                ),
                condition=condition,
            ))
        elif configured_bytes is not None and calculated_by_offset < configured_bytes:
            _append_unique_issue(state.issues, create_issue(
                code,
                "",
                description,
                "Packet Underflow",
                configured_bytes,
                calculated_by_offset,
                source_file,
                start_line,
                "Fill the remaining packet bytes or reduce the configured size for this path.",
                severity="WARNING",
                condition=condition,
            ))

        all_path_issues: List[ValidationIssue] = []
        for parameter in state.parameters:
            for issue in parameter.issues:
                _append_unique_issue(all_path_issues, issue)
        for issue in state.issues:
            _append_unique_issue(all_path_issues, issue)
        has_fail = any(issue.severity == "FAIL" for issue in all_path_issues)
        has_warning = any(issue.severity == "WARNING" for issue in all_path_issues)
        status = "FAIL" if has_fail else "WARNING" if has_warning else "PASS"
        if status == "FAIL":
            packet_result = "FAIL — Packet path contains validation errors"
        elif close_only:
            packet_result = "PASS — GC 11 close command; no payload response required"
        elif configured_bytes is None:
            packet_result = "WARNING — Packet size is not configured on this path"
        else:
            packet_result = packet_size_result(configured_bytes, calculated_by_offset)[0]
            if status == "WARNING" and packet_result.startswith("PASS"):
                packet_result = "WARNING — Packet length matches, with path warnings"
        return {
            "id": f"V{variant_index}",
            "condition": condition,
            "configuredMsb": state.configured_msb,
            "configuredLsb": state.configured_lsb,
            "configuredBytes": configured_bytes,
            "writtenBytes": written_bytes,
            "cursorBytes": cursor_bytes,
            "calculatedByOffset": calculated_by_offset,
            "responseLengthSet": state.response_length_line is not None,
            "responseEnabled": state.response_trigger_value.upper() in {"TRUE", "1"},
            "status": status,
            "packetCalResult": packet_result,
            "issues": [issue_to_json(issue) for issue in all_path_issues],
            "parameters": [variant_parameter_json(parameter) for parameter in state.parameters],
            "_state": state,
        }

    for rel_idx, raw_line in enumerate(block, start=start_line):
        line = clean_block[rel_idx - start_line].strip()
        upper = line.upper()
        if not line:
            continue

        msb_match = re.search(r"nw_snd_buffer\s*\[\s*3\s*\]\s*:=\s*(\d+)\s*;", line, re.IGNORECASE)
        lsb_match = re.search(r"nw_snd_buffer\s*\[\s*4\s*\]\s*:=\s*(\d+)\s*;", line, re.IGNORECASE)
        header_comment = (extract_comment(raw_line) or "").upper()
        is_group_size_assignment = "GROUP SIZE BYTES" in header_comment
        if msb_match or lsb_match:
            for state in active_states:
                # Some groups write response/error codes to [3]/[4] later in
                # nested CASE blocks. Keep the packet-size declaration rather
                # than letting those later status values replace it. Explicit
                # Group size comments identify the authoritative assignment;
                # when comments are absent, retain the first numeric value.
                if msb_match and (is_group_size_assignment or state.configured_msb is None):
                    state.configured_msb = int(msb_match.group(1))
                if lsb_match and (is_group_size_assignment or state.configured_lsb is None):
                    state.configured_lsb = int(lsb_match.group(1))
                    state.configured_lsb_line = rel_idx

        if re.match(r"^IF\b.*\bTHEN\s*;?$", upper):
            conditional_sequence += 1
            context_id = conditional_sequence
            base_states = deepcopy(active_states)
            context = {
                "id": context_id,
                "line": rel_idx,
                "base_states": base_states,
                "outputs": [],
                "labels": [line],
                "has_else": False,
            }
            conditional_stack.append(context)
            active_states = []
            for origin, base_state in enumerate(base_states):
                branch_state = deepcopy(base_state)
                branch_state.conditions.append(line)
                branch_state.branch_origins[context_id] = origin
                active_states.append(branch_state)
            continue

        if re.match(r"^ELSIF\b.*\bTHEN\s*;?$", upper) or upper.rstrip("; ") == "ELSE" or upper.startswith("ELSE "):
            if conditional_stack:
                context = conditional_stack[-1]
                context["outputs"].extend(active_states)
                if upper.startswith("ELSE") and not upper.startswith("ELSIF"):
                    context["has_else"] = True
                context["labels"].append(line)
                active_states = []
                for origin, base_state in enumerate(context["base_states"]):
                    branch_state = deepcopy(base_state)
                    branch_state.conditions.append(line)
                    branch_state.branch_origins[context["id"]] = origin
                    active_states.append(branch_state)
            continue

        if upper.startswith("END_IF"):
            if not conditional_stack:
                continue
            context = conditional_stack.pop()
            context["outputs"].extend(active_states)
            if not context["has_else"]:
                tested = " | ".join(context["labels"])
                for origin, base_state in enumerate(context["base_states"]):
                    unmatched = deepcopy(base_state)
                    unmatched.conditions.append(f"NO MATCH ({tested})")
                    unmatched.branch_origins[context["id"]] = origin
                    _append_unique_issue(unmatched.issues, create_issue(
                        code,
                        "",
                        description,
                        "Conditional No Match",
                        "At least one IF/ELSIF condition or an ELSE branch",
                        "No branch writes packet data",
                        source_file,
                        context["line"],
                        "Add an ELSE packet layout or prove that the selector is restricted to the listed values.",
                        severity="WARNING",
                        condition=f"NO MATCH ({tested})",
                    ))
                    context["outputs"].append(unmatched)

            by_origin: Dict[int, List[_PacketPathState]] = defaultdict(list)
            for output in context["outputs"]:
                origin = output.branch_origins.get(context["id"], 0)
                by_origin[origin].append(output)

            closed_states: List[_PacketPathState] = []
            two_way = len(context["labels"]) == 2
            for origin, origin_states in sorted(by_origin.items()):
                base_conditions = context["base_states"][origin].conditions
                if two_way:
                    signature_groups: Dict[tuple, List[_PacketPathState]] = defaultdict(list)
                    for output in origin_states:
                        signature_groups[state_signature(output)].append(output)
                    for equivalents in signature_groups.values():
                        if len(equivalents) == 1:
                            merged = equivalents[0]
                        else:
                            labels = [
                                " -> ".join(state.conditions[len(base_conditions):])
                                for state in equivalents
                            ]
                            merged = merge_states(equivalents, base_conditions, labels)
                        merged.branch_origins.pop(context["id"], None)
                        closed_states.append(merged)
                else:
                    for output in origin_states:
                        output.branch_origins.pop(context["id"], None)
                        closed_states.append(output)
            active_states = closed_states
            continue

        length_match = re.search(r"\bnw_snd_buffer_length\s*:=\s*([^;]+);", line, re.I)
        response_match = re.search(r"\bnw_snd_response\s*:=\s*([^;]+);", line, re.I)
        if length_match or response_match:
            for state in active_states:
                if length_match:
                    state.response_length_line = rel_idx
                if response_match:
                    state.response_trigger_line = rel_idx
                    state.response_trigger_value = response_match.group(1).strip()

        set_offset = re.match(r"nw_i\s*:=\s*(\d+)\s*(?:;\s*)+$", line, re.IGNORECASE)
        if set_offset:
            target_offset = int(set_offset.group(1))
            for state in active_states:
                state.cursor_initialized = True
                if target_offset > state.current_offset:
                    make_gap(state, target_offset - state.current_offset, rel_idx, "Explicit nw_i cursor jump")
                elif target_offset < state.current_offset:
                    _append_unique_issue(state.issues, create_issue(
                        code,
                        "",
                        description,
                        "Packet Cursor Rewind",
                        f">= {state.current_offset}",
                        target_offset,
                        source_file,
                        rel_idx,
                        "Do not move nw_i backwards over packet bytes already written.",
                        condition=state_condition(state),
                    ))
                    state.current_offset = target_offset
                    state.expected_offset = target_offset
                    state.pending_index = None
            continue

        memcpy_match = re.search(
            r"memcpy\s*\(\s*ADR\((.+?)\)\s*,\s*ADR\((.+?)\)\s*,\s*(.+?)\s*\)\s*;",
            line,
            re.IGNORECASE,
        )
        if memcpy_match:
            dest_expr, src_expr, size_expr = [part.strip() for part in memcpy_match.groups()]
            comment = extract_comment(raw_line) or "No Description"
            operation_sequence += 1
            for state in active_states:
                destination_valid = is_buffer_expr(dest_expr, "nw_snd_buffer")
                if destination_valid:
                    cursor_destination = parse_cursor_buffer_index(dest_expr, "nw_snd_buffer", state.current_offset)
                    running_offset = cursor_destination if cursor_destination is not None else parse_buffer_index(dest_expr, "nw_snd_buffer")
                    parameter_expr = src_expr
                elif is_buffer_expr(src_expr, "nw_rcv_buffer"):
                    cursor_source = parse_cursor_buffer_index(src_expr, "nw_rcv_buffer", state.current_offset)
                    running_offset = cursor_source if cursor_source is not None else parse_buffer_index(src_expr, "nw_rcv_buffer")
                    parameter_expr = dest_expr
                    destination_valid = True
                else:
                    running_offset = state.current_offset
                    parameter_expr = src_expr
                    destination_valid = False

                raw_memcpy_size = evaluate_size_expr(size_expr, parameter_expr)
                resolved_type = resolve_type_info(parameter_expr)
                memcpy_size = raw_memcpy_size
                resolved_packet_type = dereference_type(resolved_type) if resolved_type is not None else None
                if resolved_packet_type is not None and resolved_packet_type.kind == "string":
                    memcpy_size = 50
                elif resolved_packet_type is not None and resolved_packet_type.kind == "bool":
                    memcpy_size = 1
                resolved_type_name = format_parameter_copy_type(parameter_expr, memcpy_size, resolved_type)
                expected_size = expected_memcpy_size(parameter_expr, memcpy_size)
                source_exists = resolved_type is not None
                condition = state_condition(state)
                parameter = PacketParameter(
                    group_code=code,
                    group_description=description,
                    sequence=operation_sequence,
                    parameter_expr=parameter_expr,
                    parameter_name=parameter_expr.strip(),
                    parameter_description=comment,
                    src_expr=src_expr,
                    dest_expr=dest_expr,
                    size_expr=size_expr,
                    memcpy_size=memcpy_size,
                    expected_size=expected_size,
                    resolved_type_name=resolved_type_name,
                    source_exists=source_exists,
                    destination_valid=destination_valid,
                    running_offset=running_offset,
                    expected_offset=state.expected_offset,
                    offset_after_copy=None if running_offset is None or memcpy_size is None else running_offset + memcpy_size,
                    increment_value=None,
                    source_file=source_file,
                    line_number=rel_idx,
                    transfer_method="memcpy",
                    write_evidence=[{
                        "sourceExpression": src_expr,
                        "destinationExpression": dest_expr,
                        "condition": condition,
                        "sourceFile": source_file,
                        "lineNumber": rel_idx,
                "sourceText": lines[rel_idx - 1].strip() if 1 <= rel_idx <= len(lines) else "",
                        "transferMethod": "memcpy",
                    }],
                    condition_context=condition,
                )
                if not state.cursor_initialized and not state.initialization_reported:
                    parameter_issue(
                        state,
                        parameter,
                        "Packet Cursor Initialization",
                        "nw_i := 5 before the first payload write",
                        "NOT FOUND",
                        rel_idx,
                        "Initialize nw_i to the five-byte packet header offset immediately after configuring nw_snd_buffer[3] and [4].",
                    )
                    state.initialization_reported = True
                fixed_destination = parse_buffer_index(dest_expr, "nw_snd_buffer") if destination_valid else None
                if fixed_destination is not None and fixed_destination != state.expected_offset:
                    payload_offset = max(state.expected_offset - PACKET_HEADER_BYTES, 0)
                    expected_destination = "nw_snd_buffer[nw_i]" if payload_offset == 0 else f"nw_snd_buffer[nw_i+{payload_offset}]"
                    parameter_issue(
                        state,
                        parameter,
                        "Hardcoded Packet Destination",
                        expected_destination,
                        dest_expr,
                        rel_idx,
                        (
                            f"Replace the hardcoded buffer index with cursor-relative addressing. At payload offset {payload_offset}, "
                            f"use {expected_destination} from the base cursor, or nw_snd_buffer[nw_i] when nw_i has already been advanced to this field."
                        ),
                    )
                if not source_exists:
                    parameter_issue(state, parameter, "Variable Resolution", "Resolvable variable", "UNRESOLVED", rel_idx, "Declare the source variable or correct the memcpy source reference.")
                if not destination_valid:
                    parameter_issue(state, parameter, "memcpy Destination", "nw_snd_buffer[nw_i] or nw_rcv_buffer[nw_i]", dest_expr, rel_idx, "Copy packet data to the packet buffer destination.")
                if expected_size is None:
                    parameter_issue(state, parameter, "Data Type Resolution", "Resolvable datatype", resolved_type_name, rel_idx, "Define the datatype or correct the parameter expression.", severity="WARNING")
                if memcpy_size is None:
                    parameter_issue(state, parameter, "memcpy Size", "Resolvable memcpy size", size_expr, rel_idx, "Use a literal size or SIZEOF() that resolves to the parameter datatype size.")
                if expected_size is not None and memcpy_size is not None and expected_size != memcpy_size:
                    resolved_kind = dereference_type(resolved_type).kind if resolved_type is not None else None
                    if resolved_kind == "string":
                        parameter_issue(state, parameter, "String Packet Size", 50, memcpy_size, rel_idx, "STRING packet fields are fixed at 50 bytes for packet offset calculation.", severity="WARNING")
                    elif resolved_kind == "bool":
                        parameter_issue(state, parameter, "BOOL Packet Size", 1, memcpy_size, rel_idx, "BOOL packet fields occupy 1 byte; validate nw_i increment against +1.", severity="WARNING")
                    else:
                        parameter_issue(state, parameter, "Data Type Size", expected_size, memcpy_size, rel_idx, "Match the memcpy size to the resolved datatype size.")
                if running_offset is not None and running_offset != state.expected_offset:
                    parameter_issue(state, parameter, "Offset", state.expected_offset, running_offset, rel_idx, "Start the memcpy at the expected running offset.")
                add_parameter(state, parameter)
            continue

        direct_match = re.fullmatch(
            r"(nw_snd_buffer\s*\[\s*nw_i\s*\])\s*:=\s*(.+?)\s*;",
            line,
            re.IGNORECASE,
        )
        if direct_match:
            dest_expr, src_expr = direct_match.groups()
            operation_sequence += 1
            for state in active_states:
                running_offset = state.current_offset
                condition = state_condition(state)
                condition_expr = condition
                identifiers = re.findall(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", condition_expr)
                identifiers = [name for name in identifiers if name.upper() not in {"IF", "THEN", "ELSIF", "ELSE", "NOT", "AND", "OR", "XOR", "TRUE", "FALSE", "ANY", "OF", "NO", "MATCH"}]
                literal = bool(re.fullmatch(r"(?:\d+|TRUE|FALSE)", src_expr.strip(), re.IGNORECASE))
                parameter_name = identifiers[-1] if literal and identifiers else (
                    f"nw_snd_buffer[{running_offset}]" if literal else src_expr.strip()
                )
                parameter = PacketParameter(
                    group_code=code,
                    group_description=description,
                    sequence=operation_sequence,
                    parameter_expr=parameter_name,
                    parameter_name=parameter_name,
                    parameter_description=extract_comment(raw_line) or "Direct packet byte",
                    src_expr=src_expr,
                    dest_expr=dest_expr,
                    size_expr="1",
                    memcpy_size=1,
                    expected_size=1,
                    resolved_type_name="BYTE",
                    source_exists=True,
                    destination_valid=True,
                    running_offset=running_offset,
                    expected_offset=state.expected_offset,
                    offset_after_copy=running_offset + 1,
                    increment_value=None,
                    source_file=source_file,
                    line_number=rel_idx,
                    transfer_method="direct-byte",
                    write_evidence=[{
                        "sourceExpression": src_expr,
                        "destinationExpression": dest_expr,
                        "condition": condition,
                        "sourceFile": source_file,
                        "lineNumber": rel_idx,
                "sourceText": lines[rel_idx - 1].strip() if 1 <= rel_idx <= len(lines) else "",
                        "transferMethod": "direct-byte",
                    }],
                    condition_context=condition,
                )
                if running_offset != state.expected_offset:
                    parameter_issue(state, parameter, "Offset", state.expected_offset, running_offset, rel_idx, "Write the packet byte at the expected running offset.")
                add_parameter(state, parameter)
            continue

        # Extra terminators are empty statements, not extra cursor advances.
        increment_match = re.match(r"nw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*(?:;\s*)+$", line, re.IGNORECASE)
        if increment_match:
            increment = int(increment_match.group(1))
            for state in active_states:
                apply_increment(state, increment, rel_idx)
            continue

    # If malformed source leaves an IF open, retain the active paths and make
    # the structural problem visible instead of silently discarding data.
    if conditional_stack:
        for state in active_states:
            _append_unique_issue(state.issues, create_issue(
                code,
                "",
                description,
                "Conditional Structure",
                "END_IF",
                "NOT FOUND",
                source_file,
                end_line,
                "Close every packet IF block with END_IF.",
                condition=state_condition(state),
            ))

    variants_with_state = [finalize_variant(state, index) for index, state in enumerate(active_states, start=1)]
    packet_variants: List[dict] = []
    for variant in variants_with_state:
        public_variant = dict(variant)
        public_variant.pop("_state", None)
        packet_variants.append(public_variant)

    primary_state = variants_with_state[0]["_state"] if variants_with_state else _PacketPathState()
    primary_parameter_keys = {
        (
            parameter.line_number,
            parameter.parameter_name,
            parameter.running_offset,
            parameter.memcpy_size,
            parameter.transfer_method,
        )
        for parameter in primary_state.parameters
    }
    flattened_parameters: List[PacketParameter] = []
    flattened_by_key: Dict[tuple, PacketParameter] = {}
    for variant in variants_with_state:
        state = variant["_state"]
        for parameter in state.parameters:
            key = (
                parameter.line_number,
                parameter.parameter_name,
                parameter.running_offset,
                parameter.memcpy_size,
                parameter.transfer_method,
            )
            existing = flattened_by_key.get(key)
            if existing is None:
                clone = deepcopy(parameter)
                if key not in primary_parameter_keys:
                    setattr(clone, "_branch_only", True)
                flattened_by_key[key] = clone
                flattened_parameters.append(clone)
            else:
                for evidence in parameter.write_evidence:
                    if evidence not in existing.write_evidence:
                        existing.write_evidence.append(deepcopy(evidence))
                for issue in parameter.issues:
                    _append_unique_issue(existing.issues, deepcopy(issue))

    for sequence, parameter in enumerate(flattened_parameters, start=1):
        parameter.sequence = sequence

    all_issues: List[ValidationIssue] = []
    for parameter in flattened_parameters:
        for issue in parameter.issues:
            _append_unique_issue(all_issues, issue)
    for variant in variants_with_state:
        state = variant["_state"]
        for issue in state.issues:
            _append_unique_issue(all_issues, issue)

    configured_values = [variant.get("configuredBytes") for variant in packet_variants if variant.get("configuredBytes") is not None]
    configured_bytes = configured_values[0] if configured_values else None
    configured_msb = packet_variants[0].get("configuredMsb") if packet_variants else None
    configured_lsb = packet_variants[0].get("configuredLsb") if packet_variants else None
    result = (flattened_parameters, configured_bytes, configured_msb, configured_lsb, all_issues)
    if include_variants:
        return result + (packet_variants,)
    return result


def expand_array_packet_parameters_for_metadata(
    parameters: List[PacketParameter],
) -> Tuple[List[PacketParameter], set]:
    expanded: List[PacketParameter] = []
    array_element_ids: set = set()

    for parameter in parameters:
        if parameter.transfer_method == "direct-byte":
            expanded.append(parameter)
            continue
        base_name, indexes, _ = resolve_path_segments(parameter.parameter_expr)
        symbol = VARIABLES.get(base_name)
        base_type = dereference_type(symbol.type_info) if symbol is not None else None

        if (
            base_type is None
            or base_type.kind != "array"
            or base_type.array_range is None
            or parameter.memcpy_size is None
            or parameter.running_offset is None
            or not indexes
        ):
            expanded.append(parameter)
            continue

        element_type = dereference_type_name(base_type.base) if base_type.base else None
        element_size = size_from_type_info(element_type) if element_type is not None else None
        if not element_size or parameter.memcpy_size <= element_size:
            expanded.append(parameter)
            continue
        if parameter.memcpy_size % element_size != 0:
            expanded.append(parameter)
            continue

        count = parameter.memcpy_size // element_size
        start_index = indexes[-1]
        array_start, array_end = base_type.array_range
        if start_index < array_start or start_index + count - 1 > array_end:
            expanded.append(parameter)
            continue

        for element_no in range(count):
            element_index = start_index + element_no
            clone = copy(parameter)
            clone.parameter_expr = f"{base_name}[{element_index}]"
            clone.parameter_name = clone.parameter_expr
            clone.resolved_type_name = format_type_info(element_type) if element_type is not None else (base_type.base or "UNKNOWN")
            clone.expected_size = element_size
            clone.memcpy_size = element_size
            clone.running_offset = parameter.running_offset + element_no * element_size
            clone.expected_offset = clone.running_offset
            clone.offset_after_copy = clone.running_offset + element_size
            clone.increment_value = element_size
            clone.issues = list(parameter.issues) if element_no == 0 else []
            clone.remarks = list(parameter.remarks) if element_no == 0 else []
            setattr(clone, "_array_element_for_metadata", True)
            expanded.append(clone)
            array_element_ids.add(id(clone))

    return expanded, array_element_ids


def metadata_relative_offset(running_offset: Optional[int]) -> Optional[int]:
    if running_offset is None:
        return None
    return max(int(running_offset) - PACKET_HEADER_BYTES, 0)


def metadata_match_for_parameter(parameter, metadata_rows: List[MetadataParameter]) -> Tuple[Optional[MetadataParameter], str]:
    """Resolve the PLC Parameter to an uploaded metadata Parameter.

    The PLC Parameter is the logic comment. If the PLC declaration has no
    comment, the PLC tag/variable is used as the fallback Parameter value.

    Matching uses stable packet identity before descriptive text:
      1) approved Project Knowledge mapping -> metadata Parameter;
      2) approved Master Knowledge mapping -> metadata Parameter;
      3) exact Group Code + payload-relative offset, preferring matching size;
      4) exact normalized PLC Parameter -> metadata Parameter;
      5) no match.

    A configured mapping is an explicit engineer-approved alias and therefore
    takes precedence over the literal PLC parameter name. PLC tag/variable,
    offset, row order and fuzzy similarity are never used to silently
    substitute a different metadata row. Offset matching keeps the real PLC
    and workbook records aligned while reporting any Parameter-name mismatch.
    """
    plc_parameter=plc_parameter_value(parameter)
    if not plc_parameter:
        return None,"PLC Parameter not available"

    plc_norm=normalize_name(plc_parameter)
    plc_tag=str(getattr(parameter, "parameter_name", getattr(parameter, "parameter", "")) or "").strip()
    plc_tag_norm=normalize_name(plc_tag)
    for source_name, mappings in (("Project Knowledge", load_project_parameter_mappings()), ("Master Knowledge", load_master_parameter_mappings())):
        for mapping in mappings:
            mapping_plc=str(mapping.get("plc_parameter", "")).strip()
            mapping_tag=str(mapping.get("plc_tag", "")).strip()
            # An approved alias belongs to one PLC logic comment/tag pair.
            # Do not apply it when only a similarly named tag or comment matches.
            if plc_norm != normalize_name(mapping_plc) or plc_tag_norm != normalize_name(mapping_tag):
                continue
            target=str(mapping.get("metadata_parameter", "")).strip()
            if not target:
                continue
            for row in metadata_rows:
                if metadata_text_exact(target,row.parameter):
                    return row, f"{source_name} configured mapping"

    plc_offset = metadata_relative_offset(getattr(parameter, "running_offset", None))
    if plc_offset is not None:
        offset_candidates = [row for row in metadata_rows if row.offset is not None and row.offset == plc_offset]
        if offset_candidates:
            exact_name = [row for row in offset_candidates if metadata_text_exact(plc_parameter, row.parameter)]
            if len(exact_name) == 1:
                return exact_name[0], "Exact Group Code + payload offset + Parameter"
            plc_size = getattr(parameter, "memcpy_size", None)
            size_candidates = [row for row in offset_candidates if plc_size is not None and row.size is not None and row.size == plc_size]
            if len(size_candidates) == 1:
                return size_candidates[0], "Exact Group Code + payload offset + size"
            if len(offset_candidates) == 1:
                return offset_candidates[0], "Exact Group Code + payload offset"

    for row in metadata_rows:
        if metadata_text_exact(plc_parameter,row.parameter):
            return row,"Exact PLC Parameter = metadata Parameter"

    return None,"PLC Parameter not found in metadata"

def compare_with_metadata(
    group_code: int,
    description: str,
    parameters: List[PacketParameter],
    metadata_rows: List[MetadataParameter],
    metadata_enabled: bool,
) -> Tuple[List[ValidationIssue], List[MetadataParameter], List[PacketParameter], Optional[int]]:
    issues: List[ValidationIssue] = []
    missing_in_plc: List[MetadataParameter] = []
    extra_in_plc: List[PacketParameter] = []
    expected_bytes = None
    if not metadata_enabled:
        return issues, missing_in_plc, extra_in_plc, expected_bytes
    if metadata_rows:
        packet_sizes = [row.packet_size for row in metadata_rows if row.packet_size is not None]
        if packet_sizes:
            expected_bytes = packet_sizes[0]

    comparison_source_parameters = [
        parameter for parameter in parameters
        if not getattr(parameter, "_branch_only", False)
        and not getattr(parameter, "_skip_metadata", False)
    ]
    comparison_parameters, array_element_ids = expand_array_packet_parameters_for_metadata(comparison_source_parameters)

    metadata_by_norm = defaultdict(list)
    for row in metadata_rows:
        metadata_by_norm[normalize_name(row.parameter)].append(row)
    # Preserve the exact uploaded workbook order. Matching is by Parameter,
    # never by row position or offset.
    metadata_order = list(metadata_rows)

    unused_metadata = list(metadata_order)
    matched: List[Tuple[int, PacketParameter, MetadataParameter, bool, str]] = []
    unmatched_plc: List[PacketParameter] = []

    def take_matching(candidates):
        for candidate in candidates:
            if candidate in unused_metadata:
                unused_metadata.remove(candidate)
                return candidate
        return None

    for plc_index, plc_item in enumerate(comparison_parameters):
        is_array_element = id(plc_item) in array_element_ids
        plc_name = plc_item.parameter_name
        plc_description = plc_item.parameter_description
        resolved, match_method = metadata_match_for_parameter(plc_item, unused_metadata)
        metadata_item = take_matching([resolved]) if resolved is not None else None
        if metadata_item is None:
            unmatched_plc.append(plc_item)
        else:
            matched.append((plc_index, plc_item, metadata_item, is_array_element, match_method))

    for plc_index, plc_item, metadata_item, is_array_element, match_method in matched:
        configured_alias = "configured mapping" in str(match_method).lower()
        if group_code != 30 and not configured_alias and not is_array_element and metadata_item.parameter and not metadata_text_exact(plc_parameter_value(plc_item), metadata_item.parameter):
            issues.append(create_issue(
                group_code, plc_item.parameter_name, plc_item.parameter_description,
                "Parameter Description", metadata_item.parameter, plc_item.parameter_description,
                plc_item.source_file, plc_item.line_number,
                "Align the PLC comment with the metadata Parameter, or approve an explicit mapping.",
                severity="FAIL",
            ))

        datatype_state = metadata_type_compatibility(
            plc_item.resolved_type_name, metadata_item.datatype, group_code
        ) if metadata_item.datatype else "MISMATCH"
        if metadata_item.datatype and datatype_state in {"MISMATCH", "WARNING"}:
            issues.append(create_issue(
                group_code, plc_item.parameter_name, plc_item.parameter_description,
                "Metadata Data Type",
                ("BYTE" if group_code == 30 else (BOOL_METADATA_MODE if normalize_type_name(plc_item.resolved_type_name) == "BOOL" else plc_item.resolved_type_name)),
                metadata_item.datatype,
                plc_item.source_file, plc_item.line_number,
                "Update metadata TAG_DATA_TYPE to match the active PLC datatype representation setting.",
                severity="WARNING" if datatype_state == "WARNING" else "FAIL",
            ))
        plc_metadata_offset = metadata_relative_offset(plc_item.running_offset)
        if metadata_item.offset is not None and plc_metadata_offset is not None and metadata_item.offset != plc_metadata_offset:
            issues.append(create_issue(
                group_code, plc_item.parameter_name, plc_item.parameter_description,
                "Metadata Offset", metadata_item.offset, plc_metadata_offset,
                plc_item.source_file, plc_item.line_number,
                "Align payload-relative packet offset with metadata definition.",
            ))
        if metadata_item.size is not None and plc_item.memcpy_size is not None and metadata_item.size != plc_item.memcpy_size:
            issues.append(create_issue(
                group_code, plc_item.parameter_name, plc_item.parameter_description,
                "Metadata Size", metadata_item.size, plc_item.memcpy_size,
                plc_item.source_file, plc_item.line_number,
                "Match copied bytes to metadata size definition.",
            ))

    for plc_item in unmatched_plc:
        extra_in_plc.append(plc_item)
        issues.append(create_issue(
            group_code, plc_item.parameter_name, plc_item.parameter_description,
            "Missing in Excel", "Metadata row", "NOT FOUND",
            plc_item.source_file, plc_item.line_number,
            "Add parameter to metadata workbook or verify extra field.",
            severity="WARNING",
        ))

    for metadata_item in unused_metadata:
        missing_in_plc.append(metadata_item)
        issues.append(create_issue(
            group_code, metadata_item.parameter, metadata_item.parameter,
            "Missing in PLC", metadata_item.parameter, "NOT FOUND",
            metadata_item.sheet_name, metadata_item.row_number,
            "Add parameter to PLC packet or remove obsolete metadata.",
        ))

    duplicate_metadata = [item for item, count in Counter(normalize_name(row.parameter) for row in metadata_rows).items() if count > 1]
    for norm_name in duplicate_metadata:
        sample = metadata_by_norm[norm_name][0]
        issues.append(
            create_issue(
                group_code,
                sample.parameter,
                sample.description,
                "Duplicate Metadata Parameter",
                "Unique metadata Parameter within Group Code",
                f"{len(metadata_by_norm[norm_name])} entries",
                sample.sheet_name,
                ", ".join(str(item.row_number) for item in metadata_by_norm[norm_name]),
                "Remove or rename duplicate Parameter entries in metadata workbook.",
            )
        )

    return issues, missing_in_plc, extra_in_plc, expected_bytes


def build_effective_metadata_rows_for_group(
    group_code: int,
    packet_parameters: List[PacketParameter],
    metadata_map: Dict[int, List[MetadataParameter]],
    plc_group_codes: Optional[set] = None,
) -> List[MetadataParameter]:
    base_rows = list(metadata_map.get(group_code, []))
    if (
        group_code != 450
        or 600 not in metadata_map
        or (plc_group_codes is not None and 600 in plc_group_codes)
        or not base_rows
    ):
        return base_rows

    ordered_base = sorted(
        base_rows,
        key=lambda item: (item.offset if item.offset is not None else 10**9, item.sequence or 10**9),
    )
    ordered_600 = sorted(
        metadata_map[600],
        key=lambda item: (item.offset if item.offset is not None else 10**9, item.sequence or 10**9),
    )

    normal_count = len(ordered_base)
    if normal_count != 54:
        return base_rows

    tail = packet_parameters[normal_count:]
    overlay_count = min(len(tail), len(ordered_600))
    synthetic_rows: List[MetadataParameter] = []

    removable_issue_types = {
        "Variable Resolution", "Data Type Resolution", "Data Type Size", "Offset",
        "Offset Increment", "Offset After Copy", "Duplicate Offset", "Overlapping Offset",
        "Skipped Offset", "Packet Overflow",
    }

    for idx in range(overlay_count):
        source = ordered_600[idx]
        packet_row = tail[idx]
        packet_row.remarks = [r for r in packet_row.remarks if not r.startswith("Mapped from metadata Group 600")]
        packet_row.issues = [issue for issue in packet_row.issues if issue.validation_type not in removable_issue_types]

        mapped_offset = (162 - PACKET_HEADER_BYTES) + source.offset if source.offset is not None else None
        if mapped_offset is not None:
            packet_row.running_offset = mapped_offset
            packet_row.expected_offset = mapped_offset
            packet_row.offset_after_copy = mapped_offset + (source.size or packet_row.memcpy_size or 0)

        if source.datatype:
            packet_row.resolved_type_name = source.datatype
            packet_row.expected_size = source.size
            packet_row.memcpy_size = source.size

        if source.parameter:
            packet_row.parameter_description = source.parameter

        packet_row.remarks.append("Mapped from metadata Group 600 and transmitted as Group 450")
        synthetic_rows.append(
            MetadataParameter(
                group_code=450,
                sequence=normal_count + idx + 1,
                tag_code=getattr(source, "tag_code", None),
                parameter=source.parameter,
                description=source.description,
                datatype=source.datatype,
                offset=mapped_offset,
                size=source.size,
                packet_size=None,
                min_value=source.min_value,
                max_value=source.max_value,
                shown_value_different=source.shown_value_different,
                sheet_name=f"{source.sheet_name} (mapped to Group 450)",
                units=getattr(source, "units", ""),
                row_number=source.row_number,
            )
        )

    return ordered_base + synthetic_rows


def discover_alarm_group_files() -> List[Path]:
    """Read active HMI and shared definitions, including empty-folder fallback."""
    search_root = LOGICAL_ROOT if LOGICAL_ROOT.exists() else ROOT
    # Shared alarm groups belong to the project, even when the selected HMI
    # has an empty AlarmGroups directory. Do not stop at that empty folder.
    roots = []
    for root in HMI_PAGE_ROOTS:
        if root.is_dir() and root.resolve().is_relative_to(search_root.resolve()):
            roots.append(root)
    if not roots:
        roots = [search_root]
    shared = next((path for path in search_root.iterdir() if path.is_dir() and path.name.casefold() == "vcshared"), None) if search_root.is_dir() else None
    if shared is not None:
        roots.append(shared)
    return sorted(
        {path for root in roots for path in root.rglob("*")
         if path.is_file() and path.suffix.casefold() == ".algrp"
         and path.name.casefold() != "systemalarms.algrp"
         and not is_ignored_project_path(path)},
        key=lambda path: str(path).casefold(),
    )


RING_FRAME_SKIPPED_ALARM_PREFIXES = (
    "YBS SENSOR FAILURE SPINDLE NO",
    "CURRENT PNEUMAFILL EXCEEDED",
    "eb/100sh EXCEEDED. Current Value",
    "YBS SENSOR FAILURE IN MORE SPINDLES",
    "RSM COIL FAILURE SPINDLE NO",
    "YBS ABNORMAL SLIP SPINDLE NO",
    "RSM COMMUNICATION FAILURE DUCT",
)


def skip_ring_frame_alarm(description: str, array_name: str = "") -> bool:
    department = re.sub(r"[^a-z0-9]", "", ACTIVE_MACHINE_DEPARTMENT.casefold())
    array = re.sub(r"[^a-z0-9]", "", str(array_name).casefold())
    if department not in {"rf", "ringframe"} and array != "rfalarm":
        return False
    caption = " ".join(str(description).split()).casefold()
    return any(caption.startswith(prefix.casefold()) for prefix in RING_FRAME_SKIPPED_ALARM_PREFIXES)


def extract_alarm_descriptions() -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    group_code = 30

    for path in discover_alarm_group_files():
        try:
            root = ET.parse(path).getroot()
        except Exception:
            continue

        for description in english_text_values(root).values():
            if description and not skip_ring_frame_alarm(description, alarm_image_name(root)):
                rows.append((group_code, description))
    return rows


def extract_group30_alarm_transport() -> Optional[Tuple[str, int, int]]:
    """Read the transmitted alarm array, last bit, and first packed byte from PLC."""
    if not PLC_PACKET_FILE.exists():
        return None
    text = PLC_PACKET_FILE.read_text(encoding="utf-8", errors="ignore")
    match = re.search(
        r"(?P<byte_counter>[A-Za-z_]\w*)\s*:=\s*(?P<first_byte>\d+)\s*;"
        r".*?FOR\s+(?P<bit_counter>[A-Za-z_]\w*)\s*:=\s*0\s+TO\s+(?P<last_bit>\d+)\s+BY\s+1\s+DO"
        r".*?IF\s*\(\s*(?P<alarm_array>[A-Za-z_]\w*)\s*\[\s*(?P=bit_counter)\s*\]"
        r".*?Temp_nw_snd_buffer\s*\[\s*(?P=byte_counter)\s*\]",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return (
        match.group("alarm_array"),
        int(match.group("last_bit")),
        int(match.group("first_byte")),
    )


def alarm_packing_sources() -> List[Path]:
    sources = {PLC_PACKET_FILE} if PLC_PACKET_FILE.is_file() else set()
    search_root = LOGICAL_ROOT if LOGICAL_ROOT.exists() else ROOT
    sources.update(path for path in search_root.rglob("*") if path.is_file()
                   and path.suffix.casefold() in {".st", ".src", ".ab"}
                   and not is_ignored_project_path(path))
    return sorted(sources, key=lambda path: str(path).casefold())


def extract_direct_alarm_packings(path: Path, lines: List[str]) -> List[Dict[str, Any]]:
    """Read literal alarm-to-byte assignments without assuming sequential bits.

    Track IF branches so an ELSE, negated condition or unrelated BIT_SET does
    not acquire the preceding alarm's caption. Comments are already masked.
    """
    code = "\n".join(lines)
    tokens = re.compile(
        r"\b(?P<branch>IF|ELSIF)\b\s*(?P<condition>.*?)\bTHEN\b"
        r"|\b(?P<end>END_IF|ELSE)\b"
        r"|(?P<write>(?P<buffer>\w+)\s*\[\s*(?P<byte>-?\d+)\s*\]\s*:=\s*"
        r"BIT_SET\s*\(\s*(?P<read_buffer>\w+)\s*\[\s*(?P<read_byte>-?\d+)\s*\]"
        r"\s*,\s*(?P<bit>-?\d+)\s*\)\s*;)", re.I | re.S,
    )
    conditions = []
    grouped = defaultdict(list)
    for token in tokens.finditer(code):
        if token.group("branch"):
            condition = token.group("condition").strip()
            # Strip enclosing parentheses only; compound/negated conditions
            # intentionally remain unresolved rather than guessing a mapping.
            while condition.startswith("(") and condition.endswith(")"):
                condition = condition[1:-1].strip()
            alarm = re.fullmatch(
                r"([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]"
                r"(?:\s*(?:=\s*(?:TRUE|1)|<>\s*(?:FALSE|0)))?", condition, re.I,
            )
            binding = (alarm.group(1), int(alarm.group(2))) if alarm else None
            if token.group("branch").casefold() == "if":
                conditions.append(binding)
            elif conditions:
                # A positive ELSIF cannot override an earlier alarm guard.
                # Keep the branch unresolved if that guard was alarm-related.
                previous = conditions[-1]
                conditions[-1] = binding if previous is None else None
        elif token.group("end"):
            if conditions:
                if token.group("end").casefold() == "end_if":
                    conditions.pop()
                else:
                    conditions[-1] = None
        else:
            bindings = {(name.casefold(), index): name for binding in conditions if binding
                        for name, index in [binding]}
            if len(bindings) != 1 or not re.fullmatch(r"temp_nw_snd_buffer\d*", token.group("buffer"), re.I):
                continue
            (_, alarm_index), array = next(iter(bindings.items()))
            buffer = token.group("buffer")
            grouped[(array.casefold(), buffer.casefold())].append({
                "array": array, "index": alarm_index, "buffer": buffer,
                "byte": int(token.group("byte")), "bit": int(token.group("bit")),
                "readBuffer": token.group("read_buffer"), "readByte": int(token.group("read_byte")),
                "line": code[:token.start()].count("\n") + 1,
            })
    packings = []
    for entries in grouped.values():
        first_byte = min(entry["byte"] for entry in entries)
        last_byte = max(entry["byte"] for entry in entries)
        indices = {entry["index"] for entry in entries}
        packings.append({
            "kind": "direct", "entries": entries, "path": path,
            "file": str(safe_relative_path(path)), "line": entries[0]["line"],
            "writeLine": entries[0]["line"], "array": entries[0]["array"],
            "lower": min(indices), "upper": max(indices), "step": None,
            "boundsText": "Explicit BIT_SET assignments", "count": len(indices),
            "bytes": last_byte - first_byte + 1, "firstByte": first_byte, "firstBit": 0,
            "buffer": entries[0]["buffer"], "readBuffer": entries[0]["buffer"],
        })
    return packings


def extract_alarm_packings() -> List[Dict[str, Any]]:
    """Keep loops and explicit alarm assignments scoped to their actual buffer."""
    packings = []
    for path in alarm_packing_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "bit_set" not in text.casefold():
            continue
        lines = packet_code_lines(text)
        for index, line in enumerate(lines):
            loop = re.search(r"\bFOR\s+(\w+)\s*:=\s*(.*?)\s+TO\s+(.*?)(?:\s+BY\s+(.*?))?\s+DO\b", line, re.I)
            if not loop:
                continue
            depth = 1
            end = index
            for end in range(index + 1, len(lines)):
                depth += len(re.findall(r"\bFOR\b", lines[end], re.I))
                depth -= len(re.findall(r"\bEND_FOR\b", lines[end], re.I))
                if depth == 0:
                    break
            body = "\n".join(lines[index + 1:end])
            counter = loop.group(1)
            alarm = re.search(r"\bIF\s*\(?\s*([A-Za-z_]\w*)\s*\[\s*" + re.escape(counter) + r"\s*\]", body, re.I)
            write = re.search(r"(\w+)\s*\[\s*(\w+)\s*\]\s*:=\s*BIT_SET\s*\(\s*(\w+)\s*\[\s*(\w+)\s*\]\s*,\s*(\w+)\s*\)", body, re.I)
            if not alarm or not write or not any(re.fullmatch(r"temp_nw_snd_buffer\d*", name, re.I)
                                                for name in (write.group(1), write.group(3))):
                continue
            prefix = "\n".join(lines[:index])
            def initialized(name):
                values = re.findall(r"\b" + re.escape(name) + r"\s*:=\s*(\d+)\s*;", prefix, re.I)
                return int(values[-1]) if values else None
            first_byte, first_bit = initialized(write.group(2)), initialized(write.group(5))
            lower, upper, step = to_int(loop.group(2)), to_int(loop.group(3)), to_int(loop.group(4) or "1")
            count = (upper - lower) // step + 1 if lower is not None and upper is not None and step and step > 0 and upper >= lower else None
            packed_bytes = (count + first_bit + 7) // 8 if count is not None and first_bit is not None else None
            packings.append({
                "path": path, "file": str(safe_relative_path(path)), "line": index + 1,
                "writeLine": index + 2 + body[:write.start()].count("\n"),
                "array": alarm.group(1), "lower": lower, "upper": upper, "step": step,
                "boundsText": f"{loop.group(2)} TO {loop.group(3)} BY {loop.group(4) or '1'}",
                "count": count, "bytes": packed_bytes, "firstByte": first_byte, "firstBit": first_bit,
                "buffer": write.group(1), "readBuffer": write.group(3),
                "byteCounter": write.group(2), "readCounter": write.group(4), "bitCounter": write.group(5),
                "body": body,
            })
        packings.extend(extract_direct_alarm_packings(path, lines))
    return packings


def alarm_array_type(name: str, path: Path) -> Optional[TypeInfo]:
    for candidate in sorted(path.parent.glob("*.var")):
        declarations = parse_var_sections(candidate.read_text(encoding="utf-8", errors="ignore"))
        match = next((value for key, value in declarations.items() if key.casefold() == name.casefold()), None)
        if match:
            return dereference_type(match)
    symbol = next((value for key, value in VARIABLES.items() if key.casefold() == name.casefold()), None)
    return dereference_type(symbol.type_info) if symbol else None


def validate_alarm_packings(packings: List[Dict[str, Any]], parameters: List[PacketParameter]) -> List[ValidationIssue]:
    issues = []
    array_names = {packing["array"].casefold() for packing in packings}
    if array_names:
        for path in discover_alarm_group_files():
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            image_name = alarm_image_name(root)
            if image_name not in array_names:
                issues.append(create_issue(30, image_name or path.stem, "Alarm definition binding", "Alarm Packing Ambiguous",
                                           "AlarmImage bound to one of: " + ", ".join(sorted(array_names)), image_name or "Not configured",
                                           str(safe_relative_path(path)), 1,
                                           "Verify this alarm group's AlarmImage against the packed array. Legacy single-array caption fallback is not proof that the variables are connected; correct the binding or verify an explicit alias.", severity="WARNING"))
    direct_bits = defaultdict(list)
    for packing in packings:
        for entry in packing.get("entries", []):
            direct_bits[(entry["buffer"].casefold(), entry["byte"], entry["bit"])].append((packing, entry))
    for (_, byte, bit), assignments in direct_bits.items():
        identities = {(entry["array"].casefold(), entry["index"]) for _, entry in assignments}
        if len(identities) > 1:
            packing, entry = assignments[-1]
            references = "; ".join(f"{item['array']}[{item['index']}] at {owner['file']}:{item['line']}"
                                   for owner, item in assignments)
            issues.append(create_issue(30, entry["array"], "Multiple alarms share a transmitted bit", "Alarm Bit Collision",
                                       "A separate bit for each independently identifiable alarm",
                                       f"{entry['buffer']}[{byte}], bit {bit}: {references}",
                                       packing["file"], entry["line"],
                                       "Verify whether this shared bit is intentional. To identify the alarms separately, assign distinct bits and update the packing/copy length as needed. Sheet2 retains both captions at the actual shared bit."))
    for packing in packings:
        name, buffer = packing["array"], packing["buffer"]
        description = f"Pack {name} into {buffer} for Group 30"
        def add(kind, expected, actual, fix, line=None, severity="FAIL", file=None):
            issues.append(create_issue(30, name, description, kind, expected, actual,
                                       file or packing["file"], line or packing["line"], fix, severity=severity))
        bounds = alarm_array_type(name, packing["path"])
        if bounds is None or bounds.kind != "array" or bounds.array_range is None:
            add("Alarm Array Missing", "Declared alarm array with known bounds", name,
                f"Check the spelling of {name} and declare the alarm array before accessing its bits.")
        elif packing["count"] is not None:
            low, high = bounds.array_range
            if packing["lower"] < low or packing["upper"] > high:
                add("Alarm Array Bounds", f"Indices {low} through {high}", f"Assigned indices {packing['lower']} through {packing['upper']}",
                    f"Keep alarm accesses within declared {name}[{low}..{high}]. A smaller assigned-alarm range is valid; it need not fill the array capacity. ST includes both endpoints.")
        if packing.get("kind") == "direct":
            for entry in packing["entries"]:
                if not 0 <= entry["bit"] <= 7 or entry["byte"] < 0:
                    add("Alarm Bit Position", "A nonnegative byte index and bit 0..7",
                        f"{buffer}[{entry['byte']}], bit {entry['bit']}",
                        "Use a valid byte/bit position for this alarm.", entry["line"])
                if buffer.casefold() != entry["readBuffer"].casefold() or entry["byte"] != entry["readByte"]:
                    add("Alarm Buffer Mismatch", f"BIT_SET reads and writes {buffer}[{entry['byte']}]",
                        f"Reads {entry['readBuffer']}[{entry['readByte']}] but writes {buffer}[{entry['byte']}]",
                        "Read and write the same alarm buffer byte in BIT_SET.", entry["line"])
        if packing["count"] is None or packing["firstByte"] is None or packing["firstBit"] is None:
            add("Alarm Loop Bounds", "Known inclusive loop limits and initialized byte/bit counters", packing["boundsText"],
                "Use resolvable loop limits and initialize the packed byte index and bit position before the FOR loop.", severity="WARNING")
            continue
        if packing.get("kind") != "direct" and (buffer.casefold() != packing["readBuffer"].casefold() or packing["byteCounter"].casefold() != packing["readCounter"].casefold()):
            add("Alarm Buffer Mismatch", f"BIT_SET reads and writes {buffer}[{packing['byteCounter']}]",
                f"Reads {packing['readBuffer']}[{packing['readCounter']}] but writes {buffer}[{packing['byteCounter']}]",
                f"Use the same buffer and byte counter on both sides of BIT_SET. Verify this alarm group belongs to {buffer}.", packing["writeLine"])
        if packing.get("kind") != "direct":
            body = packing["body"]
            bit, byte = map(re.escape, (packing["bitCounter"], packing["byteCounter"]))
            sequence_ok = (packing["step"] == 1 and packing["firstBit"] == 0
                           and re.search(r"\b" + bit + r"\s*:=\s*" + bit + r"\s*\+\s*1\s*;", body, re.I)
                           and re.search(r"\bIF\s*\(?\s*" + bit + r"\s*=\s*8\b", body, re.I)
                           and re.search(r"\b" + byte + r"\s*:=\s*" + byte + r"\s*\+\s*1\s*;", body, re.I)
                           and re.search(r"\b" + bit + r"\s*:=\s*0\s*;", body, re.I))
            if not sequence_ok:
                add("Alarm Packing Sequence", "One bit per iteration; move to the next byte after 8 bits", packing["boundsText"],
                    "Start bit_pos at 0, increment it by 1 each iteration, and at 8 increment the byte index and reset bit_pos to 0.")
        for buffer_name in dict.fromkeys((buffer, packing["readBuffer"])):
            buffer_type = alarm_array_type(buffer_name, packing["path"])
            last_byte = packing["firstByte"] + packing["bytes"] - 1
            if buffer_type and buffer_type.array_range:
                low, high = buffer_type.array_range
                if packing["firstByte"] < low or last_byte > high:
                    add("Alarm Buffer Capacity", f"{buffer_name}[{low}..{high}]", f"Packing writes bytes {packing['firstByte']}..{last_byte}",
                        f"Increase {buffer_name}'s capacity or reduce the alarm range. {packing['count']} bits require {packing['bytes']} bytes.")
        copies = []
        for parameter in parameters:
            match = re.fullmatch(r"\s*" + re.escape(buffer) + r"\s*\[\s*(\d+)\s*\]\s*", parameter.src_expr, re.I)
            if match:
                copies.append((parameter, int(match.group(1))))
        if not copies:
            add("Alarm Copy Missing", f"Group 30 copies {packing['bytes']} bytes from {buffer}[{packing['firstByte']}]", "No Group 30 copy found",
                f"Add the Group 30 memcpy for {buffer}[{packing['firstByte']}] and advance nw_i by {packing['bytes']}; include all payload fields in the size header.")
        for parameter, start in copies:
            if bounds and bounds.array_range and packing["count"] is not None:
                low, high = bounds.array_range
                if low <= packing["lower"] <= packing["upper"] <= high:
                    note = (f"Alarm packing: {name}[{packing['lower']}..{packing['upper']}] has {packing['count']} assigned alarm indices in {packing['bytes']} bytes within declared capacity [{low}..{high}]. A smaller assigned-alarm range is valid.")
                    if note not in parameter.remarks: parameter.remarks.append(note)
            if start != packing["firstByte"]:
                add("Alarm Copy Start", f"{buffer}[{packing['firstByte']}]", f"{buffer}[{start}]",
                    f"Start the memcpy at {buffer}[{packing['firstByte']}] because the alarm packer starts writing there. Copying from [{start}] shifts the alarm mapping.", parameter.line_number, file=parameter.source_file)
            if parameter.memcpy_size != packing["bytes"]:
                fix = (f"The explicit assignments write {buffer}[{packing['firstByte']}..{packing['firstByte'] + packing['bytes'] - 1}]. Copy these {packing['bytes']} bytes and advance nw_i accordingly; recalculate the Group 30 payload size."
                       if packing.get("kind") == "direct" else
                       f"The inclusive range {packing['lower']}..{packing['upper']} contains {packing['count']} bits. Round up {packing['count']}/8 to {packing['bytes']} bytes; set the memcpy length and matching nw_i increment, then recalculate the Group 30 payload size.")
                add("Alarm Copy Size", f"{packing['bytes']} bytes for {packing['count']} assigned alarm indices", f"{parameter.memcpy_size} bytes copied",
                    fix, parameter.line_number, file=parameter.source_file)
    return issues


def alarm_image_name(root) -> str:
    properties = {node.get("Name"): node.get("Value") for node in root.findall("./{*}Property")}
    image = str(properties.get("AlarmImage") or "")
    match = re.fullmatch(r"Source\[[^]]+\]\.Variable\[(.*)\]", image, re.I)
    return re.sub(r"\[.*", "", (match.group(1) if match else image).split(".")[-1]).casefold()


def extract_group30_alarm_bits(include_buffer: bool = False) -> List[tuple]:
    """Map all non-system alarm definitions to the transmitted Group 30 bytes.

    Legacy projects can retain a different AlarmImage name from the packet
    array. The configured IndexMap and ImageOffset supply alarm positions;
    filenames, XML ordering, and variable-name equality do not supply positions.
    """
    rows: List[Tuple[int, int, str, str]] = []
    packings = [item for item in extract_alarm_packings() if item["count"] is not None
                and item["firstByte"] is not None and item["firstBit"] in {0, None}
                and item["buffer"].casefold() == item["readBuffer"].casefold()]
    if not packings:
        return rows
    array_names = {item["array"].casefold() for item in packings}
    for path in discover_alarm_group_files():
        try:
            root = ET.parse(path).getroot()
        except Exception:
            continue
        properties = {node.get("Name"): node.get("Value")
                      for node in root.findall("./{*}Property")}
        image_offset = to_int(properties.get("ImageOffset", "0"))
        if image_offset is None or image_offset < 0:
            continue
        english = english_text_values(root)
        image_name = alarm_image_name(root)
        matched_packings = [item for item in packings if item["array"].casefold() == image_name]
        # Retain the verified legacy alias fallback only when one alarm array
        # is packed. Multiple arrays require an unambiguous AlarmImage binding.
        if not matched_packings and len(array_names) == 1:
            matched_packings = packings
        for index in root.findall(".//{*}IndexMap/{*}Index"):
            alarm_index = to_int(index.attrib.get("Value"))
            description = english.get(str(index.attrib.get("ID", "")), "").strip()
            if alarm_index is None or not description or alarm_index < 0:
                continue
            alarm_index += image_offset
            for packing in matched_packings:
                if skip_ring_frame_alarm(description, packing["array"]):
                    continue
                if not packing["lower"] <= alarm_index <= packing["upper"]:
                    continue
                source = str(safe_relative_path(path))
                if packing.get("kind") == "direct":
                    positions = [(entry["byte"], entry["bit"]) for entry in packing["entries"]
                                 if entry["index"] == alarm_index and entry["byte"] >= 0 and 0 <= entry["bit"] <= 7
                                 and entry["buffer"].casefold() == entry["readBuffer"].casefold()
                                 and entry["byte"] == entry["readByte"]]
                else:
                    relative_bit = alarm_index - packing["lower"]
                    positions = [(packing["firstByte"] + relative_bit // 8, relative_bit % 8)]
                for byte, bit in positions:
                    rows.append((packing["buffer"], byte, bit, description, source) if include_buffer
                                else (byte, bit, description, source))
    return sorted(set(rows), key=lambda row: tuple(str(value) if isinstance(value, str) else value for value in row[:3]))


def find_duplicate_metadata_parameters(
    metadata_rows: Dict[int, List[MetadataParameter]],
) -> List[MetadataParameter]:
    duplicate_rows: List[MetadataParameter] = []
    for group_code, rows in metadata_rows.items():
        buckets: Dict[str, List[MetadataParameter]] = defaultdict(list)
        for row in rows:
            key = re.sub(r"\s+", " ", str(row.parameter or "").strip()).casefold()
            if key:
                buckets[key].append(row)
        for bucket in buckets.values():
            if len(bucket) > 1:
                duplicate_rows.extend(bucket)
    return duplicate_rows


def build_group_results(
    packet_enabled: bool = True,
    offset_enabled: bool = True,
    metadata_compare_enabled: bool = True,
) -> Tuple[List[GroupResult], List[ValidationIssue], List[MetadataParameter], List[PacketParameter]]:
    metadata_info = load_metadata() if metadata_compare_enabled else MetadataInfo(path=None, rows=defaultdict(list), issues=[])
    metadata_path = metadata_info.path
    metadata_map = metadata_info.rows
    metadata_issues = metadata_info.issues
    metadata_enabled = metadata_compare_enabled and metadata_path is not None and bool(metadata_map)

    groups_found: List[Tuple[Path, int, str, int, int]] = []
    duplicate_group_issues: List[ValidationIssue] = []
    group_occurrences: Dict[int, List[Tuple[str, int]]] = defaultdict(list)

    if PLC_PACKET_FILE.exists():
        metadata_issues.extend(packet_source_diagnostics(PLC_PACKET_FILE))
        for code, description, start_line, end_line in extract_case_blocks(PLC_PACKET_FILE):
            groups_found.append((PLC_PACKET_FILE, code, description, start_line, end_line))
            group_occurrences[code].append((str(safe_relative_path(PLC_PACKET_FILE)), start_line))
        if not groups_found:
            metadata_issues.append(
                create_issue(
                    "GLOBAL", "", "PLC packet source", "Group Code Extraction",
                    "At least one CASE nw_group_code block", "0 groups extracted",
                    str(safe_relative_path(PLC_PACKET_FILE)), "",
                    "Verify the selected packet source contains CASE nw_group_code logic or provide the correct mms_nw_r source file."
                )
            )
    else:
        metadata_issues.append(
            create_issue(
                "GLOBAL", "", "PLC packet source", "PLC File Validated",
                str(safe_relative_path(PLC_PACKET_FILE)), "NOT FOUND", "", None,
                "Restore the required PLC packet source file before running packet validation.",
            )
        )

    for code, occurrences in group_occurrences.items():
        if len(occurrences) > 1:
            first_file, first_line = occurrences[0]
            duplicate_group_issues.append(
                create_issue(code, "", "Group Code", "Duplicate Group Codes", "Single definition", f"{len(occurrences)} definitions", first_file, first_line, "Keep only one active definition of this group code.")
            )

    results: List[GroupResult] = []
    missing_in_plc_rows: List[MetadataParameter] = []
    extra_in_plc_rows: List[PacketParameter] = []
    all_issues: List[ValidationIssue] = metadata_issues + duplicate_group_issues
    alarm_packings = extract_alarm_packings()

    plc_group_codes = {code for _, code, _, _, _ in groups_found}
    metadata_group_codes = set(metadata_map.keys())

    virtual_metadata_group_codes = set(metadata_group_codes)
    if 450 in plc_group_codes and 600 in virtual_metadata_group_codes and 600 not in plc_group_codes:
        virtual_metadata_group_codes.discard(600)

    if metadata_enabled:
        for code in sorted(virtual_metadata_group_codes - plc_group_codes):
            for row in metadata_map[code]:
                issue = create_issue(code, row.parameter, row.description, "Group Code Exists", row.group_code, "NOT FOUND IN PLC", row.sheet_name, row.row_number, "Add missing group code in PLC or remove from metadata.")
                all_issues.append(issue)
                missing_in_plc_rows.append(row)
        for code in sorted(plc_group_codes - metadata_group_codes):
            issue = create_issue(code, "", "Group Code", "Missing Group Code in Excel", "Metadata group code", "NOT FOUND", "", "", "Add group code to metadata workbook.", severity="WARNING")
            all_issues.append(issue)

    for path, code, description, start_line, end_line in groups_found:
        (
            packet_parameters,
            configured_bytes,
            configured_msb,
            configured_lsb,
            group_issues,
            packet_variants,
        ) = parse_group(path, code, description, start_line, end_line, include_variants=True, validate_response_setup=True)
        if code == 30:
            alarm_issues = validate_alarm_packings(alarm_packings, packet_parameters)
            group_issues.extend(alarm_issues)
            for variant in packet_variants:
                if alarm_issues:
                    source_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    variant["issues"].extend(packet_issue_json(issue, str(safe_relative_path(path)), source_lines) for issue in alarm_issues)
                    if any(issue.severity == "FAIL" for issue in alarm_issues):
                        variant["status"] = "FAIL"
                        variant["packetCalResult"] = "FAIL — Alarm packing or Group 30 transport is invalid"
                    elif variant["status"] == "PASS":
                        variant["status"] = "WARNING"
                        variant["packetCalResult"] = "WARNING — Alarm packing requires review"
        metadata_rows = build_effective_metadata_rows_for_group(code, packet_parameters, metadata_map, plc_group_codes)
        # Keep metadata rows in the same order as the uploaded workbook.
        metadata_order = list(metadata_rows)
        metadata_compare_issues, missing_rows, extra_rows, expected_bytes = compare_with_metadata(code, description, packet_parameters, metadata_rows, metadata_enabled)
        missing_in_plc_rows.extend(missing_rows)
        extra_in_plc_rows.extend(extra_rows)
        group_issues.extend(metadata_compare_issues)

        # Packet totals are calculated per executable path. Taking the maximum
        # path value preserves the legacy scalar summary without adding fields
        # from mutually exclusive IF/ELSIF/ELSE branches together.
        if packet_variants:
            calculated_bytes = max((to_int(item.get("writtenBytes")) or 0) for item in packet_variants)
            calculated_offset_bytes = max((to_int(item.get("calculatedByOffset")) or 0) for item in packet_variants)
        else:
            calculated_bytes = 0
            calculated_offset_bytes = 0

        logical_packet_parameters, _ = expand_array_packet_parameters_for_metadata(packet_parameters)
        for display_sequence, logical_param in enumerate(logical_packet_parameters, start=1):
            logical_param.sequence = display_sequence

        param_rows: List[ParameterRow] = []
        pass_count = 0
        fail_count = 0
        warning_count = 0

        offset_related_types = {
            "Metadata Offset", "Skipped Offset", "Offset",
            "Offset After Copy", "Duplicate Offset", "Overlapping Offset"
        }
        root_cause_sequences = sorted(
            p.sequence for p in logical_packet_parameters
            if p.sequence is not None and any(
                str(issue.validation_type) == "Offset Increment"
                and str(issue.severity).upper() == "FAIL"
                for issue in getattr(p, "issues", [])
            )
        )

        unused_display_metadata = list(metadata_order)
        for param in logical_packet_parameters:
            metadata_match, metadata_match_method = (None, "Not checked")
            if not getattr(param, "_branch_only", False) and not getattr(param, "_skip_metadata", False):
                candidate, candidate_method = metadata_match_for_parameter(param, unused_display_metadata)
                metadata_match_method = candidate_method
                if candidate is not None:
                    metadata_match = candidate
                    unused_display_metadata.remove(candidate)

            param_fail = any(issue.severity == "FAIL" for issue in param.issues)
            param_warn = any(issue.severity == "WARNING" for issue in param.issues)

            issue_types = {str(issue.validation_type) for issue in param.issues}
            only_offset_cascade = bool(issue_types) and issue_types.issubset(offset_related_types)
            first_root_sequence = root_cause_sequences[0] if root_cause_sequences else None
            affected_by_root = (
                first_root_sequence is not None
                and param.sequence is not None
                and param.sequence > first_root_sequence
                and only_offset_cascade
            )

            if affected_by_root:
                status = "AFFECTED"
                param_fail = False
                param_warn = False
            else:
                status = "FAIL" if param_fail else "WARNING" if param_warn else "PASS"

            remarks = "; ".join(issue.validation_type for issue in param.issues) if param.issues else "OK"
            if affected_by_root:
                root_param = next(
                    (p.parameter_name for p in logical_packet_parameters if p.sequence == first_root_sequence),
                    "previous parameter"
                )
                remarks = f"AFFECTED BY ROOT CAUSE: {root_param}; fix the nw_i increment above and revalidate."

            validation_type = "; ".join(issue.validation_type for issue in param.issues)
            expected_value = "; ".join(issue.expected for issue in param.issues)
            actual_value = "; ".join(issue.actual for issue in param.issues)
            severity = "; ".join(issue.severity for issue in param.issues)

            detail_remarks = []
            if getattr(param, "_branch_only", False):
                detail_remarks.append("CONDITIONAL BRANCH ISSUE")
            for issue in param.issues:
                issue_type = str(issue.validation_type or "")
                if issue_type in {"Offset Increment", "Offset After Copy"}:
                    detail = str(issue.suggested_fix or "").strip()
                    if detail:
                        detail_remarks.append(detail)
                elif issue_type == "Offset":
                    detail_remarks.append(f"FAIL: expected start offset {issue.expected}, actual {issue.actual}")
            if detail_remarks and not affected_by_root:
                remarks = "; ".join(dict.fromkeys(detail_remarks))

            param_rows.append(
                ParameterRow(
                    group_code=code,
                    sequence=param.sequence,
                    parameter=param.parameter_name,
                    parameter_description=param.parameter_description,
                    data_type=param.resolved_type_name,
                    declared_data_type=param.resolved_type_name,
                    memcpy_size=param.memcpy_size,
                    declared_size=param.expected_size,
                    running_offset=param.running_offset,
                    offset_buffer=None if param.running_offset is None else max(param.running_offset - 5, 0),
                    expected_offset=param.expected_offset,
                    metadata_group_code=None if metadata_match is None else metadata_match.group_code,
                    metadata_parameter="" if metadata_match is None else metadata_match.parameter,
                    metadata_description="" if metadata_match is None else metadata_match.description,
                    metadata_data_type="" if metadata_match is None else metadata_match.datatype,
                    metadata_size=None if metadata_match is None else metadata_match.size,
                    metadata_offset=None if metadata_match is None else metadata_match.offset,
                    metadata_sequence=None if metadata_match is None else metadata_match.sequence,
                    metadata_tag_code=None if metadata_match is None else metadata_match.tag_code,
                    metadata_min_value=None if metadata_match is None else metadata_match.min_value,
                    metadata_max_value=None if metadata_match is None else metadata_match.max_value,
                    metadata_shown_value_different="" if metadata_match is None else metadata_match.shown_value_different,
                    metadata_sheet_name="" if metadata_match is None else metadata_match.sheet_name,
                    metadata_row_number=None if metadata_match is None else metadata_match.row_number,
                    metadata_match_method=metadata_match_method,
                    increment_value=param.increment_value,
                    source_expression=param.src_expr,
                    destination_expression=param.dest_expr,
                    offset_after_copy=param.offset_after_copy,
                    status=status,
                    remarks=remarks,
                    validation_type=validation_type,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    severity=severity,
                    source_file=param.source_file,
                    line_number=param.line_number,
                    increment_line_number=getattr(param, "increment_line_number", None),
                    increment_relation=getattr(param, "increment_relation", ""),
                    sequence_validation=getattr(param, "sequence_validation", "NOT FOUND"),
                    transfer_method=param.transfer_method,
                    write_evidence=param.write_evidence,
                    condition_context=getattr(param, "condition_context", ""),
                    metadata_primary_path=not getattr(param, "_branch_only", False),
                )
            )

            if status == "PASS":
                pass_count += 1
            elif status == "FAIL":
                fail_count += 1
            else:
                warning_count += 1

        variant_fail = any(str(item.get("status", "")).upper() == "FAIL" for item in packet_variants)
        variant_warning = any(str(item.get("status", "")).upper() == "WARNING" for item in packet_variants)
        group_issue_fail = any(str(getattr(issue, "severity", "")).upper() == "FAIL" for issue in group_issues)
        group_issue_warning = any(str(getattr(issue, "severity", "")).upper() == "WARNING" for issue in group_issues)
        overall_status = (
            "FAIL" if fail_count > 0 or variant_fail or group_issue_fail
            else "WARNING" if warning_count > 0 or variant_warning or group_issue_warning
            else "PASS"
        )

        results.append(
            GroupResult(
                code=code,
                description=description,
                configured_bytes=configured_bytes,
                configured_msb=configured_msb,
                configured_lsb=configured_lsb,
                expected_bytes=expected_bytes,
                calculated_bytes=calculated_bytes,
                calculated_offset_bytes=calculated_offset_bytes,
                total_parameters=len(logical_packet_parameters),
                pass_count=pass_count,
                fail_count=fail_count,
                warning_count=warning_count,
                overall_status=overall_status,
                parameters=param_rows,
                issues=group_issues,
                packet_variants=packet_variants,
            )
        )
        all_issues.extend(group_issues)

    results.sort(key=lambda item: (int(item.code) if str(item.code).isdigit() else 10**9, str(item.code)))
    return results, all_issues, missing_in_plc_rows, extra_in_plc_rows


def packet_size_result(configured_bytes: Optional[int], calculated_bytes: Optional[int]) -> Tuple[str, Optional[str]]:
    if configured_bytes is None or calculated_bytes is None:
        return "N/A — Cannot compare", None
    if calculated_bytes == configured_bytes:
        return "PASS — Configured and calculated bytes match", "C6EFCE"
    if calculated_bytes < configured_bytes:
        return f"WARNING — Configured {configured_bytes} bytes; calculated {calculated_bytes} bytes ({configured_bytes - calculated_bytes} bytes unfilled)", "FFEB9C"
    return f"FAIL — Calculated {calculated_bytes} bytes exceed configured {configured_bytes} bytes by {calculated_bytes - configured_bytes}", "FFC7CE"


def packet_variants_result(result: GroupResult) -> Tuple[str, Optional[str]]:
    variants = result.packet_variants or []
    if not variants:
        return packet_size_result(
            result.configured_bytes,
            result.calculated_offset_bytes if result.calculated_offset_bytes is not None else result.calculated_bytes,
        )
    failed = sum(1 for item in variants if str(item.get("status", "")).upper() == "FAIL")
    warned = sum(1 for item in variants if str(item.get("status", "")).upper() == "WARNING")
    if failed:
        return f"FAIL — {failed} of {len(variants)} packet variants failed", "FFC7CE"
    if warned:
        return f"WARNING — {warned} of {len(variants)} packet variants require review", "FFEB9C"
    return f"PASS — All {len(variants)} packet variants match their configured layout", "C6EFCE"


def write_excel_report(
    results: List[GroupResult],
    issues: List[ValidationIssue],
    missing_rows: List[MetadataParameter],
    extra_rows: List[PacketParameter],
    output_path: Path,
    metadata_enabled: bool = False,
    metadata_file: Optional[Path] = None,
    hmi_usage: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Path:
    wb = Workbook()
    # HMI limits are displayed for engineering traceability; they do not
    # change the PLC packet validation result.
    hmi_usage = hmi_usage if hmi_usage is not None else extract_hmi_parameter_usage()

    # 1. Validation Information
    info = wb.active
    info.title = "Validation Information"
    info_rows = [
        ["Validation Information", "Value"],
        ["Application", "uSOPp - Proven Python v1.71 Engine"],
        ["Project", PROJECT_NAME],
        ["Packet Header Bytes", PACKET_HEADER_BYTES],
        ["Metadata Uploaded", "YES" if metadata_enabled else "NO (Metadata comparison skipped)"],
        ["Metadata Offset Basis", "Group payload-relative; PLC nw_i starts at byte 5"],
        ["Report Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]
    for row in info_rows:
        info.append(row)
    for cell in info[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="17365D")
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 55

    # 2. GroupCode Summary Sheet
    summary = wb.create_sheet("GroupCode Summary")
    summary.append([
        "Group Code", "Description", "nw_snd_buffer[3]", "nw_snd_buffer[4]",
        "Configured Bytes", "Expected Bytes", "Calculated Bytes (field sum)", "Calculated by Offset", "Packet Cal Result",
        "Total Parameters", "PASS", "WARNING", "FAIL", "Overall Status", "Recommendation",
    ])
    for cell in summary[1]:
        cell.font = Font(bold=True)

    for result in results:
        cal_res, fill_color = packet_variants_result(result)
        rec = "No action required"
        if result.overall_status == "FAIL":
            rec = "Correct the first highlighted PLC or metadata error, then revalidate"
        elif result.overall_status == "WARNING":
            rec = "Review packet length, unused bytes, and metadata warnings"
        for issue in result.issues:
            if str(getattr(issue, "severity", "")).upper() in {"FAIL", "WARNING"} and getattr(issue, "suggested_fix", ""):
                rec = str(issue.suggested_fix)
                break

        summary.append([
            result.code,
            result.description,
            "" if result.configured_msb is None else result.configured_msb,
            "" if result.configured_lsb is None else result.configured_lsb,
            "" if result.configured_bytes is None else result.configured_bytes,
            "" if result.expected_bytes is None else result.expected_bytes,
            result.calculated_bytes,
            "" if result.calculated_offset_bytes is None else result.calculated_offset_bytes,
            cal_res,
            result.total_parameters,
            result.pass_count,
            result.warning_count,
            result.fail_count,
            result.overall_status,
            rec,
        ])
        if fill_color:
            for col in (5, 7, 8, 9):
                summary.cell(row=summary.max_row, column=col).fill = PatternFill(fill_type="solid", fgColor=fill_color)

    variants_sheet = wb.create_sheet("Packet Variants")
    variants_sheet.append([
        "Group Code", "Variant", "Condition / Path", "Configured MSB", "Configured LSB",
        "Configured Bytes", "Written Bytes", "Cursor Bytes", "Calculated by Offset",
        "Status", "Packet Result", "Issues",
    ])
    for cell in variants_sheet[1]:
        cell.font = Font(bold=True)
    for result in results:
        for variant in result.packet_variants:
            issue_text = "\n".join(
                f"{issue.get('severity', '')}: {issue.get('validationType', '')} | "
                f"expected {issue.get('expected', '')}, actual {issue.get('actual', '')} | "
                f"{issue.get('sourceFile', '')}:{issue.get('lineNumber', '')}"
                for issue in variant.get("issues", [])
            )
            variants_sheet.append([
                result.code,
                variant.get("id", ""),
                variant.get("condition", ""),
                variant.get("configuredMsb", ""),
                variant.get("configuredLsb", ""),
                variant.get("configuredBytes", ""),
                variant.get("writtenBytes", ""),
                variant.get("cursorBytes", ""),
                variant.get("calculatedByOffset", ""),
                variant.get("status", ""),
                variant.get("packetCalResult", ""),
                issue_text,
            ])
            status_fill = {
                "PASS": "C6EFCE",
                "WARNING": "FFEB9C",
                "FAIL": "FFC7CE",
            }.get(str(variant.get("status", "")).upper())
            if status_fill:
                variants_sheet.cell(row=variants_sheet.max_row, column=10).fill = PatternFill(fill_type="solid", fgColor=status_fill)
    variants_sheet.column_dimensions["A"].width = 13
    variants_sheet.column_dimensions["B"].width = 10
    variants_sheet.column_dimensions["C"].width = 58
    variants_sheet.column_dimensions["K"].width = 48
    variants_sheet.column_dimensions["L"].width = 90

    controls_sheet = wb.create_sheet("Packet Control Checks")
    controls_sheet.append([
        "Group Code", "Condition / Path", "Parameter", "Validation Type", "Severity",
        "Expected", "Actual", "Source File", "Line Number", "Suggested Fix",
    ])
    for cell in controls_sheet[1]:
        cell.font = Font(bold=True)
    control_issues = {}
    for issue in issues:
        if issue.validation_type in PACKET_CONTROL_CHECK_TYPES:
            control_issues.setdefault(_validation_issue_key(issue), issue)
    for issue in control_issues.values():
        controls_sheet.append([
            issue.group_code, issue.condition or "Unconditional", issue.parameter,
            issue.validation_type, issue.severity, issue.expected, issue.actual,
            issue.source_file, issue.line_number, issue.suggested_fix,
        ])
    controls_sheet.column_dimensions["H"].width = 65
    controls_sheet.column_dimensions["J"].width = 90

    # 3. PLC Logic Validation Sheet
    params = wb.create_sheet("PLC Logic Validation")
    params.append([
        "Sl.no", "Tag Code", "Group Code", "Parameter in logic", "Parameter Description in logic",
        "Data Type", "Field Size (bytes)", "Offset Buffer in logic", "Running Offset", "Expected Offset", "TCP Offset (payload starts at 0)",
        "Status", "Remarks", "Validation Type", "Expected", "Actual", "Severity",
        "Declared Data Type", "Declared Size", "Source File", "Line Number", "Packet Write Method", "Branch Assignments", "Condition / Packet Path",
    ])
    for cell in params[1]:
        cell.font = Font(bold=True)

    serials = global_serial_map(results)
    for result in results:
        for row in result.parameters:
            params.append([
                serials[id(row)],
                serials[id(row)],
                row.group_code,
                row.parameter,
                row.parameter_description,
                row.data_type,
                "" if row.memcpy_size is None else row.memcpy_size,
                "" if row.offset_buffer is None else row.offset_buffer,
                "" if row.running_offset is None else row.running_offset,
                "" if row.expected_offset is None else row.expected_offset,
                "" if row.offset_buffer is None else row.offset_buffer,
                row.status,
                row.remarks,
                row.validation_type,
                row.expected_value,
                row.actual_value,
                row.severity,
                row.declared_data_type,
                "" if row.declared_size is None else row.declared_size,
                row.source_file,
                "" if row.line_number is None else row.line_number,
                row.transfer_method,
                "\n".join(f"{e['sourceFile']}:{e['lineNumber']} | {e['condition'] or 'Unconditional'} | {e['destinationExpression']} := {e['sourceExpression']};" for e in row.write_evidence),
                row.condition_context,
            ])

    # Fills for PLC Logic Validation
    plc_fills = {
        "PASS": PatternFill(fill_type="solid", fgColor="C6EFCE"),
        "FAIL": PatternFill(fill_type="solid", fgColor="FFC7CE"),
        "WARNING": PatternFill(fill_type="solid", fgColor="FFEB9C"),
        "AFFECTED": PatternFill(fill_type="solid", fgColor="DDEBF7"),
    }
    for r in range(2, params.max_row + 1):
        st = str(params.cell(r, 12).value or "").upper().strip()
        if st in plc_fills:
            for c in range(1, params.max_column + 1):
                params.cell(r, c).fill = plc_fills[st]

    # 4. Metadata Validation Sheet (Only when metadata provided)
    if metadata_enabled:
        meta_sheet = wb.create_sheet("Metadata Validation")
        meta_sheet.append([
            "Sl.no", "PLC Tag / Variable", "Parameter (PLC Comment)", "group code in logic", "Data type in logic",
            "TCP offset (payload starts at 0)", "HMI MIN", "HMI MAX", "Metadata S No.", "Parameter in Metadata",
            "group code in Metadata", "Data type in Metadata", "offset (group-relative) in Metadata", "Metadata MIN", "Metadata MAX",
            "Result",
        ])
        for cell in meta_sheet[1]:
            cell.font = Font(bold=True)

        for result in results:
            for row in result.parameters:
                hmi_info = _hmi_usage_for_parameter(row, hmi_usage)
                hmi_min, hmi_max, _ = resolved_min_max(plc_parameter_value(row), str(row.parameter or ""), hmi_info)
                if not row.metadata_parameter and row.metadata_group_code is None:
                    res_text = "Warning — Metadata Unavailable"
                else:
                    group_mismatch = row.metadata_group_code is not None and row.metadata_group_code != row.group_code
                    parameter_mismatch = (
                        row.group_code != 30
                        and
                        "configured mapping" not in str(row.metadata_match_method or "").lower()
                        and bool(row.metadata_parameter)
                        and not metadata_text_exact(plc_parameter_value(row), row.metadata_parameter)
                    )
                    datatype_state = metadata_type_compatibility(row.data_type, row.metadata_data_type, row.group_code) if row.metadata_data_type else "MISMATCH"
                    offset_mismatch = row.metadata_offset is not None and row.offset_buffer is not None and row.metadata_offset != row.offset_buffer
                    if group_mismatch:
                        res_text = "Group Code Mismatch"
                    elif parameter_mismatch:
                        res_text = f"Parameter mismatch; PLC is {plc_parameter_value(row)} : metadata is {row.metadata_parameter}"
                    elif datatype_state == "MISMATCH":
                        res_text = f"Data Type mismatch; in logic is {row.data_type} : in metadata is {row.metadata_data_type}"
                    elif offset_mismatch:
                        res_text = "Offset Mismatch"
                    elif datatype_state == "WARNING":
                        res_text = f"WARNING — Compatible Data Type; logic is {row.data_type} : metadata is {row.metadata_data_type}"
                    else:
                        res_text = "Matching"

                meta_sheet.append([
                    serials.get(id(row), ""),
                    row.parameter,
                    row.parameter_description,
                    row.group_code,
                    "BYTE" if row.group_code == 30 else row.data_type,
                    "" if row.offset_buffer is None else row.offset_buffer,
                    "" if hmi_min is None else hmi_min,
                    "" if hmi_max is None else hmi_max,
                    row.metadata_sequence if row.metadata_sequence is not None else "",
                    row.metadata_parameter,
                    "" if row.metadata_group_code is None else row.metadata_group_code,
                    row.metadata_data_type,
                    "" if row.metadata_offset is None else row.metadata_offset,
                    "" if row.metadata_min_value is None else row.metadata_min_value,
                    "" if row.metadata_max_value is None else row.metadata_max_value,
                    res_text,
                ])

    # 5. C70_7 Dropdown Validation Sheet
    dropdown_sheet = wb.create_sheet("C70_7 Dropdown Validation")
    dropdown_sheet.append([
        "Sl.no", "Group Code", "Parameter in logic", "Parameter Description in logic",
        "PLCVAL", "SHOWNVAL", "Page File", "Control Name", "IndexDatapoint", "TextGroup", "Values",
    ])
    for cell in dropdown_sheet[1]:
        cell.font = Font(bold=True)

    dropdown_families = extract_dropdown_rows()
    for fam, d_rows in dropdown_families.items():
        for dr in d_rows:
            dropdown_sheet.append([
                "", dr.group_code or "", dr.logic_parameter, "",
                "", "", dr.page_file, dr.control_name, dr.index_datapoint, dr.text_group, dr.text_group_values,
            ])

    # 6. BOOL Dropdown Validation Sheet
    bool_sheet = wb.create_sheet("BOOL Dropdown Validation")
    bool_sheet.append([
        "Sl.no", "Group Code", "Parameter in logic", "Parameter Description in logic",
        "Data Type", "PLCVAL", "Expected SHOWNVAL", "Status", "Result",
    ])
    for cell in bool_sheet[1]:
        cell.font = Font(bold=True)

    for result in results:
        for row in result.parameters:
            if str(row.data_type).upper() == "BOOL":
                if normalize_bool_metadata_mode(BOOL_METADATA_MODE) == "USINT" and row.group_code != 30:
                    expected_pairs = ((0, "ON"), (1, "OFF"))
                    result_text = "Required in metadata Sheet2 for BOOL to USINT conversion"
                else:
                    expected_pairs = (("", "Not required"),)
                    result_text = "PLC BOOL remains BOOL; no conversion mapping is required"
                for index, (val, shown) in enumerate(expected_pairs):
                    bool_sheet.append([
                        serials.get(id(row), "") if index == 0 else "",
                        row.group_code if index == 0 else "",
                        row.parameter if index == 0 else "",
                        row.parameter_description if index == 0 else "",
                        normalize_bool_metadata_mode(BOOL_METADATA_MODE) if index == 0 else "",
                        val, shown, "EXPECTED", result_text,
                    ])

    # 7. Alarm Validation Sheet (Group 30)
    alarms = extract_alarm_descriptions()
    alarm_sheet = wb.create_sheet("Alarm Validation")
    alarm_sheet.append(["Group Code", "Alarm Description"])
    for cell in alarm_sheet[1]:
        cell.font = Font(bold=True)
    for gc, adesc in alarms:
        alarm_sheet.append([gc, adesc])

    # Autosize columns
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = max(len(str(c.value or "")) for c in col) + 2
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_len, 70)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path



def _parse_dropdown_pairs(value_text: str) -> List[Tuple[str, str]]:
    """Parse HMI TextGroup summary into individual PLCVAL/SHOWNVAL pairs."""
    if not value_text:
        return []
    pairs: List[Tuple[str, str]] = []
    for part in re.split(r";|\r?\n", str(value_text)):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            plc_val, shown_val = part.split(":", 1)
            # Only resolved numeric IndexMap entries belong in Sheet2.
            if re.fullmatch(r"[+-]?\d+", plc_val.strip()) and shown_val.strip():
                pairs.append((plc_val.strip(), shown_val.strip()))
    return pairs


def _build_generated_sheet2(
    results: List[GroupResult],
    tag_by_parameter: Optional[Dict[str, Any]] = None,
    bool_tag_codes: Optional[set[Any]] = None,
    alarm_byte_tags: Optional[Dict[int, Any]] = None,
    master_dropdown_pairs_by_tag: Optional[Dict[Any, List[Tuple[str, str]]]] = None,
) -> List[List[Any]]:
    """
    Build generated Sheet2 from actual HMI dropdown/TextGroup implementation.

    TAG_CODE is the same global tag sequence used by the generated 7.170 sheet.
    PLCVAL/SHOWNVAL pairs come from actual .page -> TextGroup extraction.
    When BOOL-to-USINT conversion is selected, every PLC BOOL is represented
    using the required metadata mapping ``0 = ON`` and ``1 = OFF``.
    """
    dropdown_rows = extract_dropdown_rows()
    tag_by_parameter = tag_by_parameter or {}
    bool_tag_codes = bool_tag_codes or set()
    alarm_byte_tags = alarm_byte_tags or {}
    master_dropdown_pairs_by_tag = master_dropdown_pairs_by_tag or {}

    output = [["TAG_CODE", "PLCVAL", "SHOWNVAL", "MACHINE VARIANT", "IS_ALARM"]]
    seen = set()

    # USINT conversion has one deterministic representation. It deliberately
    # takes precedence over HMI/master labels for converted PLC BOOL tags.
    if normalize_bool_metadata_mode(BOOL_METADATA_MODE) == "USINT":
        for tag_code in sorted(bool_tag_codes, key=lambda value: (str(value))):
            for plc_val, shown_val in (("0", "ON"), ("1", "OFF")):
                seen.add((str(tag_code), plc_val, shown_val))
                output.append([tag_code, plc_val, shown_val, "BOTH", "NO"])

    # Engineer-approved mappings take precedence over a display's TextGroup.
    # They are keyed by an exact PLC logic-comment/tag pair at generation time.
    for tag_code, pairs in master_dropdown_pairs_by_tag.items():
        if normalize_bool_metadata_mode(BOOL_METADATA_MODE) == "USINT" and tag_code in bool_tag_codes:
            continue
        for plc_val, shown_val in pairs:
            key = (str(tag_code), str(plc_val), str(shown_val))
            if key not in seen:
                seen.add(key)
                output.append([tag_code, plc_val, shown_val, "BOTH", "NO"])

    # Group 30 serializes the project's alarm bits into Temp_nw_snd_buffer.
    # Preserve the byte TAG_CODE while making each individual alarm bit visible.
    described_alarm_bits = set()
    alarm_captions = defaultdict(list)
    for buffer, byte_no, bit_no, description, source_file in extract_group30_alarm_bits(include_buffer=True):
        tag_code = alarm_byte_tags.get((buffer.casefold(), byte_no), alarm_byte_tags.get(byte_no))
        if tag_code is None or not description.strip():
            continue
        captions = alarm_captions[(tag_code, bit_no)]
        if description not in captions:
            captions.append(description)
    for (tag_code, bit_no), captions in alarm_captions.items():
        described_alarm_bits.add((str(tag_code), bit_no))
        # Two source alarms may set one bit. Keep one PLC value with both
        # captions; validation reports the collision instead of moving bits.
        description = " OR ".join(captions)
        key = (str(tag_code), str(bit_no), description)
        if key in seen:
            continue
        seen.add(key)
        output.append([tag_code, bit_no, description, "BOTH", "YES"])

    def numeric_order(value):
        number = to_int(value)
        return (0, number) if number is not None else (1, str(value).casefold())

    # Cover every bit of every transmitted alarm byte, including unused tail
    # bytes. NA is a metadata placeholder, not an inferred alarm description.
    # Number placeholders continuously in TAG_CODE / bit order for this sheet.
    missing_alarm_number = 0
    for tag_code in sorted(set(alarm_byte_tags.values()), key=numeric_order):
        for bit_no in range(8):
            if (str(tag_code), bit_no) in described_alarm_bits:
                continue
            missing_alarm_number += 1
            description = f"NA{missing_alarm_number}"
            seen.add((str(tag_code), str(bit_no), description))
            output.append([tag_code, bit_no, description, "BOTH", "YES"])

    for family_rows in dropdown_rows.values():
        for dr in family_rows:
            raw_logic = str(dr.logic_parameter or "").strip()
            param_key = normalize_name(raw_logic)
            # B&R HMI bindings are commonly written as
            # Local.<Parameter>, global.Variable[Local.<Parameter>], etc.
            # Match the final variable token as well as the full normalized value.
            final_logic = raw_logic.split(".")[-1].strip()
            final_key = normalize_name(final_logic)
            tag_code = tag_by_parameter.get(param_key, tag_by_parameter.get(final_key, ""))
            # Converted BOOL uses the deterministic mapping above rather than
            # a page-specific label such as Enabled/Disabled.
            if normalize_bool_metadata_mode(BOOL_METADATA_MODE) == "USINT" and tag_code in bool_tag_codes:
                continue
            if tag_code in master_dropdown_pairs_by_tag:
                continue
            pairs = _parse_dropdown_pairs(dr.text_group_values)
            # Sheet2 is PLC metadata. A display-only dropdown with no packet
            # TAG_CODE is deliberately excluded from this five-column sheet.
            if tag_code == "":
                continue

            for plc_val, shown_val in pairs:
                key = (str(tag_code), str(plc_val), str(shown_val))
                if key in seen:
                    continue
                seen.add(key)
                output.append([tag_code, plc_val, shown_val, "BOTH", "NO"])

    # Sort the shared rows before writing either JSON (UI) or the workbook.
    output[1:] = sorted(output[1:], key=lambda row: (numeric_order(row[0]), numeric_order(row[1])))
    return output


GROUP_SCREEN_NAMES = {
    10: "PLC Program Version",
    20: "Default Screen",
    30: "Fault History",
    40: "Current Shift Report",
    50: "Previous Shift 1 Report",
    60: "Previous Shift 2 Report",
    70: "Previous Shift 3 Report",
    80: "Previous Shift 4 Report",
    90: "Previous Shift 5 Report",
    100: "Previous Shift 6 Report",
    110: "Previous Shift 7 Report",
    120: "Previous Day Report",
    130: "Machine Settings",
    140: "Process Settings",
    150: "Machine History",
    410: "Energy Monitor",
    500: "Doff Report 1",
    510: "Doff Report 2",
    520: "Doff Report 3",
    530: "Doff Report 4",
    600: "Health Monitor",
}

def generated_screen_name(group: GroupResult) -> str:
    """Use the known engineering screen name, then the CASE label as fallback."""
    configured_name = GROUP_SCREEN_NAMES.get(group.code)
    if configured_name:
        return configured_name
    case_label = str(group.description or "").strip()
    return case_label if case_label and case_label.casefold() != "no description" else "PLC Packet"



def extract_plc_program_version() -> str:
    """Scan PLC source files for PROGRAM_VERSION assignment, return value or '<null>'."""
    root = _get_project_root()
    if root is None:
        return "<null>"
    pat = re.compile(
        r"(?:PLC_PROGRAM_VERSION|PROGRAM_VERSION|gProgramVersion|g_ProgramVersion|SW_VERSION)"
        r"\s*(?::=|=)\s*[\x27\x22]?([\d.]+)[\x27\x22]?",
        re.IGNORECASE,
    )
    source_files = [path for pattern in ("*.st","*.src","*.SRC") for path in Path(root).rglob(pattern) if not is_ignored_project_path(path)]
    for st_file in sorted(set(source_files)):
        try:
            for line in st_file.read_text(encoding="utf-8", errors="replace").splitlines():
                m = pat.search(strip_comments(line))
                if m:
                    return m.group(1).strip()
        except Exception:
            continue
    return "<null>"


def _get_project_root() -> Optional[Path]:
    """Return the initialized project root, with CLI arguments as fallback."""
    if ROOT.exists():
        return ROOT
    try:
        import sys as _sys
        for i, a in enumerate(_sys.argv):
            if a == "--project" and i + 1 < len(_sys.argv):
                return Path(_sys.argv[i + 1])
    except Exception:
        pass
    return None


def apply_generated_metadata_duplicate_highlights(ws) -> set[int]:
    """Highlight duplicate Parameters only when their Group Code also matches."""
    headers = {
        normalize_header(cell.value): cell.column
        for cell in ws[1]
        if cell.value is not None
    }
    group_column = headers.get("group code")
    parameter_column = headers.get("parameters") or headers.get("parameter")
    if not group_column or not parameter_column:
        return set()

    buckets: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for row_number in range(2, ws.max_row + 1):
        group_value = re.sub(r"\s+", " ", str(ws.cell(row_number, group_column).value or "").strip()).casefold()
        parameter_value = re.sub(r"\s+", " ", str(ws.cell(row_number, parameter_column).value or "").strip()).casefold()
        if group_value and parameter_value:
            buckets[(group_value, parameter_value)].append(row_number)

    duplicate_rows = {
        row_number
        for rows in buckets.values()
        if len(rows) > 1
        for row_number in rows
    }
    purple = PatternFill(fill_type="solid", fgColor=DUPLICATE_PARAMETER_FILL)
    final_column = ws.cell(1, ws.max_column).column_letter
    for row_number in sorted(duplicate_rows):
        ws.conditional_formatting.add(
            f"A{row_number}:{final_column}{row_number}",
            FormulaRule(
                formula=[DUPLICATE_PARAMETER_FORMULA],
                fill=purple,
                stopIfTrue=False,
            ),
        )
    return duplicate_rows



def generate_metadata_workbook(output_excel_path: Path, output_json_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Generate 7.170-style metadata plus Sheet2 from the actual PLC/HMI
    implementation. The selected PLC workspace is the only engineering source.
    """
    results, source_issues, _, _ = build_group_results(metadata_compare_enabled=False)
    wb = Workbook()
    ws = wb.active
    project_root = _get_project_root()
    project_sheet_name = sanitize_sheet_title(project_root.name if project_root is not None else output_excel_path.stem.replace("_Generated_Metadata_v4.30", ""))
    ws.title = project_sheet_name or "Metadata"

    headers = [
        "S NO.", "Screen name", "Machine Varients", "Parameters", "UNITS",
        "MIN", "MAX", "TAG_CODE", "GROUP_CODE",
        "OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES", "FROM_VERSION",
        "TO_VERSION", "TAG_DATA_TYPE", "OFFSET_FACTOR", "SCALE_FACTOR",
        "IS_VISIBLE", "IS_WRITABLE", "CONDITION_TAG_NAME", "BIT_OR_TAG",
        "BIT_NO", "BIT_CONDITION", "TAG_VALUE", "TAG_CONDITION",
        "IS_SHOWN_VALUE_DIFFERENT",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="17365D")

    all_params: List[Dict[str, Any]] = []
    dropdown_rows = extract_dropdown_rows()
    hmi_usage = extract_hmi_parameter_usage()

    # ------------------------------------------------------------------
    # FAST METADATA LOOKUPS
    # The metadata generator may emit thousands of rows.  Do not reload
    # JSON knowledge files or rescan every *.st file once per parameter.
    # These lookup tables are local to this generation run, so edits to
    # master data are picked up on the next Generate Metadata operation.
    # ------------------------------------------------------------------
    master_mappings = load_master_parameter_mappings()
    master_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
    master_by_metadata: Dict[str, Dict[str, Any]] = {}
    for mapping in sorted(master_mappings, key=lambda m: str(m.get("machine_department") or "All").casefold() != "all"):
        mp = normalize_name(str(mapping.get("plc_parameter", "")))
        mt = normalize_name(str(mapping.get("plc_tag", "")))
        mm = normalize_name(str(mapping.get("metadata_parameter", "")))
        if mp and mt and mm:
            master_by_pair[(mp, mt)] = mapping
            master_by_metadata[mm] = mapping

    master_dropdown_by_pair: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for mapping in sorted(load_master_dropdown_mappings(), key=lambda m: str(m.get("machine_department") or "All").casefold() != "all"):
        key = (normalize_name(str(mapping.get("plc_parameter", ""))), normalize_name(str(mapping.get("plc_tag", ""))))
        if not key[0] or not key[1]:
            continue
        pairs: List[Tuple[str, str]] = []
        for item in mapping.get("mapping", []):
            if isinstance(item, dict) and "PLCVAL" in item and "SHOWNVAL" in item:
                pairs.append((str(item["PLCVAL"]), str(item["SHOWNVAL"]).strip()))
        if pairs:
            master_dropdown_by_pair[key] = pairs

    master_minmax_by_pair: Dict[Tuple[str, str], Tuple[Any, Any]] = {}
    try:
        if KNOWLEDGE_MASTER_MIN_MAX_FILE.exists():
            mm_data = json.loads(KNOWLEDGE_MASTER_MIN_MAX_FILE.read_text(encoding="utf-8"))
            for mapping in (mm_data.get("mappings", []) if isinstance(mm_data, dict) else []):
                if not isinstance(mapping, dict):
                    continue
                key = (normalize_name(str(mapping.get("plc_parameter", ""))), normalize_name(str(mapping.get("plc_tag", ""))))
                if key[0] and key[1]:
                    master_minmax_by_pair[key] = (mapping.get("min"), mapping.get("max"))
    except Exception:
        pass

    generated_program_version = extract_plc_program_version()

    def fast_master_metadata_fields(metadata_parameter: str) -> Dict[str, Any]:
        mapping = master_by_metadata.get(normalize_name(metadata_parameter))
        if not mapping:
            return {}
        return {
            "units": _master_value(mapping, "units", "UNITS", default=""),
            "offset_factor": _master_value(mapping, "offset_factor", "OFFSET_FACTOR", default=1),
            "scale_factor": _master_value(mapping, "scale_factor", "SCALE_FACTOR", default=1),
            "is_visible": _master_value(mapping, "is_visible", "IS_VISIBLE", default="YES"),
            "is_writable": _master_value(mapping, "is_writable", "IS_WRITABLE", default="NO"),
        }

    def fast_metadata_parameter(plc_parameter: str, plc_tag: str) -> Tuple[str, str]:
        mapping = master_by_pair.get((normalize_name(plc_parameter), normalize_name(plc_tag)))
        if mapping and mapping.get("metadata_parameter"):
            return str(mapping["metadata_parameter"]).strip(), "Master Knowledge configured mapping"
        return plc_parameter, "PLC name"

    def fast_min_max(plc_parameter: str, plc_tag: str, hmi_info: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any], str]:
        def valid(v: Any) -> Optional[Any]:
            if v is None or str(v).strip().casefold() in {"", "none", "null", "<null>"}:
                return None
            return v
        hmin, hmax = valid(hmi_info.get("hmiMin")), valid(hmi_info.get("hmiMax"))
        mmin, mmax = master_minmax_by_pair.get((normalize_name(plc_parameter), normalize_name(plc_tag)), (None, None))
        mmin, mmax = valid(mmin), valid(mmax)
        return (hmin if hmin is not None else mmin,
                hmax if hmax is not None else mmax,
                "HMI" if hmin is not None or hmax is not None else ("Master MIN/MAX" if mmin is not None or mmax is not None else "Not configured"))
    tag_by_parameter: Dict[str, Any] = {}
    bool_tag_codes: set[Any] = set()
    alarm_byte_tags: Dict[int, Any] = {}
    configured_dropdown_pairs_by_tag: Dict[Any, List[Tuple[str, str]]] = {}
    tag_counter = 0
    metadata_naming_warnings = []

    # Build normalized HMI parameter lookup so IS_SHOWN_VALUE_DIFFERENT is
    # based on actual dropdown implementation.
    hmi_parameters = set()
    for fam_rows in dropdown_rows.values():
        for dr in fam_rows:
            raw_logic = str(dr.logic_parameter or "").strip()
            if not raw_logic:
                continue
            hmi_parameters.add(normalize_name(raw_logic))
            hmi_parameters.add(normalize_name(raw_logic.split(".")[-1].strip()))

    for grp in results:
        screen_name = generated_screen_name(grp)
        # Resolve names together so an alias cannot merge distinct PLC fields.
        # Validation still retains every conditional path, while metadata uses
        # the first path in source order.
        primary_parameters = [p for p in grp.parameters if p.metadata_primary_path]
        candidates = []
        for param in primary_parameters:
            plc_parameter = plc_parameter_value(param)
            plc_tag = str(param.parameter or '').strip()
            proposed, source = fast_metadata_parameter(plc_parameter, plc_tag)
            candidates.append({'plc_parameter':plc_parameter,'plc_tag':plc_tag,
                               'parameter':proposed,'mapping_source':source,
                               'source_file':param.source_file,'line_number':param.line_number})
        names, naming_warnings = resolve_name_collisions(candidates)
        metadata_naming_warnings.extend({'groupCode':grp.code,**warning} for warning in naming_warnings)
        for param, naming in zip(primary_parameters, names):
            tag_counter += 1
            tag_code = tag_counter
            plc_parameter = naming['plc_parameter']
            plc_tag = naming['plc_tag']
            metadata_parameter, mapping_source = naming['parameter'], naming['mapping_source']
            tag_by_parameter.setdefault(normalize_name(plc_tag), tag_code)
            tag_by_parameter.setdefault(normalize_name(plc_parameter), tag_code)
            tag_by_parameter.setdefault(normalize_name(metadata_parameter), tag_code)
            if grp.code == 30:
                alarm_byte = re.search(r"(temp_nw_snd_buffer\d*)\s*\[\s*(\d+)\s*\]", plc_tag, re.I)
                if alarm_byte:
                    alarm_byte_tags[(alarm_byte.group(1).casefold(), int(alarm_byte.group(2)))] = tag_code
            offset_val = param.offset_buffer if param.offset_buffer is not None else 0
            size_val = param.memcpy_size if param.memcpy_size is not None else 1
            is_bool = normalize_type_name(str(param.data_type or "")) == "BOOL"
            if is_bool and grp.code != 30:
                bool_tag_codes.add(tag_code)
            approved_dropdown_pairs = master_dropdown_by_pair.get((normalize_name(plc_parameter), normalize_name(plc_tag)), [])
            if grp.code == 240 and re.fullmatch(r"HW_\d+_[A-Z0-9_]+_STATUS", plc_tag, re.I):
                approved_dropdown_pairs = [("0", "MODULE MISSING"), ("1", "MODULE OK")]
            if approved_dropdown_pairs:
                configured_dropdown_pairs_by_tag[tag_code] = approved_dropdown_pairs
            converted_bool = is_bool and normalize_bool_metadata_mode(BOOL_METADATA_MODE) == "USINT" and grp.code != 30
            shown_diff = "YES" if (converted_bool or normalize_name(plc_tag) in hmi_parameters or normalize_name(plc_parameter) in hmi_parameters) else "<null>"
            if approved_dropdown_pairs:
                shown_diff = "YES"
            hmi_info = _hmi_usage_for_parameter(param, hmi_usage)
            hmi_min, hmi_max, min_max_source = fast_min_max(plc_parameter, plc_tag, hmi_info)
            hmi_min = metadata_numeric_value(hmi_min)
            hmi_max = metadata_numeric_value(hmi_max)
            master_fields = fast_master_metadata_fields(metadata_parameter)
            metadata_units = master_fields.get("units") or "<null>"
            metadata_offset_factor = metadata_numeric_value(master_fields.get("offset_factor", 1))
            metadata_scale_factor = metadata_numeric_value(master_fields.get("scale_factor", 1))
            metadata_visible = master_fields.get("is_visible", "YES")
            metadata_writable = master_fields.get("is_writable", "NO")
            metadata_datatype = "BYTE" if grp.code == 30 else (
                normalize_bool_metadata_mode(BOOL_METADATA_MODE)
                if is_bool else metadata_output_type(metadata_output_type(str(param.data_type or "")))
            )

            ws.append([
                tag_code,                                      # S NO.
                screen_name,                                    # CASE nw_group_code screen name
                "BOTH",                                        # Machine Varients
                metadata_parameter,                            # Approved metadata name, otherwise PLC comment
                metadata_units,                                # UNITS from master metadata configuration
                hmi_min if hmi_min is not None else "<null>", # MIN from HMI control
                hmi_max if hmi_max is not None else "<null>", # MAX from HMI control
                tag_code,                                      # TAG_CODE
                grp.code,                                      # GROUP_CODE
                offset_val,                                    # OFFSET...
                generated_program_version,                # FROM_VERSION: scanned from PLC source
                "<null>",                                     # TO_VERSION
                metadata_datatype,                             # TAG_DATA_TYPE
                metadata_offset_factor,                        # OFFSET_FACTOR
                metadata_scale_factor,                         # SCALE_FACTOR
                metadata_visible,                             # IS_VISIBLE
                metadata_writable,                            # IS_WRITABLE
                "<null>", "<null>", "<null>", "<null>",       # condition/bit fields
                "<null>",                                     # TAG_VALUE
                "<null>",                                     # TAG_CONDITION
                shown_diff,
            ])

            all_params.append({
                "sequence": tag_code,
                "group_code": grp.code,
                "screen_name": screen_name,
                "machine_variants": "BOTH",
                "parameter": metadata_parameter,
                "description": metadata_parameter,
                "plc_parameter": plc_parameter,
                "plc_tag": plc_tag,
                "mapping_source": mapping_source,
                "datatype": metadata_datatype,
                "offset": offset_val,
                "size": size_val,
                "units": metadata_units,
                "min": hmi_min if hmi_min is not None else "<null>",
                "max": hmi_max if hmi_max is not None else "<null>",
                "offset_factor": metadata_offset_factor,
                "scale_factor": metadata_scale_factor,
                "is_visible": metadata_visible,
                "is_writable": metadata_writable,
                "from_version": generated_program_version,
                "to_version": "<null>",
                "condition_tag_name": "<null>",
                "bit_or_tag": "<null>",
                "bit_no": "<null>",
                "bit_condition": "<null>",
                "tag_value": "<null>",
                "tag_condition": "<null>",
                "packet_size": grp.configured_bytes or grp.calculated_bytes,
                "tag_code": tag_code,
                "is_shown_value_different": shown_diff,
                "hmi_min": hmi_min,
                "hmi_max": hmi_max,
                "min_max_source": min_max_source,
            })

    # Sheet2 is generated from the actual HMI TextGroup mappings in the PLC
    # workspace, not from a default/reference workbook.
    sheet2 = wb.create_sheet("Sheet2")
    sheet2_rows = _build_generated_sheet2(
        results, tag_by_parameter, bool_tag_codes, alarm_byte_tags,
        configured_dropdown_pairs_by_tag,
    )
    for row in sheet2_rows:
        sheet2.append(row)
    for cell in sheet2[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="17365D")

    # Freeze/filter generated metadata tables.
    ws.freeze_panes = "A2"
    # AutoFilter intentionally disabled (do not enable — causes highlighted column headers)
    sheet2.freeze_panes = "A2"

    for sheet in (ws, sheet2):
        for cell in sheet[1]:
            cell.font = Font(bold=True, italic=True, color="000000")
            cell.fill = PatternFill(fill_type=None)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.row_dimensions[1].height = 60
        sheet.auto_filter.ref = None
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col) + 2
            sheet.column_dimensions[col[0].column_letter].width = min(max_len, 60)

    apply_generated_metadata_duplicate_highlights(ws)

    numeric_issues=normalize_metadata_workbook(wb)
    if numeric_issues:
        raise ValueError('SpinConnect metadata contains unresolved numeric limits/factors: '+json.dumps(numeric_issues[:30],ensure_ascii=False))

    output_excel_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_excel_path)

    # Final metadata datatype safety normalization.  This is intentionally
    # limited to TAG_DATA_TYPE cells so malformed legacy concatenations such
    # as REDUNDUNREPLICABLEREAL can never be persisted to the generated XLSX.
    try:
        from openpyxl import load_workbook as _load_metadata_wb
        _check_wb = _load_metadata_wb(output_excel_path)
        for _ws in _check_wb.worksheets:
            _headers = {str(_c.value).strip().upper(): _c.column for _c in _ws[1] if _c.value is not None}
            _dtype_col = _headers.get("TAG_DATA_TYPE")
            if _dtype_col:
                for _row in range(2, _ws.max_row + 1):
                    _cell = _ws.cell(_row, _dtype_col)
                    if _cell.value is not None:
                        _group_col = _headers.get("GROUP_CODE")
                        _cell.value = metadata_output_type(str(_cell.value), _ws.cell(_row, _group_col).value if _group_col else None)
        _check_wb.save(output_excel_path)
    except Exception:
        # Workbook generation must not fail because of this presentation-only
        # normalization safeguard.
        pass

    result_data = {
        "status": "success",
        "totalParameters": len(all_params),
        "totalGroups": len(results),
        "sheet2Rows": max(0, len(sheet2_rows) - 1),
        "sheet2Records": [
            dict(zip(sheet2_rows[0], row)) for row in sheet2_rows[1:]
        ] if sheet2_rows else [],
        "dropdownControls": sum(len(rows) for rows in dropdown_rows.values()),
        "hmiTarget": HMI_TARGET_NAME,
        "boolMetadataMode": normalize_bool_metadata_mode(BOOL_METADATA_MODE),
        "sheetName": project_sheet_name,
        "excelPath": str(output_excel_path),
        "records": all_params,
        "metadataNamingWarnings": metadata_naming_warnings,
        "alarmWarnings": [asdict(issue) for issue in source_issues if str(issue.group_code) == "30" and issue.validation_type.startswith("Alarm")],
    }

    if output_json_path:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    return result_data


def _classify_hmi_control(control, properties: Dict[str, str]) -> str:
    """Classify an HMI-bound control without treating every datapoint as a dropdown."""
    class_id = (control.get("ClassId") or control.get("ClassID") or "").strip().lower()
    if class_id in {"0x00001018", "0x1018", "1018"}:
        return "Drop down"
    blob = " ".join([str(control.get("Name") or ""), class_id] + [f"{k}={v}" for k,v in properties.items()]).lower()
    input_words = ("input", "entry", "write", "editable", "edit", "numeric", "spin", "valueinput", "setvalue")
    if any(w in blob for w in input_words):
        return "Screen input"
    return "Screen display"


def extract_hmi_parameter_usage() -> Dict[str, Dict[str, Any]]:
    """Extract screen usage independently from PLC packet and metadata matching."""
    usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "valueSource": "Logic data", "inputType": "Used only in logic, not in screen",
        "dropdown": False, "pages": [], "controls": [], "hmiMin": None, "hmiMax": None,
    })
    search_root = LOGICAL_ROOT if LOGICAL_ROOT.exists() else ROOT
    for page_path in search_root.rglob("*.page"):
        try:
            root = ET.parse(page_path).getroot()
        except Exception:
            continue
        for control in root.findall(".//{*}Controls/{*}Control"):
            properties = {child.get("Name"): child.get("Value") for child in control.findall("./{*}Property") if child.get("Name")}
            datapoint = (properties.get("IndexDatapoint") or properties.get("DataPoint") or properties.get("ValueDatapoint") or properties.get("ValueDataPoint") or "").strip()
            if not datapoint or datapoint.upper() == "NONE":
                continue
            raw = extract_last_bracket_value(datapoint) or datapoint.split(".")[-1].strip()
            # B&R page bindings commonly use ``Local.variable`` while packet
            # logic contains ``variable``. Store both aliases against the same
            # record so HMI limits can resolve to the PLC packet parameter.
            keys = list(dict.fromkeys([
                normalize_name(raw),
                normalize_name(str(raw).split(".")[-1].strip()),
            ]))
            keys = [key for key in keys if key]
            if not keys:
                continue
            item = usage[keys[0]]
            for key in keys[1:]:
                usage[key] = item
            cls = _classify_hmi_control(control, properties)
            item["pages"].append(str(safe_relative_path(page_path)))
            item["controls"].append(control.get("Name") or "")
            if cls == "Drop down":
                item["valueSource"] = "Drop down"
                item["inputType"] = "Drop down selection"
                item["dropdown"] = True
            elif not item["dropdown"] and cls == "Screen input":
                item["valueSource"] = "Screen input"
                item["inputType"] = "Numeric entry point"
            elif item["valueSource"] == "Logic data":
                item["valueSource"] = "Screen display"
                item["inputType"] = "Display only"
            # Capture explicit numeric limits when the page exposes them.
            for prop_name, val in properties.items():
                pname = re.sub(r"[^a-z0-9]", "", str(prop_name).lower())
                if str(val or "").strip().casefold() in {"", "none", "null", "<null>"}:
                    continue
                if pname in {"min", "minimum", "minvalue", "minimumvalue", "lowerlimit", "lowlimit"} and item["hmiMin"] is None:
                    item["hmiMin"] = val
                if pname in {"max", "maximum", "maxvalue", "maximumvalue", "upperlimit", "highlimit"} and item["hmiMax"] is None:
                    item["hmiMax"] = val
    for item in usage.values():
        item["pages"] = list(dict.fromkeys(item["pages"]))
        item["controls"] = list(dict.fromkeys(item["controls"]))
    return usage


def _hmi_usage_for_parameter(parameter, usage: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve HMI usage by PLC tag/variable, including final variable token.

    HMI bindings often contain Local./Source[] wrappers, while PLC packet rows
    contain the declared tag.  Parameter comments are not used to identify an
    HMI binding; they remain the metadata Parameter.
    """
    candidates = []
    for raw in (getattr(parameter, "parameter", ""), getattr(parameter, "parameter_name", ""), getattr(parameter, "parameter_expr", "")):
        text = str(raw or "").strip()
        if not text:
            continue
        candidates.extend([normalize_name(text), normalize_name(text.split(".")[-1].strip())])
    for key in candidates:
        if key and key in usage:
            return usage[key]
    return {}


def run_engine_json(
    project_dir: Path,
    metadata_file: Optional[Path] = None,
    output_excel_path: Optional[Path] = None,
    output_json_path: Optional[Path] = None,
    validation_options: Optional[Dict[str, bool]] = None,
    project_kb_file: Optional[Path] = None,
    machine_department: str = 'All',
    bool_metadata_mode: str = 'BOOL',
) -> Dict[str, Any]:
    global ACTIVE_MACHINE_DEPARTMENT, BOOL_METADATA_MODE
    ACTIVE_MACHINE_DEPARTMENT = str(machine_department or 'All').strip() or 'All'
    BOOL_METADATA_MODE = normalize_bool_metadata_mode(bool_metadata_mode)
    options = dict(DEFAULT_VALIDATION_OPTIONS)
    if validation_options:
        options.update(validation_options)

    initialize_project_context(project_dir, metadata_file, project_kb_file)

    metadata_enabled = bool(metadata_file and metadata_file.exists())
    results, issues, missing_rows, extra_rows = build_group_results(
        packet_enabled=options.get("group_code", True),
        offset_enabled=options.get("offset_datatype", True),
        metadata_compare_enabled=metadata_enabled and options.get("metadata_compare", True),
    )

    # Do not report a legacy/unsupported project as a successful zero-check
    # validation.  The selected packet source must exist and contain at least
    # one CASE nw_group_code block for this validator to have meaningful work.
    if not PLC_PACKET_FILE.exists():
        raise RuntimeError(
            f"PLC packet source not found: {PLC_PACKET_FILE}. "
            "Supported sources include mms_nw_rCyclic.st, mms_nw_r\\Cyclic.st, "
            "mms_nw_r\\mms_nw_r.st, and legacy mms_nw_r.src."
        )
    if not results:
        raise RuntimeError(
            f"No CASE nw_group_code packet groups were found in: {PLC_PACKET_FILE}. "
            "The project may use an unsupported legacy source format or the packet source could not be parsed."
        )

    if output_excel_path is None:
        output_excel_path = project_dir / "AI_QC" / f"{project_dir.name}_uSOPp_v171.xlsx"

    hmi_usage = extract_hmi_parameter_usage()
    excel_file = write_excel_report(
        results=results,
        issues=issues,
        missing_rows=missing_rows,
        extra_rows=extra_rows,
        output_path=output_excel_path,
        metadata_enabled=metadata_enabled,
        metadata_file=metadata_file,
        hmi_usage=hmi_usage,
    )

    # Compute high-level KPIs
    total_checks = 0
    passed = 0
    warnings = 0
    failed = 0

    groups_json = []
    global_serials = global_serial_map(results)
    for g in results:
        g_status = g.overall_status
        packet_res, _ = packet_variants_result(g)

        # Count parameters
        for p in g.parameters:
            total_checks += 1
            if p.status == "PASS":
                passed += 1
            elif p.status == "FAIL":
                failed += 1
            else:
                warnings += 1

        rec = "No action required"
        if g.overall_status == "FAIL":
            rec = "Correct the first highlighted PLC or metadata error, then revalidate"
        elif g.overall_status == "WARNING":
            rec = "Review packet length, unused bytes, and metadata warnings"
        for issue in g.issues:
            if str(getattr(issue, "severity", "")).upper() in {"FAIL", "WARNING"} and getattr(issue, "suggested_fix", ""):
                rec = str(issue.suggested_fix)
                break

        groups_json.append({
            "groupCode": g.code,
            "description": g.description,
            "configuredBytes": g.configured_bytes,
            "configuredMsb": g.configured_msb,
            "configuredLsb": g.configured_lsb,
            "expectedBytes": g.expected_bytes,
            "calculatedBytes": g.calculated_bytes,
            "calculatedByOffset": g.calculated_offset_bytes if g.calculated_offset_bytes is not None else g.calculated_bytes,
            "packetCalResult": packet_res,
            "packetVariants": g.packet_variants,
            "totalParameters": g.total_parameters,
            "passCount": g.pass_count,
            "failCount": g.fail_count,
            "warningCount": g.warning_count,
            "overallStatus": g_status,
            "recommendation": rec,
            "parameters": [
                {
                    "sequence": p.sequence,
                    "logicSequence": global_serials.get(id(p), p.sequence),
                    "groupCode": p.group_code,
                    "parameter": p.parameter,
                    "description": p.parameter_description,
                    "dataType": p.data_type,
                    "declaredDataType": p.declared_data_type,
                    "declaredSize": p.declared_size,
                    "sourceExpression": p.source_expression,
                    "destinationExpression": p.destination_expression,
                    "memcpySize": p.memcpy_size,
                    "transferMethod": p.transfer_method,
                    "conditionContext": p.condition_context,
                    "writeEvidence": p.write_evidence,
                    "incrementValue": p.increment_value,
                    "incrementLineNumber": p.increment_line_number,
                    "incrementRelation": p.increment_relation,
                    "sequenceValidation": p.sequence_validation,
                    "offsetAfterCopy": p.offset_after_copy,
                    "offsetBuffer": p.offset_buffer,
                    "tcpOffset": p.offset_buffer,
                    "runningOffset": p.running_offset,
                    "expectedOffset": p.expected_offset,
                    "status": p.status,
                    "remarks": p.remarks,
                    "validationType": p.validation_type,
                    "expected": p.expected_value,
                    "actual": p.actual_value,
                    "severity": p.severity,
                    "sourceFile": p.source_file,
                    "lineNumber": p.line_number,
                    "valueSource": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"valueSource":"Logic data","inputType":"Used only in logic, not in screen","dropdown":False,"pages":[],"controls":[],"hmiMin":None,"hmiMax":None}))["valueSource"],
                    "inputType": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"valueSource":"Logic data","inputType":"Used only in logic, not in screen","dropdown":False,"pages":[],"controls":[],"hmiMin":None,"hmiMax":None}))["inputType"],
                    "dropdown": bool(hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"dropdown":False})).get("dropdown", False)),
                    "hmiPages": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"pages":[]})).get("pages", []),
                    "hmiControls": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"controls":[]})).get("controls", []),
                    "hmiMin": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"hmiMin":None})).get("hmiMin"),
                    "hmiMax": hmi_usage.get(normalize_name(p.parameter), hmi_usage.get(normalize_name(str(p.parameter).split(".")[-1].strip()), {"hmiMax":None})).get("hmiMax"),
                }
                for p in g.parameters
            ],
        })

    # Dropdown validation results. HMI is compared against the SAME
    # uploaded metadata workbook used by metadata validation.
    dropdown_families = extract_dropdown_rows()
    dropdown_list = []

    uploaded_meta = load_metadata() if metadata_enabled else MetadataInfo(path=None, rows=defaultdict(list), issues=[])
    meta_by_group_param = {}
    meta_by_param = defaultdict(list)
    for gc, rows in uploaded_meta.rows.items():
        for mr in rows:
            key = normalize_name(mr.parameter)
            if key:
                meta_by_group_param[(gc, key)] = mr
                meta_by_param[key].append(mr)

    # Sheet2 mapping from the uploaded workbook only. Both .xlsx and legacy .xls are supported.
    uploaded_sheet2 = defaultdict(list)
    if metadata_enabled and metadata_file and metadata_file.exists():
        try:
            if metadata_file.suffix.lower()==".xls":
                if xlrd is None: raise RuntimeError("Legacy .xls metadata requires xlrd.")
                ref=xlrd.open_workbook(str(metadata_file),on_demand=True)
                try: sws=ref.sheet_by_name("Sheet2")
                except Exception: sws=None
                if sws is not None:
                    header_row=None; cols={}
                    for ridx in range(min(20,sws.nrows)):
                        rr=sws.row_values(ridx); found={str(v or "").strip().upper():i for i,v in enumerate(rr,start=1) if str(v or "").strip()}
                        if {"TAG_CODE","PLCVAL","SHOWNVAL"}.issubset(found): header_row=ridx+1; cols=found; break
                    if header_row:
                        for ridx in range(header_row,sws.nrows):
                            rr=sws.row_values(ridx); tag=rr[cols["TAG_CODE"]-1] if cols["TAG_CODE"]<=len(rr) else ""
                            if tag in (None,""): continue
                            pv=rr[cols["PLCVAL"]-1] if cols["PLCVAL"]<=len(rr) else ""; sv=rr[cols["SHOWNVAL"]-1] if cols["SHOWNVAL"]<=len(rr) else ""
                            uploaded_sheet2[str(tag).strip()].append((str(pv if pv is not None else "").strip(),str(sv if sv is not None else "").strip()))
                ref.release_resources()
            else:
                ref=load_workbook(metadata_file,data_only=True,read_only=True)
                if "Sheet2" in ref.sheetnames:
                    sws=ref["Sheet2"]; header_row=None; cols={}
                    for ridx,rr in enumerate(sws.iter_rows(min_row=1,max_row=min(20,sws.max_row),values_only=True),start=1):
                        found={str(v or "").strip().upper():i for i,v in enumerate(rr,start=1) if str(v or "").strip()}
                        if {"TAG_CODE","PLCVAL","SHOWNVAL"}.issubset(found): header_row=ridx; cols=found; break
                    if header_row:
                        for rr in sws.iter_rows(min_row=header_row+1,values_only=True):
                            tag=rr[cols["TAG_CODE"]-1] if cols["TAG_CODE"]<=len(rr) else ""
                            if tag in (None,""): continue
                            pv=rr[cols["PLCVAL"]-1] if cols["PLCVAL"]<=len(rr) else ""; sv=rr[cols["SHOWNVAL"]-1] if cols["SHOWNVAL"]<=len(rr) else ""
                            uploaded_sheet2[str(tag).strip()].append((str(pv if pv is not None else "").strip(),str(sv if sv is not None else "").strip()))
                ref.close()
        except Exception as exc:
            emit_status(f"Sheet2 metadata mapping load skipped: {exc}")

    def _pairs_from_text(text):
        return _parse_dropdown_pairs(text)

    for fam, d_rows in dropdown_families.items():
        for dr in d_rows:
            logic_name = str(dr.logic_parameter or "").strip()
            logic_key = normalize_name(logic_name)
            logic_leaf = normalize_name(logic_name.split(".")[-1].strip())
            # Resolve the HMI binding to the PLC parameter/group. B&R HMI
            # bindings often contain Local./Source[] prefixes, so compare both
            # the complete expression and its final variable token.
            plc_candidates = []
            for g in results:
                for pr in g.parameters:
                    pr_key = normalize_name(pr.parameter)
                    pr_leaf = normalize_name(str(pr.parameter).split(".")[-1].strip())
                    if pr_key in {logic_key, logic_leaf} or pr_leaf in {logic_key, logic_leaf}:
                        plc_candidates.append(pr)
            plc_row = plc_candidates[0] if plc_candidates else None
            # Only validate dropdowns bound to the Spin Connect PLC packet.
            # HMI-only controls are intentionally excluded from the result.
            if plc_row is None:
                continue
            group_code = plc_row.group_code
            # Use the SAME metadata matching concept as the main metadata
            # validation: parameter name/comment first, then group-relative
            # payload offset with datatype/size compatibility. This prevents
            # HMI dropdown validation from selecting an unrelated metadata row.
            metadata_row = None
            metadata_match_method = "Not found"
            group_meta_rows = list(uploaded_meta.rows.get(group_code, [])) if group_code is not None else []
            if group_meta_rows:
                metadata_row, metadata_match_method = metadata_match_for_parameter(plc_row, group_meta_rows)
            tag_code = metadata_row.sequence if metadata_row is not None else None
            # Approved master values take precedence only when both the PLC
            # comment and PLC tag exactly match the configured mapping.
            configured_pairs = master_dropdown_pairs(
                plc_parameter_value(plc_row),
                str(getattr(plc_row, "parameter", "") or ""),
            )
            hmi_pairs = configured_pairs or _pairs_from_text(dr.text_group_values)
            pair_source = "Master configured dropdown" if configured_pairs else "HMI TextGroup"
            meta_pairs = uploaded_sheet2.get(str(tag_code).strip(), []) if tag_code is not None else []
            hmi_set = {(str(a).strip(), str(b).strip()) for a, b in hmi_pairs}
            meta_set = {(str(a).strip(), str(b).strip()) for a, b in meta_pairs}

            if not metadata_enabled:
                status = "Metadata unavailable"
                reason = "No metadata workbook was uploaded; dropdown comparison was not performed."
            elif metadata_row is None:
                status = "Metadata unavailable"
                reason = "HMI dropdown parameter was not found in the uploaded metadata workbook."
            elif not meta_pairs:
                status = "Metadata unavailable"
                reason = f"TAG_CODE {tag_code} has no PLCVAL/SHOWNVAL mapping in uploaded Sheet2."
            elif hmi_set == meta_set:
                status = "Matching"
                reason = f"{pair_source} PLCVAL/SHOWNVAL mapping matches the uploaded Sheet2 mapping."
            else:
                status = "Mismatch"
                missing = sorted(meta_set - hmi_set)
                extra = sorted(hmi_set - meta_set)
                parts = []
                if missing: parts.append("missing HMI: " + ", ".join(f"{a}={b}" for a,b in missing))
                if extra: parts.append("extra/different HMI: " + ", ".join(f"{a}={b}" for a,b in extra))
                reason = "; ".join(parts) or "PLCVAL/SHOWNVAL mapping mismatch."

            dropdown_list.append({
                "family": dr.family,
                "pageFile": dr.page_file,
                "controlName": dr.control_name,
                "indexDatapoint": dr.index_datapoint,
                "logicParameter": logic_name,
                "logicComment": str(getattr(plc_row, "parameter_description", "") or "").strip(),
                "groupCode": group_code or "",
                "tagCode": tag_code if tag_code is not None else "",
                "metadataMatchMethod": metadata_match_method,
                "logicSourceFile": getattr(plc_row, "source_file", "") or "",
                "logicLineNumber": getattr(plc_row, "line_number", None),
                "textGroup": dr.text_group,
                "textGroupName": dr.text_group_name,
                "textGroupValues": dr.text_group_values,
                "pairSource": pair_source,
                "hmiPairs": [[a,b] for a,b in hmi_pairs],
                "metadataParameterName": metadata_row.parameter if metadata_row else "",
                "metadataPairs": [[a,b] for a,b in meta_pairs],
                "status": status,
                "reason": reason,
                "sourceFile": dr.text_group_source,
            })

    # BOOL metadata representation check. In USINT mode the datatype and the
    # exact Sheet2 mapping form one validation contract.
    bool_rows = []
    expected_bool_mapping = {("0", "ON"), ("1", "OFF")}
    for g in results:
        for p in g.parameters:
            if str(p.data_type).upper() == "BOOL":
                tag_code = p.metadata_tag_code if p.metadata_tag_code is not None else p.metadata_sequence
                actual_pairs = {
                    (str(plc_value).strip(), str(shown_value).strip().upper())
                    for plc_value, shown_value in uploaded_sheet2.get(str(tag_code).strip(), [])
                } if tag_code is not None else set()
                mapping_required = BOOL_METADATA_MODE == "USINT" and p.group_code != 30
                if not metadata_enabled:
                    mapping_status = "NOT VALIDATED"
                    mapping_reason = "No metadata workbook was uploaded."
                elif not mapping_required:
                    mapping_status = "PASS"
                    mapping_reason = "PLC BOOL remains BOOL; a conversion mapping is not required."
                elif actual_pairs == expected_bool_mapping:
                    mapping_status = "PASS"
                    mapping_reason = "Metadata USINT mapping matches 0 = ON and 1 = OFF."
                else:
                    mapping_status = "FAIL"
                    mapping_reason = "Expected Sheet2 mapping 0 = ON and 1 = OFF."
                bool_rows.append({
                    "groupCode": p.group_code,
                    "parameter": p.parameter,
                    "description": p.parameter_description,
                    "metadataType": p.metadata_data_type,
                    "metadataTagCode": tag_code,
                    "expectedPairs": [["0", "ON"], ["1", "OFF"]] if mapping_required else [],
                    "actualPairs": [list(pair) for pair in sorted(actual_pairs)],
                    "status": mapping_status,
                    "reason": mapping_reason,
                })

    # Alarm list
    alarms = extract_alarm_descriptions()
    alarm_list = [{"groupCode": gc, "description": desc} for gc, desc in alarms]

    # Metadata comparison list — this always compares PLC logic against the
    # workbook explicitly uploaded by the user. It never uses the generated
    # metadata workbook as a validation source.
    meta_comparison_list = []
    meta_duplicates_list = []
    if metadata_enabled:
        metadata_for_duplicates = load_metadata().rows if metadata_enabled else {}
        duplicate_rows = find_duplicate_metadata_parameters(metadata_for_duplicates) if metadata_for_duplicates else []
        meta_duplicates_list = [f"Group {r.group_code}: {r.parameter}" for r in duplicate_rows]

        for result in results:
            for row in result.parameters:
                # Metadata result is a separate validation layer.  The
                # machine-facing status is deliberately normalized to PASS /
                # WARNING / FAIL so the frontend cannot mistake a descriptive
                # code such as OFFSET_MISMATCH for a successful match.
                # A PLC row without a real logic comment uses the PLC tag as
                # its Parameter fallback, so metadata matching can still be
                # performed without inventing a description.
                comment = plc_parameter_value(row)
                no_comment = not comment
                datatype_state = metadata_type_compatibility(
                    row.data_type, row.metadata_data_type, row.group_code
                ) if row.metadata_data_type else "MISMATCH"
                if not row.metadata_parameter and row.metadata_group_code is None:
                    if no_comment:
                        comp_status = "FAIL"
                        details = "PLC Parameter is not available for metadata matching."
                    else:
                        comp_status = "FAIL"
                        details = "PLC Parameter not found in the uploaded metadata workbook."
                else:
                    group_mismatch = row.metadata_group_code is not None and row.metadata_group_code != row.group_code
                    configured_alias = "configured mapping" in str(row.metadata_match_method or "").lower()
                    parameter_mismatch = (
                        row.group_code != 30
                        and
                        not configured_alias
                        and bool(row.metadata_parameter)
                        and not metadata_text_exact(comment, row.metadata_parameter)
                    )
                    offset_mismatch = row.metadata_offset is not None and row.offset_buffer is not None and row.metadata_offset != row.offset_buffer
                    bool_mapping_mismatch = False
                    bool_mapping_details = ""
                    if normalize_type_name(row.data_type) == "BOOL" and BOOL_METADATA_MODE == "USINT" and row.group_code != 30:
                        bool_tag_code = row.metadata_tag_code if row.metadata_tag_code is not None else row.metadata_sequence
                        actual_bool_pairs = {
                            (str(plc_value).strip(), str(shown_value).strip().upper())
                            for plc_value, shown_value in uploaded_sheet2.get(str(bool_tag_code).strip(), [])
                        } if bool_tag_code is not None else set()
                        bool_mapping_mismatch = (
                            actual_bool_pairs != expected_bool_mapping
                            or str(row.metadata_shown_value_different or "").strip().upper() != "YES"
                        )
                        if bool_mapping_mismatch:
                            actual_text = ", ".join(f"{a}={b}" for a, b in sorted(actual_bool_pairs)) or "missing"
                            bool_mapping_details = (
                                "BOOL to USINT mapping mismatch; expected Sheet2 0=ON, 1=OFF and "
                                f"IS_SHOWN_VALUE_DIFFERENT=YES; actual mapping is {actual_text}."
                            )

                    # This is a generated display sequence, not a PLC TAG_CODE.
                    # ST packet assignments do not expose the workbook's S.No
                    # as a PLC identity, so comparing these values creates
                    # false metadata failures when earlier groups differ.
                    if offset_mismatch:
                        comp_status = "FAIL"
                        details = f"Offset mismatch; in logic is {row.offset_buffer}B : in metadata is {row.metadata_offset}B"
                    elif group_mismatch:
                        comp_status = "FAIL"
                        details = f"Group code mismatch: in PLC is {row.group_code} vs in metadata is {row.metadata_group_code}"
                    elif parameter_mismatch:
                        comp_status = "FAIL"
                        details = f"Parameter mismatch; PLC is {comment}; uploaded metadata is {row.metadata_parameter}"
                    elif datatype_state == "MISMATCH":
                        comp_status = "FAIL"
                        expected_type = "BYTE" if row.group_code == 30 else (BOOL_METADATA_MODE if normalize_type_name(row.data_type) == "BOOL" else row.data_type)
                        details = f"Data Type mismatch; PLC logic is {row.data_type}; expected metadata is {expected_type}; actual metadata is {row.metadata_data_type}"
                    elif bool_mapping_mismatch:
                        comp_status = "FAIL"
                        details = bool_mapping_details
                    elif datatype_state == "WARNING":
                        comp_status = "WARNING"
                        details = f"Compatible Data Type: logic is {row.data_type} : metadata is {row.metadata_data_type}"
                    else:
                        comp_status = "PASS"
                        details = "Parameter mapping resolved; offset, group code, and data type match."

                plc_parameter_display = plc_parameter_value(row)
                hmi_info = _hmi_usage_for_parameter(row, hmi_usage)
                hmi_min, hmi_max, min_max_source = resolved_min_max(
                    plc_parameter_display,
                    str(row.parameter or ""),
                    hmi_info,
                )
                configured_pairs = master_dropdown_pairs(
                    plc_parameter_display,
                    str(getattr(row, "parameter", "") or ""),
                )
                meta_comparison_list.append({
                    "parameterName": plc_parameter_display or "Param",
                    "logicSequence": global_serials.get(id(row), row.sequence),
                    "logicParameterName": plc_parameter_display or "Param",
                    "plcTag": row.parameter or "",
                    "logicDescription": row.parameter_description or "",
                    "metadataParameterName": row.metadata_parameter or "",
                    "metadataDescription": row.metadata_description or "",
                    "groupCode": row.group_code,
                    "metadataGroupCode": row.metadata_group_code,
                    "status": comp_status,
                    "comparisonStatus": comp_status,
                    "recordType": "PLC_WITH_METADATA" if row.metadata_parameter else "PLC_ONLY",
                    "plcOffset": row.offset_buffer,
                    "plcSize": row.memcpy_size,
                    "plcType": "BYTE" if row.group_code == 30 else row.data_type,
                    "plcDeclaredType": row.data_type,
                    "metadataOffset": row.metadata_offset,
                    "metadataType": row.metadata_data_type,
                    "datatypeCompatibility": datatype_state,
                    "metadataSize": row.metadata_size,
                    "metadataSequence": row.metadata_sequence,
                    "metadataTagCode": getattr(row, "metadata_tag_code", None),
                    "metadataMin": row.metadata_min_value,
                    "metadataMax": row.metadata_max_value,
                    "metadataShownValueDifferent": row.metadata_shown_value_different,
                    "metadataSheet": row.metadata_sheet_name,
                    "metadataRow": row.metadata_row_number,
                    "matchMethod": row.metadata_match_method,
                    "logicComment": row.parameter_description or "",
                    "logicSourceFile": row.source_file or "",
                    "logicLineNumber": row.line_number,
                    "details": details,
                    "valueSource": "Master configured dropdown" if configured_pairs else hmi_info.get("valueSource", "Logic data"),
                    "inputType": "Configured dropdown" if configured_pairs else hmi_info.get("inputType", "Used only in logic, not in screen"),
                    "dropdown": bool(configured_pairs) or bool(hmi_info.get("dropdown", False)),
                    "hmiPairs": [[a, b] for a, b in configured_pairs],
                    "hmiMin": hmi_min,
                    "hmiMax": hmi_max,
                    "minMaxSource": min_max_source,
                })

        for r in missing_rows:
            meta_comparison_list.append({
                "parameterName": getattr(r, "parameter", "Unknown"),
                "logicSequence": None,
                "logicParameterName": "",
                "plcTag": "",
                "logicDescription": "",
                "metadataParameterName": getattr(r, "parameter", "Unknown"),
                "metadataDescription": getattr(r, "description", ""),
                "groupCode": None,
                "metadataGroupCode": getattr(r, "group_code", 0),
                "status": "FAIL",
                "comparisonStatus": "MISSING_IN_PLC",
                "recordType": "METADATA_ONLY",
                "metadataOffset": getattr(r, "offset", None),
                "metadataType": getattr(r, "datatype", None),
                "metadataSize": getattr(r, "size", None),
                "metadataSequence": getattr(r, "sequence", None),
                "metadataTagCode": getattr(r, "tag_code", None),
                "metadataMin": getattr(r, "min_value", None),
                "metadataMax": getattr(r, "max_value", None),
                "metadataShownValueDifferent": getattr(r, "shown_value_different", ""),
                "metadataSheet": getattr(r, "sheet_name", ""),
                "metadataRow": getattr(r, "row_number", None),
                "matchMethod": "Metadata Parameter not found in PLC",
                "logicVariableName": "",
                "valueSource": "Not available",
                "inputType": "Not available",
                "dropdown": False,
                "hmiMin": None,
                "hmiMax": None,
                "logicComment": "",
                "logicSourceFile": "",
                "logicLineNumber": None,
                "details": "Listed in the uploaded metadata workbook but not found in PLC packet writes.",
            })

    # Raw uploaded metadata source rows. This is deliberately independent of
    # matching: the frontend must be able to display every workbook record
    # exactly as supplied, including metadata-only records.
    metadata_source_rows = []
    if metadata_enabled:
        # Preserve the uploaded workbook order exactly. Do not sort by Group Code
        # because the workbook's A-column S.NO./H-column TAG_CODE order is the
        # source record order shown to the engineer.
        for mr in [item for group_rows in uploaded_meta.rows.values() for item in group_rows]:
                metadata_source_rows.append({
                    "sequence": mr.sequence,
                    "tagCode": mr.tag_code,
                    "screenName": getattr(mr, "screen_name", ""),
                    "machineVariants": getattr(mr, "machine_variants", ""),
                    "parameter": mr.parameter,
                    "groupCode": mr.group_code,
                    "dataType": mr.datatype,
                    "offset": mr.offset,
                    "min": mr.min_value,
                    "max": mr.max_value,
                    "shownValueDifferent": mr.shown_value_different,
                    "units": getattr(mr, "units", ""),
                    "offsetFactor": getattr(mr, "offset_factor", ""),
                    "scaleFactor": getattr(mr, "scale_factor", ""),
                    "isVisible": getattr(mr, "is_visible", ""),
                    "isWritable": getattr(mr, "is_writable", ""),
                    "sheetName": mr.sheet_name,
                    "rowNumber": mr.row_number,
                })

    metadata_passed = sum(1 for x in meta_comparison_list if str(x.get("status", "")).upper() == "PASS")
    metadata_warnings = sum(1 for x in meta_comparison_list if str(x.get("status", "")).upper() == "WARNING")
    metadata_failed = sum(1 for x in meta_comparison_list if str(x.get("status", "")).upper() == "FAIL")
    control_checks = {}
    for issue in issues:
        if issue.validation_type in PACKET_CONTROL_CHECK_TYPES:
            control_checks.setdefault(_validation_issue_key(issue), issue)
    for issue in control_checks.values():
        total_checks += 1
        if issue.severity == "FAIL":
            failed += 1
        elif issue.severity == "WARNING":
            warnings += 1
        else:
            passed += 1

    metadata_total = metadata_passed + metadata_warnings + metadata_failed
    total_checks += metadata_total
    passed += metadata_passed
    warnings += metadata_warnings
    failed += metadata_failed
    score_denom = total_checks if total_checks > 0 else 1
    compliance_score = max(0, min(100, round(((passed + warnings * 0.5) / score_denom) * 100)))

    report_payload = {
        "engineVersion": "v1.71",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "projectName": project_dir.name,
        "metadataUploaded": metadata_enabled,
        "metadataFile": str(metadata_file.name) if metadata_file else None,
        "boolMetadataMode": BOOL_METADATA_MODE,
        "metadataMessage": "Metadata: Not Uploaded – Metadata comparison skipped" if not metadata_enabled else f"Metadata loaded: {metadata_file.name}",
        "excelReportPath": str(excel_file),
        "summary": {
            "totalChecks": total_checks,
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "complianceScore": compliance_score,
            "totalGroups": len(results),
        },
        "groups": groups_json,
        "datatypeIndex": datatype_index(),
        "hmiParameterUsage": hmi_usage,
        "metadataSourceRows": metadata_source_rows,
        "metadataComparison": {
            "totalRecords": len(meta_comparison_list),
            "passed": metadata_passed,
            "warnings": metadata_warnings,
            "failed": metadata_failed,
            "results": meta_comparison_list,
            "duplicates": meta_duplicates_list,
        },
        "dropdownValidation": {
            "totalControls": len(dropdown_list),
            "controls": dropdown_list,
            "boolChecks": bool_rows,
        },
        "alarmValidation": {
            "totalAlarms": len(alarm_list),
            "alarms": alarm_list,
        },
        "issues": [
            {
                "groupCode": issue.group_code,
                "parameter": issue.parameter,
                "description": issue.description,
                "validationType": issue.validation_type,
                "expected": issue.expected,
                "actual": issue.actual,
                "severity": issue.severity,
                "sourceFile": issue.source_file,
                "lineNumber": issue.line_number,
                "suggestedFix": issue.suggested_fix,
                "condition": issue.condition,
            }
            for issue in issues
        ],
    }

    if output_json_path:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    return report_payload


def main():
    global ACTIVE_MACHINE_DEPARTMENT, BOOL_METADATA_MODE
    parser = argparse.ArgumentParser(description="uSOPp Python v1.71 Validation Engine")
    parser.add_argument("--project", type=str, help="Path to B&R project root folder")
    parser.add_argument("--metadata", type=str, help="Optional path to metadata workbook (.xlsx, .xls, .csv)")
    parser.add_argument("--project-kb", type=str, help="Optional project Knowledge Store JSON file for approved parameter mappings")
    parser.add_argument("--machine-department", type=str, default="All", help="Machine scope for approved master mappings")
    parser.add_argument("--bool-metadata-mode", choices=("BOOL", "USINT"), default="BOOL", help="Metadata representation required for PLC BOOL tags")
    parser.add_argument("--output-excel", type=str, help="Path to output Excel workbook")
    parser.add_argument("--output-json", type=str, help="Path to output JSON report")
    parser.add_argument("--generate-metadata", action="store_true", help="Generate metadata workbook from PLC implementation")

    args = parser.parse_args()
    BOOL_METADATA_MODE = normalize_bool_metadata_mode(args.bool_metadata_mode)

    if args.generate_metadata:
        if not args.project:
            print("Error: --project is required for --generate-metadata", file=sys.stderr)
            sys.exit(1)
        proj_dir = Path(args.project).resolve()
        ACTIVE_MACHINE_DEPARTMENT = args.machine_department or 'All'
        initialize_project_context(proj_dir, None)
        out_excel = Path(args.output_excel).resolve() if args.output_excel else proj_dir / "AI_QC" / f"{proj_dir.name}_Generated_Metadata.xlsx"
        out_json = Path(args.output_json).resolve() if args.output_json else None
        res = generate_metadata_workbook(out_excel, out_json)
        print(json.dumps({"status": "success", "excelPath": str(out_excel), "totalParameters": res["totalParameters"]}))
        return

    if args.project:
        proj_dir = Path(args.project).resolve()
        meta_file = Path(args.metadata).resolve() if args.metadata else None
        out_excel = Path(args.output_excel).resolve() if args.output_excel else proj_dir / "AI_QC" / f"{proj_dir.name}_uSOPp_v171.xlsx"
        out_json = Path(args.output_json).resolve() if args.output_json else None

        result = run_engine_json(
            project_dir=proj_dir,
            metadata_file=meta_file,
            output_excel_path=out_excel,
            output_json_path=out_json,
            project_kb_file=Path(args.project_kb).resolve() if args.project_kb else None,
            machine_department=args.machine_department,
            bool_metadata_mode=args.bool_metadata_mode,
        )
        if result["summary"]["totalGroups"] == 0:
            print(json.dumps({
                "status": "error",
                "message": "No PLC group codes were extracted from the selected packet source.",
                "packetSource": str(PLC_PACKET_FILE),
            }), file=sys.stderr)
            sys.exit(2)
        print(json.dumps({
            "status": "success",
            "complianceScore": result["summary"]["complianceScore"],
            "totalGroups": result["summary"]["totalGroups"],
            "totalChecks": result["summary"]["totalChecks"],
            "excelReportPath": result["excelReportPath"],
        }))
        return

    print("uSOPp Python v1.71 Engine ready. Use --help for command line usage.")


if __name__ == "__main__":
    main()
