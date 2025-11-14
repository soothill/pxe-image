#!/bin/bash
set -euo pipefail

smallest_disk=$(lsblk -ndo NAME,SIZE,TYPE | awk '$3 == "disk" {print $1 " " $2}' | sort -h -k2 | head -n1 | awk '{print $1}')
if [[ -z "$smallest_disk" ]]; then
    echo "No disk devices found" >&2
    exit 1
fi

echo "/dev/${smallest_disk}"
