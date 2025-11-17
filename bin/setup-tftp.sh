
#!/usr/bin/env bash
# Set up a KIWI full root directory for PXE boot (NFS root) using dnsmasq + TFTP.
# Assumptions:
#   - dnsmasq is already your main DHCP server.
#   - KIWI produced a full root filesystem directory (image-root), not squashfs.

set -euo pipefail

### --- CONFIGURABLE VARIABLES -------------------------------------------------

# Path to KIWI-generated full root filesystem (image-root)
KIWI_IMAGE_ROOT="${KIWI_IMAGE_ROOT:-/home/darren/pxe-image/build/artifacts/build/image-root}"

# PXE/NFS server IP address (seen by PXE clients)
SERVER_IP="${SERVER_IP:-10.10.115.200}"

# TFTP root directory
TFTP_ROOT="${TFTP_ROOT:-/srv/tftpboot}"

# NFS export directory where the root filesystem will live
NFS_ROOT_DIR="${NFS_ROOT_DIR:-/srv/pxe/rootfs}"

### ---------------------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0)"
  exit 1
fi

echo "==> KIWI image-root: $KIWI_IMAGE_ROOT"
echo "==> TFTP root:       $TFTP_ROOT"
echo "==> NFS root:        $NFS_ROOT_DIR"
echo "==> Server IP:       $SERVER_IP"
echo "==> dnsmasq is already DHCP server; only PXE/TFTP options will be added."

# Sanity checks
if [[ ! -d "$KIWI_IMAGE_ROOT" ]]; then
  echo "ERROR: KIWI_IMAGE_ROOT directory not found: $KIWI_IMAGE_ROOT"
  exit 1
fi

if [[ ! -d "$KIWI_IMAGE_ROOT/boot" ]]; then
  echo "ERROR: $KIWI_IMAGE_ROOT/boot not found (no kernel/initrd?)."
  exit 1
fi

# Try to find kernel and initrd inside the image-root/boot
shopt -s nullglob
KERNEL_SRC=$(ls "$KIWI_IMAGE_ROOT"/boot/vmlinuz* 2>/dev/null | head -n1 || true)

INITRD_SRC=""
for candidate in "$KIWI_IMAGE_ROOT"/boot/initrd*; do
  # Glob may not match anything; skip the literal pattern in that case.
  [[ -e "$candidate" ]] || continue

  resolved=$(readlink -f "$candidate" || true)
  if [[ -n "$resolved" && -e "$resolved" ]]; then
    INITRD_SRC="$resolved"
    break
  else
    echo "WARNING: Skipping initrd candidate $candidate (broken link or missing target)" >&2
  fi
done
shopt -u nullglob

if [[ -z "$KERNEL_SRC" || -z "$INITRD_SRC" ]]; then
  echo "ERROR: Could not find vmlinuz* and initrd* in $KIWI_IMAGE_ROOT/boot"
  exit 1
fi

echo "==> Using kernel: $KERNEL_SRC"
echo "==> Using initrd: $INITRD_SRC"

echo "==> Installing required packages (nfs-kernel-server, syslinux, shim, grub2-x86_64-efi, dnsmasq if missing)..."
if command -v zypper >/dev/null 2>&1; then
  zypper -n in nfs-kernel-server syslinux shim grub2-x86_64-efi dnsmasq || true
else
  echo "WARNING: This script assumes openSUSE with zypper; adjust package installs if needed."
fi

echo "==> Preparing NFS root directory..."
mkdir -p "$NFS_ROOT_DIR"

echo "==> Copying KIWI root filesystem to NFS root (this may take a while)..."
# You could also use rsync or a bind-mount instead of a full copy:
#   mount --bind "$KIWI_IMAGE_ROOT" "$NFS_ROOT_DIR"
cp -a "$KIWI_IMAGE_ROOT/." "$NFS_ROOT_DIR/"

echo "==> Configuring NFS export in /etc/exports..."
if ! grep -q "^$NFS_ROOT_DIR " /etc/exports 2>/dev/null; then
  echo "$NFS_ROOT_DIR *(rw,no_root_squash,async,no_subtree_check)" >> /etc/exports
else
  echo "    NFS root already present in /etc/exports; leaving as-is."
fi

echo "==> Reloading NFS exports and enabling NFS server..."
exportfs -ra
systemctl enable nfs-server.service || true
systemctl restart nfs-server.service

echo "==> Creating TFTP directory tree..."
mkdir -p "$TFTP_ROOT/bios/pxelinux.cfg" "$TFTP_ROOT/uefi"

echo "==> Copying kernel and initrd to TFTP directories..."
cp "$KERNEL_SRC" "$TFTP_ROOT/bios/vmlinuz"
cp "$INITRD_SRC" "$TFTP_ROOT/bios/initrd"
cp "$KERNEL_SRC" "$TFTP_ROOT/uefi/vmlinuz"
cp "$INITRD_SRC" "$TFTP_ROOT/uefi/initrd"

