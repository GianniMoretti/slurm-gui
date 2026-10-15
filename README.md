# SLURM GUI

A cross-platform desktop app (PyQt6) to monitor and control your jobs on any SLURM cluster.
It runs on your laptop and talks to the cluster's login node over SSH: nothing is installed
on the cluster.

## Features

Everything happens in one window. A 2-second splash screen leads to the **connections screen**:
the logo, your saved connections as cards (click one to connect, or edit or delete it), and
**Add connection**, which opens an inline form. While the app connects and loads the first data,
a **loading screen** shows each step; password and 2FA/OTP prompts appear inline there. Then the
**workspace** opens, and **Disconnect** in its header brings you back to the connections screen.

| Page | What it shows |
|---|---|
| Dashboard | Your running and pending jobs, GPUs in use against your account's limit, fairshare, free GPUs by type in the partitions you can use, and a live activity feed (started, completed, failed) |
| Queue | The live queue: filter by text, owner and state. Cancel, hold or release your jobs. Hover a pending reason for a plain-English explanation. Double-click a job for details |
| Nodes | Every node as a tile: state, GPUs allocated, CPU use. Filter by partition and GPU type |
| History | Finished jobs from `sacct` (24 h / 7 d / 30 d), with completed, failed and timed-out counts and GPU hours |
| Account | Your associations (group limits, fairshare) and the partitions with their default and maximum times |
| Job details | The full `scontrol show job` record and a live tail of the job's stdout and stderr |

Desktop notifications fire when one of your jobs starts, completes or fails.

## Install and run

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/slurm-gui            # or: .venv/bin/python -m slurm_gui
```

On first launch, add a connection. The host can be an alias from `~/.ssh/config`; user, port,
keys, agent and `ProxyJump` are then taken from there. The host key must already be in
`known_hosts` (connect once with `ssh <host>`).

### Where your settings live

All per-user state is in one folder, following each platform's convention:

| OS | Folder |
|---|---|
| Linux | `~/.config/slurm-gui` (or `$XDG_CONFIG_HOME/slurm-gui`) |
| macOS | `~/Library/Application Support/slurm-gui` |
| Windows | `%APPDATA%\slurm-gui` |

It contains `profiles.json` (saved connections) and `settings.ini` (window size, last page).
The connections screen shows the path, and clicking it opens the folder.

### Logo

`src/slurm_gui/assets/logo.svg` (three bars in the theme's blue, violet and green) is used for the
splash screen, the connections and loading screens, and the window icon. Replace it to rebrand
(a `logo.png` works too).

On Linux under Wayland the app runs through XWayland when it is available, because Wayland does
not let apps position their windows (the splash would not be centred). Set
`QT_QPA_PLATFORM=wayland` to force native Wayland.

## How it works

- **SSH.** One persistent [asyncssh](https://asyncssh.readthedocs.io) connection per cluster,
  running on a background asyncio thread (`core/async_bridge.py`). Every query is a channel on
  it. This works the same on Linux, macOS and Windows, and needs no `ControlMaster`.
- **Text formats, not `--json`.** `squeue --json` is about 100× larger than a delimited text
  format (2 MB vs 21 KB on a 150-job cluster) and is missing on older SLURM versions. Every
  query uses a `|`-separated format with the free-text job name last
  (`slurm/commands.py`), or `scontrol show … -o` key=value lines.
- **Gentle polling.** Each refresh is one `squeue` plus one `scontrol show node` (30 s by
  default and minimum), and refreshes never overlap. `sacct` runs only on demand.
- **Banner-proof.** Commands print a marker before their output, so login banners and
  shell-profile noise are discarded.

```
src/slurm_gui/
  core/       async bridge (asyncio <-> Qt), SSH session
  slurm/      command lines, pure parsers, dataclasses, pending-reason texts, async client
  services/   ClusterState: connection, polling, job events, actions (Qt signals)
  config/     settings folder, connection profiles
  ui/         theme, logo, main window (welcome -> loading -> workspace), pages, widgets
  assets/     logo
tests/        parser tests against captured, anonymized outputs of real clusters
scripts/      capture_fixtures.py, anonymize_fixtures.py
```

## Tests and fixtures

```bash
.venv/bin/pytest
```

Parsers are tested against `tests/fixtures/example/`, a synthetic cluster written to cover
the tricky cases (job names containing the separator, array jobs, drained nodes with reasons,
hidden and account-restricted partitions, unlimited time limits). Outputs captured from a real
cluster can be dropped into `tests/fixtures/<name>/` to run the same tests against them; that
folder is gitignored, so a real site's data never ends up in the repository:

```bash
.venv/bin/python scripts/capture_fixtures.py <ssh-host> <name>       # read-only commands only
.venv/bin/python scripts/anonymize_fixtures.py tests/fixtures/<name> --keep <your-username>
```

## Roadmap

- Submit page: form with partition, account, GPU and feature, time and memory, live `#SBATCH`
  preview, saved templates, parameter sweeps, `--test-only` validation
- GPU utilisation of running jobs (`srun --overlap --jobid … nvidia-smi`)
- Remote file browser (SFTP) for logs and results
- Per-profile custom commands
- An integrated SSH terminal (deferred)
- Packaged executables (PyInstaller) for Linux, macOS and Windows
