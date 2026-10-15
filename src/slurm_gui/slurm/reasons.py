"""Plain-English explanations of the most common pending reasons."""

from __future__ import annotations

_REASONS = {
    "Priority": "Waiting for jobs with higher priority to start first",
    "Resources": "Next in line; waiting for enough resources to free up",
    "Dependency": "Waiting for a job it depends on to finish",
    "DependencyNeverSatisfied": "A dependency can never be met (it failed or was cancelled); cancel this job",
    "BeginTime": "Its requested start time has not been reached",
    "JobHeldUser": "Held by you; release it to let it run",
    "JobHeldAdmin": "Held by an administrator",
    "ReqNodeNotAvail": "A requested node is down, drained or reserved",
    "PartitionTimeLimit": "Requested time exceeds the partition limit; it will never start",
    "PartitionNodeLimit": "Requested node count exceeds the partition limit",
    "PartitionDown": "The partition is down",
    "PartitionInactive": "The partition is inactive",
    "QOSMaxJobsPerUserLimit": "You already run the maximum number of jobs allowed by your QOS",
    "QOSMaxGRESPerUser": "You already use the maximum number of GPUs allowed by your QOS",
    "QOSMaxCpuPerUserLimit": "You already use the maximum number of CPUs allowed by your QOS",
    "QOSGrpGRES": "Your QOS group is at its GPU limit",
    "AssocGrpGRES": "Your account is at its GPU limit; it starts when one of its jobs ends",
    "AssocGrpCpuLimit": "Your account is at its CPU limit",
    "AssocGrpMemLimit": "Your account is at its memory limit",
    "AssocGrpJobsLimit": "Your account runs the maximum number of jobs",
    "AssocMaxJobsLimit": "You run the maximum number of jobs for this account",
    "AssocGrpSubmitJobsLimit": "Your account has the maximum number of queued jobs",
    "Reservation": "Waiting for its reservation to become active",
    "launch failed requeued held": "Launch failed; requeued and held (release it to retry)",
    "BadConstraints": "The requested constraints cannot be satisfied by any node",
    "InvalidAccount": "The account is invalid for this partition",
    "InvalidQOS": "The QOS is invalid for this account or partition",
    "NodeDown": "A node required by the job is down",
    "Licenses": "Waiting for licenses",
    "None": "",
}


def explain_reason(reason: str) -> str:
    """A human sentence for a pending reason; the raw reason when it is not known."""
    reason = reason.strip().strip("()")
    if reason in _REASONS:
        return _REASONS[reason]
    for key, text in _REASONS.items():
        if key and reason.startswith(key):
            return text
    return reason
