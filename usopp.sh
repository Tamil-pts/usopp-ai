#!/usr/bin/env bash
set -euo pipefail
usopp_demo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$usopp_demo_root/scripts/ubuntu_demo.py" "$@"
