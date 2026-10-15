"""The live queue (squeue), with filters and job actions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from ...services.cluster_state import ClusterState
from ...slurm.models import ACTIVE_STATES, WAITING_STATES, Job
from ..job_model import JobFilterProxy, JobTableModel, ProgressDelegate
from ..widgets.common import label, page_header, setup_table

COLUMNS = ["id", "name", "user", "state", "partition", "gpus", "cpus", "mem", "elapsed", "progress", "limit", "where", "when"]
_STATE_FILTERS = {"All states": None, "Running": ACTIVE_STATES, "Pending": WAITING_STATES}


class QueuePage(QWidget):
    def __init__(self, state: ClusterState, open_job) -> None:
        super().__init__()
        self.state = state
        self.open_job = open_job
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        self.count = label("", "Muted")
        lay.addLayout(page_header("Queue", self.count))

        bar = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Filter by id, name, node, reason…")
        self.search.setClearButtonEnabled(True)
        self.mine = QPushButton("My jobs", checkable=True, checked=True)
        self.states = QComboBox()
        self.states.addItems(list(_STATE_FILTERS))
        self.cancel_btn = QPushButton("Cancel", objectName="Danger")
        self.hold_btn = QPushButton("Hold")
        self.release_btn = QPushButton("Release")
        bar.addWidget(self.search, 1)
        bar.addWidget(self.mine)
        bar.addWidget(self.states)
        bar.addSpacing(16)
        for b in (self.hold_btn, self.release_btn, self.cancel_btn):
            bar.addWidget(b)
        lay.addLayout(bar)

        self.model = JobTableModel(COLUMNS)
        self.proxy = JobFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        setup_table(self.view)
        self.view.setItemDelegateForColumn(COLUMNS.index("progress"), ProgressDelegate(self.view))
        self.view.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        for col, width in {"id": 80, "name": 230, "user": 90, "state": 55, "partition": 90, "gpus": 110,
                           "cpus": 55, "mem": 70, "elapsed": 90, "progress": 90, "limit": 90, "where": 150}.items():
            self.view.setColumnWidth(COLUMNS.index(col), width)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lay.addWidget(self.view, 1)

        self.search.textChanged.connect(lambda t: self.proxy.set_filters(text=t))
        self.mine.toggled.connect(self._apply_owner)
        self.states.currentTextChanged.connect(lambda t: self.proxy.set_filters(states=_STATE_FILTERS[t]))
        self.cancel_btn.clicked.connect(self.cancel_selected)
        self.hold_btn.clicked.connect(lambda: self._act("hold"))
        self.release_btn.clicked.connect(lambda: self._act("release"))
        self.view.doubleClicked.connect(lambda idx: self.open_job(self._job(idx.row())))
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.selectionModel().selectionChanged.connect(self._update_buttons)

        delete = QAction(self.view)
        delete.setShortcut(QKeySequence.StandardKey.Delete)
        delete.triggered.connect(self.cancel_selected)
        self.view.addAction(delete)

        state.snapshot.connect(self._on_snapshot)
        state.info_changed.connect(lambda _i: self._apply_owner(self.mine.isChecked()))
        self._update_buttons()

    def _apply_owner(self, only_mine: bool) -> None:
        user = self.state.info.user if self.state.info else None
        self.proxy.set_filters(user=user if only_mine else None)
        self._update_count()

    def _on_snapshot(self, jobs: list[Job], _nodes) -> None:
        self.model.set_jobs(jobs)
        self._update_count()
        self._update_buttons()

    def _update_count(self) -> None:
        self.count.setText(f"{self.proxy.rowCount()} shown · {self.model.rowCount()} in queue")

    def _job(self, proxy_row: int) -> Job:
        return self.model.job_at(self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row())

    def selected_jobs(self) -> list[Job]:
        return [self._job(i.row()) for i in self.view.selectionModel().selectedRows()]

    def _own_selected(self) -> list[Job]:
        user = self.state.info.user if self.state.info else None
        return [j for j in self.selected_jobs() if j.user == user]

    def _update_buttons(self) -> None:
        own = self._own_selected()
        self.cancel_btn.setEnabled(bool(own))
        self.hold_btn.setEnabled(any(j.is_pending for j in own))
        self.release_btn.setEnabled(any(j.is_pending for j in own))

    def cancel_selected(self) -> None:
        jobs = self._own_selected()
        if not jobs:
            return
        names = "\n".join(f"{j.job_id}  {j.name}" for j in jobs[:12]) + ("\n…" if len(jobs) > 12 else "")
        answer = QMessageBox.question(self, "Cancel jobs", f"Cancel {len(jobs)} job(s)?\n\n{names}")
        if answer == QMessageBox.StandardButton.Yes:
            self.state.run_action("cancel", [j.job_id for j in jobs])

    def _act(self, action: str) -> None:
        ids = [j.job_id for j in self._own_selected() if j.is_pending]
        self.state.run_action(action, ids)

    def _menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        job = self._job(index.row())
        menu = QMenu(self)
        menu.addAction("Open details", lambda: self.open_job(job))
        menu.addSeparator()
        menu.addAction("Copy job ID", lambda: QApplication.clipboard().setText(job.job_id))
        if job.work_dir:
            menu.addAction("Copy working directory", lambda: QApplication.clipboard().setText(job.work_dir))
        own = self._own_selected()
        if own:
            menu.addSeparator()
            if any(j.is_pending for j in own):
                menu.addAction("Hold", lambda: self._act("hold"))
                menu.addAction("Release", lambda: self._act("release"))
            menu.addAction(f"Cancel {len(own)} job(s)…", self.cancel_selected)
        menu.exec(self.view.viewport().mapToGlobal(pos))
