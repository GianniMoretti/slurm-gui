"""One persistent SSH connection per cluster, shared by every query (asyncssh channels).

Host, user, port, keys and ProxyJump come from ``~/.ssh/config`` exactly as for the ``ssh``
command. Password and keyboard-interactive (2FA/OTP) prompts are forwarded to a callback,
which the UI answers with a dialog.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncssh

# Printed right before the command output, so login banners and shell-profile noise can be cut away.
_MARK = "\x1eSLURMGUI\x1e"

# (title, instructions, [(prompt, echo)]) -> answers, or None if the user cancelled.
Prompter = Callable[[str, str, list[tuple[str, bool]]], Awaitable[list[str] | None]]


class SshError(Exception):
    """A connection problem, with a message fit for the user."""


@dataclass(slots=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class _Client(asyncssh.SSHClient):
    def __init__(self, prompter: Prompter | None) -> None:
        self._prompter = prompter

    async def password_auth_requested(self) -> str | None:  # type: ignore[override]
        if self._prompter is None:
            return None
        answers = await self._prompter("Password", "", [("Password:", False)])
        return answers[0] if answers else None

    async def kbdint_challenge_received(self, name, instructions, lang, prompts):  # type: ignore[override]
        if not prompts:
            return []
        if self._prompter is None:
            return None
        return await self._prompter(name or "Authentication", instructions, list(prompts))


class SshSession:
    def __init__(self, host: str, user: str = "", port: int | None = None, key_file: str = "",
                 login_shell: bool = True, max_parallel: int = 4) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.key_file = key_file
        self.login_shell = login_shell
        self._conn: asyncssh.SSHClientConnection | None = None
        self._slots = asyncio.Semaphore(max_parallel)   # stay below the server's MaxSessions

    @property
    def connected(self) -> bool:
        return self._conn is not None and not self._conn.is_closed()

    async def connect(self, prompter: Prompter | None = None, timeout: float = 20) -> None:
        options: dict = {"connect_timeout": timeout, "keepalive_interval": 30}
        if self.user:
            options["username"] = self.user
        if self.port:
            options["port"] = self.port
        if self.key_file:
            options["client_keys"] = [self.key_file]
        try:
            self._conn, _ = await asyncssh.create_connection(lambda: _Client(prompter), self.host, **options)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise SshError(
                f"The host key of {self.host} is not in your known_hosts. "
                f"Run `ssh {self.host}` once in a terminal to verify and accept it, then retry."
            ) from exc
        except asyncssh.PermissionDenied as exc:
            raise SshError(f"Authentication to {self.host} failed: {exc.reason}") from exc
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise SshError(
                f"Timed out connecting to {self.host}. If the cluster is only reachable through a VPN, "
                "check that the VPN is connected."
            ) from exc
        except OSError as exc:
            raise SshError(f"Couldn't reach {self.host}: {exc.strerror or exc}") from exc
        except asyncssh.Error as exc:
            raise SshError(f"SSH error with {self.host}: {exc.reason}") from exc

    async def run(self, command: str, timeout: float = 60) -> CommandResult:
        if not self.connected:
            raise SshError("Not connected")
        script = f"printf '%s\\n' {shlex.quote(_MARK)}; {command}"
        shell = "bash -lc" if self.login_shell else "sh -c"
        async with self._slots:
            try:
                result = await asyncio.wait_for(
                    self._conn.run(f"{shell} {shlex.quote(script)}", check=False), timeout  # type: ignore[union-attr]
                )
            except asyncio.TimeoutError as exc:
                raise SshError(f"Command timed out after {timeout:.0f}s: {command.split()[0]}") from exc
            except (asyncssh.Error, OSError) as exc:
                raise SshError(f"Connection lost: {exc}") from exc
        stdout = str(result.stdout or "")
        _, found, after = stdout.partition(_MARK + "\n")
        return CommandResult(command, result.exit_status or 0, after if found else stdout, str(result.stderr or ""))

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None
