#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[custom-image] Running config.sh from ${SCRIPT_DIR}" >&2

# Ensure the first boot provisioning service is enabled
if [[ -f /usr/lib/systemd/system/custom-firstboot.service ]]; then
    mkdir -p /etc/systemd/system/multi-user.target.wants
    ln -sf /usr/lib/systemd/system/custom-firstboot.service \
        /etc/systemd/system/multi-user.target.wants/custom-firstboot.service
fi

CONFIG_JSON="/opt/custom/config.json"
if [[ -f "$CONFIG_JSON" ]]; then
    echo "[custom-image] Installing additional packages declared in ${CONFIG_JSON}" >&2
    mapfile -t EXTRA_PACKAGES < <(python3 - <<'PY'
import json
import sys
from pathlib import Path

config_path = Path("/opt/custom/config.json")
if not config_path.exists():
    sys.exit(0)

data = json.loads(config_path.read_text())
packages = data.get("packages", [])
for pkg in packages:
    if not isinstance(pkg, str):
        continue
    pkg = pkg.strip()
    if pkg:
        print(pkg)
PY
    )

    if (( ${#EXTRA_PACKAGES[@]} )); then
        zypper --non-interactive --gpg-auto-import-keys refresh
        zypper --non-interactive --no-gpg-checks install --auto-agree-with-licenses --no-recommends "${EXTRA_PACKAGES[@]}"
    fi
else
    echo "[custom-image] No configuration found at ${CONFIG_JSON}; skipping dynamic package installation" >&2
fi

