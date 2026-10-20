"""Bounded previews that never first copy an entire PLC array."""
from itertools import islice


def value_preview(value, depth=0):
    if isinstance(value, str) and len(value) > 1024:
        return value[:1024], False
    if isinstance(value, (list, dict)):
        if depth >= 3:
            return None, False
        complete = len(value) <= 32
        selected = [] if isinstance(value, list) else {}
        entries = enumerate(value) if isinstance(value, list) else value.items()
        for key, item in islice(entries, 32):
            result, whole = value_preview(item, depth+1)
            complete = complete and whole
            if isinstance(selected, list): selected.append(result)
            else: selected[key] = result
        return selected, complete
    return value, True
