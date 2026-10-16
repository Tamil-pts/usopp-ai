"""Keep configured metadata names tied to distinct PLC packet fields."""
from collections import defaultdict
import re


def metadata_display_name(value):
    """Use readable spaces in output captions; retain PLC identities separately."""
    return re.sub(r'\s+', ' ', str(value or '').replace('_', ' ')).strip()


def resolve_name_collisions(candidates):
    """Reject aliases that merge different source captions in one group.

    Genuine repeated PLC comments remain repeated, so the existing duplicate
    check can report them. Never remove, reorder or merge packet fields.
    """
    rows = [dict(row) for row in candidates]
    warnings = []

    def key(value):
        return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())

    while True:
        buckets = defaultdict(list)
        for index, row in enumerate(rows):
            buckets[key(row['parameter'])].append(index)
        changed = False
        for indexes in buckets.values():
            if len(indexes) < 2 or len({key(rows[i]['plc_parameter']) for i in indexes}) < 2:
                continue
            for index in indexes:
                row = rows[index]
                if key(row['parameter']) == key(row['plc_parameter']):
                    continue
                warnings.append({
                    'plcTag': row['plc_tag'],
                    'plcParameter': row['plc_parameter'],
                    'rejectedName': row['parameter'],
                    'conflictingTags': [rows[i]['plc_tag'] for i in indexes if i != index],
                    'sourceFile': row.get('source_file', ''),
                    'lineNumber': row.get('line_number'),
                    'message': 'Configured alias duplicates a different PLC parameter in this group; retained the PLC source name.',
                })
                row['parameter'] = row['plc_parameter']
                row['mapping_source'] = 'PLC name (conflicting master alias rejected)'
                changed = True
        if not changed:
            return rows, warnings
