"""Small reusable widgets."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from .. import theme


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


class StatCard(QFrame):
    """Muted caption, big coloured number, optional subtitle and usage bar."""

    def __init__(self, caption: str, color: str = theme.TEXT) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._color = color
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        lay.addWidget(label(caption, "Muted"))
        self.value = label("–", "CardValue")
        self.value.setStyleSheet(f"color: {color};")
        lay.addWidget(self.value)
        self.subtitle = label("", "Muted")
        lay.addWidget(self.subtitle)
        self.bar = UsageBar(color)
        self.bar.hide()
        lay.addWidget(self.bar)

    def set(self, value: str, subtitle: str = "", fraction: float | None = None) -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)
        self.bar.setVisible(fraction is not None)
        if fraction is not None:
            self.bar.set_fraction(fraction)


class UsageBar(QWidget):
    def __init__(self, color: str = theme.BLUE, height: int = 5) -> None:
        super().__init__()
        self._color = QColor(color)
        self._fraction = 0.0
        self.setFixedHeight(height)

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = self.rect()
        radius = r.height() / 2
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(r, radius, radius)
        if self._fraction > 0:
            r.setWidth(max(int(r.height()), int(r.width() * self._fraction)))
            p.setBrush(self._color)
            p.drawRoundedRect(r, radius, radius)


class Dot(QWidget):
    """Coloured status dot."""

    def __init__(self, color: str = theme.TEXT_DIM, size: int = 9) -> None:
        super().__init__()
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(self.rect())


def page_header(title: str, *right: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(label(title, "PageTitle"))
    row.addStretch()
    for w in right:
        row.addWidget(w)
    return row


def setup_table(view: QTableView) -> None:
    view.setAlternatingRowColors(True)
    view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    view.setShowGrid(False)
    view.setSortingEnabled(True)
    view.setWordWrap(False)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(28)
    view.horizontalHeader().setHighlightSections(False)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    view.horizontalHeader().setStretchLastSection(True)
    view.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
