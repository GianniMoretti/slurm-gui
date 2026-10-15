"""Plain data objects produced by the parsers. The UI only ever sees these."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Job states grouped by how the UI treats them.
ACTIVE_STATES = {"RUNNING", "COMPLETING", "CONFIGURING", "SUSPENDED", "STOPPED", "SIGNALING", "STAGE_OUT"}
WAITING_STATES = {"PENDING", "REQUEUED", "REQUEUE_HOLD", "REQUEUE_FED", "RESV_DEL_HOLD", "RESIZING"}
FAILED_STATES = {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL", "DEADLINE", "PREEMPTED"}

STATE_SHORT = {
    "PENDING": "PD", "RUNNING": "R", "COMPLETING": "CG", "COMPLETED": "CD", "CONFIGURING": "CF",
    "CANCELLED": "CA", "FAILED": "F", "TIMEOUT": "TO", "OUT_OF_MEMORY": "OOM", "NODE_FAIL": "NF",
    "PREEMPTED": "PR", "SUSPENDED": "S", "BOOT_FAIL": "BF", "DEADLINE": "DL", "REQUEUED": "RQ",
}


@dataclass(slots=True)
class Job:
    job_id: str                         # "1234" or "1234_7" for an array task
    name: str
    user: str
    state: str                          # long form, e.g. "RUNNING"
    account: str = ""
    partition: str = ""
    qos: str = ""
    reason: str = ""                    # pending reason, "None" when running
    elapsed: int = 0                    # seconds
    time_limit: int | None = None       # seconds; None = unlimited / unknown
    node_count: int = 0
    cpus: int = 0
    memory_mb: int | None = None
    gpus: int = 0
    gpu_type: str = ""
    nodelist: str = ""
    submit_time: datetime | None = None
    start_time: datetime | None = None  # actual start, or the expected start while pending
    end_time: datetime | None = None
    priority: int | None = None
    work_dir: str = ""
    exit_code: str = ""
    array_job_id: str = ""
    array_task_id: str = ""

    @property
    def short_state(self) -> str:
        return STATE_SHORT.get(self.state, self.state[:2])

    @property
    def is_pending(self) -> bool:
        return self.state in WAITING_STATES

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def is_failed(self) -> bool:
        return self.state in FAILED_STATES

    @property
    def progress(self) -> float | None:
        """Fraction of the time limit already used, for running jobs with a finite limit."""
        if not self.time_limit or not self.is_active:
            return None
        return min(1.0, self.elapsed / self.time_limit)


@dataclass(slots=True)
class Node:
    name: str
    state: str                          # base state, e.g. "MIXED"
    flags: list[str] = field(default_factory=list)  # e.g. ["DRAIN", "POWERED_DOWN"]
    partitions: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    cpus_total: int = 0
    cpus_alloc: int = 0
    cpu_load: float | None = None
    mem_total_mb: int = 0
    mem_alloc_mb: int = 0
    mem_free_mb: int | None = None
    gpus_total: int = 0
    gpus_alloc: int = 0
    gpu_type: str = ""
    reason: str = ""

    @property
    def is_unavailable(self) -> bool:
        return self.state in {"DOWN", "FUTURE", "UNKNOWN"} or bool({"DRAIN", "FAIL", "NOT_RESPONDING"} & set(self.flags))

    @property
    def gpus_free(self) -> int:
        return 0 if self.is_unavailable else max(0, self.gpus_total - self.gpus_alloc)


@dataclass(slots=True)
class Partition:
    name: str
    state: str
    is_default: bool = False
    nodes: str = ""
    total_nodes: int = 0
    total_cpus: int = 0
    total_gpus: int = 0
    default_time: int | None = None     # seconds; None = unlimited / not set
    max_time: int | None = None
    allow_accounts: str = "ALL"
    deny_accounts: str = ""
    hidden: bool = False

    def allows(self, accounts: set[str]) -> bool:
        """Whether a job under one of ``accounts`` may run here (group restrictions not checked)."""
        allowed = set(self.allow_accounts.split(",")) if self.allow_accounts not in ("", "ALL") else None
        denied = set(self.deny_accounts.split(",")) if self.deny_accounts else set()
        usable = accounts - denied
        return bool(usable if allowed is None else usable & allowed)


@dataclass(slots=True)
class Association:
    account: str
    partition: str = ""
    qos: str = ""
    grp_tres: dict[str, str] = field(default_factory=dict)
    max_tres: dict[str, str] = field(default_factory=dict)
    max_jobs: int | None = None
    max_submit: int | None = None
    max_wall: int | None = None         # seconds
    fairshare: float | None = None
    norm_shares: float | None = None        # the account's entitled fraction of the cluster
    effective_usage: float | None = None    # its recent (decayed) fraction of the cluster's usage


@dataclass(slots=True)
class ClusterInfo:
    user: str
    version: str
    cluster_name: str = ""
    default_time: int | None = None
    max_array_size: int | None = None
    priority_type: str = ""                 # e.g. "priority/multifactor" or "priority/basic"
    fairshare_weight: int | None = None     # PriorityWeightFairShare; 0 = fairshare is ignored
    decay_half_life: int | None = None      # seconds; how fast past usage is forgotten
