"""Anonymize captured SLURM outputs before they are committed as test fixtures.

Other users' names become ``userNN``; their job names and working directories are replaced
with neutral placeholders. The user given with ``--keep`` (normally yourself) is left as is.
Expects the files written by ``scripts/capture_fixtures.py``.

    python scripts/anonymize_fixtures.py tests/fixtures/<cluster> --keep <your-username>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slurm_gui.slurm.commands import SACCT_FIELDS, SEP, SQUEUE_FIELDS  # noqa: E402

_SQ = {name: i for i, (name, _) in enumerate(SQUEUE_FIELDS)}
_SA = {name: i for i, name in enumerate(SACCT_FIELDS)}


def _rows(path: Path) -> list[list[str]]:
    return [line.split(SEP) for line in path.read_text().splitlines() if line] if path.exists() else []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--keep", required=True, help="username to leave untouched")
    args = parser.parse_args()
    squeue, sacct = args.folder / "squeue.txt", args.folder / "sacct.txt"

    users = {r[_SQ["user"]] for r in _rows(squeue)} | {r[_SA["User"]] for r in _rows(sacct)}
    users -= {args.keep, ""}
    mapping = {user: f"user{i + 1:02d}" for i, user in enumerate(sorted(users))}

    def scrub(path: Path, user_col: int, id_col: int, name_col: int, dir_col: int) -> None:
        out = []
        for row in _rows(path):
            if row[user_col] in mapping:
                anon = mapping[row[user_col]]
                row[name_col] = f"job{row[id_col]}"
                row[dir_col] = f"/home/{anon}/work"
            out.append(SEP.join(row))
        path.write_text("\n".join(out) + "\n")

    if squeue.exists():
        scrub(squeue, _SQ["user"], _SQ["job_id"], len(SQUEUE_FIELDS) - 1, _SQ["work_dir"])
    if sacct.exists():
        scrub(sacct, _SA["User"], _SA["JobID"], len(SACCT_FIELDS) - 1, _SA["WorkDir"])

    if mapping:
        word = re.compile(r"\b(" + "|".join(map(re.escape, mapping)) + r")\b")
        for path in args.folder.iterdir():
            path.write_text(word.sub(lambda m: mapping[m.group(1)], path.read_text()))
    print(f"anonymized {len(mapping)} users in {args.folder}")


if __name__ == "__main__":
    main()
