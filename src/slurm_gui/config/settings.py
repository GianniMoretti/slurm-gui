"""The app's per-user folder, where profiles and every user setting live.

Platform conventions:

- Linux:   ``$XDG_CONFIG_HOME/slurm-gui`` (normally ``~/.config/slurm-gui``)
- macOS:   ``~/Library/Application Support/slurm-gui``
- Windows: ``%APPDATA%\\slurm-gui``

It holds ``profiles.json`` (saved connections) and ``settings.ini`` (window state, last page, ...).
Settings are always an INI file there, never the Windows registry or a macOS plist, so the whole
user state is in one folder that can be backed up or deleted.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, QStandardPaths

APP_DIR_NAME = "slurm-gui"


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation)
    elif sys.platform == "darwin":
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    else:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_settings() -> QSettings:
    return QSettings(str(config_dir() / "settings.ini"), QSettings.Format.IniFormat)
