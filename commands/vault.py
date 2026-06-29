"""
geode vault – Vault management commands.

  geode vault set-url <url>   Configure remote and vault for the current directory.
"""

import os
from urllib.parse import urlparse

from lib import config
from lib.pusher import resolve_vault_by_path


def register_vault_command(subparsers):
    vault_parser = subparsers.add_parser("vault", help="Vault management commands")
    vault_sub = vault_parser.add_subparsers(dest="vault_command", required=True)

    set_url = vault_sub.add_parser("set-url", help="Configure upstream remote")
    set_url.add_argument("url", help="Remote URL (https://geode.beaglabs.com) or local path")
    set_url.add_argument("--vault-id", help="Vault UUID (optional, auto-detected from URL)")
    set_url.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")

    vault_sub.add_parser("create", help="Create a new local vault (stub)")


def handle_vault(args):
    if args.vault_command == "set-url":
        token = args.token or os.environ.get("GEODE_TOKEN")
        remote = config.normalize_remote_url(args.url)
        vault_id = args.vault_id

        if args.url and not vault_id:
            remote, vault_id = _detect_vault_config(args.url, token)

        config.set_remote(remote)
        config.set_head_commit_id(None)

        if vault_id:
            config.set_vault_id(vault_id)

        print(f"Remote set to: {remote}")
        if vault_id:
            print(f"Vault ID set to: {vault_id}")
        else:
            print("Vault ID not set. Use a full vault URL or pass --vault-id before running push/sync/status.")

    elif args.vault_command == "create":
        print("geode vault create: stub — implementation pending")


def _detect_vault_config(remote_value: str, token: str | None) -> tuple[str, str | None]:
    if not (remote_value.startswith("http://") or remote_value.startswith("https://")):
        return remote_value, None

    parsed = urlparse(remote_value)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return remote_value, None

    remote = f"{parsed.scheme}://{parsed.netloc}"
    owner = parts[-2]
    vault_slug = parts[-1]

    try:
        vault = resolve_vault_by_path(remote, owner, vault_slug, token)
    except Exception as exc:
        print(f"Warning: could not auto-detect vault id from {remote_value}: {exc}")
        return remote, None

    return remote, vault.get("id")
