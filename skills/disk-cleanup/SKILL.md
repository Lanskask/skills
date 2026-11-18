---
name: disk-cleanup
description:
  Use when the computer (macOS, Linux or Windows) is low on disk space or the user asks what can be safely deleted. Runs
  a Python scan that ranks caches, project build dirs and big files by size and safety, so the model only reads one
  short table.
---

# Disk cleanup

Python does the work; do not run `du`/`find` yourself and do not read files. Costs: one scan (about 90 s), one table.
`SCRIPT` below is `disk_cleanup.py` in this skill's base directory; run it with `python3` (on Windows: `python`). It
needs only the standard library.

1. Run `python3 SCRIPT scan` (read-only). Pass `--min-mb`, `--big-mb`, `--top` (rows per group) to change thresholds,
   and `--overview` only if the report does not explain the missing space.
2. Show the user the report as printed: three groups with sizes, no row numbers. `SAFE TO DELETE` regenerates by itself;
   `DELETE, BUT COSTS A RE-DOWNLOAD/REBUILD` loses nothing; `YOUR DECISION` may hold user data and is never deleted by
   the tool (point at the note's own command, e.g. `docker system prune`).
3. Say that only the first two groups are deletable, and wait for the user's go-ahead.
4. Dry run first: `python3 SCRIPT clean safe rebuild`. Selectors are `safe`, `rebuild`, or a part of a path
   (`Caches/uv`). After approval, add `--yes`.
5. Report the `disk free changed` line. If a new location is missing from the report, add it to `KNOWN` in the script
   and a test to `tests/test_disk_cleanup.py`.
