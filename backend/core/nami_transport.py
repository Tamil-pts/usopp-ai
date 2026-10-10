"""Serialized PLC exchanges for the Nami binary protocol."""
import logging
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from backend.core.nami_simulator import frame

log = logging.getLogger('usopp.nami')
_targets = {}
_guard = threading.Lock()

def read_request(machine_id, group):
    return frame(machine_id, int(group).to_bytes(2, 'big'), 1)

class ReceiveError(OSError):
    def __init__(self, message, raw, expected):
        super().__init__(message)
        self.raw = list(raw)
        self.expected = expected

@contextmanager
def connection(ip, port, timeout_ms):
    key = (ip, port)
    with _guard:
        lock = _targets.setdefault(key, threading.Lock())
    with lock:
        try:
            with socket.create_connection(key, timeout_ms / 1000) as sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(timeout_ms / 1000)
                yield sock
        finally:
            # Some controllers need time to release their previous TCP session.
            time.sleep(.18)

def receive(sock):
    data = bytearray()
    expected = 5
    timeout = sock.gettimeout()
    deadline = time.monotonic() + timeout
    try:
        while len(data) < expected:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('response timed out')
            sock.settimeout(remaining)
            part = sock.recv(expected - len(data))
            if not part:
                raise ConnectionError(f'PLC closed with an incomplete frame ({len(data)}/{expected} bytes)')
            data.extend(part)
            if len(data) == 5:
                expected = int.from_bytes(data[3:5], 'big') + 7
    except OSError as exc:
        if isinstance(exc, TimeoutError):
            message = ('No response from PLC. Check that the SpinConnect function is enabled, '
                       'the Machine ID matches, and no previous client session is still active.'
                       if not data else f'Incomplete PLC response: received {len(data)}/{expected} bytes before timeout.')
        else:
            message = str(exc) or type(exc).__name__
        raise ReceiveError(message, data, expected) from exc
    finally:
        sock.settimeout(timeout)
    return list(data)

def exchange(sock, request):
    started = time.monotonic()
    result = dict(success=False, rawBytes=[], sentBytes=[], tcpConnected=True, stage='send')
    try:
        sock.sendall(request)
        result.update(sentBytes=list(request), stage='receive')
        result.update(rawBytes=receive(sock), success=True, stage='complete')
        raw = result['rawBytes']
        checksum = 0
        for byte in raw[:-2]:
            checksum ^= byte
        if raw[0] != 3 or raw[-1] != 2 or raw[1] != request[1] or checksum != raw[-2]:
            result.update(success=False, stage='validate', error='Invalid PLC response marker, Machine ID or checksum.')
    except OSError as exc:
        result['error'] = str(exc) or type(exc).__name__
        if isinstance(exc, ReceiveError):
            result.update(rawBytes=exc.raw, expectedFrameBytes=exc.expected)
    result['rttMs'] = round((time.monotonic() - started) * 1000)
    return result

def request_close(sock, machine_id, trace):
    """GC 11 has no response frame: wait for the PLC's EOF/reset instead."""
    request = read_request(machine_id, 11)
    result = dict(success=False, groupCode=11, sentBytes=[], plcClosed=False)
    started = time.monotonic()
    try:
        sock.sendall(request)
        result.update(success=True, sentBytes=list(request))
        log.info('DataInspect [%s] GC11 sent hex=%s; waiting for PLC close', trace, request.hex(' '))
        # Bound cleanup time; the 300-second idle timeout is not a response timeout.
        deadline = started + min(sock.gettimeout(), 3.0)
        while time.monotonic() < deadline:
            sock.settimeout(max(.001, deadline - time.monotonic()))
            if not sock.recv(4096):
                result['plcClosed'] = True
                break
    except (ConnectionResetError, ConnectionAbortedError):
        if result['sentBytes']:
            result['plcClosed'] = True
        else:
            result.update(error='PLC closed before GC 11 could be sent', normalClose=False)
    except TimeoutError:
        result['warning'] = 'GC 11 sent, but PLC closure was not confirmed before the close wait expired.'
    except OSError as exc:
        result.update(error=str(exc) or type(exc).__name__, normalClose=False)
    if result['sentBytes'] and not result['plcClosed'] and not result.get('error'):
        result.setdefault('warning', 'GC 11 sent, but PLC closure was not confirmed before the close wait expired.')
    result['normalClose'] = result['plcClosed']
    result['rttMs'] = round((time.monotonic() - started) * 1000)
    log.info('DataInspect [%s] GC11 sent=%s plc_closed=%s duration_ms=%s detail=%s',
             trace, bool(result['sentBytes']), result['plcClosed'], result['rttMs'],
             result.get('error') or result.get('warning') or 'complete')
    return result

