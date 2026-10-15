"""Regenerate the README screenshots in docs/screenshots/ from the demo cluster (no real data).

    QT_QPA_PLATFORM=offscreen python scripts/screenshots.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"

# A throwaway home and settings folder holding only demo connections; the user's own are never
# touched, and the settings path in the screenshots reads ~/.config/slurm-gui.
_home = tempfile.mkdtemp(prefix="slurm-gui-shots-")
_cfg = os.path.join(_home, ".config")
os.environ["HOME"] = _home
os.environ["XDG_CONFIG_HOME"] = _cfg
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from slurm_gui.config.profiles import Profile, save_profiles  # noqa: E402
from slurm_gui.core.async_bridge import AsyncBridge  # noqa: E402
from slurm_gui.demo import DEMO_PROFILE  # noqa: E402
from slurm_gui.ui import theme  # noqa: E402
from slurm_gui.ui.logo import splash_pixmap  # noqa: E402
from slurm_gui.ui.main_window import MainWindow  # noqa: E402
from slurm_gui.ui.theme import apply_theme  # noqa: E402

SIZE = (1280, 800)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save_profiles([
        Profile(name="Demo cluster", host=DEMO_PROFILE.host, user="alice", last_used=(datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")),
        Profile(name="University HPC", host="login.hpc.example.edu", user="alice"),
        Profile(name="Lab GPU server", host="gpu-lab", refresh_seconds=60),
    ])
    (Path(_cfg) / "slurm-gui" / "profiles.json").write_text(
        json.dumps(json.loads((Path(_cfg) / "slurm-gui" / "profiles.json").read_text()), indent=2))

    app = QApplication(sys.argv)
    apply_theme(app)
    splash_pixmap().save(str(OUT / "splash.png"))
    bridge = AsyncBridge()
    w = MainWindow(bridge)
    w.resize(*SIZE)
    w.show()
    ws = w.workspace

    def shot(name: str, widget=None) -> None:
        (widget or w).grab().save(str(OUT / f"{name}.png"))
        print("saved", name)

    def page(i: int) -> None:
        ws.nav.setCurrentRow(i)

    def queue_all() -> None:
        page(1)
        ws.pages.widget(1).mine.setChecked(False)

    def job_dialog() -> None:
        job = next(j for j in w.state.jobs if j.job_id == "5001")
        w.open_job(job)

    def job_output() -> None:
        d = w._dialogs[0]
        d.resize(1000, 640)
        d.tabs.setCurrentIndex(1)

    def fairshare_tip() -> None:
        tip = QLabel(ws.pages.widget(0).fairshare.toolTip())
        tip.setWordWrap(True)
        tip.setFixedWidth(420)
        tip.setStyleSheet(f"background:{theme.SURFACE_2}; color:{theme.TEXT}; border:1px solid {theme.BORDER}; padding:6px;")
        tip.adjustSize()
        shot("fairshare", tip)

    steps = [
        (600, lambda: shot("welcome")),
        (100, lambda: w.connect_to(DEMO_PROFILE)),
        (300, lambda: shot("loading")),
        (3500, lambda: (page(0),)),
        (1500, lambda: shot("dashboard")),
        (100, fairshare_tip),
        (100, queue_all),
        (500, lambda: shot("queue")),
        (100, lambda: page(2)),
        (500, lambda: shot("nodes")),
        (100, lambda: page(3)),
        (1500, lambda: shot("history")),
        (100, lambda: page(4)),
        (500, lambda: shot("account")),
        (100, job_dialog),
        (1500, job_output),
        (1500, lambda: shot("job", w._dialogs[0])),
        (100, app.quit),
    ]

    def run(i: int = 0) -> None:
        if i < len(steps):
            delay, fn = steps[i]
            QTimer.singleShot(delay, lambda: (fn(), run(i + 1)))

    run()
    app.exec()
    bridge.shutdown()


if __name__ == "__main__":
    main()
