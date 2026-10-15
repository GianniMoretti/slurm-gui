"""Job details: the full ``scontrol show job`` record and a live tail of its output files."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QHeaderView, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..services.cluster_state import ClusterState
from ..slurm.models import Job
from ..slurm.parse import format_duration
from ..slurm.reasons import explain_reason
from . import theme
from .widgets.common import label, setup_table

# The fields worth reading first; everything else follows alphabetically.
_FIRST = ["JobId", "JobName", "UserId", "Account", "Partition", "QOS", "JobState", "Reason", "ExitCode",
          "SubmitTime", "StartTime", "EndTime", "RunTime", "TimeLimit", "NodeList", "NumNodes", "NumCPUs",
          "AllocTRES", "ReqTRES", "Features", "Dependency", "WorkDir", "Command", "StdOut", "StdErr"]
_LOG_LINES = 1000


class LogView(QWidget):
    def __init__(self, state: ClusterState, path: str) -> None:
        super().__init__()
        self.state, self.path = state, path
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(label(path, "Muted"), 1)
        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        refresh = QPushButton("Refresh")
        top.addWidget(self.follow)
        top.addWidget(refresh)
        lay.addLayout(top)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont()
        font.setFamilies([f.strip() for f in theme.MONO.split(",")])
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text.setFont(font)
        self.text.setStyleSheet(f"background: #0a0c11; color: {theme.TEXT};")
        lay.addWidget(self.text, 1)
        refresh.clicked.connect(self.load)
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.follow.isChecked() and self.load())
        self.timer.start(5000)
        self.load()

    def load(self) -> None:
        if self.state.client:
            self.state.call(self.state.client.tail(self.path, _LOG_LINES), self._show,
                            lambda exc: self.text.setPlainText(f"Couldn't read the file: {exc}"))

    def _show(self, content: str) -> None:
        bar = self.text.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        if content != self.text.toPlainText():
            self.text.setPlainText(content)
            if at_bottom or self.follow.isChecked():
                self.text.moveCursor(QTextCursor.MoveOperation.End)


class JobDialog(QDialog):
    def __init__(self, state: ClusterState, job: Job, parent=None) -> None:
        super().__init__(parent)
        self.state, self.job = state, job
        self.setWindowTitle(f"Job {job.job_id} · {job.name}")
        self.resize(980, 680)
        lay = QVBoxLayout(self)

        head = QHBoxLayout()
        title = label(f"{job.job_id}  {job.name}", "PageTitle")
        st = label(job.state)
        st.setStyleSheet(f"color: {theme.job_state_color(job.state)}; font-weight: 600;")
        head.addWidget(title)
        head.addWidget(st)
        head.addStretch()
        mine = state.info is not None and job.user == state.info.user
        if mine and (job.is_active or job.is_pending):
            cancel = QPushButton("Cancel job", objectName="Danger")
            cancel.clicked.connect(self._cancel)
            head.addWidget(cancel)
        lay.addLayout(head)

        summary = f"{job.user} · {job.partition} · {job.gpus} GPU {job.gpu_type} · {job.cpus} CPUs · " \
                  f"{format_duration(job.elapsed)} of {format_duration(job.time_limit)}"
        lay.addWidget(label(summary, "Muted"))
        if job.is_pending and job.reason:
            why = label(f"Pending: {explain_reason(job.reason)} ({job.reason})", wrap=True)
            why.setStyleSheet(f"color: {theme.VIOLET};")
            lay.addWidget(why)

        self.tabs = QTabWidget()
        self.info = QTableWidget(0, 2)
        self.info.setHorizontalHeaderLabels(["Field", "Value"])
        setup_table(self.info)
        self.info.setSortingEnabled(False)
        self.info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.info.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.info, "Details")
        lay.addWidget(self.tabs, 1)
        self.status = label("Loading…", "Muted")
        lay.addWidget(self.status)

        if state.client:
            state.call(state.client.job_details(job.job_id), self._on_details, self._on_missing)

    def _on_missing(self, _exc: BaseException) -> None:
        self.status.setText("The controller no longer has this job (it finished a while ago); "
                            "only accounting data is available.")
        rows = [("JobId", self.job.job_id), ("JobName", self.job.name), ("State", self.job.state),
                ("ExitCode", self.job.exit_code), ("NodeList", self.job.nodelist), ("WorkDir", self.job.work_dir)]
        self._fill(rows)

    def _on_details(self, kv: dict[str, str]) -> None:
        self.status.setText("")
        keys = [k for k in _FIRST if k in kv] + sorted(k for k in kv if k not in _FIRST)
        self._fill([(k, kv[k]) for k in keys])
        logs = []
        for key in ("StdOut", "StdErr"):
            path = kv.get(key, "")
            if path and path != "/dev/null" and path not in logs:
                logs.append(path)
        for i, path in enumerate(logs):
            self.tabs.addTab(LogView(self.state, path), "Output" if i == 0 else "Errors")
        if logs and (self.job.is_active or not self.job.is_pending):
            self.tabs.setCurrentIndex(1)

    def _fill(self, rows: list[tuple[str, str]]) -> None:
        self.info.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            key = QTableWidgetItem(k)
            key.setForeground(Qt.GlobalColor.gray)
            self.info.setItem(r, 0, key)
            self.info.setItem(r, 1, QTableWidgetItem(v))

    def _cancel(self) -> None:
        answer = QMessageBox.question(self, "Cancel job", f"Cancel job {self.job.job_id} ({self.job.name})?")
        if answer == QMessageBox.StandardButton.Yes:
            self.state.run_action("cancel", [self.job.job_id])
            self.accept()