def sequence(ip, port, machine_id, groups, timeout_ms):
    results = []
    close = None
    error = None
    connected = False
    trace = uuid.uuid4().hex[:12]
    started = time.monotonic()
    log.info('DataInspect [%s] connect target=%s:%s machine_id=%s groups=%s timeout_ms=%s',
             trace, ip, port, machine_id, groups, timeout_ms)
    try:
        with connection(ip, port, timeout_ms) as sock:
            connected = True
            log.info('DataInspect [%s] TCP connected local=%s target=%s:%s', trace, sock.getsockname(), ip, port)
            try:
                for group in groups:
                    request = read_request(machine_id, group)
                    log.info('DataInspect [%s] GC%s request hex=%s', trace, group, request.hex(' '))
                    result = dict(exchange(sock, request), groupCode=group, traceId=trace)
                    results.append(result)
                    log.info('DataInspect [%s] GC%s stage=%s sent=%s received=%s rtt_ms=%s error=%s',
                             trace, group, result['stage'], len(result['sentBytes']), len(result['rawBytes']),
                             result['rttMs'], result.get('error', '-'))
                    if not result['success']:
                        error = result.get('error')
                        # A late reply cannot safely be associated with the next group.
                        break
            finally:
                sock.settimeout(timeout_ms / 1000)
                close = request_close(sock, machine_id, trace)
    except (OSError, ValueError) as exc:
        error = f'TCP connection to {ip}:{port} failed: {str(exc) or type(exc).__name__}'
        log.warning('DataInspect [%s] %s', trace, error)
    for group in groups[len(results):]:
        skipped = bool(results)
        results.append(dict(success=False, groupCode=group, rawBytes=[], sentBytes=[],
                            rttMs=0 if skipped else round((time.monotonic() - started) * 1000),
                            tcpConnected=connected, stage='not_sent' if skipped else 'connect', traceId=trace,
                            error=f'Not requested: sequence stopped after an earlier failure. {error}' if skipped else error))
    return dict(results=results, closeResult=close, error=error, tcpConnected=connected, traceId=trace,
                totalDurationMs=round((time.monotonic() - started) * 1000))

def raw_exchange(ip, port, request, timeout_ms, close_session=False):
    # Standard manual group reads use the same GC 11 cleanup as the main UI.
    if len(request) == 9 and request[2] == 1:
        group = int.from_bytes(request[5:7], 'big')
        if group != 11 and request == read_request(request[1], group):
            result = sequence(ip, port, request[1], [group], timeout_ms)
            return dict(result['results'][0], closeResult=result['closeResult'])
    try:
        with connection(ip, port, timeout_ms) as sock:
            trace = uuid.uuid4().hex[:12]
            log.info('DataInspect [%s] raw request target=%s:%s length=%s hex=%s', trace, ip, port, len(request), request.hex(' '))
            result = None
            try:
                result = dict(exchange(sock, request), traceId=trace)
                return result
            finally:
                if close_session:
                    sock.settimeout(timeout_ms / 1000)
                    close = request_close(sock, request[1], trace)
                    if result is not None:
                        result['closeResult'] = close
    except OSError as exc:
        return dict(success=False, rawBytes=[], sentBytes=[], rttMs=0, tcpConnected=False,
                    stage='connect', error=f'TCP connection to {ip}:{port} failed: {str(exc) or type(exc).__name__}')
