"""Configuration loading and validation helpers."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, List, Mapping, MutableMapping, Sequence


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
        raise ConfigError(
            f"Configuration '{path}' must contain a JSON object at the top level"
        )

    return data


def _normalise_packages(packages: Iterable[object]) -> List[str]:
    normalised: List[str] = []
    seen = set()
    for pkg in packages:
        if not isinstance(pkg, str):
            continue
        stripped = pkg.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalised.append(stripped)
    return normalised


def _chunked(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


_MISSING_RE = re.compile(r"Package '([^']+)' not found\.\s*", re.IGNORECASE)


def _extract_missing_packages(output: str, requested: Sequence[str]) -> List[str]:
    missing: List[str] = []
    if output:
        matches = _MISSING_RE.findall(output)
        if matches:
            missing.extend(matches)
    if not missing:
        missing.extend(requested)
    return missing


def validate_packages(packages: Iterable[object]) -> List[str]:
    """Validate that each package listed exists via ``zypper info``."""
    pkg_list = _normalise_packages(packages)
    if not pkg_list:
        return []

    if shutil.which("zypper") is None:
        raise ConfigError("zypper not found on the host; package validation cannot continue")

    missing: List[str] = []
    for chunk in _chunked(pkg_list, 25):
        command = ["zypper", "--non-interactive", "--no-refresh", "info", *chunk]
        print("Validating packages with:", " ".join(command))
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            chunk_missing = _extract_missing_packages(result.stdout + result.stderr, chunk)
            for pkg in chunk_missing:
                if pkg not in missing:
                    missing.append(pkg)

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


__all__ = [
    "ConfigError",
    "JsonMapping",
    "load_config",
    "validate_packages",
    "merge_overlay_config",
]
