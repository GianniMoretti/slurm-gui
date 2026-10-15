"""Overview: my jobs, my GPU budget, free GPUs on the cluster, and recent events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGridLayout, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ...services.cluster_state import ClusterState, JobEvent
from ...slurm.models import Association, ClusterInfo, Job, Node
from ...slurm.parse import format_duration
from .. import theme
from ..widgets.common import StatCard, UsageBar, label, page_header

_EVENT_COLORS = {"started": theme.GREEN, "completed": theme.BLUE, "failed": theme.RED,
                 "cancelled": theme.TEXT_MUTED, "submitted": theme.VIOLET, "left": theme.TEXT_MUTED}


def gpu_limit(assocs: list[Association], account: str | None) -> int | None:
    """The group GPU limit of ``account`` (or of the first account that has one)."""
    for a in sorted(assocs, key=lambda a: a.account != account):
        value = a.grp_tres.get("gres/gpu") or a.max_tres.get("gres/gpu")
        if value and value.isdigit():
            return int(value)
    return None


def fairshare_help(main: Association, all_assocs: list[Association], info: ClusterInfo) -> str:
    """Hover text for the fairshare card, with this cluster's own numbers."""
    def pct(x: float | None) -> str:
        return "–" if x is None else f"{x * 100:.2f}%"

    half_life = info.decay_half_life
    decay = (f"Past usage is forgotten gradually: it counts half after {half_life // 86400} days"
             if half_life and half_life % 86400 == 0 else
             f"Past usage is forgotten gradually (half-life {format_duration(half_life)})" if half_life else
             "Past usage is forgotten gradually over time")
    if info.fairshare_weight == 0:
        verdict = ("<p style='color:%s'><b>On this cluster fairshare has no effect:</b> "
                   "PriorityWeightFairShare is 0, so it does not change job priority. "
                   "Jobs are ordered by other factors (often simply submission order).</p>" % theme.AMBER)
    elif info.priority_type and "multifactor" not in info.priority_type:
        verdict = (f"<p style='color:{theme.AMBER}'><b>This cluster uses {info.priority_type}</b>: "
                   "jobs start in submission order and fairshare is not used.</p>")
    else:
        verdict = (f"<p>Here it weighs <b>{info.fairshare_weight}</b> in the job priority "
                   "(PriorityWeightFairShare).</p>" if info.fairshare_weight else "")
    where = ""
    if main.norm_shares is not None and main.effective_usage is not None:
        more = main.effective_usage > main.norm_shares
        where = (f"<p><b>{main.account}</b>: entitled to {pct(main.norm_shares)} of the cluster, "
                 f"recent usage {pct(main.effective_usage)}. You have used "
                 f"<b>{'more' if more else 'less'}</b> than your share, so your priority "
                 f"{'would be' if info.fairshare_weight == 0 else 'is'} <b>{'lower' if more else 'higher'}</b>.</p>")
    others = "".join(f"<br>{a.account}: {a.fairshare:.3f}" for a in all_assocs if a is not main)
    return (
        f"<div style='max-width:380px'><b>Fairshare: {main.fairshare:.3f}</b> ({main.account})"
        "<p>Fairshare decides whose jobs go first when several users compete for the same resources. "
        "It runs from 0 to 1.</p>"
        "<ul style='margin-left:-20px'>"
        "<li>Each account is entitled to a share of the cluster.</li>"
        "<li>SLURM compares that share with how much the account used recently.</li>"
        "<li>Used less than your share: close to 1, your jobs move up. "
        "Used more: towards 0, others go first.</li>"
        f"<li>{decay}, so a busy week is not held against you forever.</li>"
        "</ul>"
        f"{where}{verdict}"
        + (f"<p style='color:{theme.TEXT_MUTED}'>Other accounts:{others}</p>" if others else "")
        + "</div>"
    )


