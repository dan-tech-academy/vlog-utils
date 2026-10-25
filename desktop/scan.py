"""See which files an agent turn touched."""

from __future__ import annotations

from pathlib import Path


def snapshot(root: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    if not root.exists():
        return found
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            found[path.relative_to(root).as_posix()] = path.stat().st_mtime_ns
        except OSError:
            continue
    return found


def unexpected_writes(before: dict[str, int], after: dict[str, int]) -> list[str]:
    bad: list[str] = []
    for rel, mtime in after.items():
        if rel == "edit" or rel.startswith("edit/"):
            continue
        if before.get(rel) != mtime:
            bad.append(rel)
    return sorted(bad)


def repo_snapshot(repo: Path) -> dict[str, int]:
    paths = [repo / "SKILL.md"]
    helpers = repo / "helpers"
    desktop = repo / "desktop"
    if helpers.is_dir():
        paths.extend(sorted(helpers.glob("*.py")))
    if desktop.is_dir():
        paths.extend(sorted(p for p in desktop.glob("*.py")))
    found: dict[str, int] = {}
    for path in paths:
        if path.is_file():
            try:
                found[str(path)] = path.stat().st_mtime_ns
            except OSError:
                continue
    return found


def repo_changes(before: dict[str, int], after: dict[str, int]) -> list[str]:
    bad = [path for path, mtime in after.items() if before.get(path) != mtime]
    bad.extend(path for path in before if path not in after)
    return sorted(bad)
