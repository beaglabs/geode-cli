import difflib
import os
from typing import Optional

from . import hasher, ignore
from .converters import output_type


def scan_workspace(root: str = ".") -> dict[str, dict]:
    ignore_patterns = ignore.load_patterns(root)
    entries: dict[str, dict] = {}

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            name for name in dirs
            if not ignore.should_ignore(os.path.join(current_root, name), ignore_patterns, root)
            and name != ".geode"
        ]

        for filename in files:
            full_path = os.path.join(current_root, filename)
            if ".geode" in full_path.split(os.sep):
                continue
            if ignore.should_ignore(full_path, ignore_patterns, root):
                continue

            rel_path = os.path.relpath(full_path, root)
            ext = os.path.splitext(rel_path)[1].lower()
            digest = hasher.hash_file(full_path)
            entries[rel_path] = {
                "path": rel_path,
                "type": output_type(ext, rel_path),
                "hash": digest,
                "size_bytes": os.path.getsize(full_path),
                "fingerprint": digest,
            }

    return dict(sorted(entries.items()))


def diff_entry_maps(base_entries: dict[str, dict], current_entries: dict[str, dict]) -> dict[str, list[str]]:
    changed: list[str] = []
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for path in sorted(set(base_entries) | set(current_entries)):
        base_entry = base_entries.get(path)
        current_entry = current_entries.get(path)
        if _fingerprint(base_entry) == _fingerprint(current_entry):
            continue

        changed.append(path)
        if base_entry is None:
            added.append(path)
        elif current_entry is None:
            deleted.append(path)
        else:
            modified.append(path)

    return {
        "changed": changed,
        "added": added,
        "modified": modified,
        "deleted": deleted,
    }


def plan_sync(base_entries: dict[str, dict], local_entries: dict[str, dict], remote_entries: dict[str, dict]) -> dict:
    local_delta = diff_entry_maps(base_entries, local_entries)
    remote_delta = diff_entry_maps(base_entries, remote_entries)
    conflicts = sorted(set(local_delta["changed"]) & set(remote_delta["changed"]))

    remote_apply = sorted(set(remote_delta["changed"]) - set(conflicts))
    remote_additions = [path for path in remote_apply if path in remote_delta["added"]]
    remote_modifications = [path for path in remote_apply if path in remote_delta["modified"]]
    remote_deletions = [path for path in remote_apply if path in remote_delta["deleted"]]

    return {
        "local": local_delta,
        "remote": remote_delta,
        "conflicts": conflicts,
        "apply": {
            "changed": remote_apply,
            "additions": remote_additions,
            "modifications": remote_modifications,
            "deletions": remote_deletions,
        },
    }


def classify_push_outcome(local_entries: dict[str, dict], base_entries: dict[str, dict], remote_entries: dict[str, dict]) -> str:
    local_delta = diff_entry_maps(base_entries, local_entries)
    remote_delta = diff_entry_maps(base_entries, remote_entries)
    if not remote_delta["changed"]:
        return "fast-forward"
    if set(local_delta["changed"]) & set(remote_delta["changed"]):
        return "conflict"
    return "auto-merge"


def unified_diff_for_paths(root: str, left_path: str, right_path: Optional[str]) -> str:
    left_text = _read_text(os.path.join(root, left_path))
    right_text = _read_text(os.path.join(root, right_path)) if right_path else ""
    if left_text is None or right_text is None:
        return ""

    diff = difflib.unified_diff(
        left_text.splitlines(),
        right_text.splitlines(),
        fromfile=left_path,
        tofile=right_path or "/dev/null",
        lineterm="",
    )
    return "\n".join(diff)


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (UnicodeDecodeError, OSError):
        return None


def _fingerprint(entry: dict | None) -> str | None:
    if entry is None:
        return None
    return entry.get("fingerprint") or entry.get("hash")
