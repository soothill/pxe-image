#!/usr/bin/env bash
set -euo pipefail

# create-proxmox-vm.sh
# Helper script to create and delete PXE-bootable VMs on a Proxmox host via SSH.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_DIR="${REPO_ROOT}/build"
LAST_VMID_FILE="${STATE_DIR}/proxmox_last_vmid"

PROXMOX_HOST="${PROXMOX_HOST:-root@proxmox.local}"
PROXMOX_NODE="${PROXMOX_NODE:-pxe_test}"
PROXMOX_SSH_OPTS="${PROXMOX_SSH_OPTS:-}"

DEFAULT_BRIDGE="${DEFAULT_BRIDGE:-vmbr10g115}"
DEFAULT_STORAGE="${DEFAULT_STORAGE:-RaidZ}"
DEFAULT_CORES="${DEFAULT_CORES:-4}"
DEFAULT_MEMORY_MB="${DEFAULT_MEMORY_MB:-4096}"
DEFAULT_DISK_GB="${DEFAULT_DISK_GB:-20}"
DEFAULT_SOCKETS="${DEFAULT_SOCKETS:-1}"
DEFAULT_OSTYPE="${DEFAULT_OSTYPE:-l26}"
DEFAULT_VM_NAME="${DEFAULT_VM_NAME:-pxe-test-vm}"
DEFAULT_VMID="${DEFAULT_VMID:-350}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") create [options]
  $(basename "$0") delete [options]

Environment variables:
  PROXMOX_HOST       SSH target for Proxmox (default: ${PROXMOX_HOST})
  PROXMOX_NODE       Proxmox node name (default: ${PROXMOX_NODE})
  PROXMOX_SSH_OPTS   Extra ssh options (optional)
  DEFAULT_BRIDGE     Default bridge name (default: ${DEFAULT_BRIDGE})
  DEFAULT_STORAGE    Default storage ID (default: ${DEFAULT_STORAGE})

Subcommands:
  create   Create a new PXE-bootable VM
  delete   Delete an existing VM

Create options:
  --name NAME          VM name (required)
  --vmid ID            VMID (required, must not already exist)
  --cores N            Number of CPU cores (default: ${DEFAULT_CORES})
  --memory MB          RAM in MB (default: ${DEFAULT_MEMORY_MB})
  --disk-gb GB         Disk size in GB (default: ${DEFAULT_DISK_GB})
  --storage ID         Storage ID (default: ${DEFAULT_STORAGE})
  --bridge BR          Network bridge (default: ${DEFAULT_BRIDGE})
  --vlan-tag TAG       VLAN tag for NIC (optional)
  --node NODE          Proxmox node name (default: PROXMOX_NODE env)
  --start              Start the VM after creation

Delete options:
  --vmid ID            VMID to delete (optional; if omitted, uses last created VMID)
  --node NODE          Proxmox node name (default: PROXMOX_NODE env)
  --yes                Do not prompt for confirmation

Notes:
  - VM creation will fail if the requested VMID is already in use; the script will
    print a message suggesting you use the Makefile delete target to clean up.
  - The last successfully created VMID is stored in:
      ${LAST_VMID_FILE}
    and used by delete if no --vmid is supplied.
EOF
}

ssh_pve() {
  # shellcheck disable=SC2086
  ssh ${PROXMOX_SSH_OPTS} "${PROXMOX_HOST}" "$@"
}

ensure_state_dir() {
  mkdir -p "${STATE_DIR}"
}

save_last_vmid() {
  local vmid="$1"
  ensure_state_dir
  echo "${vmid}" > "${LAST_VMID_FILE}"
}

load_last_vmid() {
  if [[ -f "${LAST_VMID_FILE}" ]]; then
    cat "${LAST_VMID_FILE}"
  else
    return 1
  fi
}

