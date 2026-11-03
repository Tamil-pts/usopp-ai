"""Inclusive project-date filtering shared by the project register export path."""
from datetime import date

DATE_FIELDS={'due_date':'Due date','start_date':'Planned start date','started_at':'Actual start date',
             'completed_at':'Closure date','created_at':'Created date','updated_at':'Last updated date'}


def value(project,field,custom_fields=()):
    if field=='completed_at' and project['stage']!='released':return ''
    raw=next((f['value'] for f in custom_fields if f['id']==field and f['type']=='date'),'') if field.startswith('custom_') else project.get(field)
    if not isinstance(raw,str):return ''
    try:return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:return ''


def matches(project,field,start,end,custom_fields=()):
    if not start and not end:return True
    day=value(project,field,custom_fields)
    return bool(day and (not start or day>=start) and (not end or day<=end))
