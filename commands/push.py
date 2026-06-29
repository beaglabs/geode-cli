"""
geode push – Push current directory to a Geode vault.

Flow:
  1. Walk cwd, respect .geodeignore
  2. Convert supported formats to Zarr/Arrow (with cache)
  3. Hash all outputs (BLAKE3)
  4. POST /push/start → get presigned S3 URL + dedup
  5. Build tar of needed files
  6. PUT tar to S3
  7. POST /push/complete → trigger processing
"""

import os
import sys
import tempfile
import time
from typing import Optional

import httpx

from lib import config, ignore, hasher, cache
from lib.converters import can_convert, convert, output_type
from lib.pusher import (
    build_tar,
    complete_push,
    get_push_run_status,
    get_vault_info,
    get_vault_tree_metadata,
    start_push,
    upload_tar,
)
from lib.workspace import classify_push_outcome, diff_entry_maps, scan_workspace


def register_push_command(subparsers):
    push_parser = subparsers.add_parser("push", help="Push current directory to remote vault")
    push_parser.add_argument(
        "-m", "--message", default="Push data", help="Commit message"
    )
    push_parser.add_argument(
        "--dry-run", action="store_true", help="Preview what would be pushed"
    )
    push_parser.add_argument(
        "--token", help="API auth token (or set GEODE_TOKEN env var)"
    )


def handle_push(args):
    remote = config.get_remote()
    if not remote:
        print("Error: no remote configured. Run 'geode vault set-url <url>' first.")
        sys.exit(1)

    vault_id = config.get_vault_id()
    if not vault_id:
        print("Error: no vault configured. Run 'geode vault set-url <url>' first.")
        sys.exit(1)

    token = args.token or os.environ.get("GEODE_TOKEN")
    message = args.message
    base_commit_id = config.get_head_commit_id()
    ignore_patterns = ignore.load_patterns()

    if not base_commit_id:
        try:
            vault_info = get_vault_info(remote, vault_id, token)
        except httpx.HTTPError as exc:
            print(f"Error: failed to resolve vault head: {exc}")
            sys.exit(1)

        remote_head = vault_info.get("head_commit_id")
        if remote_head:
            print("Error: this vault already has history, but this directory has no recorded base commit.")
            print("Clone or sync the vault contents locally before pushing, then set the tracked head commit.")
            sys.exit(1)

    file_list = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if not ignore.should_ignore(os.path.join(root, d), ignore_patterns)]
        for f in files:
            full = os.path.join(root, f)
            if ignore.should_ignore(full, ignore_patterns):
                continue
            if ".geode" in full.split(os.sep):
                continue
            file_list.append(full)

    if not file_list:
        print("No files to push.")
        return

    if args.dry_run:
        local_entries = scan_workspace(".")
        if base_commit_id:
            try:
                metadata = get_vault_tree_metadata(remote, vault_id, base_commit_id, token)
                base_entries = metadata.get("base_entries", {})
                remote_entries = metadata.get("head_entries", {})
                delta = diff_entry_maps(base_entries, local_entries)
                outcome = classify_push_outcome(local_entries, base_entries, remote_entries)
                print(f"Would push against tracked base {base_commit_id[:8]}")
                print(f"Predicted outcome: {outcome}")
                _print_delta(delta)
                return
            except httpx.HTTPError:
                pass

        print(f"Would push {len(file_list)} files:")
        for f in file_list:
            ext = os.path.splitext(f)[1].lower()
            otype = output_type(ext, f)
            print(f"  {f} → {otype}")
        return

    manifest = []
    tar_files = []

    for filepath in sorted(file_list):
        logical_path = os.path.relpath(filepath, ".")
        ext = os.path.splitext(filepath)[1].lower()

        if can_convert(ext):
            source_hash = hasher.hash_file(filepath)
            cached = cache.get_cached(filepath, source_hash)

            if cached:
                output_path = cached
            else:
                print(f"  Converting: {logical_path} → {output_type(ext)}")
                output_path = convert(filepath)
                cache.put_cache(filepath, source_hash, output_path)

            source_upload_path = os.path.join("_source", logical_path).replace(os.sep, "/")
            tar_files.append((source_upload_path, filepath))

            if os.path.isdir(output_path):
                normalized_entries = []
                for zarr_root, zarr_dirs, zarr_files in os.walk(output_path):
                    for zf in zarr_files:
                        zf_path = os.path.join(zarr_root, zf)
                        rel_normalized_path = os.path.relpath(zf_path, output_path).replace(os.sep, "/")
                        arcname = os.path.join("_normalized", f"{logical_path}.zarr", rel_normalized_path).replace(os.sep, "/")
                        zf_hash = hasher.hash_file(zf_path)
                        normalized_entries.append({
                            "path": rel_normalized_path,
                            "upload_path": arcname,
                            "hash": zf_hash,
                            "size": os.path.getsize(zf_path),
                        })
                        tar_files.append((arcname, zf_path))

                manifest.append({
                    "path": logical_path,
                    "type": "converted",
                    "storage_type": "zarr",
                    "source_format": ext.lstrip("."),
                    "source": {
                        "hash": source_hash,
                        "size": os.path.getsize(filepath),
                        "upload_path": source_upload_path,
                    },
                    "normalized": {
                        "type": "zarr",
                        "entries": normalized_entries,
                    },
                })
            else:
                arcname = os.path.join("_normalized", f"{logical_path}.arrow").replace(os.sep, "/")
                out_hash = hasher.hash_file(output_path)
                manifest.append({
                    "path": logical_path,
                    "type": "converted",
                    "storage_type": "arrow",
                    "source_format": ext.lstrip("."),
                    "source": {
                        "hash": source_hash,
                        "size": os.path.getsize(filepath),
                        "upload_path": source_upload_path,
                    },
                    "normalized": {
                        "type": "arrow",
                        "hash": out_hash,
                        "size": os.path.getsize(output_path),
                        "upload_path": arcname,
                    },
                })
                tar_files.append((arcname, output_path))
        else:
            file_hash = hasher.hash_file(filepath)
            manifest.append({
                "path": logical_path,
                "hash": file_hash,
                "size": os.path.getsize(filepath),
                "type": output_type(ext, filepath),
                "upload_path": logical_path,
            })
            tar_files.append((logical_path, filepath))

    print(f"Starting push: {len(manifest)} entries...")
    try:
        start_result = start_push(remote, vault_id, manifest, message, base_commit_id, token)
    except httpx.HTTPStatusError as exc:
        _handle_push_http_error(exc)
    needed = set(start_result.get("needed", []))
    run_id = start_result.get("run_id")

    upload_lookup = {item["upload_path"]: item for entry in manifest for item in _manifest_upload_items(entry)}
    needed_files = [(arcname, path) for arcname, path in tar_files if upload_lookup[arcname]["hash"] in needed]

    if needed_files:
        print(f"Uploading {len(needed_files)} files...")
    else:
        print("No new content bytes need upload. Finalizing push from the manifest...")
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        build_tar(needed_files, tmp.name)
    try:
        upload_url = start_result.get("upload_url")
        if upload_url:
            print(f"  Uploading to S3...")
            if not upload_tar(upload_url, tmp.name):
                print("Error: S3 upload failed.")
                sys.exit(1)
        else:
            print("Warning: no presigned URL. Skipping S3 upload.")

        print(f"Triggering processing...")
        try:
            complete_result = complete_push(
                remote, vault_id, run_id, manifest, message,
                start_result.get("upload_key", f"uploads/{run_id}.tar"), base_commit_id, token,
            )
        except httpx.HTTPStatusError as exc:
            _handle_push_http_error(exc)

        print(f"Push queued: {complete_result['run_id']}")
        print("Waiting for server-side processing...")

        commit_id = _wait_for_push_completion(remote, vault_id, complete_result["run_id"], token)
        if commit_id:
            config.set_head_commit_id(commit_id)
            print(f"Done. Head advanced to {commit_id[:8]}")
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def _wait_for_push_completion(remote: str, vault_id: str, run_id: str, token: Optional[str]) -> Optional[str]:
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            status = get_push_run_status(remote, vault_id, run_id, token)
        except httpx.HTTPError as exc:
            print(f"Warning: unable to poll push status: {exc}")
            return None

        state = status.get("status")
        if state == "success":
            return status.get("commit_id")
        if state in {"failure", "cancelled"}:
            logs = status.get("logs") or ""
            print(f"Push {state}.")
            if logs:
                print(logs)
            sys.exit(1)

        time.sleep(1)

    print("Push is still processing on the server. Re-run later to confirm the new head commit.")
    return None


