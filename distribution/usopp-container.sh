#!/usr/bin/env bash
set -euo pipefail
action=${1:-status}
image=${2:-}
archive=${3:-}
config_root=${USOPP_CONTAINER_CONFIG:-"$HOME/.config/usopp-container"}
if [[ "$action" == update && ! -f "$config_root/image" ]]; then echo 'Run install before updating a server.' >&2; exit 1; fi
if [[ "$action" == install && -f "$config_root/image" && "$image" != "$(cat "$config_root/image")" ]]; then echo 'Use update to change an installed release with a full backup.' >&2; exit 1; fi
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ "$action" == update-release ]]; then
  release_input=${2:-}
  release_version=${release_input#v}
  [[ "$release_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || { echo 'Supply a published version such as 4.65.13 or v4.65.13.' >&2; exit 1; }
  [[ -f "$config_root/image" ]] || { echo 'Run install before updating a server.' >&2; exit 1; }
  command -v docker >/dev/null || { echo 'Install Docker Engine and its Compose plugin first; see README.md.' >&2; exit 1; }
  [[ $(docker info --format '{{.OSType}}') == linux ]] || { echo 'Start Docker in Linux containers mode.' >&2; exit 1; }
  for tool in curl sha256sum unzip; do command -v "$tool" >/dev/null || { echo "Install $tool before downloading a release." >&2; exit 1; }; done
  download_root=$(mktemp -d "${TMPDIR:-/tmp}/usopp-release-${release_version}.XXXXXX")
  trap 'rm -rf -- "$download_root"' EXIT
  release_base="https://github.com/Tamil-pts/usopp-distribution/releases/download/v${release_version}"
  launcher_zip="uSOPp_AI_${release_version}_Container_Launchers.zip"
  image_archive="uSOPp_AI_${release_version}_Container_linux_amd64.tar.gz"
  assets=("$launcher_zip" "$launcher_zip.sha256" "$image_archive" "$image_archive.sha256")
  for asset in "${assets[@]}"; do
    echo "Downloading $asset"
    curl --fail --location --retry 3 --retry-delay 2 --silent --show-error "$release_base/$asset" --output "$download_root/$asset"
  done
  for checksum in "$launcher_zip.sha256" "$image_archive.sha256"; do
    sed -i 's/\r$//' "$download_root/$checksum"
    (cd "$download_root" && sha256sum --check "$checksum")
  done
  mkdir "$download_root/launchers"
  unzip -q "$download_root/$launcher_zip" -d "$download_root/launchers"
  [[ -f "$download_root/launchers/usopp-container.sh" && -f "$download_root/launchers/compose.yaml" ]] || { echo 'The release launcher ZIP is missing required files.' >&2; exit 1; }
  echo "Checksums verified. Updating to usopp-ai:$release_version (the installer backs up the existing data volume)."
  bash "$download_root/launchers/usopp-container.sh" update "usopp-ai:$release_version" "$download_root/$image_archive"
  exit $?
fi
command -v docker >/dev/null || { echo 'Install Docker Engine and its Compose plugin first; see README.md.' >&2; exit 1; }
[[ $(docker info --format '{{.OSType}}') == linux ]] || { echo 'Start Docker in Linux containers mode.' >&2; exit 1; }
case "$action" in
  install|update)
    [[ "$image" =~ ^[a-z0-9][a-z0-9._/:@-]+$ ]] || { echo 'Supply the release image name, e.g. usopp-ai:4.65.7.' >&2; exit 1; }
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
    bind_address=${USOPP_BIND_ADDRESS:-}
    if [[ -z "$bind_address" && -f "$config_root/bind-address" ]]; then bind_address=$(cat "$config_root/bind-address"); fi
    bind_address=${bind_address:-127.0.0.1}
    [[ "$bind_address" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Use an IPv4 server bind address.' >&2; exit 1; }
    IFS=. read -r -a octets <<< "$bind_address"
    for octet in "${octets[@]}"; do [[ ${#octet} -le 3 && $((10#$octet)) -le 255 ]] || { echo 'Invalid IPv4 address.' >&2; exit 1; }; done
    data_volume=usopp-container_data
    if [[ -f "$config_root/data-volume" ]]; then data_volume=$(cat "$config_root/data-volume"); fi
    cp -- "$script_root/compose.yaml" "$config_root/compose.yaml"
    ;;
  start|stop|status|logs|backup|restore) ;;
  *) echo 'Use install, start, stop, status, logs, update, update-release, backup or restore.' >&2; exit 1 ;;
esac
if [[ "$action" == install || "$action" == update ]]; then
  export USOPP_IMAGE="$image" USOPP_PORT="$port" USOPP_BIND_ADDRESS="$bind_address" USOPP_DATA_VOLUME="$data_volume"
else
  [[ -f "$config_root/image" ]] || { echo 'Run install first.' >&2; exit 1; }
  export USOPP_IMAGE=$(cat "$config_root/image")
  export USOPP_PORT=$(cat "$config_root/port")
  export USOPP_BIND_ADDRESS=127.0.0.1 USOPP_DATA_VOLUME=usopp-container_data
  if [[ -f "$config_root/bind-address" ]]; then export USOPP_BIND_ADDRESS=$(cat "$config_root/bind-address"); fi
  if [[ -f "$config_root/data-volume" ]]; then export USOPP_DATA_VOLUME=$(cat "$config_root/data-volume"); fi
fi
export USOPP_ADMIN_PASSWORD_FILE="$config_root/admin-password.txt"
compose=(docker compose --project-name usopp-container --file "$config_root/compose.yaml")
assert_stopped() {
  [[ -z $(docker ps --filter "volume=$USOPP_DATA_VOLUME" --format '{{.ID}}') ]] || { echo 'Finish active tests and run stop before backup/restore.' >&2; exit 1; }
}
backup_server() {
  assert_stopped
  backup_root=${USOPP_BACKUP_DIRECTORY:-"$config_root/backups"}
  mkdir -p -- "$backup_root"
  chmod 700 -- "$backup_root"
  backup_root=$(cd -- "$backup_root" && pwd)
  [[ "$backup_root" != *,* ]] || { echo 'Use a backup path without commas.' >&2; exit 1; }
  backup_name="usopp-server-$(date -u +%Y%m%d-%H%M%S)-$RANDOM.tar.gz"
  docker run --rm --network none --user 0 --entrypoint python --env USOPP_DATA_ROOT=/data --mount "type=volume,source=$USOPP_DATA_VOLUME,target=/data,readonly" --mount "type=bind,source=$backup_root,target=/backup" "$USOPP_IMAGE" /opt/usopp/container_maintenance.pyc backup "/backup/$backup_name" --owner "$(id -u)"
  echo "Backup and checksum: $backup_root/$backup_name"
}
if [[ "$action" == install ]]; then docker volume create "$USOPP_DATA_VOLUME" >/dev/null
else docker volume inspect "$USOPP_DATA_VOLUME" >/dev/null || { echo 'The data volume is missing. Restore a backup; do not start with an empty replacement.' >&2; exit 1; }; fi
if [[ "$action" == update ]]; then "${compose[@]}" stop; backup_server; fi
if [[ "$action" == install || "$action" == update ]]; then
  printf '%s' "$USOPP_IMAGE" > "$config_root/image"
  printf '%s' "$USOPP_PORT" > "$config_root/port"
  printf '%s' "$USOPP_BIND_ADDRESS" > "$config_root/bind-address"
  printf '%s' "$USOPP_DATA_VOLUME" > "$config_root/data-volume"
fi
case "$action" in
  install|start|update) "${compose[@]}" up -d --pull never; echo "Open http://<server-LAN-IP>:$USOPP_PORT (bound to $USOPP_BIND_ADDRESS); sign in as Admin with your chosen password." ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail 100 ;;
  backup) backup_server ;;
  restore)
    assert_stopped
    backup_path=${2:?Supply the backup archive path}
    new_volume=${3:?Supply a new empty volume name}
    [[ "$new_volume" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]+$ && "$new_volume" != "$USOPP_DATA_VOLUME" ]] || { echo 'Use a new volume name; existing data is retained.' >&2; exit 1; }
    backup_root=$(cd -- "$(dirname -- "$backup_path")" && pwd)
    [[ "$backup_root" != *,* ]] || { echo 'Use a backup path without commas.' >&2; exit 1; }
    docker volume create "$new_volume" >/dev/null
    docker run --rm --network none --user 0 --entrypoint python --env USOPP_DATA_ROOT=/data --mount "type=volume,source=$new_volume,target=/data" --mount "type=bind,source=$backup_root,target=/backup,readonly" "$USOPP_IMAGE" /opt/usopp/container_maintenance.pyc restore "/backup/$(basename -- "$backup_path")"
    printf '%s' "$new_volume" > "$config_root/data-volume"
    echo 'Restore complete. Run start; the original data volume is retained separately.'
    ;;
esac
