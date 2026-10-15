"""PyInstaller entry point (a plain script, so the package is imported normally)."""

import sys

from slurm_gui.app import main

sys.exit(main())