class DashboardPage(QWidget):
    def __init__(self, state: ClusterState) -> None:
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)
        lay.addLayout(page_header("Dashboard"))

        cards = QGridLayout()
        cards.setSpacing(12)
        self.running = StatCard("Running", theme.GREEN)
        self.pending = StatCard("Pending", theme.VIOLET)
        self.gpus = StatCard("My GPUs / limit", theme.BLUE)
        self.fairshare = StatCard("Fairshare", theme.TEXT)
        for i, card in enumerate((self.running, self.pending, self.gpus, self.fairshare)):
            cards.addWidget(card, 0, i)
        lay.addLayout(cards)

        lower = QGridLayout()
        lower.setSpacing(12)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 1)
        lower.addWidget(label("Free GPUs you can use", "SectionTitle"), 0, 0)
        activity_head = QVBoxLayout()
        activity_head.setSpacing(2)
        activity_head.addWidget(label("Activity", "SectionTitle"))
        activity_head.addWidget(label("Your jobs in the last 24 hours, then live changes", "Muted"))
        lower.addLayout(activity_head, 0, 1)
        self.free_box = QVBoxLayout()
        self.free_box.setSpacing(8)
        free_holder = QWidget()
        free_holder.setLayout(self.free_box)
        lower.addWidget(free_holder, 1, 0, Qt.AlignmentFlag.AlignTop)
        self.events = QListWidget()
        self.events.setMinimumHeight(200)
        lower.addWidget(self.events, 1, 1)
        lay.addLayout(lower, 1)

        state.snapshot.connect(self._on_snapshot)
        state.associations_changed.connect(lambda _a: self._on_snapshot(state.jobs, state.nodes))
        state.job_event.connect(self.add_event)
        state.connection_changed.connect(lambda ok: ok or self.events.clear())

    def _on_snapshot(self, jobs: list[Job], nodes: list[Node]) -> None:
        if not self.state.info:
            return
        mine = [j for j in jobs if j.user == self.state.info.user]
        running = [j for j in mine if j.is_active]
        pending = [j for j in mine if j.is_pending]
        self.running.set(str(len(running)), f"{sum(j.gpus for j in running)} GPUs, {sum(j.cpus for j in running)} CPUs")
        reasons = defaultdict(int)
        for j in pending:
            reasons[j.reason] += 1
        top = ", ".join(f"{n}× {r}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:2])
        self.pending.set(str(len(pending)), top)

        used = sum(j.gpus for j in running)
        main_account = max((j.account for j in mine), key=[j.account for j in mine].count, default=None)
        limit = gpu_limit(self.state.associations, main_account)
        if limit:
            self.gpus.set(f"{used} / {limit}", main_account or "", used / limit)
        else:
            self.gpus.set(str(used), "no group limit")

        fs = [a for a in self.state.associations if a.fairshare is not None]
        best = next((a for a in fs if a.account == main_account), fs[0] if fs else None)
        if best:
            ignored = self.state.info.fairshare_weight == 0
            note = "not used for priority here" if ignored else "higher is better"
            self.fairshare.set(f"{best.fairshare:.3f}", f"{best.account} · {note}", best.fairshare)
            self.fairshare.setToolTip(fairshare_help(best, fs, self.state.info))
        self._show_free_gpus(nodes)

    def _show_free_gpus(self, nodes: list[Node]) -> None:
        while self.free_box.count():
            item = self.free_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    item.layout().takeAt(0).widget().deleteLater()
            elif item.widget():
                item.widget().deleteLater()
        total: dict[str, int] = defaultdict(int)
        free: dict[str, int] = defaultdict(int)
        accounts = {a.account for a in self.state.associations}
        usable = {p.name for p in self.state.partitions if p.allows(accounts)} if accounts else None
        for n in nodes:
            if n.gpus_total and (usable is None or usable & set(n.partitions)):
                kind = n.gpu_type or "gpu"
                total[kind] += 0 if n.is_unavailable else n.gpus_total
                free[kind] += n.gpus_free
        if not total:
            self.free_box.addWidget(label("No GPU nodes found", "Muted"))
        total = {k: v for k, v in total.items() if v}   # types only on down/drained nodes are not usable
        if not total:
            self.free_box.addWidget(label("No GPUs available right now", "Muted"))
        for kind in sorted(total, key=lambda k: (-free[k], k)):
            row = QGridLayout()
            row.addWidget(label(kind), 0, 0)
            count = label(f"{free[kind]} free of {total[kind]}", "Muted")
            row.addWidget(count, 0, 1, Qt.AlignmentFlag.AlignRight)
            bar = UsageBar(theme.GREEN)
            bar.set_fraction(free[kind] / total[kind] if total[kind] else 0)
            row.addWidget(bar, 1, 0, 1, 2)
            self.free_box.addLayout(row)

    def add_event(self, event: JobEvent) -> None:
        when = f"{event.time:%H:%M}" if event.time.date() == datetime.now().date() else f"{event.time:%d %b %H:%M}"
        item = QListWidgetItem(f"{when}  {event.job_id}  {event.text}")
        item.setForeground(QColor(_EVENT_COLORS.get(event.kind, theme.TEXT)))
        self.events.insertItem(0, item)
        while self.events.count() > 200:
            self.events.takeItem(self.events.count() - 1)
