import os
import sys

import httpx

from lib import config
from lib.pusher import get_vault_tree_metadata
from lib.workspace import classify_push_outcome, plan_sync, scan_workspace


def register_status_command(subparsers):
    status_parser = subparsers.add_parser("status", help="Show local, base, and remote workspace status")
    status_parser.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")


def handle_status(args):
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

    local_entries = scan_workspace(".")
    try:
        metadata = get_vault_tree_metadata(remote, vault_id, base_commit_id, token)
    except httpx.HTTPError as exc:
        print(f"Error: failed to load remote tree metadata: {exc}")
        sys.exit(1)

    base_entries = metadata.get("base_entries", {})
    remote_entries = metadata.get("head_entries", {})
    sync_plan = plan_sync(base_entries, local_entries, remote_entries)
    push_outcome = classify_push_outcome(local_entries, base_entries, remote_entries)

    print(f"Tracked head: {base_commit_id[:8] if base_commit_id else 'none'}")
    print(f"Remote head:  {metadata.get('head_commit_id', '')[:8] if metadata.get('head_commit_id') else 'empty'}")
    print()

    _print_delta("Local changes", sync_plan["local"])
    print()
    _print_delta("Remote changes", sync_plan["remote"])
    print()
    print(f"Push outcome: {push_outcome}")
    print(f"Sync outcome: {'conflict' if sync_plan['conflicts'] else 'clean apply'}")
    if sync_plan["conflicts"]:
        print("Conflicting paths:")
        for path in sync_plan["conflicts"]:
            print(f"  {path}")


def _print_delta(title: str, delta: dict):
    print(f"{title}: {len(delta['changed'])}")
    if delta["added"]:
        print("  Added:")
        for path in delta["added"]:
            print(f"    {path}")
    if delta["modified"]:
        print("  Modified:")
        for path in delta["modified"]:
            print(f"    {path}")
    if delta["deleted"]:
        print("  Deleted:")
        for path in delta["deleted"]:
            print(f"    {path}")