def _handle_push_http_error(exc: httpx.HTTPStatusError):
    if exc.response.status_code == 409:
        try:
            detail = exc.response.json().get("detail", {})
        except ValueError:
            detail = {}
        message = detail.get("message") or "Push rejected because the remote vault has advanced."
        current_head = detail.get("current_head_commit_id")
        print(f"Error: {message}")
        if current_head:
            print(f"Current remote head: {current_head[:8]}")
        sys.exit(1)

    print(f"Error: push failed ({exc.response.status_code}): {exc.response.text}")
    sys.exit(1)


def _manifest_upload_items(entry: dict) -> list[dict]:
    if entry.get("type") != "converted":
        return [{
            "upload_path": entry["upload_path"],
            "hash": entry["hash"],
        }]

    items = [{
        "upload_path": entry["source"]["upload_path"],
        "hash": entry["source"]["hash"],
    }]

    normalized = entry.get("normalized") or {}
    if normalized.get("type") == "arrow":
        items.append({
            "upload_path": normalized["upload_path"],
            "hash": normalized["hash"],
        })
    else:
        for nested in normalized.get("entries", []):
            items.append({
                "upload_path": nested["upload_path"],
                "hash": nested["hash"],
            })
    return items


def _print_delta(delta: dict):
    print("Added:")
    for path in delta["added"]:
        print(f"  {path}")
    print("Modified:")
    for path in delta["modified"]:
        print(f"  {path}")
    print("Deleted:")
    for path in delta["deleted"]:
        print(f"  {path}")
