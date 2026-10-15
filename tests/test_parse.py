from pathlib import Path

import pytest

from slurm_gui.slurm import parse as p
from slurm_gui.slurm.reasons import explain_reason

FIX = Path(__file__).parent / "fixtures"
CLUSTERS = sorted(d.name for d in FIX.iterdir() if d.is_dir())


def read(cluster: str, name: str) -> str:
    return (FIX / cluster / name).read_text()


@pytest.mark.parametrize(
    "text, seconds",
    [("0:00", 0), ("12:34", 754), ("1:02:03", 3723), ("2-00:00:00", 172800), ("7-00:00:00", 604800),
     ("1-12", 129600), ("30", 1800), ("UNLIMITED", None), ("INVALID", None), ("N/A", None)],
)
def test_parse_duration(text, seconds):
    assert p.parse_duration(text) == seconds


def test_format_duration_roundtrip():
    for s in (0, 59, 3723, 172800 + 61):
        assert p.parse_duration(p.format_duration(s)) == s
    assert p.format_duration(None) == "∞"


@pytest.mark.parametrize(
    "text, expected",
    [("gpu:rtx_4090:3(S:0-1)", (3, "rtx_4090")), ("gres/gpu:1", (1, "")), ("gpu:a100:2,shard:a100:8", (2, "a100")),
     ("gres/gpu:rtx_a5000:2", (2, "rtx_a5000")), ("(null)", (0, "")), ("", (0, ""))],
)
def test_gpus_from_gres(text, expected):
    assert p.gpus_from_gres(text) == expected


def test_gpus_from_tres():
    assert p.gpus_from_tres("cpu=10,mem=32G,gres/gpu=2,gres/gpu:rtx_a5000=2") == (2, "rtx_a5000")
    assert p.gpus_from_tres("cpu=4,mem=8G") == (0, "")


def test_memory():
    assert p.parse_memory_mb("64G") == 65536
    assert p.parse_memory_mb("32000M") == 32000
    assert p.parse_memory_mb("4Gc") == 4096
    assert p.parse_memory_mb("") is None


def test_key_values_with_spaces():
    kv = p.parse_key_values("NodeName=n1 OS=Linux 4.18 #1 SMP State=DOWN+DRAIN Reason=Not responding [root@2026-10-01]")
    assert kv["OS"] == "Linux 4.18 #1 SMP"
    assert kv["State"] == "DOWN+DRAIN"
    assert kv["Reason"] == "Not responding [root@2026-10-01]"


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_squeue(cluster):
    jobs = p.parse_squeue(read(cluster, "squeue.txt"))
    assert len(jobs) == len(read(cluster, "squeue.txt").splitlines())
    assert all(j.job_id and j.user and j.state for j in jobs)
    running = [j for j in jobs if j.state == "RUNNING"]
    assert running and all(j.nodelist and j.start_time for j in running)


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_nodes(cluster):
    nodes = p.parse_nodes(read(cluster, "nodes.txt"))
    assert nodes and all(n.cpus_total > 0 for n in nodes)
    assert all(0 <= n.gpus_alloc <= n.gpus_total for n in nodes)


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_partitions(cluster):
    parts = p.parse_partitions(read(cluster, "partitions.txt"))
    assert parts and sum(pt.is_default for pt in parts) <= 1


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_sacct(cluster):
    jobs = p.parse_sacct(read(cluster, "sacct.txt"))
    assert jobs and all(" " not in j.state for j in jobs)


def test_example_cluster():
    """Synthetic cluster in tests/fixtures/example: checks the values, not just the shape."""
    jobs = {j.job_id: j for j in p.parse_squeue(read("example", "squeue.txt"))}
    assert jobs["5002"].name == "eval|ablation-v2"          # separator inside the (last) name field
    assert jobs["5001"].gpus == 2 and jobs["5001"].gpu_type == "a100"
    assert jobs["5020"].gpus == 8                           # 4 per node on 2 nodes
    assert jobs["5011_[3-8]"].is_pending and jobs["5011_[3-8]"].array_job_id == "5011"
    assert jobs["5022"].reason.startswith("ReqNodeNotAvail")
    assert jobs["5010"].elapsed == 2 * 86400 + 3600 and jobs["5010"].time_limit == 7 * 86400

    nodes = {n.name: n for n in p.parse_nodes(read("example", "nodes.txt"))}
    assert (nodes["gpu01"].gpus_total, nodes["gpu01"].gpus_alloc, nodes["gpu01"].gpu_type) == (4, 3, "a100")
    assert nodes["gpu04"].flags == ["DRAIN", "NOT_RESPONDING"] and nodes["gpu04"].is_unavailable
    assert nodes["gpu04"].reason == "GPU 1 fell off the bus [admin@2026-01-14T18:00:00]"
    assert nodes["gpu04"].gpus_free == 0 and nodes["gpu04"].partitions == ["gpu", "maint"]
    assert nodes["gpu05"].flags == ["POWERED_DOWN"] and nodes["gpu05"].gpus_free == 4
    assert nodes["cpu01"].gpus_total == 0 and nodes["cpu01"].features == []

    parts = {pt.name: pt for pt in p.parse_partitions(read("example", "partitions.txt"))}
    assert parts["gpu"].is_default and parts["gpu"].default_time == 3600 and parts["gpu"].max_time == 2 * 86400
    assert parts["cpu"].default_time is None and parts["lab"].max_time is None and parts["maint"].hidden
    assert parts["gpu"].total_gpus == 18
    assert parts["gpu"].allows({"research"}) and parts["lab"].allows({"vision"})
    assert not parts["lab"].allows({"research", "physics"})

    assocs = {a.account: a for a in p.parse_associations(read("example", "assoc.txt"), read("example", "sshare.txt"))}
    research = assocs["research"]
    assert research.grp_tres["gres/gpu"] == "8" and research.max_tres == {"gres/gpu": "4"}
    assert (research.max_jobs, research.max_submit, research.max_wall) == (50, 200, 2 * 86400)
    assert research.fairshare == pytest.approx(0.3125) and research.norm_shares == pytest.approx(0.25)
    assert research.effective_usage == pytest.approx(0.4)
    assert assocs["vision"].partition == "lab"

    info = p.cluster_info("alice\n", read("example", "version.txt"), read("example", "config.txt"))
    assert (info.user, info.version, info.cluster_name) == ("alice", "24.11.3", "example")
    assert info.fairshare_weight == 10000 and info.decay_half_life == 7 * 86400
    assert info.priority_type == "priority/multifactor" and info.max_array_size == 1001

    history = {j.job_id: j for j in p.parse_sacct(read("example", "sacct.txt"))}
    assert history["4904"].state == "CANCELLED"
    assert history["4903"].state == "TIMEOUT" and history["4903"].exit_code == "0:15"
    assert history["4906"].nodelist == "" and history["4906"].start_time is None
    assert history["4901"].gpus == 2 and history["4901"].end_time is not None
    assert history["5001"].end_time is None

    job = p.parse_show_job(read("example", "show_job.txt"))
    assert job["JobState"] == "RUNNING" and job["StdOut"].endswith("5001.out")
    assert job["UserId"] == "alice(1001)"


def test_explain_reason():
    assert "GPU limit" in explain_reason("AssocGrpGRES")
    assert explain_reason("SomethingNew") == "SomethingNew"
