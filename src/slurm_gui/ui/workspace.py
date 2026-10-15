"""The connected view: header (cluster, refresh, disconnect), sidebar navigation and the pages."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QListWidget, QPushButton, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from ..services.cluster_state import ClusterState
from . import theme
from .pages.account import AccountPage
from .pages.dashboard import DashboardPage
from .pages.history import HistoryPage
from .pages.nodes import NodesPage
from .pages.queue import QueuePage
from .widgets.common import Dot, label

PAGES = ("Dashboard", "Queue", "Nodes", "History", "Account")


class Workspace(QWidget):
    disconnect_requested = pyqtSignal()
    reconnect_requested = pyqtSignal()

    def __init__(self, state: ClusterState, open_job) -> None:
        super().__init__()
        self.state = state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(170)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        self.nav = QListWidget()
        side.addWidget(self.nav)
        body.addWidget(sidebar)

        self.pages = QStackedWidget()
        for title, page in zip(PAGES, (
            DashboardPage(state), QueuePage(state, open_job), NodesPage(state),
            HistoryPage(state, open_job), AccountPage(state),
        )):
            self.nav.addItem(title)
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        self.status = QStatusBar()
        self.updated = label("", "Muted")
        self.status.addPermanentWidget(self.updated)
        outer.addWidget(self.status)

        for i in range(len(PAGES)):
            act = QAction(self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _c=False, i=i: self.nav.setCurrentRow(i))
            self.addAction(act)
        refresh = QAction(self)
        refresh.setShortcuts([QKeySequence.StandardKey.Refresh, QKeySequence("Ctrl+R")])
        refresh.triggered.connect(state.refresh)
        self.addAction(refresh)

        state.connection_changed.connect(self._on_connection)
        state.info_changed.connect(self._on_info)
        state.snapshot.connect(lambda _j, _n: self._tick())
        state.busy_changed.connect(lambda busy: self.refresh_btn.setText("Refreshing…" if busy else "Refresh"))
        state.error.connect(lambda msg: self.status.showMessage(msg, 15000))
        state.message.connect(lambda msg: self.status.showMessage(msg, 6000))
        self.clock = QTimer(self, interval=1000)
        self.clock.timeout.connect(self._tick)
        self.clock.start()

    def _build_header(self) -> QWidget:
        header = QFrame(objectName="Header")
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 8, 14, 8)
        self.dot = Dot(theme.GREEN)
        self.cluster_name = label("")
        self.cluster_name.setStyleSheet("font-weight: 600;")
        self.cluster_detail = label("", "Muted")
        self.refresh_btn = QPushButton("Refresh")
        self.reconnect_btn = QPushButton("Reconnect", objectName="Primary")
        self.reconnect_btn.hide()
        disconnect = QPushButton("Disconnect", objectName="Danger")
        row.addWidget(self.dot)
        row.addWidget(self.cluster_name)
        row.addWidget(self.cluster_detail)
        row.addStretch()
        for b in (self.refresh_btn, self.reconnect_btn, disconnect):
            row.addWidget(b)
        self.refresh_btn.clicked.connect(lambda: self.state.refresh())
        self.reconnect_btn.clicked.connect(self.reconnect_requested)
        disconnect.clicked.connect(self.disconnect_requested)
        return header

    def _on_connection(self, ok: bool) -> None:
        self.dot.set_color(theme.GREEN if ok else theme.RED)
        self.refresh_btn.setVisible(ok)
        self.reconnect_btn.setVisible(not ok)
        if not ok:
            self.cluster_detail.setText("connection lost")
            self.updated.setText("")

    def _on_info(self, info) -> None:
        p = self.state.profile
        self.cluster_name.setText(p.name if p else info.cluster_name)
        self.cluster_detail.setText(f"{info.user}@{p.host if p else ''} · Slurm {info.version}")

    def _tick(self) -> None:
        if self.state.last_update and self.state.connected:
            ago = int((datetime.now() - self.state.last_update).total_seconds())
            self.updated.setText(f"updated {ago}s ago · every {self.state.profile.refresh_seconds}s")
