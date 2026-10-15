"""The SLURM command lines the app runs, in one place.

Every query uses a plain-text format rather than ``--json``: the text output is about 100x
smaller (21 KB vs 2 MB for ``squeue`` on a 150-job cluster), is cheap for the controller, and
works on every SLURM version. Free-text fields (job names) always come last, so a ``|`` inside
them cannot shift the other columns.
"""

from __future__ import annotations

import shlex

SEP = "|"

# (field, squeue format code); the name is last on purpose.
SQUEUE_FIELDS: list[tuple[str, str]] = [
    ("job_id", "%i"),
    ("array_job_id", "%F"),
    ("array_task_id", "%K"),
    ("user", "%u"),
    ("account", "%a"),
    ("partition", "%P"),
    ("qos", "%q"),
    ("state", "%T"),
    ("reason", "%r"),
    ("elapsed", "%M"),
    ("time_limit", "%l"),
    ("node_count", "%D"),
    ("cpus", "%C"),
    ("memory", "%m"),
    ("tres_per_node", "%b"),
    ("nodelist", "%N"),
    ("submit_time", "%V"),
    ("start_time", "%S"),
    ("priority", "%Q"),
    ("work_dir", "%Z"),
    ("name", "%j"),
]

SACCT_FIELDS: list[str] = [
    "JobID", "User", "Account", "Partition", "QOS", "State", "ExitCode", "Submit", "Start", "End",
    "Elapsed", "Timelimit", "NNodes", "NCPUS", "ReqMem", "AllocTRES", "NodeList", "WorkDir", "JobName",
]

VERSION = "sinfo --version"
WHOAMI = "id -un"
SQUEUE = "squeue -a -h -o " + shlex.quote(SEP.join(code for _, code in SQUEUE_FIELDS))
NODES = "scontrol show node -o"
PARTITIONS = "scontrol show partition -o"
CONFIG = "scontrol show config"
ASSOCIATIONS = (
    "sacctmgr -nP show assoc user=$USER "
    "format=Account,Partition,QOS,GrpTRES,MaxTRES,MaxJobs,MaxSubmit,MaxWall"
)
FAIRSHARE = "sshare -U -n -P -o Account,User,RawShares,NormShares,RawUsage,EffectvUsage,FairShare"


def sacct(start: str = "now-7days", end: str = "now", user: str | None = None) -> str:
    """Finished and running allocations (``-X``: no job steps) between ``start`` and ``end``."""
    who = f"-u {shlex.quote(user)}" if user else "-u $USER"
    return (
        f"sacct -X -n -P {who} -S {shlex.quote(start)} -E {shlex.quote(end)} "
        f"-o {','.join(SACCT_FIELDS)}"
    )


def show_job(job_id: str) -> str:
    return f"scontrol show job -o {shlex.quote(job_id)}"


def cancel(job_ids: list[str]) -> str:
    return "scancel " + " ".join(map(shlex.quote, job_ids))


def hold(job_ids: list[str]) -> str:
    return "scontrol hold " + ",".join(map(shlex.quote, job_ids))


def release(job_ids: list[str]) -> str:
    return "scontrol release " + ",".join(map(shlex.quote, job_ids))


def final_states(job_ids: list[str]) -> str:
    """Final state of jobs that just left the queue."""
    return f"sacct -X -n -P -j {','.join(map(shlex.quote, job_ids))} -o JobID,State,ExitCode,Elapsed"
