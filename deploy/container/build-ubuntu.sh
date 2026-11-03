#!/usr/bin/env bash
set -euo pipefail
action=${1:-build}
[[ "$action" == build || "$action" == plan ]] || { echo 'Use build or plan, followed by an optional image name.' >&2; exit 1; }
[[ $# -le 2 ]] || { echo 'Too many arguments.' >&2; exit 1; }
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_root=${USOPP_BUILD_ROOT:-"$script_root/../.."}
source_root=$(cd -- "$source_root" && pwd)
[[ -f "$source_root/package.json" && -f "$source_root/Dockerfile" ]] || { echo 'Choose the extracted private source bundle or current source checkout.' >&2; exit 1; }
version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$source_root/package.json" | head -n 1)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || { echo 'Invalid application version in package.json.' >&2; exit 1; }
image=${2:-"usopp-ai:$version"}
[[ "$image" =~ ^[a-z0-9][a-z0-9._/:@-]+$ ]] || { echo 'Supply a valid lowercase image name.' >&2; exit 1; }
args=(build --pull --platform linux/amd64 --target ubuntu --file "$source_root/Dockerfile" --build-arg "APP_VERSION=$version" --tag "$image")
if command -v git >/dev/null; then
    commit=$(git -C "$source_root" rev-parse HEAD 2>/dev/null || true)
    if [[ "$commit" =~ ^[0-9a-f]{40,64}$ ]]; then args+=(--build-arg "SOURCE_COMMIT=$commit"); fi
fi
args+=("$source_root")
if [[ "$action" == plan ]]; then printf 'docker'; printf ' %q' "${args[@]}"; printf '\n'; exit 0; fi
command -v docker >/dev/null || { echo 'Install Docker Engine and start it before building.' >&2; exit 1; }
[[ $(docker info --format '{{.OSType}}') == linux ]] || { echo 'Docker Engine must be available in Linux containers mode.' >&2; exit 1; }
docker "${args[@]}"
echo "Built $image for Docker Engine on Ubuntu. Install with distribution/usopp-container.sh."
