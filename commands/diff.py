import argparse
import os
import sys

import httpx

from ..lib import config
from ..lib.pusher import get_vault_tree_metadata
from ..lib.workspace import diff_entry_maps, scan_workspace


def register_diff_command(subparsers):
    diff_parser = subparsers.add_parser("diff", help="Show summary diffs for local or remote changes")
    group = diff_parser.add_mutually_exclusive_group()
    group.add_argument("--local", action="store_true", help="Diff local workspace against tracked base")
    group.add_argument("--remote", action="store_true", help="Diff remote head against tracked base")
    group.add_argument("--staged-push", action="store_true", help="Diff the current local workspace that would be pushed")
    diff_parser.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")


def handle_diff(args):
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

    if args.remote:
        title = "Remote vs tracked base"
        delta = diff_entry_maps(base_entries, remote_entries)
    else:
        title = "Local vs tracked base"
        delta = diff_entry_maps(base_entries, local_entries)

    if args.staged_push:
        title = "Current local workspace vs tracked base"

    print(title)
    print("Added:")
    for path in delta["added"]:
        print(f"  {path}")
    print("Modified:")
    for path in delta["modified"]:
        print(f"  {path}")
    print("Deleted:")
    for path in delta["deleted"]:
        print(f"  {path}")
