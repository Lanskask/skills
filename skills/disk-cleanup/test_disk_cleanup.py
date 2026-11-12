"""Tests run the CLI against a fake home (DC_HOME) so nothing real is touched."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent / "disk_cleanup.py"
MB2 = b"x" * 2_000_000


def run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DC_HOME": str(home)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, text=True, capture_output=True, check=False)


def make(home: Path, rel: str) -> Path:
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(MB2)
    return p


def items(home: Path) -> dict[str, dict[str, object]]:
    data = json.loads((home / ".cache/disk-cleanup/last.json").read_text())
    return {Path(i["path"]).relative_to(home).as_posix(): i for i in data}


def scan(home: Path) -> dict[str, dict[str, object]]:
    r = run(home, "scan", "--min-mb", "1", "--big-mb", "1", "--top", "100")
    assert r.returncode == 0, r.stderr
    return items(home)


def test_scan_classifies(tmp_path: Path) -> None:
    make(tmp_path, "proj/node_modules/a.bin")
    make(tmp_path, "proj/package.json")
    make(tmp_path, "Library/Caches/foo/blob")
    make(tmp_path, "Downloads/big.iso")
    found = scan(tmp_path)
    assert found["proj/node_modules"]["safety"] == "rebuild"
    assert found["Library/Caches/foo"]["safety"] == "safe"
    assert found["Downloads/big.iso"]["safety"] == "review"


def test_no_manifest_means_review(tmp_path: Path) -> None:
    make(tmp_path, "proj/node_modules/a.bin")  # no package.json: cannot be rebuilt
    make(tmp_path, "rust/target/debug/x")  # no Cargo.toml
    found = scan(tmp_path)
    assert found["proj/node_modules"]["safety"] == "review"
    assert found["rust/target"]["safety"] == "review"


def test_target_with_marker_rebuilds(tmp_path: Path) -> None:
    make(tmp_path, "rust/target/debug/x")
    make(tmp_path, "rust/Cargo.toml")
    assert scan(tmp_path)["rust/target"]["safety"] == "rebuild"


def test_report_is_grouped_and_numberless(tmp_path: Path) -> None:
    make(tmp_path, "Library/Caches/foo/blob")
    out = run(tmp_path, "scan", "--min-mb", "1").stdout
    assert "SAFE TO DELETE" in out and "Library/Caches/foo" in out and "clean safe" in out


def test_clean_by_fragment_dry_run_then_yes(tmp_path: Path) -> None:
    make(tmp_path, "Library/Caches/foo/blob")
    scan(tmp_path)
    assert "dry run" in run(tmp_path, "clean", "Caches/foo").stdout
    assert (tmp_path / "Library/Caches/foo/blob").exists()
    assert run(tmp_path, "clean", "Caches/foo", "--yes").returncode == 0
    assert not (tmp_path / "Library/Caches/foo/blob").exists()


def test_clean_group_safe_skips_rebuild(tmp_path: Path) -> None:
    make(tmp_path, "Library/Caches/foo/blob")
    make(tmp_path, ".cargo/registry/crate")  # rebuild
    scan(tmp_path)
    assert run(tmp_path, "clean", "safe", "--yes").returncode == 0
    assert not (tmp_path / "Library/Caches/foo/blob").exists()
    assert (tmp_path / ".cargo/registry/crate").exists()


def test_clean_refuses_review_and_unknown(tmp_path: Path) -> None:
    f = make(tmp_path, "Downloads/big.iso")
    scan(tmp_path)
    assert run(tmp_path, "clean", "big.iso", "--yes").returncode != 0
    assert run(tmp_path, "clean", "nonexistent", "--yes").returncode != 0
    assert f.exists()


def test_linux_and_windows_locations(tmp_path: Path) -> None:
    make(tmp_path, ".local/share/Trash/files/old")
    make(tmp_path, "AppData/Local/Temp/junk")
    found = scan(tmp_path)
    assert found[".local/share/Trash"]["safety"] == "safe"
    assert found["AppData/Local/Temp"]["safety"] == "safe"


def test_sizes_without_du(tmp_path: Path) -> None:
    make(tmp_path, "Library/Caches/foo/blob")
    env = {**os.environ, "DC_HOME": str(tmp_path), "PATH": ""}  # no `du`, as on Windows
    r = subprocess.run([sys.executable, str(SCRIPT), "scan", "--min-mb", "1"], env=env, text=True, capture_output=True, check=False)
    assert r.returncode == 0, r.stderr
    assert items(tmp_path)["Library/Caches/foo"]["kb"] >= 1900
