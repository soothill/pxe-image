#!/bin/bash
# Copyright (c) 2025 Darren Soothill
set -euo pipefail
LOG_FILE="/var/log/custom-firstboot.log"
exec >>"${LOG_FILE}" 2>&1

echo "[$(date --iso-8601=seconds)] Starting custom first boot provisioning"
CONFIG="/opt/custom/config.json"
if [[ ! -f "$CONFIG" ]]; then
    echo "[$(date --iso-8601=seconds)] No configuration at $CONFIG; skipping provisioning"
    exit 0
fi

/usr/bin/env python3 /usr/local/lib/custom/provision.py --config "$CONFIG" run

echo "[$(date --iso-8601=seconds)] Custom provisioning complete"
