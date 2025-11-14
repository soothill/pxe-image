"""Configuration loading and validation helpers."""
# Copyright (c) 2024 Darren Soothill

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping


class ConfigError(RuntimeError):
    """Raised when a configuration file cannot be processed."""


JsonMapping = MutableMapping[str, object]


def load_config(path: Path) -> JsonMapping:
    """Load the JSON configuration file located at *path*."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file '{path}' does not exist") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Failed to parse configuration '{path}': {exc}") from exc

    if not isinstance(data, MutableMapping):
        raise ConfigError(f"Configuration '{path}' must contain a JSON object at the top level")

    return data


def _normalise_packages(packages: Iterable[object]) -> List[str]:
    normalised: List[str] = []
    for pkg in packages:
        if isinstance(pkg, str):
            stripped = pkg.strip()
            if stripped:
                normalised.append(stripped)
    return normalised


def validate_packages(packages: Iterable[object]) -> List[str]:
    """Validate that each package listed exists via ``zypper info``."""
    pkg_list = _normalise_packages(packages)
    if not pkg_list:
        return []

    if shutil.which("zypper") is None:
        raise ConfigError("zypper not found on the host; package validation cannot continue")

    missing: List[str] = []
    for pkg in pkg_list:
        print(f"Validating package '{pkg}' with zypper info")
        result = subprocess.run(
            ["zypper", "--non-interactive", "info", pkg],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(pkg)
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)

    if missing:
        raise ConfigError(
            "The following packages could not be validated: " + ", ".join(sorted(missing))
        )

    return pkg_list


def merge_overlay_config(base: JsonMapping, network: Mapping[str, object]) -> JsonMapping:
    """Return a copy of *base* that includes the network block."""
    merged = dict(base)
    merged["network"] = dict(network)
    return merged


__all__ = ["ConfigError", "JsonMapping", "load_config", "validate_packages", "merge_overlay_config"]
