#!/bin/sh
set -eu
umask 077
python /opt/usopp/container_bootstrap.pyc
exec python -m uvicorn backend.app:app --host 0.0.0.0 --port 8200 --workers 1 --no-proxy-headers --timeout-graceful-shutdown 900
