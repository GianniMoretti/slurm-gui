"""The live view of one cluster: connection, polling, and actions, exposed to the UI as Qt signals.

One poll = one ``squeue`` + one ``scontrol show node`` over the shared SSH connection, every
``Profile.refresh_seconds``. Polls never overlap. Changes to the user's own jobs are turned
into events (started, finished, failed) for the dashboard feed and desktop notifications.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..config.profiles import MIN_REFRESH_SECONDS, Profile
from ..core.async_bridge import AsyncBridge
from ..core.ssh import SshError, SshSession
from ..slurm.client import SlurmClient
from ..slurm.models import Association, ClusterInfo, Job, Node, Partition

@dataclass(slots=True)
class JobEvent:
    time: datetime
    job_id: str
    name: str
    kind: str        # "submitted", "started", "completed", "failed", "cancelled", "left"
    text: str
    live: bool = True   # False for events replayed from accounting when connecting (no notification)


def _end_event(name: str, state: str, exit_code: str) -> tuple[str, str]:
    if state == "COMPLETED":
        return "completed", f"{name} completed"
    if state == "CANCELLED":
        return "cancelled", f"{name} was cancelled"
    if state:
        return "failed", f"{name} ended with {state} (exit {exit_code})"
    return "left", f"{name} left the queue"


class ClusterState(QObject):
    connection_changed = pyqtSignal(bool)
    info_changed = pyqtSignal(object)            # ClusterInfo
    snapshot = pyqtSignal(object, object)        # list[Job], list[Node]
    partitions_changed = pyqtSignal(object)      # list[Partition]
    associations_changed = pyqtSignal(object)    # list[Association]
    job_event = pyqtSignal(object)               # JobEvent
    busy_changed = pyqtSignal(bool)
    stage = pyqtSignal(str)                      # progress text while connecting
    # (title, instructions, [(prompt, echo)], reply): call reply(list[str]) or reply(None) to cancel.
    auth_requested = pyqtSignal(str, str, object, object)
    connect_failed = pyqtSignal(str)             # the connection attempt failed
    ready = pyqtSignal()                         # connected and the first snapshot arrived
    error = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, bridge: AsyncBridge) -> None:
        super().__init__()
        self._bridge = bridge
        self._generation = 0           # bumped on every connect/disconnect; stale callbacks are ignored
        self._connecting: concurrent.futures.Future | None = None
        self._first_snapshot = False
        self.profile: Profile | None = None
        self.session: SshSession | None = None
        self.client: SlurmClient | None = None
        self.info: ClusterInfo | None = None
        self.jobs: list[Job] = []
        self.nodes: list[Node] = []
        self.partitions: list[Partition] = []
        self.associations: list[Association] = []
        self.last_update: datetime | None = None
        self._my_jobs: dict[str, Job] | None = None
        self._polling = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------ connection

    @property
    def connected(self) -> bool:
        return self.session is not None and self.session.connected

    def connect_to(self, profile: Profile) -> None:
        self.disconnect()
        gen = self._generation
        self.profile = profile
        self.session = session = SshSession(profile.host, profile.user, profile.port, profile.key_file,
                                            profile.login_shell)
        self.client = client = SlurmClient(session)
        self._first_snapshot = False
        self.stage.emit(f"Connecting to {profile.host}…")

        async def prompter(title, instructions, prompts):
            self.stage.emit("Waiting for authentication…")
            answers = await self._bridge.ask_main(
                lambda reply: self.auth_requested.emit(title, instructions, prompts, reply))
            self.stage.emit("Authenticating…")
            return answers

        async def start():
            await session.connect(prompter)
            self.stage.emit("Reading the cluster configuration…")
            return await asyncio.gather(client.info(), client.partitions(), client.associations())

        def guard(fn):
            return lambda arg: fn(arg) if gen == self._generation else None

        self._connecting = self._bridge.submit(start(), guard(self._on_connected), guard(self._on_connect_failed))

    def _on_connected(self, result) -> None:
        self._connecting = None
        self.info, self.partitions, self.associations = result
        default = next((p for p in self.partitions if p.is_default), None)
        if default:
            self.info.default_time = default.default_time
        self.connection_changed.emit(True)
        self.info_changed.emit(self.info)
        self.partitions_changed.emit(self.partitions)
        self.associations_changed.emit(self.associations)
        self.stage.emit("Loading jobs and nodes…")
        self._timer.start(max(MIN_REFRESH_SECONDS, self.profile.refresh_seconds) * 1000)
        self.refresh()

    def _on_connect_failed(self, exc: BaseException) -> None:
        self._connecting = None
        session, self.session, self.client = self.session, None, None
        if session is not None:
            self._bridge.submit(session.close())
        self.connect_failed.emit(str(exc) if isinstance(exc, SshError) else f"Connection failed: {exc}")

    def disconnect(self) -> None:
        """Close the connection, or abandon an attempt in progress."""
        self._generation += 1
        self._timer.stop()
        self._polling = False
        if self._connecting is not None:
            self._connecting.cancel()
            self._connecting = None
        if self.session is not None:
            self._bridge.submit(self.session.close())
        was_connected = self.connected
        self.session = self.client = self.info = None
        self.jobs, self.nodes, self._my_jobs = [], [], None
        self.last_update = None
        if was_connected:
            self.connection_changed.emit(False)

    # ------------------------------------------------------------ polling

    def refresh(self) -> None:
        if self._polling or not self.connected:
            return
        self._polling = True
        self.busy_changed.emit(True)

        gen, client = self._generation, self.client

        async def poll():
            return await asyncio.gather(client.jobs(), client.nodes())

        self._bridge.submit(poll(),
                            lambda r: self._on_snapshot(r) if gen == self._generation else None,
                            lambda e: self._on_poll_failed(e) if gen == self._generation else None)

    def _on_snapshot(self, result) -> None:
        self._polling = False
        self.busy_changed.emit(False)
        self.jobs, self.nodes = result
        self.last_update = datetime.now()
        self.snapshot.emit(self.jobs, self.nodes)
        self._diff_my_jobs()
        if not self._first_snapshot:
            self._first_snapshot = True
            self.ready.emit()
            self._load_recent_events()

    def _on_poll_failed(self, exc: BaseException) -> None:
        self._polling = False
        self.busy_changed.emit(False)
        if not self._first_snapshot:
            self.disconnect()
            self.connect_failed.emit(f"Connected, but reading the queue failed: {exc}")
            return
        if not self.connected:
            self._timer.stop()
            self.connection_changed.emit(False)
            self.error.emit("Connection lost. Use Reconnect in the header.")
        else:
            self.error.emit(f"Refresh failed: {exc}")

    def _diff_my_jobs(self) -> None:
        user = self.info.user if self.info else ""
        current = {j.job_id: j for j in self.jobs if j.user == user}
        previous, self._my_jobs = self._my_jobs, current
        if previous is None:          # first poll after connecting: nothing to compare with
            return
        now = datetime.now()
        for jid, job in current.items():
            old = previous.get(jid)
            if old is None:
                self.job_event.emit(JobEvent(now, jid, job.name, "submitted", f"{job.name} entered the queue"))
            elif old.is_pending and job.is_active:
                self.job_event.emit(JobEvent(now, jid, job.name, "started", f"{job.name} started on {job.nodelist}"))
        gone = [jid for jid in previous if jid not in current]
        if gone and self.client:
            self._bridge.submit(self.client.final_states(gone),
                                lambda states: self._emit_finished(previous, gone, states),
                                lambda _exc: self._emit_finished(previous, gone, {}))

    def _load_recent_events(self, hours: int = 24) -> None:
        """Replay the last day of the user's jobs from sacct so the activity feed is not empty."""
        gen = self._generation

        def emit(jobs: list[Job]) -> None:
            if gen != self._generation:
                return
            since = datetime.now() - timedelta(hours=hours)
            events = []
            for j in jobs:
                if j.start_time and j.start_time >= since:
                    events.append(JobEvent(j.start_time, j.job_id, j.name, "started",
                                           f"{j.name} started on {j.nodelist}", live=False))
                if j.end_time and j.end_time >= since and not (j.is_active or j.is_pending):
                    kind, text = _end_event(j.name, j.state, j.exit_code)
                    events.append(JobEvent(j.end_time, j.job_id, j.name, kind, text, live=False))
            for event in sorted(events, key=lambda e: e.time):
                self.job_event.emit(event)

        self._bridge.submit(self.client.history(f"now-{hours}hours"), emit, lambda _exc: None)

    def _emit_finished(self, previous: dict[str, Job], gone: list[str], states: dict[str, tuple[str, str]]) -> None:
        now = datetime.now()
        for jid in gone:
            job = previous[jid]
            state, exit_code = states.get(jid, ("", ""))
            kind, text = _end_event(job.name, state, exit_code)
            self.job_event.emit(JobEvent(now, jid, job.name, kind, text))

    # ------------------------------------------------------------ actions

    def run_action(self, name: str, job_ids: list[str]) -> None:
        """name: "cancel", "hold" or "release"."""
        if not self.client or not job_ids:
            return
        coro = getattr(self.client, name)(job_ids)
        label = {"cancel": "Cancelled", "hold": "Held", "release": "Released"}[name]

        def done(_):
            self.message.emit(f"{label} {len(job_ids)} job(s)")
            self.refresh()

        self._bridge.submit(coro, done, lambda exc: self.error.emit(f"{name.capitalize()} failed: {exc}"))

    def call(self, coro, done, error=None) -> None:
        """Run any client coroutine; errors go to the status bar unless ``error`` is given."""
        self._bridge.submit(coro, done, error or (lambda exc: self.error.emit(str(exc))))
