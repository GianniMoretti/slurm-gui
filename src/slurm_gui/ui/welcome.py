"""Entry screen: logo, saved connections as clickable cards, and an inline editor to add or edit one."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..config.profiles import MIN_REFRESH_SECONDS, Profile, load_profiles, save_profiles, ssh_config_hosts
from ..config.settings import config_dir
from . import theme
from .logo import APP_NAME, logo_pixmap
from .widgets.common import label


def _ago(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "never connected"
    secs = int((datetime.now() - then).total_seconds())
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if secs >= size:
            n = secs // size
            return f"last used {n} {unit}{'s' if n > 1 else ''} ago"
    return "last used just now"


class ConnectionCard(QFrame):
    """A saved connection. Click to connect; Edit and Delete on the right."""

    clicked = pyqtSignal()
    edit = pyqtSignal()
    delete = pyqtSignal()

    def __init__(self, profile: Profile) -> None:
        super().__init__()
        self.setObjectName("ConnectionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(76)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 10, 10)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = label(profile.name)
        name.setStyleSheet("font-size: 15px; font-weight: 600; background: transparent;")
        target = f"{profile.user}@{profile.host}" if profile.user else profile.host
        text.addWidget(name)
        text.addWidget(label(f"{target} · {_ago(profile.last_used) if profile.last_used else 'never connected'}", "Muted"))
        lay.addLayout(text, 1)
        edit = QPushButton("Edit", objectName="Link")
        self.delete_btn = QPushButton("Delete", objectName="Link")
        for b in (edit, self.delete_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
        edit.clicked.connect(self.edit)
        self.delete_btn.clicked.connect(self._delete_clicked)
        self._armed = False
        self._disarm_timer = QTimer(self, singleShot=True, interval=3000)   # dies with the card
        self._disarm_timer.timeout.connect(self._disarm)
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {theme.BLUE}; font-size: 18px; background: transparent; padding-left: 6px;")
        lay.addWidget(arrow)

    def _delete_clicked(self) -> None:
        """Delete needs a second click within 3 seconds, so no confirmation popup is needed."""
        if self._armed:
            self.delete.emit()
            return
        self._armed = True
        self.delete_btn.setText("Click again to delete")
        self.delete_btn.setStyleSheet(f"color: {theme.RED};")
        self._disarm_timer.start()

    def _disarm(self) -> None:
        self._armed = False
        self.delete_btn.setText("Delete")
        self.delete_btn.setStyleSheet("")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProfileEditor(QWidget):
    saved = pyqtSignal(object, bool)   # (Profile, connect now)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._original: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.title = label("New connection", "SectionTitle")
        lay.addWidget(self.title)
        lay.addWidget(label("The host can be an alias from ~/.ssh/config: user, port, keys and ProxyJump "
                            "are then taken from there.", "Muted", wrap=True))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(10)
        self.name = QLineEdit(placeholderText="My cluster")
        self.host = QComboBox(editable=True)
        self.host.addItems(ssh_config_hosts())
        self.host.lineEdit().setPlaceholderText("login.cluster.example.org")
        self.user = QLineEdit(placeholderText="from ~/.ssh/config")
        self.port = QSpinBox(minimum=0, maximum=65535, specialValueText="default")
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        self.key = QLineEdit(placeholderText="from ~/.ssh/config or ssh-agent")
        browse = QPushButton("Browse…")
        key_row.addWidget(self.key, 1)
        key_row.addWidget(browse)
        key_holder = QWidget()
        key_holder.setLayout(key_row)
        self.refresh = QSpinBox(minimum=MIN_REFRESH_SECONDS, maximum=600, suffix=" s", value=30)
        self.login = QCheckBox("Run commands in a login shell (loads modules and PATH from your profile)")
        form.addRow("Name", self.name)
        form.addRow("Host", self.host)
        form.addRow("User", self.user)
        form.addRow("Port", self.port)
        form.addRow("Key file", key_holder)
        form.addRow("Refresh every", self.refresh)
        form.addRow("", self.login)
        lay.addLayout(form)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color: {theme.RED}; background: transparent;")
        lay.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        go = QPushButton("Save and connect", objectName="Primary")
        for b in (cancel, save, go):
            buttons.addWidget(b)
        lay.addLayout(buttons)

        browse.clicked.connect(self._browse)
        cancel.clicked.connect(self.cancelled)
        save.clicked.connect(lambda: self._emit(False))
        go.clicked.connect(lambda: self._emit(True))

    def edit(self, profile: Profile | None) -> None:
        self._original = profile.name if profile else None
        self.title.setText(f"Edit {profile.name}" if profile else "New connection")
        p = profile or Profile(name="", host="")
        self.name.setText(p.name)
        self.host.setCurrentText(p.host)
        self.user.setText(p.user)
        self.port.setValue(p.port or 0)
        self.key.setText(p.key_file)
        self.refresh.setValue(p.refresh_seconds)
        self.login.setChecked(p.login_shell)
        self.error.clear()
        self._last_used = p.last_used
        self.name.setFocus()

    def _browse(self) -> None:
        # Start where the current key is, else in ~/.ssh (the same on Linux, macOS and Windows).
        current = Path(self.key.text().strip()).expanduser()
        ssh_dir = Path.home() / ".ssh"
        start = current.parent if current.parent.is_dir() and self.key.text().strip() else (
            ssh_dir if ssh_dir.is_dir() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "SSH private key", str(start), "All files (*)")
        if path:
            self.key.setText(path)

    def _emit(self, connect: bool) -> None:
        host = self.host.currentText().strip()
        if not host:
            self.error.setText("Enter a host name or an ~/.ssh/config alias.")
            return
        name = self.name.text().strip() or host
        if name != self._original and any(p.name == name for p in load_profiles()):
            self.error.setText(f"A connection called “{name}” already exists.")
            return
        profile = Profile(
            name=name, host=host, user=self.user.text().strip(), port=self.port.value() or None,
            key_file=self.key.text().strip(), refresh_seconds=self.refresh.value(),
            login_shell=self.login.isChecked(), last_used=self._last_used,
        )
        profiles = load_profiles()
        names = [p.name for p in profiles]
        if self._original in names:
            profiles[names.index(self._original)] = profile
        else:
            profiles.append(profile)
        save_profiles(profiles)
        self.saved.emit(profile, connect)


class WelcomePage(QWidget):
    connect_requested = pyqtSignal(object)   # Profile

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        holder = QWidget()
        scroll.setWidget(holder)
        center = QHBoxLayout(holder)
        center.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(620)
        column.setMinimumWidth(460)
        center.addWidget(column, 3)
        center.addStretch(1)

        lay = QVBoxLayout(column)
        lay.setContentsMargins(0, 48, 0, 24)
        lay.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo.setStyleSheet("background: transparent;")
        lay.addWidget(logo)
        title = label(APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-size: 26px; font-weight: 700; background: transparent;")
        lay.addWidget(title)
        sub = label("Choose a cluster to connect to", "Muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)
        lay.addSpacing(18)

        self.banner = label("", wrap=True)
        self.banner.setObjectName("ErrorBanner")
        self.banner.hide()
        lay.addWidget(self.banner)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        list_page = QWidget()
        lp = QVBoxLayout(list_page)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label("Saved connections", "SectionTitle"))
        head.addStretch()
        add = QPushButton("+  Add connection", objectName="Primary")
        head.addWidget(add)
        lp.addLayout(head)
        self.cards = QGridLayout()
        self.cards.setSpacing(10)
        lp.addLayout(self.cards)
        self.empty = label("No saved connections yet. Add one to get started.", "Muted", wrap=True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lp.addWidget(self.empty)
        lp.addStretch()
        self.stack.addWidget(list_page)

        self.editor = ProfileEditor()
        self.stack.addWidget(self.editor)
        lay.addStretch()

        shown = str(config_dir()).replace(str(Path.home()), "~", 1)
        folder = QPushButton(f"Settings folder: {shown}", objectName="Link")
        folder.setToolTip("Open the folder with your saved connections and settings")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir()))))
        lay.addWidget(folder, 0, Qt.AlignmentFlag.AlignHCenter)

        add.clicked.connect(lambda: self._open_editor(None))
        self.editor.cancelled.connect(lambda: self.stack.setCurrentIndex(0))
        self.editor.saved.connect(self._on_saved)
        self.reload()

    def show_error(self, message: str) -> None:
        self.banner.setText(message)
        self.banner.setVisible(bool(message))

    def reload(self) -> None:
        while self.cards.count():
            self.cards.takeAt(0).widget().deleteLater()
        profiles = sorted(load_profiles(), key=lambda p: p.last_used, reverse=True)
        for row, profile in enumerate(profiles):
            card = ConnectionCard(profile)
            card.clicked.connect(lambda p=profile: self._connect(p))
            card.edit.connect(lambda p=profile: self._open_editor(p))
            card.delete.connect(lambda p=profile: self._delete(p))
            self.cards.addWidget(card, row, 0)
        self.empty.setVisible(not profiles)
        self.stack.setCurrentIndex(0)

    def _open_editor(self, profile: Profile | None) -> None:
        self.show_error("")
        self.editor.edit(profile)
        self.stack.setCurrentIndex(1)

    def _on_saved(self, profile: Profile, connect: bool) -> None:
        self.reload()
        if connect:
            self._connect(profile)

    def _connect(self, profile: Profile) -> None:
        self.show_error("")
        self.connect_requested.emit(profile)

    def _delete(self, profile: Profile) -> None:
        save_profiles([p for p in load_profiles() if p.name != profile.name])
        self.reload()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.Show:
            self.reload()
        return super().event(e)
