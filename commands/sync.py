"""geode sync - Replace the current working directory with the remote vault head."""

import os
import shutil
import sys
import tempfile

from lib import config
from lib.archive import extract_archive_bytes, replace_directory_from_archive
from lib.pusher import download_vault_archive, get_vault_info, get_vault_tree_metadata
from lib.workspace import plan_sync, scan_workspace


PRESERVE_NAMES = {".geode", ".git"}


def register_sync_command(subparsers):
    sync_parser = subparsers.add_parser("sync", help="Sync the current directory to the remote vault head")
    sync_parser.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")
    sync_parser.add_argument("--dry-run", action="store_true", help="Show what sync would do without modifying files")
    sync_parser.add_argument("--discard-local", action="store_true", help="Discard local changes and fully replace tracked contents")


def handle_sync(args):
    remote = config.get_remote()
    if not remote:
        print("Error: no remote configured. Run 'geode vault set-url <url>' first.")
        sys.exit(1)

    vault_id = config.get_vault_id()
    if not vault_id:
        print("Error: no vault configured. Run 'geode vault set-url <url>' first.")
        sys.exit(1)

    token = args.token or os.environ.get("GEODE_TOKEN")
    base_commit_id = config.get_head_commit_id()
    vault_info = get_vault_info(remote, vault_id, token)
    metadata = get_vault_tree_metadata(remote, vault_id, base_commit_id, token)
    local_entries = scan_workspace(".")
    sync_plan = plan_sync(metadata.get("base_entries", {}), local_entries, metadata.get("head_entries", {}))

    if args.dry_run:
        _print_sync_plan(vault_info.get("name", vault_id), metadata.get("head_commit_id"), sync_plan)
        return

    if args.discard_local:
        archive_bytes, head_commit_id = download_vault_archive(remote, vault_id, token)
        replace_directory_from_archive(archive_bytes, ".", PRESERVE_NAMES)
        config.set_head_commit_id(head_commit_id)
        print(f"Synced {vault_info.get('name', vault_id)} to {head_commit_id[:8] if head_commit_id else 'empty head'}.")
        return

    if sync_plan["conflicts"]:
        _print_sync_plan(vault_info.get("name", vault_id), metadata.get("head_commit_id"), sync_plan)
        print("Error: sync would overwrite conflicting local changes.")
        sys.exit(1)

    archive_bytes, head_commit_id = download_vault_archive(remote, vault_id, token)
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_archive_bytes(archive_bytes, tmpdir)
        _apply_sync_changes(tmpdir, sync_plan)

    config.set_head_commit_id(head_commit_id)
    print(f"Synced {vault_info.get('name', vault_id)} to {head_commit_id[:8] if head_commit_id else 'empty head'}.")


def _print_sync_plan(name: str, head_commit_id: str | None, sync_plan: dict) -> None:
    print(f"Would sync {name} to head {head_commit_id[:8] if head_commit_id else 'empty'}")
    if sync_plan["apply"]["additions"]:
        print("Would add:")
        for path in sync_plan["apply"]["additions"]:
            print(f"  {path}")
    if sync_plan["apply"]["modifications"]:
        print("Would update:")
        for path in sync_plan["apply"]["modifications"]:
            print(f"  {path}")
    if sync_plan["apply"]["deletions"]:
        print("Would delete:")
        for path in sync_plan["apply"]["deletions"]:
            print(f"  {path}")
    if sync_plan["conflicts"]:
        print("Conflicts:")
        for path in sync_plan["conflicts"]:
            print(f"  {path}")


def _apply_sync_changes(extracted_root: str, sync_plan: dict) -> None:
    for path in sync_plan["apply"]["deletions"]:
        full_path = os.path.join(".", path)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            shutil.rmtree(full_path)
        elif os.path.exists(full_path):
            os.unlink(full_path)

    for path in sync_plan["apply"]["additions"] + sync_plan["apply"]["modifications"]:
        source_path = os.path.join(extracted_root, path)
        target_path = os.path.join(".", path)
        if not os.path.exists(source_path):
            continue
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(source_path, target_path)
