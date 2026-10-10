"""Install and manage the source-based Ubuntu demo as the current user."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv-ubuntu'
PYTHON = VENV / 'bin' / 'python'
STATE = ROOT / '.usopp_server' / 'server.json'
LOG = ROOT / 'logs' / 'ubuntu-demo.log'


def load_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def process_identity(pid):
    """Check Linux process start time as well as PID to avoid PID reuse."""
    try:
        proc = Path('/proc') / str(int(pid))
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'started': fields[19],
                'command': (proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')}
    except (OSError, ValueError, IndexError):
        return None


def is_running(state):
    identity = process_identity(state.get('pid', 0))
    return bool(identity and state.get('root') == str(ROOT) and
                identity == state.get('identity'))


def install():
    if sys.version_info < (3, 11):
        raise RuntimeError('Use Python 3.11 or later for the Ubuntu demo.')
    npm, node = shutil.which('npm'), shutil.which('node')
    if not npm or not node:
        raise RuntimeError('Install Node.js 20 or later with npm, then run install again.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 20:
        raise RuntimeError(f'Node {version} is too old. Install Node.js 20 or later with npm.')
    if is_running(load_state()):
        raise RuntimeError('Stop the demo before installing an update: bash usopp.sh stop')
    if not PYTHON.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
    for command in (
        [str(PYTHON), '-m', 'pip', 'install', '-r', str(ROOT / 'backend_requirements.txt')],
        [npm, 'ci', '--no-audit', '--no-fund'],
        [npm, 'run', 'build'],
    ):
        subprocess.run(command, cwd=ROOT, check=True)
    print('Installation complete. Start with: bash usopp.sh start')


def health(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
            return json.loads(response.read().decode('utf-8'))
    except (OSError, ValueError):
        return None


def start(host, port):
    state = load_state()
    if is_running(state):
        print(f"uSOPp is already running (PID {state['pid']}, port {state['port']}).")
        return
    if not PYTHON.is_file() or not (ROOT / 'dist' / 'index.html').is_file():
        raise RuntimeError('Install the demo first: bash usopp.sh install')
    # A listening process without our identity is never adopted or stopped.
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'Port {port} is already in use. Choose another port with --port.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    command = [str(PYTHON), '-m', 'uvicorn', 'backend.app:app',
               '--host', host, '--port', str(port), '--no-access-log']
    with LOG.open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True,
                                   env={**os.environ, 'PYTHONUTF8': '1', 'USOPP_NO_BROWSER': '1'})
    deadline = time.monotonic() + 35
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Server exited. Read the log: {LOG}')
            data = health(port)
            if data and data.get('version') == version:
                identity = process_identity(process.pid)
                if not identity:
                    raise RuntimeError('Could not confirm the server process identity.')
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps({'pid': process.pid, 'identity': identity,
                    'root': str(ROOT), 'host': host, 'port': port, 'version': version}), encoding='utf-8')
                print(f'uSOPp {version} started (PID {process.pid}).')
                print(f'On this server: http://127.0.0.1:{port}')
                if host == '0.0.0.0':
                    print(f'From another computer: http://<server-IP>:{port}')
                print(f'Log: {LOG}')
                return
            time.sleep(.25)
        raise RuntimeError(f'Server did not become ready within 35 seconds. Read: {LOG}')
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def stop():
    state = load_state()
    if not is_running(state):
        STATE.unlink(missing_ok=True)
        print('uSOPp demo is stopped.')
        return
    os.kill(state['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 15
    while is_running(state) and time.monotonic() < deadline:
        time.sleep(.2)
    if is_running(state):
        os.kill(state['pid'], signal.SIGKILL)
    STATE.unlink(missing_ok=True)
    print('uSOPp demo stopped.')


def status():
    state = load_state()
    if not is_running(state):
        print('uSOPp demo is stopped.')
        return
    data = health(state['port'])
    print(f"Running: PID {state['pid']}, port {state['port']}, version {state['version']}.")
    print('Health: ready' if data else 'Health: not responding; inspect the log.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'start', 'stop', 'restart', 'status', 'logs'])
    parser.add_argument('--host', default=os.getenv('USOPP_API_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.getenv('USOPP_API_PORT', '8200')))
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('This launcher is for Ubuntu/Linux. Use the existing Windows launcher on Windows.')
    if not 8200 <= args.port <= 8500:
        parser.error('Port must be between 8200 and 8500.')
    import fcntl
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with STATE.with_suffix('.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.action == 'install':
                install()
            elif args.action == 'start':
                start(args.host, args.port)
            elif args.action == 'stop':
                stop()
            elif args.action == 'restart':
                stop()
                start(args.host, args.port)
            elif args.action == 'status':
                status()
            else:
                print('\n'.join(LOG.read_text(encoding='utf-8', errors='replace').splitlines()[-80:])
                      if LOG.is_file() else 'No demo log yet.')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'uSOPp: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
