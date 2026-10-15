"""Entry point: ``slurm-gui`` or ``python -m slurm_gui``."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget

from .core.async_bridge import AsyncBridge
from .ui.logo import APP_NAME, logo_pixmap, splash_pixmap
from .ui.main_window import MainWindow
from .ui.theme import apply_theme

SPLASH_MS = 2000


def _prefer_xwayland() -> None:
    """Wayland does not let apps place their own windows, so the splash could not be centred.
    Use XWayland when available (falls back to native Wayland). Set QT_QPA_PLATFORM to override."""
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb;wayland")


def center_on_screen(widget: QWidget) -> None:
    screen = QApplication.primaryScreen()
    if screen is not None:
        frame = widget.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        widget.move(frame.topLeft())


def main() -> int:
    _prefer_xwayland()
    app = QApplication(sys.argv)
    app.setApplicationName("slurm-gui")
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(QIcon(logo_pixmap(256)))
    apply_theme(app)

    splash = QSplashScreen(splash_pixmap(), Qt.WindowType.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    center_on_screen(splash)
    splash.show()
    app.processEvents()

    bridge = AsyncBridge()
    window = MainWindow(bridge)

    def show_main() -> None:
        if not window.restored_geometry:
            center_on_screen(window)
        window.show()
        splash.finish(window)

    def start() -> None:
        show_main()
        if "--demo" in sys.argv:
            from .demo import DEMO_PROFILE
            window.connect_to(DEMO_PROFILE)

    QTimer.singleShot(SPLASH_MS, start)
    code = app.exec()
    bridge.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
