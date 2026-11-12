# disk-cleanup

A Claude Code skill that finds safely deletable disk space with a Python script instead of LLM tokens. It runs on macOS,
Linux and Windows with Python 3.9+ and no dependencies.

## Install

See the [repository README](../../README.md#install) to install it alone or with the other skills.

Then ask Claude "what can I delete to free disk space?" or type `/disk-cleanup`. The script also works on its own.

## Use

- `make scan` (or `python3 disk_cleanup.py scan`) ranks caches, project build dirs (`node_modules`, `.venv`, `target`)
  and big files under your home folder, labelled `safe`, `rebuild` or `review`. It is read-only and saves the list to
  `~/.cache/disk-cleanup/last.json`.
- `python3 disk_cleanup.py clean safe rebuild` is a dry run; add `--yes` to delete. Selectors are `safe`, `rebuild` or
  part of a path (`Caches/uv`). It matches only items from the last scan and refuses `review` rows and anything outside
  the home folder.
- To teach it a new location, add a line to `KNOWN` in `disk_cleanup.py` and a test.
- `make test` and `make lint` run the checks (they need `uv`).

## Coverage

| OS      | Known locations                                                                            |
| ------- | ------------------------------------------------------------------------------------------ |
| macOS   | `~/.Trash`, `~/Library/Caches`, logs, Xcode, simulators, Docker, iPhone backups, app data  |
| Linux   | `~/.local/share/Trash`, `~/.cache`, Flatpak caches, Steam, Podman                          |
| Windows | `AppData\Local\Temp`, crash dumps, browser cache, npm/pip/Go caches, Docker                |
| All     | npm, Go, Cargo, Gradle, Maven, Ivy, Terraform, NuGet caches; project build dirs; big files |

Only the home folder is scanned. System folders (`/var`, `C:\Windows`) need admin rights and are out of scope. Windows
support is covered by tests that simulate it, not yet tried on a real Windows machine.
