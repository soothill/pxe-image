"""Network discovery utilities."""
# Copyright (c) 2025 Darren Soothill
# Copyright (c) 2024 Darren Soothill

import json
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from typing import Dict, Iterable, List, Optional


class NetworkError(RuntimeError):
    """Raised when host network information cannot be gathered."""


NetworkInfo = Dict[str, object]


def _load_default_routes(strict: bool) -> List[Dict[str, object]]:
def detect_default_interface() -> str:
    try:
        result = subprocess.run(
            ["ip", "-json", "route", "show", "default"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
    except FileNotFoundError as exc:
        if strict:
            raise NetworkError(f"Unable to query default routes: {exc}") from exc
        return []

    if result.returncode != 0:
        if strict:
            message = result.stderr.strip() or f"exit status {result.returncode}"
            raise NetworkError(f"Unable to query default routes: {message}")
        return []

    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        if strict:
            raise NetworkError(f"Failed to parse default route information: {exc}") from exc
        return []

    if not isinstance(data, list):
        if strict:
            raise NetworkError("Unexpected format received from default route query")
        return []

    filtered: List[Dict[str, object]] = []
    for entry in data:
        if isinstance(entry, dict):
            filtered.append(entry)
    return filtered


def _extract_route_field(routes: Iterable[Dict[str, object]], field: str) -> Optional[str]:
    for entry in routes:
        value = entry.get(field)
        if value:
            return str(value)
    return None


def detect_default_interface_and_gateway() -> Tuple[str, Optional[str]]:
    routes = _load_default_routes(strict=True)
    interface = _extract_route_field(routes, "dev")
    if not interface:
        raise NetworkError("No default network interface detected")
    gateway = _extract_route_field(routes, "gateway")
    return interface, gateway


def detect_default_interface() -> str:
    interface, _ = detect_default_interface_and_gateway()
    return interface


def detect_default_gateway() -> Optional[str]:
    routes = _load_default_routes(strict=False)
    return _extract_route_field(routes, "gateway")


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


def _build_interface_config(interface: str, gateway: Optional[str]) -> NetworkInfo:
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
        "gateway": gateway,
        "gateway": detect_default_gateway(),
        "dns": read_resolv_conf(),
        "mtu": data.get("mtu"),
    }


def gather_interface_config(interface: str) -> NetworkInfo:
    return _build_interface_config(interface, detect_default_gateway())


def gather_interface_config_with_gateway(interface: str, gateway: Optional[str]) -> NetworkInfo:
    return _build_interface_config(interface, gateway)


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
    "detect_default_interface_and_gateway",
    "detect_default_interface",
    "detect_default_gateway",
    "read_resolv_conf",
    "gather_interface_config",
    "gather_interface_config_with_gateway",
    "render_ifcfg",
]
