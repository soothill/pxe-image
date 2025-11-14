"""Parsers for the text-based configuration inputs."""
# Copyright (c) 2024 Darren Soothill

import json
import shlex
from pathlib import Path
from typing import Dict, List, Optional


class RepoSpec(object):
    """Simple data container describing a GitHub repository location."""

    __slots__ = ("owner", "repo", "path", "ref")

    def __init__(self, owner: str, repo: str, path: str = "authorized_keys", ref: str = "main") -> None:
        self.owner = owner
        self.repo = repo
        self.path = path
        self.ref = ref


def read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]


def parse_packages(path: Path) -> List[str]:
    packages: List[str] = []
    for line in read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        packages.append(stripped)
    return packages


def parse_services(path: Path) -> List[str]:
    services: List[str] = []
    for line in read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        services.append(stripped)
    return services


def parse_repo_spec(spec: str, lineno: int) -> RepoSpec:
    ref = "main"
    if "@" in spec:
        spec, ref = spec.rsplit("@", 1)
        ref = ref or "main"
    path = "authorized_keys"
    if ":" in spec:
        repo_part, path = spec.split(":", 1)
        path = path or "authorized_keys"
    else:
        repo_part = spec
    if "/" not in repo_part:
        raise ValueError(f"Line {lineno}: repository specification '{spec}' must include owner/repo")
    owner, repo = repo_part.split("/", 1)
    if not owner or not repo:
        raise ValueError(f"Line {lineno}: repository specification '{spec}' is invalid")
    return RepoSpec(owner=owner, repo=repo, path=path, ref=ref)


def ensure_user_defaults(user: Dict[str, object]) -> None:
    user.setdefault("gecos", user["username"])
    user.setdefault("shell", "/bin/bash")


def parse_user_line(line: str, lineno: int) -> Dict[str, object]:
    tokens = shlex.split(line, comments=True, posix=True)
    if not tokens:
        raise ValueError(f"Line {lineno}: empty user definition")
    if len(tokens) < 3:
        raise ValueError(
            f"Line {lineno}: expected 'username password repo[:path][@ref] [additional ...]'"
        )

    username = tokens[0]
    raw_password = tokens[1]
    password_is_hashed = False
    if raw_password in {"-", "none", "null"}:
        password: Optional[str] = None
    elif raw_password.startswith("hash:"):
        password = raw_password.split(":", 1)[1]
        password_is_hashed = True
    else:
        password = raw_password

    user: Dict[str, object] = {
        "username": username,
        "github_keys": [],
    }
    if password:
        user["password"] = password
        if password_is_hashed:
            user["password_is_hashed"] = True

    for token in tokens[2:]:
        if "=" in token:
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in {"gecos", "shell", "home"}:
                user[key] = value
            elif key in {"uid", "gid"}:
                try:
                    user[key] = int(value)
                except ValueError as exc:
                    raise ValueError(f"Line {lineno}: {key} must be an integer") from exc
            elif key == "github_user":
                user.setdefault("github_keys", []).append({"type": "user", "user": value})
            elif key == "github_url":
                user.setdefault("github_keys", []).append({"type": "url", "url": value})
            else:
                raise ValueError(f"Line {lineno}: unsupported attribute '{key}'")
        else:
            repo_spec = parse_repo_spec(token, lineno)
            user.setdefault("github_keys", []).append(
                {
                    "type": "repo",
                    "owner": repo_spec.owner,
                    "repo": repo_spec.repo,
                    "path": repo_spec.path,
                    "ref": repo_spec.ref,
                }
            )

    if not user["github_keys"]:
        raise ValueError(f"Line {lineno}: at least one GitHub key source must be provided")

    ensure_user_defaults(user)
    return user


def parse_users(path: Path) -> List[Dict[str, object]]:
    users: List[Dict[str, object]] = []
    for lineno, line in enumerate(read_lines(path), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        users.append(parse_user_line(line, lineno))
    return users


def render_config(users: List[Dict[str, object]], packages: List[str], services: List[str]) -> Dict[str, object]:
    return {
        "packages": packages,
        "services": {
            "enable": services,
            "disable": [],
        },
        "users": users,
    }


def render_from_files(users: Path, packages: Path, services: Path) -> Dict[str, object]:
    parsed_users = parse_users(users)
    parsed_packages = parse_packages(packages)
    parsed_services = parse_services(services)
    return render_config(parsed_users, parsed_packages, parsed_services)


def dump_config(config: Dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "RepoSpec",
    "dump_config",
    "parse_packages",
    "parse_services",
    "parse_user_line",
    "parse_users",
    "render_config",
    "render_from_files",
]
