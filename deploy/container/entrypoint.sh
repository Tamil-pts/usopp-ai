#!/bin/sh
set -eu
umask 077
python /opt/usopp/container_bootstrap.pyc
set -- python -m uvicorn virtual_plc.server:create_app --factory --host 0.0.0.0 --port 8200 --workers 1 --timeout-graceful-shutdown 900
# Trust forwarded HTTPS/client headers only when the operator selects the proxy.
if [ -n "${USOPP_FORWARDED_ALLOW_IPS:-}" ]; then
    set -- "$@" --proxy-headers --forwarded-allow-ips "$USOPP_FORWARDED_ALLOW_IPS"
else
    set -- "$@" --no-proxy-headers
fi
exec "$@"
