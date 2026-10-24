#!/usr/bin/env bash
set -eu
studio_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3 was not found. See README.md > Linux prerequisites.' >&2
    exit 1
fi
if python3 "$studio_dir/bootstrap.py" "$@"; then
    exit 0
else
    status=$?
    if [[ -t 0 ]]; then
        read -r -p 'Startup failed. Read the error above and README.md. Press Enter to close.' || true
    fi
    exit "$status"
fi
