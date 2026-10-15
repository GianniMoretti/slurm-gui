"""A fake cluster for trying the app without SLURM (``slurm-gui --demo``) and for screenshots.

``DemoSession`` stands in for :class:`slurm_gui.core.ssh.SshSession`: it answers the commands of
:mod:`slurm_gui.slurm.commands` with the synthetic outputs in ``data/`` (also the parser test
fixtures). Their dates are shifted so that the data always looks recent.
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime
from pathlib import Path

from ..config.profiles import Profile
from ..core.ssh import CommandResult

DATA = Path(__file__).resolve().parent / "data"
DEMO_HOST = "slurm-gui-demo"
DEMO_PROFILE = Profile(name="Demo cluster", host=DEMO_HOST, user="alice")

# The data was written as if it were this moment; every timestamp is moved by (now - _WRITTEN_AT).
_WRITTEN_AT = datetime(2026, 1, 15, 10, 0, 0)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

_ANSWERS = [  # (command prefix, data file); first match wins
    ("id -un", None),
    ("sinfo --version", "version.txt"),
    ("scontrol show config", "config.txt"),
    ("squeue", "squeue.txt"),
    ("scontrol show node", "nodes.txt"),
    ("scontrol show partition", "partitions.txt"),
    ("scontrol show job", "show_job.txt"),
    ("sacctmgr", "assoc.txt"),
    ("sshare", "sshare.txt"),
    ("sacct -X -n -P -j", None),      # final state of jobs that just left the queue
    ("sacct", "sacct.txt"),
    ("tail", None),
]


def _training_log(lines: int) -> str:
    rng = random.Random(5001)
    out, loss = [], 2.3
    for epoch in range(1, min(lines, 120) + 1):
        loss *= 0.97 + rng.random() * 0.02
        acc = min(0.97, 0.1 + epoch * 0.0075 + rng.random() * 0.01)
        out.append(f"epoch {epoch:3d} | loss {loss:.4f} | val_acc {acc:.4f} | lr 3.0e-04 | 41.2 s")
    return "\n".join(out) + "\n"


class DemoSession:
    def __init__(self, *_args, **_kwargs) -> None:
        self._connected = False
        self._shift = datetime.now().replace(microsecond=0) - _WRITTEN_AT

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, prompter=None, timeout: float = 20) -> None:
        await asyncio.sleep(0.8)   # let the loading screen show
        self._connected = True

    async def run(self, command: str, timeout: float = 60) -> CommandResult:
        await asyncio.sleep(0.05)
        for prefix, name in _ANSWERS:
            if command.startswith(prefix):
                break
        else:
            return CommandResult(command, 1, "", f"demo: unsupported command: {command.split()[0]}")
        if prefix == "id -un":
            text = "alice\n"
        elif prefix == "tail":
            text = _training_log(400)
        elif name is None:
            text = ""
        else:
            text = _TIMESTAMP.sub(
                lambda m: (datetime.fromisoformat(m.group()) + self._shift).isoformat(), (DATA / name).read_text())
        return CommandResult(command, 0, text, "")

    async def close(self) -> None:
        self._connected = False
