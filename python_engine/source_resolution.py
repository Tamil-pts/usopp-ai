"""Resolve equivalent B&R task source layouts without mixing task sections."""
from __future__ import annotations
from pathlib import Path
import fnmatch
import re

LOGIC_EXTENSIONS={'.st','.ld','.ab','.c','.src','.prg'}
DECLARATION_EXTENSIONS={'.var','.typ'}
PROJECT_ROOTS={'logical','physical','configuration','configurations'}


def _normal(value:str)->str:
    value=str(value or '').strip().replace('\\','/').casefold()
    while value.startswith('./'): value=value[2:]
    return value


def _task_request(pattern:str):
    """Return task, section and requested extension for a non-wildcard source."""
    normalized=_normal(pattern)
    if not normalized or any(ch in normalized for ch in '*?[]') or normalized.startswith('/') or ':' in normalized:
        return None
    parts=normalized.split('/')
    if '..' in parts or parts[0] in PROJECT_ROOTS:
        return None
    name=parts[-1]
    suffix=Path(name).suffix
    stem=Path(name).stem if suffix else name
    parent=parts[-2] if len(parts)>1 else ''
    if suffix in DECLARATION_EXTENSIONS:
        task=parent or stem
        section='var' if suffix=='.var' else 'typ'
        return task,section,suffix
    if suffix and suffix not in LOGIC_EXTENSIONS:
        return None
    for section in ('cyclic','init','exit'):
        if stem==section and parent:
            return parent,section,suffix
        if stem.endswith(section) and len(stem)>len(section):
            return stem[:-len(section)],section,suffix
    # B&R also permits TaskName.st/TaskName.src for the cyclic implementation.
    return parent or stem,'cyclic',suffix


def source_pattern_matches(relative_path:str,pattern:str)->bool:
    """Match exact paths plus B&R-equivalent task/section filenames."""
    relative=_normal(relative_path);requested=_normal(pattern)
    if not requested or requested.startswith('/') or ':' in requested or '..' in requested.split('/'):
        return False
    path=Path(relative);name=path.name.casefold();suffix=path.suffix.casefold()
    if '/' not in requested and fnmatch.fnmatchcase(name,requested): return True
    if fnmatch.fnmatchcase(relative,requested): return True
    if requested.split('/')[0] not in PROJECT_ROOTS:
        parts=relative.split('/')
        if any(fnmatch.fnmatchcase('/'.join(parts[index:]),requested) for index in range(1,len(parts))): return True
    task_request=_task_request(requested)
    if not task_request: return False
    task,section,_=task_request
    parent=path.parent.name.casefold()
    stem=path.stem.casefold()
    if section in {'var','typ'}:
        if suffix!=('.var' if section=='var' else '.typ'): return False
        return (parent==task and stem in {task,'variables' if section=='var' else 'types'}) or stem==task
    if suffix not in LOGIC_EXTENSIONS: return False
    section_names={section,task+section}
    # TaskName.st and TaskName.src are cyclic-only representations.
    if section=='cyclic': section_names.add(task)
    return (parent==task and stem in section_names) or stem==task+section or (section=='cyclic' and stem==task)


def matching_sources(root:Path,pattern:str,files)->list[Path]:
    return sorted((p for p in files if source_pattern_matches(p.relative_to(root).as_posix(),pattern)),
                  key=lambda p:p.as_posix().casefold())
