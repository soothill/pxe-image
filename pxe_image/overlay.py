"""Helpers for rendering the overlay filesystem used during the build."""
# Copyright (c) 2024 Darren Soothill

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Mapping

from .config import JsonMapping, merge_overlay_config
from .network import NetworkInfo, render_ifcfg


def prepare_overlay_root(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_overlay(overlay_root: Path, config: JsonMapping, network: Mapping[str, object]) -> None:
    opt_dir = overlay_root / "opt/custom"
    opt_dir.mkdir(parents=True, exist_ok=True)
    rendered_config = merge_overlay_config(config, network)
    (opt_dir / "config.json").write_text(json.dumps(rendered_config, indent=2), encoding="utf-8")

    network_dir = overlay_root / "etc/sysconfig/network"
    network_dir.mkdir(parents=True, exist_ok=True)
    iface_path = network_dir / f"ifcfg-{network['interface']}"
    iface_path.write_text(render_ifcfg(network), encoding="utf-8")

    custom_dir = overlay_root / "etc/custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    (custom_dir / "network.json").write_text(json.dumps(network, indent=2), encoding="utf-8")


__all__ = ["prepare_overlay_root", "write_overlay"]