echo "==> Installing PXELINUX (BIOS) bootloader files..."
SYSLINUX_DIR="/usr/share/syslinux"
if [[ -d "$SYSLINUX_DIR" ]]; then
  cp "$SYSLINUX_DIR/pxelinux.0"   "$TFTP_ROOT/bios/" || true
  cp "$SYSLINUX_DIR/ldlinux.c32"  "$TFTP_ROOT/bios/" || true
  cp "$SYSLINUX_DIR/libcom32.c32" "$TFTP_ROOT/bios/" || true
  cp "$SYSLINUX_DIR/libutil.c32"  "$TFTP_ROOT/bios/" || true
else
  echo "WARNING: $SYSLINUX_DIR not found; install syslinux for BIOS PXE."
fi

echo "==> Installing UEFI shim and GRUB..."
if [[ -f /usr/share/efi/x86_64/shim.efi ]]; then
  cp /usr/share/efi/x86_64/shim.efi "$TFTP_ROOT/uefi/shimx64.efi"
elif [[ -f /usr/share/efi/x86_64/shim-opensuse.efi ]]; then
  cp /usr/share/efi/x86_64/shim-opensuse.efi "$TFTP_ROOT/uefi/shimx64.efi"
else
  echo "WARNING: shim.efi not found; UEFI Secure Boot chain may not work."
fi

if [[ -f /usr/share/efi/x86_64/grub.efi ]]; then
  cp /usr/share/efi/x86_64/grub.efi "$TFTP_ROOT/uefi/grubx64.efi"
else
  echo "ERROR: grub.efi not found; install grub2-x86_64-efi"
  exit 1
fi

echo "==> Writing BIOS PXELINUX config..."
cat > "$TFTP_ROOT/bios/pxelinux.cfg/default" <<EOF
DEFAULT kiwi
PROMPT 0
TIMEOUT 5

LABEL kiwi
    KERNEL vmlinuz
    INITRD initrd
    APPEND root=/dev/nfs rw nfsroot=$SERVER_IP:$NFS_ROOT_DIR ip=dhcp
EOF

echo "==> Writing UEFI GRUB config..."
cat > "$TFTP_ROOT/uefi/grub.cfg" <<EOF
set timeout=5
set default=0

menuentry "KIWI NFS-root PXE Boot" {
    linuxefi /uefi/vmlinuz root=/dev/nfs rw nfsroot=$SERVER_IP:$NFS_ROOT_DIR ip=dhcp
    initrdefi /uefi/initrd
}
EOF

echo "==> Creating dnsmasq PXE/TFTP config snippet (no dhcp-range)..."
mkdir -p /etc/dnsmasq.d
DNSMASQ_PXE_CONF="/etc/dnsmasq.d/pxe.conf"

cat > "$DNSMASQ_PXE_CONF" <<EOF
# PXE / TFTP settings for dnsmasq acting as the main DHCP server.
# Existing dhcp-range lines elsewhere remain in effect.

enable-tftp
tftp-root=$TFTP_ROOT

# Match UEFI x86_64 clients (7 = EFI, 9 = EFI BC)
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9

# UEFI clients get shimx64.efi
dhcp-boot=tag:efi64,uefi/shimx64.efi

# Legacy BIOS clients get pxelinux.0
dhcp-boot=tag:!efi64,bios/pxelinux.0
EOF

echo "==> Restarting dnsmasq.service..."
systemctl restart dnsmasq.service

echo "==> Basic NFS export check..."
exportfs -v | grep "$NFS_ROOT_DIR" || echo "WARNING: NFS root not visible in exportfs -v."

echo "==> Basic TFTP test (if tftp client installed)..."
if command -v tftp >/dev/null 2>&1; then
  if echo -e "get bios/pxelinux.0\nquit" | tftp 127.0.0.1 >/dev/null 2>&1; then
    echo "TFTP test: OK (bios/pxelinux.0 downloadable from localhost)"
  else
    echo "WARNING: TFTP test failed from localhost. Check firewall or dnsmasq interface binding."
  fi
else
  echo "NOTE: tftp client not installed; skipping TFTP test."
fi

echo
echo "==================================================================="
echo " Done!"
echo
echo " NFS root:  $NFS_ROOT_DIR  (exported as $SERVER_IP:$NFS_ROOT_DIR)"
echo " BIOS PXE:  $TFTP_ROOT/bios (pxelinux.0, vmlinuz, initrd)"
echo " UEFI PXE:  $TFTP_ROOT/uefi (shimx64.efi, grubx64.efi, vmlinuz, initrd)"
echo
echo " dnsmasq is still your main DHCP server."
echo " PXE/TFTP options were added in: $DNSMASQ_PXE_CONF"
echo "==================================================================="


