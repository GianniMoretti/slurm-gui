"""Parsers for the text output of the commands in :mod:`slurm_gui.slurm.commands`.

All functions are pure (string in, models out) so they can be tested against captured fixtures.
"""

from __future__ import annotations

import re
from datetime import datetime

from .commands import SACCT_FIELDS, SEP, SQUEUE_FIELDS
from .models import Association, ClusterInfo, Job, Node, Partition

_EMPTY = {"", "N/A", "(null)", "None", "Unknown", "NONE"}


# ---------------------------------------------------------------- scalar helpers

def parse_duration(text: str) -> int | None:
    """SLURM duration ("[D-]HH:MM:SS", "MM:SS", "MM", ...) to seconds. None for unlimited/unknown."""
    text = text.strip()
    if text.upper() in {"UNLIMITED", "INFINITE", "PARTITION_LIMIT", "INVALID"} or text in _EMPTY:
        return None
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [float(p) for p in text.split(":")]
    if len(parts) == 1:   # minutes (or days-hours when a day was given)
        h, m, s = (parts[0], 0, 0) if days else (0, parts[0], 0)
    elif len(parts) == 2:  # MM:SS, or days-HH:MM
        h, m, s = (parts[0], parts[1], 0) if days else (0, parts[0], parts[1])
    else:
        h, m, s = parts[-3:]
    return int(days * 86400 + h * 3600 + m * 60 + s)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "∞"
    days, rest = divmod(int(seconds), 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    return f"{days}-{h:02d}:{m:02d}:{s:02d}" if days else f"{h:02d}:{m:02d}:{s:02d}"


def parse_time(text: str) -> datetime | None:
    text = text.strip()
    if text in _EMPTY:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_int(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_memory_mb(text: str) -> int | None:
    """"64G", "32000M", "500000" (MB), "4Gc"/"4Gn" (sacct ReqMem suffixes) to MB."""
    m = re.fullmatch(r"\s*([\d.]+)\s*([KMGTP]?)[cn]?\s*", text or "")
    if not m:
        return None
    scale = {"K": 1 / 1024, "": 1, "M": 1, "G": 1024, "T": 1024**2, "P": 1024**3}[m.group(2)]
    return int(float(m.group(1)) * scale)


def parse_tres(text: str) -> dict[str, str]:
    """"cpu=10,mem=32G,gres/gpu=1" -> {"cpu": "10", "mem": "32G", "gres/gpu": "1"}."""
    out: dict[str, str] = {}
    for item in (text or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def gpus_from_tres(text: str) -> tuple[int, str]:
    """GPU count and type from a TRES string ("gres/gpu=1,gres/gpu:rtx_a5000=1")."""
    count, gpu_type = 0, ""
    for key, value in parse_tres(text).items():
        if key == "gres/gpu":
            count = parse_int(value) or 0
        elif key.startswith("gres/gpu:"):
            gpu_type = key.split(":", 1)[1]
            count = count or (parse_int(value) or 0)
    return count, gpu_type


def gpus_from_gres(text: str) -> tuple[int, str]:
    """GPU count and type from a GRES spec ("gpu:rtx_4090:3(S:0-1)", "gres/gpu:1", "gpu:a100:2,shard:8")."""
    count, gpu_type = 0, ""
    for item in re.split(r",(?![^(]*\))", text or ""):
        item = re.sub(r"\(.*?\)", "", item).removeprefix("gres/")
        parts = item.split(":")
        if parts[0] != "gpu":
            continue
        if len(parts) == 2 and parts[1].isdigit():
            count += int(parts[1])
        elif len(parts) >= 3:
            gpu_type = gpu_type or parts[1]
            count += parse_int(parts[2]) or 0
        else:
            count += 1
    return count, gpu_type


def parse_key_values(line: str) -> dict[str, str]:
    """One ``scontrol show <entity> -o`` line to a dict.

    Values may contain spaces (``OS=Linux 4.18 #1 SMP ...``, ``Reason=Not responding [root@...]``),
    so a value runs until the next `` Key=`` token.
    """
    out: dict[str, str] = {}
    for m in re.finditer(r"(?:^|\s)([A-Za-z][\w/:.]*)=(.*?)(?=\s+[A-Za-z][\w/:.]*=|\s*$)", line.strip()):
        out[m.group(1)] = m.group(2).strip()
    return out


# ---------------------------------------------------------------- commands

def parse_version(text: str) -> str:
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return m.group(1) if m else text.strip()


def parse_config(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            out[key.strip()] = value.strip()
    return out


def cluster_info(user: str, version_text: str, config_text: str) -> ClusterInfo:
    cfg = parse_config(config_text)
    return ClusterInfo(
        user=user.strip(),
        version=parse_version(version_text),
        cluster_name=cfg.get("ClusterName", ""),
        max_array_size=parse_int(cfg.get("MaxArraySize", "")),
        priority_type=cfg.get("PriorityType", ""),
        fairshare_weight=parse_int(cfg.get("PriorityWeightFairShare", "")),
        decay_half_life=parse_duration(cfg.get("PriorityDecayHalfLife", "")),
    )


def parse_squeue(text: str) -> list[Job]:
    names = [name for name, _ in SQUEUE_FIELDS]
    jobs = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split(SEP, len(names) - 1)   # the name (last) may contain the separator
        if len(cols) != len(names):
            continue
        r = dict(zip(names, cols))
        gpus, gpu_type = gpus_from_gres(r["tres_per_node"])
        node_count = parse_int(r["node_count"]) or 1
        jobs.append(Job(
            job_id=r["job_id"],
            name=r["name"],
            user=r["user"],
            state=r["state"],
            account=r["account"],
            partition=r["partition"],
            qos=r["qos"],
            reason=r["reason"],
            elapsed=parse_duration(r["elapsed"]) or 0,
            time_limit=parse_duration(r["time_limit"]),
            node_count=node_count,
            cpus=parse_int(r["cpus"]) or 0,
            memory_mb=parse_memory_mb(r["memory"]),
            gpus=gpus * node_count,
            gpu_type=gpu_type,
            nodelist=r["nodelist"],
            submit_time=parse_time(r["submit_time"]),
            start_time=parse_time(r["start_time"]),
            priority=parse_int(r["priority"]),
            work_dir=r["work_dir"],
            array_job_id=r["array_job_id"] if r["array_task_id"] not in _EMPTY else "",
            array_task_id=r["array_task_id"] if r["array_task_id"] not in _EMPTY else "",
        ))
    return jobs


def parse_sacct(text: str) -> list[Job]:
    jobs = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = line.split(SEP, len(SACCT_FIELDS) - 1)
        if len(cols) != len(SACCT_FIELDS):
            continue
        r = dict(zip(SACCT_FIELDS, cols))
        gpus, gpu_type = gpus_from_tres(r["AllocTRES"])
        jobs.append(Job(
            job_id=r["JobID"],
            name=r["JobName"],
            user=r["User"],
            state=r["State"].split()[0],          # "CANCELLED by 123" -> "CANCELLED"
            account=r["Account"],
            partition=r["Partition"],
            qos=r["QOS"],
            exit_code=r["ExitCode"],
            elapsed=parse_duration(r["Elapsed"]) or 0,
            time_limit=parse_duration(r["Timelimit"]),
            node_count=parse_int(r["NNodes"]) or 0,
            cpus=parse_int(r["NCPUS"]) or 0,
            memory_mb=parse_memory_mb(r["ReqMem"]),
            gpus=gpus,
            gpu_type=gpu_type,
            nodelist=r["NodeList"] if r["NodeList"] != "None assigned" else "",
            submit_time=parse_time(r["Submit"]),
            start_time=parse_time(r["Start"]),
            end_time=parse_time(r["End"]),
            work_dir=r["WorkDir"],
        ))
    return jobs


def parse_nodes(text: str) -> list[Node]:
    nodes = []
    for line in text.splitlines():
        kv = parse_key_values(line)
        if "NodeName" not in kv:
            continue
        state, *flags = kv.get("State", "UNKNOWN").replace("*", "").split("+")
        gpus_total, gpu_type = gpus_from_gres(kv.get("Gres", ""))
        if not gpus_total:  # some sites only expose GPUs as TRES
            gpus_total, gpu_type = gpus_from_tres(kv.get("CfgTRES", ""))
        gpus_alloc, _ = gpus_from_tres(kv.get("AllocTRES", ""))
        features = kv.get("ActiveFeatures") or kv.get("AvailableFeatures") or ""
        nodes.append(Node(
            name=kv["NodeName"],
            state=state,
            flags=flags,
            partitions=[p for p in kv.get("Partitions", "").split(",") if p],
            features=[f for f in features.split(",") if f and f not in _EMPTY],
            cpus_total=parse_int(kv.get("CPUTot", "")) or 0,
            cpus_alloc=parse_int(kv.get("CPUAlloc", "")) or 0,
            cpu_load=float(kv["CPULoad"]) if kv.get("CPULoad", "N/A") not in _EMPTY else None,
            mem_total_mb=parse_int(kv.get("RealMemory", "")) or 0,
            mem_alloc_mb=parse_int(kv.get("AllocMem", "")) or 0,
            mem_free_mb=parse_int(kv.get("FreeMem", "")),
            gpus_total=gpus_total,
            gpus_alloc=gpus_alloc,
            gpu_type=gpu_type,
            reason=kv.get("Reason", ""),
        ))
    return nodes


def parse_partitions(text: str) -> list[Partition]:
    parts = []
    for line in text.splitlines():
        kv = parse_key_values(line)
        if "PartitionName" not in kv:
            continue
        tres = parse_tres(kv.get("TRES", ""))
        parts.append(Partition(
            name=kv["PartitionName"],
            state=kv.get("State", ""),
            is_default=kv.get("Default") == "YES",
            nodes=kv.get("Nodes", ""),
            total_nodes=parse_int(kv.get("TotalNodes", "")) or 0,
            total_cpus=parse_int(kv.get("TotalCPUs", "")) or 0,
            total_gpus=parse_int(tres.get("gres/gpu", "")) or 0,
            default_time=parse_duration(kv.get("DefaultTime", "NONE")),
            max_time=parse_duration(kv.get("MaxTime", "UNLIMITED")),
            allow_accounts=kv.get("AllowAccounts", "ALL"),
            deny_accounts=kv.get("DenyAccounts", "") if kv.get("DenyAccounts") not in _EMPTY else "",
            hidden=kv.get("Hidden") == "YES",
        ))
    return parts


def parse_associations(assoc_text: str, share_text: str = "") -> list[Association]:
    shares: dict[str, tuple[float | None, float | None, float | None]] = {}
    for line in share_text.splitlines():
        cols = line.strip().split(SEP)
        if len(cols) >= 7:
            def f(x: str) -> float | None:
                try:
                    return float(x)
                except ValueError:
                    return None
            shares[cols[0].strip()] = (f(cols[6]), f(cols[5]), f(cols[3]))
    out = []
    for line in assoc_text.splitlines():
        cols = line.split(SEP)
        if len(cols) < 8 or not cols[0]:
            continue
        fairshare, usage, norm = shares.get(cols[0], (None, None, None))
        out.append(Association(
            account=cols[0],
            partition=cols[1],
            qos=cols[2],
            grp_tres=parse_tres(cols[3]),
            max_tres=parse_tres(cols[4]),
            max_jobs=parse_int(cols[5]),
            max_submit=parse_int(cols[6]),
            max_wall=parse_duration(cols[7]) if cols[7] else None,
            fairshare=fairshare,
            norm_shares=norm,
            effective_usage=usage,
        ))
    return out


def parse_show_job(text: str) -> dict[str, str]:
    """``scontrol show job -o <id>`` to its raw key/value pairs (for the detail view)."""
    line = next((ln for ln in text.splitlines() if ln.startswith("JobId=")), "")
    return parse_key_values(line)
