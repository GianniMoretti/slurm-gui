"""Async SLURM API on top of an SSH session: runs the commands and parses their output."""

from __future__ import annotations

import asyncio
import shlex

from ..core.ssh import CommandResult, SshSession
from . import commands as c
from . import parse
from .models import Association, ClusterInfo, Job, Node, Partition


class SlurmError(Exception):
    def __init__(self, result: CommandResult) -> None:
        detail = (result.stderr or result.stdout).strip().splitlines()
        super().__init__(detail[-1] if detail else f"{result.command.split()[0]} exited with {result.returncode}")
        self.result = result


class SlurmClient:
    def __init__(self, session: SshSession) -> None:
        self.session = session

    async def _run(self, command: str, timeout: float = 60) -> str:
        result = await self.session.run(command, timeout)
        if not result.ok:
            raise SlurmError(result)
        return result.stdout

    async def info(self) -> ClusterInfo:
        user, version, config = await asyncio.gather(
            self._run(c.WHOAMI), self._run(c.VERSION), self._run(c.CONFIG)
        )
        return parse.cluster_info(user, version, config)

    async def jobs(self) -> list[Job]:
        return parse.parse_squeue(await self._run(c.SQUEUE))

    async def nodes(self) -> list[Node]:
        return parse.parse_nodes(await self._run(c.NODES))

    async def partitions(self) -> list[Partition]:
        return parse.parse_partitions(await self._run(c.PARTITIONS))

    async def history(self, start: str = "now-7days", end: str = "now") -> list[Job]:
        return parse.parse_sacct(await self._run(c.sacct(start, end), timeout=120))

    async def associations(self) -> list[Association]:
        assoc, share = await asyncio.gather(self._run(c.ASSOCIATIONS), self._run(c.FAIRSHARE))
        return parse.parse_associations(assoc, share)

    async def job_details(self, job_id: str) -> dict[str, str]:
        return parse.parse_show_job(await self._run(c.show_job(job_id)))

    async def tail(self, path: str, lines: int = 400) -> str:
        """Last lines of a text file on the cluster (job logs)."""
        result = await self.session.run(f"tail -n {int(lines)} -- {shlex.quote(path)}")
        if not result.ok:
            raise SlurmError(result)
        return result.stdout

    async def cancel(self, job_ids: list[str]) -> None:
        await self._run(c.cancel(job_ids))

    async def hold(self, job_ids: list[str]) -> None:
        await self._run(c.hold(job_ids))

    async def release(self, job_ids: list[str]) -> None:
        await self._run(c.release(job_ids))

    async def final_states(self, job_ids: list[str]) -> dict[str, tuple[str, str]]:
        """{job id: (state, exit code)} from accounting, for jobs no longer in the queue."""
        out: dict[str, tuple[str, str]] = {}
        for line in (await self._run(c.final_states(job_ids))).splitlines():
            cols = line.split(c.SEP)
            if len(cols) >= 3:
                out[cols[0]] = (cols[1].split()[0], cols[2])
        return out
