"""Table model for jobs (queue and history), updated in place so views keep selection and scroll."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..slurm.models import Job
from ..slurm.parse import format_duration
from ..slurm.reasons import explain_reason
from . import theme

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 2


@dataclass(frozen=True)
class Column:
    title: str
    text: Callable[[Job], str]
    sort: Callable[[Job], object] | None = None
    align_right: bool = False


def _when(j: Job) -> str:
    t = j.start_time if (j.is_pending or j.is_active or j.end_time is None) else j.end_time
    return t.strftime("%a %d %b %H:%M") if t else ""


def _reason(j: Job) -> str:
    return j.reason if j.is_pending else j.nodelist


COLUMNS: dict[str, Column] = {
    "id": Column("ID", lambda j: j.job_id, lambda j: (int(j.job_id.split("_")[0]) if j.job_id.split("_")[0].isdigit() else 0, j.job_id)),
    "name": Column("Name", lambda j: j.name),
    "user": Column("User", lambda j: j.user),
    "state": Column("State", lambda j: j.short_state, lambda j: j.state),
    "partition": Column("Partition", lambda j: j.partition),
    "account": Column("Account", lambda j: j.account),
    "elapsed": Column("Elapsed", lambda j: format_duration(j.elapsed), lambda j: j.elapsed, True),
    "limit": Column("Limit", lambda j: format_duration(j.time_limit), lambda j: j.time_limit or 10**12, True),
    "progress": Column("Time used", lambda j: "", lambda j: j.progress if j.progress is not None else -1),
    "gpus": Column("GPUs", lambda j: (f"{j.gpus} {j.gpu_type}".strip() if j.gpus else ""), lambda j: j.gpus, True),
    "cpus": Column("CPUs", lambda j: str(j.cpus or ""), lambda j: j.cpus, True),
    "mem": Column("Memory", lambda j: (f"{j.memory_mb / 1024:.0f}G" if j.memory_mb else ""), lambda j: j.memory_mb or 0, True),
    "where": Column("Node / reason", _reason),
    "when": Column("Start / end", _when, lambda j: (j.end_time or j.start_time or j.submit_time).timestamp() if (j.end_time or j.start_time or j.submit_time) else 0),
    "exit": Column("Exit", lambda j: j.exit_code),
}


class JobTableModel(QAbstractTableModel):
    def __init__(self, columns: list[str]) -> None:
        super().__init__()
        self.columns = [COLUMNS[c] for c in columns]
        self.keys = columns
        self.jobs: list[Job] = []
        self._row: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section].title
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        job = self.jobs[index.row()]
        col = self.columns[index.column()]
        key = self.keys[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return col.text(job)
        if role == SORT_ROLE:
            return (col.sort or col.text)(job)
        if role == PROGRESS_ROLE:
            return job.progress
        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "state":
                return QColor(theme.job_state_color(job.state))
            if key == "where" and job.is_pending:
                return QColor(theme.VIOLET)
            if key == "exit" and job.exit_code not in ("", "0:0"):
                return QColor(theme.RED)
            if key in ("user", "account", "partition", "limit"):
                return QColor(theme.TEXT_MUTED)
        if role == Qt.ItemDataRole.TextAlignmentRole and col.align_right:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if key == "where" and job.is_pending:
                return explain_reason(job.reason)
            if key == "name":
                return f"{job.name}\n{job.work_dir}" if job.work_dir else job.name
        return None

    def job_at(self, row: int) -> Job:
        return self.jobs[row]

    def set_jobs(self, jobs: list[Job]) -> None:
        """Update in place: rows that left are removed, rows that stay are refreshed, new rows appended."""
        new = {j.job_id: j for j in jobs}
        for row in sorted((r for jid, r in self._row.items() if jid not in new), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.jobs[row]
            self.endRemoveRows()
        self.jobs = [new[j.job_id] for j in self.jobs]
        if self.jobs:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.jobs) - 1, len(self.columns) - 1))
        present = {j.job_id for j in self.jobs}
        added = [j for j in jobs if j.job_id not in present]
        if added:
            self.beginInsertRows(QModelIndex(), len(self.jobs), len(self.jobs) + len(added) - 1)
            self.jobs.extend(added)
            self.endInsertRows()
        self._row = {j.job_id: i for i, j in enumerate(self.jobs)}


class JobFilterProxy(QSortFilterProxyModel):
    """Sorts on raw values; filters by text, owner and state group."""

    def __init__(self) -> None:
        super().__init__()
        self.setSortRole(SORT_ROLE)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.user: str | None = None
        self.states: set[str] | None = None
        self.text = ""

    def set_filters(self, *, user: str | None = ..., states: set[str] | None = ..., text: str | None = None) -> None:  # type: ignore[assignment]
        if user is not ...:
            self.user = user
        if states is not ...:
            self.states = states
        if text is not None:
            self.text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:  # noqa: N802
        job = self.sourceModel().job_at(row)
        if self.user and job.user != self.user:
            return False
        if self.states is not None and job.state not in self.states:
            return False
        if self.text:
            hay = f"{job.job_id} {job.name} {job.user} {job.partition} {job.nodelist} {job.reason} {job.account}".lower()
            return all(word in hay for word in self.text.split())
        return True

    def lessThan(self, left, right) -> bool:  # noqa: N802
        a, b = left.data(SORT_ROLE), right.data(SORT_ROLE)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class ProgressDelegate(QStyledItemDelegate):
    """Thin bar showing elapsed / time limit; green, amber above 90 %."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        value = index.data(PROGRESS_ROLE)
        if value is None:
            return
        r = option.rect.adjusted(8, option.rect.height() // 2 - 2, -8, -(option.rect.height() // 2 - 2))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.BORDER))
        painter.drawRoundedRect(r, 2, 2)
        r.setWidth(max(2, int(r.width() * value)))
        painter.setBrush(QColor(theme.AMBER if value > 0.9 else theme.GREEN))
        painter.drawRoundedRect(r, 2, 2)
        painter.restore()
