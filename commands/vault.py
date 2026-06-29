"""
geode vault – Vault management commands.

  geode vault set-url <url>   Configure remote and vault for the current directory.
"""

import argparse
from ..lib import config


def register_vault_command(subparsers):
    vault_parser = subparsers.add_parser("vault", help="Vault management commands")
    vault_sub = vault_parser.add_subparsers(dest="vault_command", required=True)

    set_url = vault_sub.add_parser("set-url", help="Configure upstream remote")
    set_url.add_argument("url", help="Remote URL (https://geode.beaglabs.com) or local path")
    set_url.add_argument("--vault-id", help="Vault UUID (optional, auto-detected from URL)")

    vault_sub.add_parser("create", help="Create a new local vault (stub)")


def handle_vault(args):
    if args.vault_command == "set-url":
        url = args.url
        config.set_remote(url)
        config.set_head_commit_id(None)

        if args.vault_id:
            config.set_vault_id(args.vault_id)

        print(f"Remote set to: {url}")
        if args.vault_id:
            print(f"Vault ID set to: {args.vault_id}")

    elif args.vault_command == "create":
        print("geode vault create: stub — implementation pending")
