"""Request frame selection, independent of the machine department.

Old saved YBS targets retain their profile when no explicit selection exists.
"""

def frame_protocol(data):
    plc = data.get('plc') if isinstance(data.get('plc'), dict) else data
    selected = data.get('frameProtocol', plc.get('frameProtocol'))
    if selected is None:
        return 'ybs' if plc.get('machineType', data.get('machineType')) == 'YBS' else 'spinconnect'
    if selected not in ('spinconnect', 'ybs'):
        raise ValueError('Request frame must be Server to B&R (spinconnect) or Server to YBS (ybs).')
    return selected
