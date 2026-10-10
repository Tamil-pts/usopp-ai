#!/usr/bin/env bash
set -euo pipefail
action=${1:-status}
image=${2:-}
archive=${3:-}
config_root=${USOPP_CONTAINER_CONFIG:-"$HOME/.config/usopp-container"}
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v docker >/dev/null || { echo 'Install Docker Engine and its Compose plugin first; see README.md.' >&2; exit 1; }
[[ $(docker info --format '{{.OSType}}') == linux ]] || { echo 'Start Docker in Linux containers mode.' >&2; exit 1; }
case "$action" in
  install|update)
    [[ "$image" =~ ^[a-z0-9][a-z0-9._/:@-]+$ ]] || { echo 'Supply the release image name, e.g. usopp-ai:4.65.6.' >&2; exit 1; }
    mkdir -p -- "$config_root"
    chmod 700 -- "$config_root"
    if [[ -n "$archive" ]]; then docker image load --input "$archive"; fi
    docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"
    if [[ ! -f "$config_root/admin-password.txt" ]]; then
      read -r -s -p 'Choose the initial Admin password (12 to 128 characters): ' password
      echo
      [[ ${#password} -ge 12 && ${#password} -le 128 ]] || { echo 'Invalid password length.' >&2; exit 1; }
      (umask 077; printf '%s' "$password" > "$config_root/admin-password.txt")
      unset password
      # Compose binds this file; the non-root container needs read access.
      # The host parent remains 0700, so other host users cannot open it.
      chmod 644 -- "$config_root/admin-password.txt"
    fi
    port=${USOPP_PORT:-}
    if [[ -z "$port" && -f "$config_root/port" ]]; then port=$(cat "$config_root/port"); fi
    port=${port:-8200}
    [[ "$port" =~ ^[0-9]+$ && "$port" -ge 8200 && "$port" -le 8500 ]] || { echo 'Use a port between 8200 and 8500.' >&2; exit 1; }
    printf '%s' "$image" > "$config_root/image"
    printf '%s' "$port" > "$config_root/port"
    cp -- "$script_root/compose.yaml" "$config_root/compose.yaml"
    ;;
  start|stop|status|logs) ;;
  *) echo 'Use install, start, stop, status, logs or update.' >&2; exit 1 ;;
esac
[[ -f "$config_root/image" ]] || { echo 'Run install first.' >&2; exit 1; }
export USOPP_IMAGE=$(cat "$config_root/image")
export USOPP_PORT=$(cat "$config_root/port")
export USOPP_ADMIN_PASSWORD_FILE="$config_root/admin-password.txt"
compose=(docker compose --project-name usopp-container --file "$config_root/compose.yaml")
case "$action" in
  install|start|update) "${compose[@]}" up -d --pull never; echo "Open http://127.0.0.1:$USOPP_PORT; sign in as Admin with your chosen password." ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail 100 ;;
esac
