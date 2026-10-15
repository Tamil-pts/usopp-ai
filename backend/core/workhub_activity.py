"""Summarize already-authorized saved run records for the WorkHub dashboard."""
from collections import Counter
from datetime import datetime, timedelta, timezone


TOOL_LABELS = {
    'validation': 'ByteMap', 'metadata': 'MetaWorks', 'rules': 'LogicScan',
    'compare': 'MatchView', 'datainspect': 'DataInspect',
    'data-model': 'DataInspect references',
}


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def summarize_activity(records, days=7, now=None):
    """Count recorded activity, never infer compliance or a successful validation."""
    if not 1 <= days <= 30:
        raise ValueError('Activity range must be between 1 and 30 days.')
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    dates = [(start + timedelta(days=offset)).date().isoformat() for offset in range(days)]
    daily, tools, users, recent = Counter(), Counter(), {}, []
    for record in records:
        kind = record.get('kind')
        created = _timestamp(record.get('createdAt'))
        # Legacy imports use file modification time, not a recorded run time.
        if record.get('legacy') or kind not in TOOL_LABELS or created is None or not start <= created <= now:
            continue
        owner = record.get('user') or {}
        user_id = owner.get('id')
        username = str(owner.get('username') or 'User not recorded')
        key = ('user', user_id) if user_id is not None else ('unattributed', '')
        daily[created.date().isoformat()] += 1
        tools[kind] += 1
        person = users.setdefault(key, {'id': user_id, 'username': username, 'count': 0,
                                       'lastRunAt': created.isoformat(), 'tools': set()})
        person['count'] += 1
        person['lastRunAt'] = max(person['lastRunAt'], created.isoformat())
        person['tools'].add(TOOL_LABELS[kind])
        # Deliberately exclude filesystem paths, findings, source and raw PLC data.
        recent.append({'id': str(record.get('id') or ''), 'kind': kind,
                       'toolLabel': TOOL_LABELS[kind], 'projectName': str(record.get('projectName') or 'Not recorded'),
                       'machineDepartment': str(record.get('machineDepartment') or ''),
                       'createdAt': created.isoformat(),
                       'completedAt': record.get('completedAt') or None,
                       'user': {'id': user_id, 'username': username} if owner else None,
                       'status': str(record.get('status') or 'completed'),
                       'testId': str(record.get('testId') or '')})
    people = [{**person, 'tools': sorted(person['tools'])} for person in users.values()]
    people.sort(key=lambda person: (person['lastRunAt'], person['username']), reverse=True)
    recent.sort(key=lambda record: (record['createdAt'], record['id']), reverse=True)
    return {'days': days, 'timezone': 'UTC', 'generatedAt': now.isoformat(),
            'totalRuns': sum(daily.values()),
            'daily': [{'date': date, 'count': daily[date]} for date in dates],
            'users': people,
            'tools': [{'kind': kind, 'label': label, 'count': tools[kind]}
                      for kind, label in TOOL_LABELS.items() if tools[kind]],
            'recent': recent[:8]}
