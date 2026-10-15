# slurm-gui: notes for Claude

- **Language:** all code, comments, UI text and docs are in English (the conversation with the user may be in Italian).
- **Scope:** a per-user tool. No admin features (draining nodes, managing accounts). No coupling to the
  user's research projects. It must work on any SLURM cluster: never hard-code anything about a specific one.
- **Runs on the laptop**, talks to the cluster over SSH (asyncssh). Never install anything on the cluster.
- **Queries use text formats, not `--json`** (see `slurm/commands.py` for why). Free-text fields go last.
  Parsers in `slurm/parse.py` stay pure and are tested against `tests/fixtures/`.
- **Theme:** dark with blue/violet/green accents. Every colour comes from the tokens in `ui/theme.py`:
  blue = actions/resources, violet = selection/pending, green = running/success, red only for errors,
  amber for held/drained. Fusion style on every OS.
- **One window, no popups for connecting:** splash (2 s) -> welcome (saved connections, inline editor)
  -> loading (steps, inline auth prompts) -> workspace (Disconnect returns to welcome). See `ui/main_window.py`.
- **User state** lives only in `config/settings.py:config_dir()` (profiles.json + settings.ini as INI, never
  the registry or a plist). Use `app_settings()`, not a bare `QSettings()`.
- **Deferred:** the integrated SSH terminal. The user decided to leave it out for now.
- **Testing against the real cluster:** only read-only commands (squeue, sinfo, sacct, scontrol show,
  sacctmgr show, sshare). Never submit, cancel or modify jobs without the user asking. Run the GUI with
  `QT_QPA_PLATFORM=offscreen` and a temporary `XDG_CONFIG_HOME` so the user's profiles are not touched.
- **Test data / demo:** the synthetic cluster in `src/slurm_gui/demo/data/` is both the parser fixtures and
  `slurm-gui --demo`. The repo is public: data captured from real clusters stays local in `tests/fixtures/`
  (gitignored) because it describes a real site and its users. Screenshots come only from the demo
  (`scripts/screenshots.py`).
- **Releases:** Linux x86_64 (AppImage + tar.gz) and macOS Apple Silicon (.dmg) only, unsigned, built by
  `.github/workflows/release.yml` on a `vX.Y.Z` tag via `packaging/build.py`. No Windows, no Intel Mac, no PyPI
  (user decision): those users run from source.
