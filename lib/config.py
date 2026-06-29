"""
Geode CLI — Config management.

Reads/writes .geode/config.yaml in the project root.
"""

import os
from urllib.parse import urlparse

import yaml
from typing import Optional


CONFIG_DIR = ".geode"


def _config_dir(root_dir: str = ".") -> str:
    return os.path.join(root_dir, CONFIG_DIR)


def _config_file(root_dir: str = ".") -> str:
    return os.path.join(_config_dir(root_dir), "config.yaml")


def ensure_config_dir(root_dir: str = "."):
    os.makedirs(_config_dir(root_dir), exist_ok=True)


def load_config(root_dir: str = ".") -> dict:
    config_file = _config_file(root_dir)
    if not os.path.exists(config_file):
        return {}
    with open(config_file, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict, root_dir: str = "."):
    config = config.copy()
    remote = config.get("remote")
    if isinstance(remote, str):
        config["remote"] = normalize_remote_url(remote)

    ensure_config_dir(root_dir)
    with open(_config_file(root_dir), "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)


def get_remote(root_dir: str = ".") -> Optional[str]:
    remote = load_config(root_dir).get("remote")
    if not isinstance(remote, str):
        return remote
    return normalize_remote_url(remote)


def get_vault_id(root_dir: str = ".") -> Optional[str]:
    return load_config(root_dir).get("vault_id")


def get_head_commit_id(root_dir: str = ".") -> Optional[str]:
    return load_config(root_dir).get("head_commit_id")


def set_remote(url: str, root_dir: str = "."):
    config = load_config(root_dir)
    config["remote"] = url
    save_config(config, root_dir)


def set_vault_id(vault_id: str, root_dir: str = "."):
    config = load_config(root_dir)
    config["vault_id"] = vault_id
    save_config(config, root_dir)


def set_head_commit_id(head_commit_id: Optional[str], root_dir: str = "."):
    config = load_config(root_dir)
    if head_commit_id:
        config["head_commit_id"] = head_commit_id
    else:
        config.pop("head_commit_id", None)
    save_config(config, root_dir)


def normalize_remote_url(url: str) -> str:
    if not (url.startswith("http://") or url.startswith("https://")):
        return url

    parsed = urlparse(url)
    if not parsed.netloc:
        return url

    return f"{parsed.scheme}://{parsed.netloc}"
