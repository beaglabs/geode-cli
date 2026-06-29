import argparse
import os
import sys
from urllib.parse import urlparse

import httpx

from ..lib import config
from ..lib.archive import extract_archive_bytes
from ..lib.pusher import download_vault_archive, resolve_vault_by_path


def register_clone_command(subparsers):
    clone_parser = subparsers.add_parser("clone", help="Clone a vault from a remote")
    clone_parser.add_argument(
        "source",
        help="Remote vault URL (https://geode.beaglabs.com/owner/vault) or shorthand (owner/vault)",
    )
    clone_parser.add_argument("directory", nargs="?", help="Destination directory (defaults to vault slug)")
    clone_parser.add_argument("--remote", help="Remote host to use with owner/vault shorthand")
    clone_parser.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")
    clone_parser.add_argument("--force", action="store_true", help="Allow cloning into a non-empty destination")


def _parse_clone_source(source: str, explicit_remote: str | None) -> tuple[str, str, str]:
    if source.startswith("http://") or source.startswith("https://"):
        parsed = urlparse(source)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"invalid vault URL '{source}'")
        return f"{parsed.scheme}://{parsed.netloc}", parts[-2], parts[-1]

    parts = [part for part in source.split("/") if part]
    if len(parts) != 2:
        raise ValueError(f"invalid vault reference '{source}'. Use owner/vault or a full URL.")

    remote = explicit_remote or config.get_remote()
    if not remote:
        raise ValueError("owner/vault shorthand requires --remote or an existing workspace remote")

    return remote, parts[0], parts[1]


def _ensure_clone_destination(path: str, force: bool) -> None:
    if not os.path.exists(path):
        return

    if not os.path.isdir(path):
        raise ValueError(f"destination exists and is not a directory: {path}")

    if os.listdir(path) and not force:
        raise ValueError(f"destination is not empty: {path}. Re-run with --force to use it anyway.")


def handle_clone(args):
    token = args.token or os.environ.get("GEODE_TOKEN")

    try:
        remote, owner, vault_slug = _parse_clone_source(args.source, args.remote)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    destination = args.directory or vault_slug

    try:
        _ensure_clone_destination(destination, args.force)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Cloning {owner}/{vault_slug} from {remote} into {destination}...")

    try:
        vault_info = resolve_vault_by_path(remote, owner, vault_slug, token)
        archive_bytes, head_commit_id = download_vault_archive(remote, vault_info["id"], token)
    except httpx.HTTPError as exc:
        print(f"Error: failed to clone vault: {exc}")
        sys.exit(1)

    os.makedirs(destination, exist_ok=True)

    try:
        extract_archive_bytes(archive_bytes, destination)
    except ValueError as exc:
        print(f"Error: failed to extract vault archive: {exc}")
        sys.exit(1)

    config.save_config(
        {
            "remote": remote,
            "vault_id": vault_info["id"],
            "head_commit_id": head_commit_id,
        },
        root_dir=destination,
    )

    display_head = head_commit_id[:8] if head_commit_id else "empty"
    print(f"Cloned {vault_info.get('name', vault_slug)} at head {display_head}.")
