"""Network discovery utilities."""
# Copyright (c) 2024 Darren Soothill

import json
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional


class NetworkError(RuntimeError):
    """Raised when host network information cannot be gathered."""


NetworkInfo = Dict[str, object]


def detect_default_interface() -> str:
    try:
        result = subprocess.run(
            ["ip", "-json", "route", "show", "default"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise NetworkError(f"Unable to detect default interface: {exc}") from exc

    routes = json.loads(result.stdout or "[]")
    for entry in routes:
        dev = entry.get("dev")
        if dev:
            return str(dev)
    raise NetworkError("No default network interface detected")


def detect_default_gateway() -> Optional[str]:
    try:
        result = subprocess.run(
            ["ip", "-json", "route", "show", "default"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    routes = json.loads(result.stdout or "[]")
    for entry in routes:
        gateway = entry.get("gateway")
        if gateway:
            return str(gateway)
    return None


def read_resolv_conf(path: Path = Path("/etc/resolv.conf")) -> List[str]:
    if not path.exists():
        return []

    servers: List[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "nameserver":
            servers.append(parts[1])
    return servers


def gather_interface_config(interface: str) -> NetworkInfo:
    try:
        result = subprocess.run(
            ["ip", "-json", "addr", "show", "dev", interface],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise NetworkError(f"Unable to inspect interface {interface}: {exc}") from exc

    addr_info = json.loads(result.stdout or "[]")
    if not addr_info:
        raise NetworkError(f"Interface {interface} has no address information")

    data = addr_info[0]
    inet_entry = next((entry for entry in data.get("addr_info", []) if entry.get("family") == "inet"), None)
    if not inet_entry:
        raise NetworkError(f"Interface {interface} has no IPv4 configuration")

    address = inet_entry.get("local")
    prefixlen = inet_entry.get("prefixlen")
    if not address or prefixlen is None:
        raise NetworkError(f"Incomplete IPv4 configuration detected for interface {interface}")

    return {
        "interface": interface,
        "address": address,
        "prefixlen": prefixlen,
        "gateway": detect_default_gateway(),
        "dns": read_resolv_conf(),
        "mtu": data.get("mtu"),
    }


def render_ifcfg(network: NetworkInfo) -> str:
    dns = " ".join(str(value) for value in network.get("dns", []) if value)
    gateway = network.get("gateway")
    mtu = network.get("mtu")

    lines = [
        f"DEVICE='{network['interface']}'",
        "BOOTPROTO='static'",
        "STARTMODE='auto'",
        "ONBOOT='yes'",
        "DEFROUTE='yes'",
        "PEERDNS='no'",
        f"IPADDR='{network['address']}/{network['prefixlen']}'",
    ]
    if gateway:
        lines.append(f"GATEWAY='{gateway}'")
    if dns:
        lines.append(f"DNS='{dns}'")
    if mtu:
        lines.append(f"MTU='{mtu}'")
    return "\n".join(lines) + "\n"


__all__ = [
    "NetworkError",
    "NetworkInfo",
    "detect_default_interface",
    "detect_default_gateway",
    "read_resolv_conf",
    "gather_interface_config",
    "render_ifcfg",
]
