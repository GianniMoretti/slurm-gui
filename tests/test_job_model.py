import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from slurm_gui.slurm.models import Job  # noqa: E402
from slurm_gui.ui.job_model import JobTableModel  # noqa: E402

app = QApplication.instance() or QApplication([])


def job(jid: str, state: str = "RUNNING") -> Job:
    return Job(job_id=jid, name=f"n{jid}", user="me", state=state)


def test_set_jobs_updates_in_place():
    m = JobTableModel(["id", "state"])
    m.set_jobs([job("1"), job("2"), job("3")])
    removed, inserted = [], []
    m.rowsRemoved.connect(lambda _p, a, b: removed.append((a, b)))
    m.rowsInserted.connect(lambda _p, a, b: inserted.append((a, b)))
    m.set_jobs([job("3", "COMPLETING"), job("1"), job("4")])
    assert [j.job_id for j in m.jobs] == ["1", "3", "4"]
    assert m.jobs[1].state == "COMPLETING"
    assert removed == [(1, 1)] and inserted == [(2, 2)]
