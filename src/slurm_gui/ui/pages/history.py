"""Finished jobs from accounting (sacct), loaded on demand."""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QTableView, QVBoxLayout, QWidget

from ...services.cluster_state import ClusterState
from ...slurm.models import FAILED_STATES, Job
from .. import theme
from ..job_model import JobFilterProxy, JobTableModel
from ..widgets.common import StatCard, label, page_header, setup_table

COLUMNS = ["id", "name", "state", "exit", "partition", "gpus", "cpus", "mem", "elapsed", "limit", "where", "when"]
_RANGES = {"Last 24 hours": "now-1days", "Last 7 days": "now-7days", "Last 30 days": "now-30days"}


class HistoryPage(QWidget):
    def __init__(self, state: ClusterState, open_job) -> None:
        super().__init__()
        self.state = state
        self.open_job = open_job
        self._loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        self.range = QComboBox()
        self.range.addItems(list(_RANGES))
        self.range.setCurrentText("Last 7 days")
        self.load_btn = QPushButton("Load", objectName="Primary")
        lay.addLayout(page_header("History", self.range, self.load_btn))

        cards = QHBoxLayout()
        self.c_total = StatCard("Jobs")
        self.c_ok = StatCard("Completed", theme.BLUE)
        self.c_failed = StatCard("Failed / timed out", theme.RED)
        self.c_gpuh = StatCard("GPU hours", theme.GREEN)
        for c in (self.c_total, self.c_ok, self.c_failed, self.c_gpuh):
            cards.addWidget(c)
        lay.addLayout(cards)

        self.search = QLineEdit(placeholderText="Filter by id, name, node, state…")
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)

        self.model = JobTableModel(COLUMNS)
        self.proxy = JobFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        setup_table(self.view)
        self.view.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        for col, width in {"id": 80, "name": 260, "state": 55, "exit": 55, "partition": 90, "gpus": 110,
                           "cpus": 55, "mem": 70, "elapsed": 90, "limit": 90, "where": 120}.items():
            self.view.setColumnWidth(COLUMNS.index(col), width)
        lay.addWidget(self.view, 1)
        self.status = label("", "Muted")
        lay.addWidget(self.status)

        self.load_btn.clicked.connect(self.load)
        self.range.currentTextChanged.connect(lambda _t: self.load())
        self.search.textChanged.connect(lambda t: self.proxy.set_filters(text=t))
        self.view.doubleClicked.connect(
            lambda idx: self.open_job(self.model.job_at(self.proxy.mapToSource(idx).row())))
        state.connection_changed.connect(lambda ok: setattr(self, "_loaded", False) if ok else None)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded and self.state.connected:
            self.load()

    def load(self) -> None:
        if not self.state.client:
            return
        self._loaded = True
        self.load_btn.setEnabled(False)
        self.status.setText("Loading accounting data…")
        self.state.call(self.state.client.history(_RANGES[self.range.currentText()]), self._on_loaded, self._on_error)

    def _on_error(self, exc: BaseException) -> None:
        self.load_btn.setEnabled(True)
        self.status.setText(f"Couldn't load history: {exc}")

    def _on_loaded(self, jobs: list[Job]) -> None:
        self.load_btn.setEnabled(True)
        self.model.set_jobs(jobs)
        states = Counter(j.state for j in jobs)
        failed = sum(n for s, n in states.items() if s in FAILED_STATES)
        gpu_hours = sum(j.gpus * j.elapsed for j in jobs) / 3600
        self.c_total.set(str(len(jobs)), ", ".join(f"{n} {s.lower()}" for s, n in states.most_common(3)))
        self.c_ok.set(str(states.get("COMPLETED", 0)))
        self.c_failed.set(str(failed), f"{states.get('TIMEOUT', 0)} timeouts · {states.get('OUT_OF_MEMORY', 0)} OOM")
        self.c_gpuh.set(f"{gpu_hours:.1f}", f"{sum(j.elapsed for j in jobs) / 3600:.1f} wall-clock hours")
        self.status.setText(f"{len(jobs)} jobs · {self.range.currentText().lower()}")
