"""The app logo: ``assets/logo.svg`` or ``assets/logo.png`` when present, otherwise a drawn placeholder."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from . import theme

ASSETS = Path(__file__).resolve().parent.parent / "assets"
APP_NAME = "SLURM GUI"


def _asset() -> Path | None:
    for name in ("logo.svg", "logo.png"):
        if (ASSETS / name).exists():
            return ASSETS / name
    return None


def logo_pixmap(size: int) -> QPixmap:
    """A square logo of ``size`` px (device-pixel-ratio aware)."""
    path = _asset()
    if path is not None:
        icon = QIcon(str(path))
        pix = icon.pixmap(size, size)
        if not pix.isNull():
            return pix
    return _placeholder(size)


def _placeholder(size: int) -> QPixmap:
    """Three staggered bars (a job queue) in the theme's blue, violet and green."""
    ratio = 2
    pix = QPixmap(size * ratio, size * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.SURFACE))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    bar_h = size * 0.13
    for i, (color, x0, width) in enumerate(((theme.BLUE, 0.20, 0.60), (theme.VIOLET, 0.30, 0.50), (theme.GREEN, 0.20, 0.38))):
        p.setBrush(QColor(color))
        y = size * (0.26 + i * 0.19)
        p.drawRoundedRect(QRectF(size * x0, y, size * width, bar_h), bar_h / 2, bar_h / 2)
    p.end()
    return pix


def splash_pixmap(width: int = 560, height: int = 340) -> QPixmap:
    ratio = 2
    pix = QPixmap(width * ratio, height * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(theme.BORDER))
    p.setBrush(QColor(theme.BG))
    p.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 16, 16)
    logo = 120
    p.drawPixmap(int((width - logo) / 2), 56, logo_pixmap(logo))
    title = QFont()
    title.setPointSize(20)
    title.setBold(True)
    p.setFont(title)
    p.setPen(QColor(theme.TEXT))
    p.drawText(QRectF(0, 196, width, 40), Qt.AlignmentFlag.AlignHCenter, APP_NAME)
    sub = QFont()
    sub.setPointSize(10)
    p.setFont(sub)
    p.setPen(QColor(theme.TEXT_MUTED))
    p.drawText(QRectF(0, 236, width, 24), Qt.AlignmentFlag.AlignHCenter, "Your SLURM jobs, at a glance")
    p.end()
    return pix
