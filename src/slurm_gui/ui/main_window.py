"""The single app window. It switches between three screens:

welcome (saved connections) -> loading (connecting, first data) -> workspace (the cluster).
Disconnecting goes back to the welcome screen. No extra windows are opened for connecting.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QSystemTrayIcon

from ..config.profiles import Profile, load_profiles, save_profiles
from ..config.settings import app_settings
from ..core.async_bridge import AsyncBridge
from ..services.cluster_state import ClusterState, JobEvent
from ..slurm.models import Job
from .job_dialog import JobDialog
from .loading import LoadingPage
from .logo import APP_NAME
from .welcome import WelcomePage
from .workspace import Workspace

WELCOME, LOADING, WORKSPACE = range(3)


class MainWindow(QMainWindow):
    def __init__(self, bridge: AsyncBridge) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 820)
        self.setMinimumSize(900, 600)
        self.state = ClusterState(bridge)
        self._dialogs: list[JobDialog] = []

        self.screens = QStackedWidget()
        self.welcome = WelcomePage()
        self.loading = LoadingPage()
        self.workspace = Workspace(self.state, self.open_job)
        for w in (self.welcome, self.loading, self.workspace):
            self.screens.addWidget(w)
        self.setCentralWidget(self.screens)

        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self) if QSystemTrayIcon.isSystemTrayAvailable() else None

        self.welcome.connect_requested.connect(self.connect_to)
        self.loading.cancelled.connect(self.go_welcome)
        self.workspace.disconnect_requested.connect(self.go_welcome)
        self.workspace.reconnect_requested.connect(lambda: self.state.profile and self.connect_to(self.state.profile))
        self.state.stage.connect(self.loading.set_step)
        self.state.auth_requested.connect(self.loading.ask)
        self.state.connect_failed.connect(self._on_failed)
        self.state.ready.connect(self._on_ready)
        self.state.job_event.connect(self._notify)

        settings = app_settings()
        geometry = settings.value("window/geometry")
        self.restored_geometry = isinstance(geometry, QByteArray) and self.restoreGeometry(geometry)
        self.workspace.nav.setCurrentRow(int(settings.value("window/page", 0)))
        self.screens.setCurrentIndex(WELCOME)

    # ------------------------------------------------------------ screens

    def connect_to(self, profile: Profile) -> None:
        self._close_dialogs()
        self.loading.start(profile.name)
        self.screens.setCurrentIndex(LOADING)
        self.state.connect_to(profile)

    def _on_ready(self) -> None:
        profile = self.state.profile
        profiles = load_profiles()
        for p in profiles:
            if p.name == profile.name:
                p.last_used = datetime.now().isoformat(timespec="seconds")
        save_profiles(profiles)
        self.setWindowTitle(f"{APP_NAME} · {profile.name}")
        if self.tray:
            self.tray.show()
        self.screens.setCurrentIndex(WORKSPACE)

    def _on_failed(self, message: str) -> None:
        if self.screens.currentIndex() == WORKSPACE:   # a reconnect from the workspace failed
            self.workspace.status.showMessage(message, 15000)
            return
        self.welcome.show_error(message)
        self.screens.setCurrentIndex(WELCOME)

    def go_welcome(self) -> None:
        self.state.disconnect()
        self._close_dialogs()
        if self.tray:
            self.tray.hide()
        self.setWindowTitle(APP_NAME)
        self.screens.setCurrentIndex(WELCOME)

    # ------------------------------------------------------------ jobs

    def open_job(self, job: Job) -> None:
        dialog = JobDialog(self.state, job, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(lambda _r, d=dialog: self._dialogs.remove(d) if d in self._dialogs else None)
        self._dialogs.append(dialog)
        dialog.show()

    def _close_dialogs(self) -> None:
        for d in list(self._dialogs):
            d.close()

    def _notify(self, event: JobEvent) -> None:
        if self.tray and event.live and event.kind in {"started", "completed", "failed"}:
            icon = (QSystemTrayIcon.MessageIcon.Warning if event.kind == "failed"
                    else QSystemTrayIcon.MessageIcon.Information)
            self.tray.showMessage(f"Job {event.job_id}", event.text, icon, 8000)

    def closeEvent(self, event) -> None:  # noqa: N802
        settings = app_settings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/page", self.workspace.nav.currentRow())
        self.state.disconnect()
        super().closeEvent(event)
