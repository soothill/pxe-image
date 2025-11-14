#!/usr/bin/env python3
# Copyright (c) 2024 Darren Soothill
"""First boot provisioning helper for the custom KIWI image."""

import argparse
import json
import os
import pwd
import grp
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from socket import timeout
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_config(config_path: Path) -> Dict:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_group(name: str) -> None:
    try:
        grp.getgrnam(name)
    except KeyError:
        subprocess.run(["groupadd", "-f", name], check=True)


def set_user_password(username: str, password: str, hashed: bool = False) -> None:
    command = ["chpasswd"]
    if hashed:
        command.append("-e")
    try:
        subprocess.run(
            command,
            input="{}:{}\n".format(username, password),
            universal_newlines=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"Failed to set password for {username}: {exc}", file=sys.stderr)


def ensure_user(user: Dict) -> None:
    username = user["username"]
    gecos = user.get("gecos", username)
    shell = user.get("shell", "/bin/bash")
    home = user.get("home")
    create_home_args: List[str] = ["-m"]
    if home:
        create_home_args.extend(["-d", home])

    useradd_cmd = ["useradd", "-c", gecos, "-s", shell, *create_home_args]

    uid = user.get("uid")
    if isinstance(uid, int):
        useradd_cmd.extend(["-u", str(uid)])

    gid = user.get("gid")
    if isinstance(gid, int):
        useradd_cmd.extend(["-g", str(gid)])

    useradd_cmd.append(username)

    try:
        pwd.getpwnam(username)
        user_exists = True
    except KeyError:
        user_exists = False

    if not user_exists:
        subprocess.run(useradd_cmd, check=True)

    subprocess.run(["usermod", "-aG", "sudo", username], check=True)

    wheel_group = "wheel"
    try:
        grp.getgrnam(wheel_group)
    except KeyError:
        wheel_group = None
    if wheel_group:
        subprocess.run(["usermod", "-aG", wheel_group, username], check=True)

    password = user.get("password")
    if isinstance(password, str) and password:
        hashed = bool(user.get("password_is_hashed"))
        set_user_password(username, password, hashed)

    authorized_keys = collect_authorized_keys(user)
    if authorized_keys:
        install_authorized_keys(username, authorized_keys)


def collect_authorized_keys(user: Dict) -> List[str]:
    collected: List[str] = []
    seen: Set[str] = set()

    for source in user.get("github_keys", []):
        if not isinstance(source, dict):
            continue
        source_type = source.get("type")
        try:
            if source_type == "user":
                username = source["user"]
                url = f"https://github.com/{username}.keys"
                keys = fetch_remote_keys(url)
            elif source_type == "repo":
                owner = source["owner"]
                repo = source["repo"]
                path = source["path"]
                ref = source.get("ref", "main")
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
                keys = fetch_remote_keys(url)
            elif source_type == "url":
                url = source["url"]
                keys = fetch_remote_keys(url)
            else:
                continue
        except (KeyError, RuntimeError):
            continue

        for key in keys:
            if key and key not in seen:
                seen.add(key)
                collected.append(key)

    return collected


def fetch_remote_keys(url: str) -> List[str]:
    request = Request(url, headers={"User-Agent": "custom-kiwi-builder/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, timeout) as exc:
        raise RuntimeError(f"Failed to fetch keys from {url}: {exc}") from exc

    return [line.strip() for line in body.splitlines() if line.strip()]


def install_authorized_keys(username: str, keys: Iterable[str]) -> None:
    user_info = pwd.getpwnam(username)
    home = Path(user_info.pw_dir)
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    authorized_keys_path = ssh_dir / "authorized_keys"
    existing_keys: Set[str] = set()
    if authorized_keys_path.exists():
        existing_keys = {line.strip() for line in authorized_keys_path.read_text(encoding="utf-8").splitlines() if line.strip()}

    new_keys = existing_keys.union(keys)
    authorized_keys_path.write_text("\n".join(sorted(new_keys)) + "\n", encoding="utf-8")
    os.chown(ssh_dir, user_info.pw_uid, user_info.pw_gid)
    os.chown(authorized_keys_path, user_info.pw_uid, user_info.pw_gid)
    os.chmod(authorized_keys_path, 0o600)


def enable_services(services: Iterable[str]) -> None:
    for service in services:
        service = service.strip()
        if not service:
            continue
        subprocess.run(["systemctl", "enable", service], check=False)
        subprocess.run(["systemctl", "start", service], check=False)


def disable_services(services: Iterable[str]) -> None:
    for service in services:
        service = service.strip()
        if not service:
            continue
        subprocess.run(["systemctl", "disable", service], check=False)
        subprocess.run(["systemctl", "stop", service], check=False)


def record_target_disk(target_path: Path) -> Optional[str]:
    detector = Path("/usr/local/sbin/detect-smallest-disk.sh")
    if not detector.exists():
        return None
    try:
        result = subprocess.run(
            [str(detector)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError:
        return None
    disk = result.stdout.strip()
    if not disk:
        return None

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(disk + "\n", encoding="utf-8")
    return disk


def install_to_disk(disk: Optional[str]) -> None:
    if not disk:
        return
    kiwi_install = shutil.which("kiwi-install")
    if not kiwi_install:
        return

    state_dir = Path("/var/lib/custom-installer")
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / "installed"
    if marker.exists():
        return

    try:
        subprocess.run([kiwi_install, disk], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to install image onto {disk}: {exc}", file=sys.stderr)
        return

    marker.write_text(disk + "\n", encoding="utf-8")
    print(f"Installed image onto {disk}")


def run(config_path: Path) -> None:
    config = read_config(config_path)
    ensure_group("sudo")

    for user in config.get("users", []):
        if not isinstance(user, dict):
            continue
        if "username" not in user:
            continue
        ensure_user(user)

    services = config.get("services", {}) if isinstance(config.get("services"), dict) else {}
    enable_services(services.get("enable", []))
    disable_services(services.get("disable", []))

    target_disk_path = Path("/etc/custom/install_target")
    disk = record_target_disk(target_disk_path)
    install_to_disk(disk)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision services, packages and users on first boot")
    parser.add_argument("--config", required=True, type=Path, help="Path to the rendered configuration JSON")
    parser.add_argument("command", choices=["run"], help="Action to execute")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "run":
        run(args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
