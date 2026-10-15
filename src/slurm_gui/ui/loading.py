"""Shown between choosing a connection and the first data: a spinner, the current step, and inline
password / 2FA prompts when the server asks for them."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import theme
from .logo import logo_pixmap
from .widgets.common import label


class Spinner(QWidget):
    def __init__(self, size: int = 44) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._step)

    def _step(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def showEvent(self, e) -> None:  # noqa: N802
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        p.setPen(QPen(QColor(theme.BORDER), 4))
        p.drawEllipse(r)
        for color, offset, span in ((theme.VIOLET, 0, 100), (theme.BLUE, 180, 60)):
            pen = QPen(QColor(color), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(r, -(self._angle + offset) * 16, span * 16)


class LoadingPage(QWidget):
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._reply: Callable[[list[str] | None], None] | None = None
        self._fields: list[QLineEdit] = []

        lay = QVBoxLayout(self)
        lay.addStretch(2)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(logo)
        lay.addSpacing(8)
        self.title = label("")
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.title.setStyleSheet("font-size: 20px; font-weight: 700;")
        lay.addWidget(self.title)
        lay.addSpacing(18)
        self.spinner = Spinner()
        lay.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)
        self.step = label("", "Muted")
        self.step.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.step)

        # Inline authentication (password, OTP, ...), hidden until the server asks.
        self.auth = QWidget()
        self.auth.setMaximumWidth(420)
        auth_lay = QVBoxLayout(self.auth)
        auth_lay.setContentsMargins(0, 12, 0, 0)
        self.auth_title = label("", "SectionTitle")
        self.auth_info = label("", "Muted", wrap=True)
        self.auth_form = QFormLayout()
        auth_lay.addWidget(self.auth_title)
        auth_lay.addWidget(self.auth_info)
        auth_lay.addLayout(self.auth_form)
        self.auth_ok = QPushButton("Continue", objectName="Primary")
        self.auth_ok.clicked.connect(self._submit_auth)
        auth_lay.addWidget(self.auth_ok, 0, Qt.AlignmentFlag.AlignRight)
        self.auth.hide()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.auth)
        row.addStretch()
        lay.addLayout(row)

        lay.addSpacing(18)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel)
        lay.addWidget(cancel, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(3)

    def start(self, name: str) -> None:
        self.title.setText(f"Connecting to {name}")
        self.step.setText("")
        self._clear_auth(None)

    def set_step(self, text: str) -> None:
        self.step.setText(text)

    def ask(self, title: str, instructions: str, prompts: list[tuple[str, bool]],
            reply: Callable[[list[str] | None], None]) -> None:
        self._clear_auth(None)
        self._reply = reply
        self.auth_title.setText(title or "Authentication required")
        self.auth_info.setText(instructions)
        self.auth_info.setVisible(bool(instructions))
        for prompt, echo in prompts:
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Normal if echo else QLineEdit.EchoMode.Password)
            field.returnPressed.connect(self._submit_auth)
            self.auth_form.addRow(prompt.strip().rstrip(":"), field)
            self._fields.append(field)
        self.auth.show()
        if self._fields:
            self._fields[0].setFocus()

    def _submit_auth(self) -> None:
        self._clear_auth([f.text() for f in self._fields])

    def _clear_auth(self, answer: list[str] | None) -> None:
        reply, self._reply = self._reply, None
        while self.auth_form.rowCount():
            self.auth_form.removeRow(0)
        self._fields = []
        self.auth.hide()
        if reply is not None:
            reply(answer)

    def _cancel(self) -> None:
        self._clear_auth(None)
        self.cancelled.emit()
