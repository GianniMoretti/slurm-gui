"""SLURM GUI: monitor and control your SLURM jobs from the desktop."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("slurm-gui")
except PackageNotFoundError:   # running from a source tree that was not pip-installed
    __version__ = "0.0.0+dev"
