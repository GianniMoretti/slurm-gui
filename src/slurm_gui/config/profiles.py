"""Cluster connection profiles, stored as JSON in the user's config directory."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .settings import config_dir


MIN_REFRESH_SECONDS = 30   # polling faster than this only loads the controller


@dataclass(slots=True)
class Profile:
    name: str
    host: str                      # ssh host or alias from ~/.ssh/config
    user: str = ""                 # empty: from ~/.ssh/config or the local user
    port: int | None = None
    key_file: str = ""
    refresh_seconds: int = 30      # polling interval, at least MIN_REFRESH_SECONDS
    login_shell: bool = True       # run commands in a login shell (module/profile PATH setup)
    last_used: str = ""            # ISO timestamp of the last successful connection


def _profiles_file() -> Path:
    return config_dir() / "profiles.json"


def load_profiles() -> list[Profile]:
    try:
        data = json.loads(_profiles_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    known = {f.name for f in fields(Profile)}
    profiles = [Profile(**{k: v for k, v in item.items() if k in known}) for item in data.get("profiles", [])]
    for p in profiles:
        p.refresh_seconds = max(MIN_REFRESH_SECONDS, p.refresh_seconds)
    return profiles


def save_profiles(profiles: list[Profile]) -> None:
    _profiles_file().write_text(json.dumps({"profiles": [asdict(p) for p in profiles]}, indent=2))


def ssh_config_hosts(path: Path | None = None) -> list[str]:
    """Concrete host aliases (no wildcards) defined in ``~/.ssh/config``, to suggest in the UI."""
    path = path or Path.home() / ".ssh" / "config"
    try:
        text = path.read_text()
    except OSError:
        return []
    hosts: list[str] = []
    for m in re.finditer(r"^\s*Host\s+(.+)$", text, re.MULTILINE | re.IGNORECASE):
        hosts += [h for h in m.group(1).split() if not any(ch in h for ch in "*?!")]
    return list(dict.fromkeys(hosts))
