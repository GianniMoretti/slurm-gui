"""Capture the read-only SLURM outputs the parsers are tested against.

Runs only query commands (squeue, scontrol show, sacct, sacctmgr show, sshare) over SSH and
writes one file per command into ``tests/fixtures/<name>``. Anonymize them before committing:

    python scripts/capture_fixtures.py <ssh-host> <name>
    python scripts/anonymize_fixtures.py tests/fixtures/<name> --keep <your-username>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slurm_gui.slurm import commands as c  # noqa: E402

MARK = "@@@FIXTURE "


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", help="ssh host or alias")
    parser.add_argument("name", help="fixture folder name, e.g. the cluster name")
    args = parser.parse_args()

    queries = {
        "version.txt": c.VERSION,
        "squeue.txt": c.SQUEUE,
        "nodes.txt": c.NODES,
        "partitions.txt": c.PARTITIONS,
        "config.txt": c.CONFIG,
        "assoc.txt": c.ASSOCIATIONS,
        "sshare.txt": c.FAIRSHARE,
        "sacct.txt": c.sacct("now-5days"),
        "show_job.txt": "scontrol show job -o $(squeue -h -u $USER -o %i | head -1)",
    }
    script = f"echo '{MARK}START'\n" + "".join(f"echo '{MARK}{n}'; {cmd}\n" for n, cmd in queries.items())
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", args.host, "bash -s"],
        input=script, capture_output=True, text=True, check=True,
    ).stdout
    out = out[out.index(f"{MARK}START") + len(MARK) + 6:]

    folder = ROOT / "tests" / "fixtures" / args.name
    folder.mkdir(parents=True, exist_ok=True)
    for block in out.split(MARK)[1:]:
        name, body = block.split("\n", 1)
        (folder / name).write_text(body)
    print(f"wrote {len(queries)} files to {folder}")


if __name__ == "__main__":
    main()
