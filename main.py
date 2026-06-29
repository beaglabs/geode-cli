"""Geode CLI entrypoint module."""

import argparse

from commands.clone import register_clone_command
from commands.diff import register_diff_command
from commands.init import register_init_command
from commands.push import register_push_command
from commands.status import register_status_command
from commands.sync import register_sync_command
from commands.vault import register_vault_command


def main():
    parser = argparse.ArgumentParser(
        prog="geode",
        description="Geode CLI – Cloud-native geospatial data vault client.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_init_command(subparsers)
    register_push_command(subparsers)
    register_clone_command(subparsers)
    register_status_command(subparsers)
    register_diff_command(subparsers)
    register_sync_command(subparsers)
    register_vault_command(subparsers)

    args = parser.parse_args()

    if args.command == "init":
        from commands.init import handle_init

        handle_init(args)
    elif args.command == "clone":
        from commands.clone import handle_clone

        handle_clone(args)
    elif args.command == "push":
        from commands.push import handle_push

        handle_push(args)
    elif args.command == "status":
        from commands.status import handle_status

        handle_status(args)
    elif args.command == "diff":
        from commands.diff import handle_diff

        handle_diff(args)
    elif args.command == "sync":
        from commands.sync import handle_sync

        handle_sync(args)
    elif args.command == "vault":
        from commands.vault import handle_vault

        handle_vault(args)
    else:
        parser.print_help()
