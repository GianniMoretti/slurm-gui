"""Build a standalone release of SLURM GUI for the current OS.

    pip install -e '.[build]'
    python packaging/build.py                 # Linux: .tar.gz (+ .AppImage if appimagetool is found)
    python packaging/build.py                 # macOS: .dmg with "SLURM GUI.app"

Outputs go to dist/release/. PyInstaller cannot cross-compile: run this on each target OS
(the GitHub Actions workflow does that for every tagged release). Builds are not code-signed.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "slurm_gui"
BUILD = ROOT / "build" / "pyinstaller"
DIST = ROOT / "dist"
RELEASE = DIST / "release"
APP_NAME = "SLURM GUI"
APP_ID = "slurm-gui"
BUNDLE_ID = "io.github.giannimoretti.slurmgui"

# Qt modules the app never imports; PyInstaller would otherwise pick some up through plugins.
EXCLUDES = ["PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
            "PyQt6.QtMultimedia", "PyQt6.QtPdf", "PyQt6.QtBluetooth", "PyQt6.QtSql", "PyQt6.QtTest",
            "PyQt6.Qt3DCore", "PyQt6.QtCharts", "PyQt6.QtDesigner", "tkinter"]


def version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from importlib.metadata import version as v
    return v("slurm-gui")


def run(*cmd: str, **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def render_icons() -> Path:
    """PNG icons from assets/logo.svg (and an .icns on macOS), rendered with Qt itself."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])  # noqa: F841 - needed for QIcon rendering
    out = BUILD / "icons"
    out.mkdir(parents=True, exist_ok=True)
    icon = QIcon(str(PKG / "assets" / "logo.svg"))

    def png(size: int, path: Path) -> None:
        pix = icon.pixmap(size, size)
        pix.setDevicePixelRatio(1)
        pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.SmoothTransformation).save(str(path))

    png(256, out / f"{APP_ID}.png")
    if sys.platform == "darwin":
        iconset = out / f"{APP_ID}.iconset"
        iconset.mkdir(exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            png(size, iconset / f"icon_{size}x{size}.png")
            png(size * 2, iconset / f"icon_{size}x{size}@2x.png")
        run("iconutil", "-c", "icns", str(iconset), "-o", str(out / f"{APP_ID}.icns"))
        return out / f"{APP_ID}.icns"
    return out / f"{APP_ID}.png"


def pyinstaller(icon: Path) -> Path:
    name = APP_NAME if sys.platform == "darwin" else APP_ID
    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "launcher.py"),
        "--noconfirm", "--clean", "--windowed", "--name", name,
        "--distpath", str(DIST), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
        "--add-data", f"{PKG / 'assets'}{sep}slurm_gui/assets",
        "--add-data", f"{PKG / 'demo' / 'data'}{sep}slurm_gui/demo/data",
        "--copy-metadata", "slurm-gui",
        "--icon", str(icon),
    ]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", BUNDLE_ID]
    run(*cmd)
    return DIST / (f"{APP_NAME}.app" if sys.platform == "darwin" else APP_ID)


def package_linux(app_dir: Path, ver: str, icon: Path, appimagetool: str | None) -> list[Path]:
    arch = platform.machine()
    out = []
    tgz = RELEASE / f"{APP_ID}-{ver}-linux-{arch}.tar.gz"
    with tarfile.open(tgz, "w:gz") as tar:
        tar.add(app_dir, arcname=f"{APP_ID}-{ver}")
    out.append(tgz)

    tool = appimagetool or shutil.which("appimagetool")
    if not tool:
        print("appimagetool not found: skipping the AppImage")
        return out
    appdir = BUILD / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(app_dir, appdir / "usr" / "bin")
    shutil.copy(icon, appdir / f"{APP_ID}.png")
    (appdir / f"{APP_ID}.desktop").write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name={APP_NAME}\nComment=Monitor and control your SLURM jobs\n"
        f"Exec={APP_ID}\nIcon={APP_ID}\nCategories=Development;Utility;\nTerminal=false\n")
    apprun = appdir / "AppRun"
    apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                      f'exec "$HERE/usr/bin/{APP_ID}" "$@"\n')
    apprun.chmod(0o755)
    image = RELEASE / f"{APP_ID}-{ver}-linux-{arch}.AppImage"
    env = dict(os.environ, ARCH=arch)
    run(tool, "--appimage-extract-and-run", str(appdir), str(image), env=env)
    out.append(image)
    return out


def package_macos(app: Path, ver: str) -> list[Path]:
    staging = BUILD / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")   # drag-to-install target
    dmg = RELEASE / f"{APP_ID}-{ver}-macos-{platform.machine()}.dmg"
    run("hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg))
    return [dmg]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--appimagetool", help="path to appimagetool (Linux)")
    args = parser.parse_args()
    if sys.platform not in ("linux", "darwin"):
        sys.exit("Releases are built for Linux and macOS only.")

    ver = version()
    RELEASE.mkdir(parents=True, exist_ok=True)
    icon = render_icons()
    app = pyinstaller(icon)
    files = (package_macos(app, ver) if sys.platform == "darwin"
             else package_linux(app, ver, BUILD / "icons" / f"{APP_ID}.png", args.appimagetool))
    for f in files:
        print(f"built {f.relative_to(ROOT)}  ({f.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