create_vm() {
  local name="${DEFAULT_VM_NAME}"
  local vmid="${DEFAULT_VMID}"
  local cores="${DEFAULT_CORES}"
  local memory="${DEFAULT_MEMORY_MB}"
  local disk_gb="${DEFAULT_DISK_GB}"
  local storage="${DEFAULT_STORAGE}"
  local bridge="${DEFAULT_BRIDGE}"
  local vlan_tag=""
  local node="${PROXMOX_NODE}"
  local start_after=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --name)
        name="$2"; shift 2;;
      --vmid)
        vmid="$2"; shift 2;;
      --cores)
        cores="$2"; shift 2;;
      --memory)
        memory="$2"; shift 2;;
      --disk-gb)
        disk_gb="$2"; shift 2;;
      --storage)
        storage="$2"; shift 2;;
      --bridge)
        bridge="$2"; shift 2;;
      --vlan-tag)
        vlan_tag="$2"; shift 2;;
      --node)
        node="$2"; shift 2;;
      --start)
        start_after=true; shift 1;;
      -h|--help)
        usage; exit 0;;
      *)
        echo "Unknown option for create: $1" >&2
        usage
        exit 1;;
    esac
  done

  if [[ -z "${name}" ]]; then
    echo "Error: --name is required for create" >&2
    usage
    exit 1
  fi

  if [[ -z "${vmid}" ]]; then
    echo "Error: --vmid is required for create" >&2
    usage
    exit 1
  fi

  # Basic numeric validation
  if ! [[ "${cores}" =~ ^[0-9]+$ ]]; then
    echo "Error: --cores must be an integer" >&2
    exit 1
  fi
  if ! [[ "${memory}" =~ ^[0-9]+$ ]]; then
    echo "Error: --memory must be an integer (MB)" >&2
    exit 1
  fi
  if ! [[ "${disk_gb}" =~ ^[0-9]+$ ]]; then
    echo "Error: --disk-gb must be an integer (GB)" >&2
    exit 1
  fi

  echo "Connecting to Proxmox host ${PROXMOX_HOST} (node=${node})..." >&2

  # Check if VMID already exists
  if ssh_pve "qm status ${vmid} >/dev/null 2>&1"; then
    echo "Error: VMID ${vmid} already exists on node ${node}." >&2
    echo "If this VM is no longer needed, use the Make delete target, for example:" >&2
    echo "  make proxmox-vm-delete PROXMOX_VMID=${vmid}" >&2
    exit 1
  fi

  local vlan_part=""
  if [[ -n "${vlan_tag}" ]]; then
    vlan_part=",tag=${vlan_tag}"
  fi

  echo "Creating VM ${name} (VMID=${vmid}) with:" >&2
  echo "  cores=${cores}, memory=${memory}MB, disk=${disk_gb}G" >&2
  echo "  storage=${storage}, bridge=${bridge}${vlan_part}" >&2
  echo "  node=${node}" >&2

  ssh_pve "qm create ${vmid} \
    --name \"${name}\" \
    --memory ${memory} \
    --cores ${cores} \
    --sockets ${DEFAULT_SOCKETS} \
    --ostype ${DEFAULT_OSTYPE} \
    --net0 virtio,bridge=${bridge}${vlan_part}"

  # Add disk using virtio bus on the specified storage
  # For LVM-like storage (e.g. local-lvm), Proxmox expects size without a unit suffix (GB implied).
  ssh_pve "qm set ${vmid} --virtio0 ${storage}:${disk_gb}"

  # Set PXE (network) as first boot device (BIOS legacy PXE)
  ssh_pve "qm set ${vmid} --boot order=net0"

  # Configure serial console and use it as the primary display for easier logging
  # - serial0=socket allows attaching via 'qm terminal <vmid>' or over the Proxmox web UI
  # - vga=serial0 routes the VM console output to the serial device instead of a graphical VGA console
  ssh_pve "qm set ${vmid} --serial0 socket --vga serial0"

  if [[ "${start_after}" == true ]]; then
    echo "Starting VM ${vmid}..." >&2
    ssh_pve "qm start ${vmid}"
  fi

  save_last_vmid "${vmid}"

  echo "VM created successfully with VMID=${vmid}" >&2
  echo "${vmid}"
}

delete_vm() {
  local vmid=""
  local node="${PROXMOX_NODE}"
  local assume_yes=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --vmid)
        vmid="$2"; shift 2;;
      --node)
        node="$2"; shift 2;;
      --yes|-y)
        assume_yes=true; shift 1;;
      -h|--help)
        usage; exit 0;;
      *)
        echo "Unknown option for delete: $1" >&2
        usage
        exit 1;;
    esac
  done

  if [[ -z "${vmid}" ]]; then
    if vmid=$(load_last_vmid 2>/dev/null); then
      echo "Using last created VMID from ${LAST_VMID_FILE}: ${vmid}" >&2
    else
      echo "Error: --vmid not provided and no last VMID file found at ${LAST_VMID_FILE}" >&2
      exit 1
    fi
  fi

  if [[ "${assume_yes}" != true ]]; then
    read -r -p "Are you sure you want to delete VMID ${vmid} on node ${node}? [y/N] " reply
    case "${reply}" in
      [Yy]*) ;;
      *) echo "Aborted." >&2; exit 0;;
    esac
  fi

  echo "Deleting VMID ${vmid} on node ${node} via ${PROXMOX_HOST}..." >&2

  # Stop VM if running (ignore failures)
  ssh_pve "qm stop ${vmid}" || true

  # Destroy VM (ignore failures but print message)
  if ! ssh_pve "qm destroy ${vmid} --purge"; then
    echo "Warning: Failed to destroy VMID ${vmid}. It may not exist." >&2
  else
    echo "VMID ${vmid} destroyed." >&2
  fi
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  local cmd="$1"; shift || true

  case "${cmd}" in
    create)
      create_vm "$@";;
    delete)
      delete_vm "$@";;
    -h|--help|help)
      usage;;
    *)
      echo "Unknown subcommand: ${cmd}" >&2
      usage
      exit 1;;
  esac
}

main "$@"
