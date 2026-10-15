"""My accounts, their limits and fairshare, and the partitions I can see."""

from __future__ import annotations

from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ...services.cluster_state import ClusterState
from ...slurm.models import Association, ClusterInfo, Partition
from ...slurm.parse import format_duration
from ..widgets.common import label, page_header, setup_table


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    setup_table(t)
    t.setSortingEnabled(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(False)
    return t


def _fill(table: QTableWidget, rows: list[list[str]]) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(text))


def _tres(d: dict[str, str]) -> str:
    return ", ".join(f"{k.removeprefix('gres/')}={v}" for k, v in d.items()) or "–"


class AccountPage(QWidget):
    def __init__(self, state: ClusterState) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        self.cluster = label("", "Muted")
        lay.addLayout(page_header("Account and limits", self.cluster))

        lay.addWidget(label("Associations", "SectionTitle"))
        self.assoc = _table(["Account", "Partition", "QOS", "Group limits", "Per-job limits",
                             "Max jobs", "Max wall", "Fairshare", "Usage"])
        lay.addWidget(self.assoc, 1)

        lay.addWidget(label("Partitions", "SectionTitle"))
        self.parts = _table(["Partition", "State", "Nodes", "CPUs", "GPUs", "Default time", "Max time", "Accounts"])
        lay.addWidget(self.parts, 2)

        state.associations_changed.connect(self._on_assocs)
        state.partitions_changed.connect(self._on_parts)
        state.info_changed.connect(self._on_info)

    def _on_info(self, info: ClusterInfo) -> None:
        self.cluster.setText(f"{info.user} on {info.cluster_name or 'cluster'} · Slurm {info.version}")

    def _on_assocs(self, assocs: list[Association]) -> None:
        _fill(self.assoc, [[
            a.account, a.partition or "any", a.qos, _tres(a.grp_tres), _tres(a.max_tres),
            str(a.max_jobs or "–"), format_duration(a.max_wall) if a.max_wall else "–",
            f"{a.fairshare:.3f}" if a.fairshare is not None else "–",
            f"{a.effective_usage:.3f}" if a.effective_usage is not None else "–",
        ] for a in assocs])

    def _on_parts(self, parts: list[Partition]) -> None:
        rows = []
        for p in sorted(parts, key=lambda p: (not p.is_default, p.name)):
            if p.hidden:
                continue
            rows.append([
                p.name + (" (default)" if p.is_default else ""), p.state, str(p.total_nodes), str(p.total_cpus),
                str(p.total_gpus or "–"),
                format_duration(p.default_time) if p.default_time else "–", format_duration(p.max_time),
                p.allow_accounts,
            ])
        _fill(self.parts, rows)
