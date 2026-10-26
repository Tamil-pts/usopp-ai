from __future__ import annotations

import os
import json
import runpy
import sys
from pathlib import Path


ENGINE_FLAG = "--usopp-engine"
ENGINE_FILES = {
    "packet_validation_report_uSOPp_v1.71_final.py",
    "rule_engine_v4_30.py",
    "compare.py",
}


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()


def run_embedded_engine() -> int:
    if len(sys.argv) < 3 or sys.argv[2] not in ENGINE_FILES:
        raise SystemExit("Unknown uSOPp engine request.")
    script = resource_root() / "python_engine" / sys.argv[2]
    if getattr(sys, "frozen", False):
        script = script.with_suffix('.pyc')
    if not script.is_file():
        raise SystemExit(f"Embedded engine is missing: {script.name}")
    sys.argv = [str(script), *sys.argv[3:]]
    sys.path.insert(0, str(script.parent))
    runpy.run_path(str(script), run_name="__main__")
    return 0


def hide_packaged_console() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()
        if window:
            ctypes.windll.user32.ShowWindow(window, 0)
    except Exception:
        pass


def server_main() -> int:
    hide_packaged_console()
    import threading
    import urllib.request
    import webbrowser

    import uvicorn

    port = int(os.getenv("USOPP_API_PORT", "8200"))
    if not 8200 <= port <= 8500:
        raise SystemExit('uSOPp application port must be between 8200 and 8500.')
    host = os.getenv("USOPP_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    url = f"http://127.0.0.1:{port}"
    package = json.loads((resource_root() / "package.json").read_text(encoding="utf-8"))
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as response:
            health = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and health.get("version") == package.get("version"):
                if health.get('capabilities',{}).get('accounts'):
                    if os.getenv('USOPP_NO_BROWSER') != '1':
                        webbrowser.open(url)
                    return 0
                raise SystemExit(f'The server already running on port {port} predates account support. Finish active jobs, stop the old uSOPp server, then launch this version again.')
    except Exception:
        pass

    from virtual_plc.server import create_app
    app = create_app()

    if os.getenv('USOPP_NO_BROWSER') != '1':
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, reload=False, access_log=False)
    return 0


if __name__ == "__main__":
    if len(sys.argv)>1 and sys.argv[1]=='--workhub-job':
        from backend.core.workhub_intelligence.job_runner import run
        run(*sys.argv[2:4])
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == ENGINE_FLAG:
        raise SystemExit(run_embedded_engine())
    raise SystemExit(server_main())
