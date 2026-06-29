import os
import sys
from urllib.parse import urlparse

from lib import config
from lib.pusher import resolve_vault_by_path


DEFAULT_GEODEIGNORE = """# Geode ignore (gitignore-compatible format)
__pycache__/
*.pyc
.DS_Store
node_modules/
.geode/
venv/
env/
.env
.env.*
dist/
build/
.git/
*.log
tmp/
temp/
"""


def register_init_command(subparsers):
    init_parser = subparsers.add_parser("init", help="Initialize the current directory as a Geode workspace")
    init_parser.add_argument("directory", nargs="?", default=".", help="Directory to initialize (defaults to current directory)")
    init_parser.add_argument("--remote", help="Default remote URL to store in .geode/config.yaml. A full vault URL also works.")
    init_parser.add_argument("--vault-id", help="Vault UUID to store in .geode/config.yaml")
    init_parser.add_argument("--token", help="API auth token (or set GEODE_TOKEN env var)")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config values when re-initializing")
    init_parser.add_argument("--no-ignorefile", action="store_true", help="Do not create a starter .geodeignore file")


def handle_init(args):
    root_dir = os.path.abspath(args.directory)

    if not os.path.exists(root_dir):
        print(f"Error: directory does not exist: {root_dir}")
        sys.exit(1)

    if not os.path.isdir(root_dir):
        print(f"Error: not a directory: {root_dir}")
        sys.exit(1)

    existing_config = config.load_config(root_dir)
    if existing_config and not args.force and (args.remote or args.vault_id):
        print("Error: workspace already has config values. Re-run with --force to overwrite them.")
        sys.exit(1)

    remote = config.normalize_remote_url(args.remote) if args.remote else None
    vault_id = args.vault_id
    token = args.token or os.environ.get("GEODE_TOKEN")

    if args.remote and not vault_id:
        parsed_remote, detected_vault_id = _detect_vault_config(args.remote, token)
        remote = parsed_remote
        vault_id = detected_vault_id

    next_config = existing_config.copy()
    if args.force and existing_config:
        next_config.pop("head_commit_id", None)
    if remote:
        next_config["remote"] = remote
    if vault_id:
        next_config["vault_id"] = vault_id

    config.save_config(next_config, root_dir=root_dir)

    ignorefile_created = False
    ignorefile_path = os.path.join(root_dir, ".geodeignore")
    if not args.no_ignorefile and not os.path.exists(ignorefile_path):
        with open(ignorefile_path, "w") as f:
            f.write(DEFAULT_GEODEIGNORE)
        ignorefile_created = True

    print(f"Initialized Geode workspace in {root_dir}")
    print(f"Config path: {os.path.join(root_dir, '.geode', 'config.yaml')}")
    if remote:
        print(f"Remote set to: {remote}")
    if vault_id:
        print(f"Vault ID set to: {vault_id}")
    if ignorefile_created:
        print(f"Created starter ignore file: {ignorefile_path}")

    if not remote:
        print("Next step: run 'geode vault set-url <url> --vault-id <vault-id>' or 'geode clone <owner/vault>'.")
    elif not vault_id:
        print("Next step: set or resolve a vault id, then run 'geode push' or 'geode sync'.")
    else:
        print("Next step: run 'geode push' or 'geode sync' from this workspace.")


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
