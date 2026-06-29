"""
Hematite CLI — Push HTTP client.

Handles the three-phase push protocol:
  1. POST /push/start  → manifest dedup + presigned URL
  2. PUT tar to S3 presigned URL
  3. POST /push/complete → trigger processing
"""

import os
import json
import tarfile
import io
import httpx
from typing import Optional


def _api_url(remote: str, path: str) -> str:
    return f"{remote.rstrip('/')}/api{path}"


def start_push(
    remote: str,
    vault_id: str,
    manifest: list[dict],
    message: str,
    base_commit_id: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.post(
        _api_url(remote, f"/vaults/{vault_id}/push/start"),
        json={"files": manifest, "message": message, "base_commit_id": base_commit_id},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_tar(upload_url: str, tar_path: str) -> bool:
    with open(tar_path, "rb") as f:
        resp = httpx.put(upload_url, content=f.read(), timeout=300)
        return resp.status_code in (200, 201, 204)


def complete_push(
    remote: str,
    vault_id: str,
    run_id: str,
    manifest: list[dict],
    message: str,
    upload_key: str,
    base_commit_id: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.post(
        _api_url(remote, f"/vaults/{vault_id}/push/{run_id}/complete"),
        json={
            "manifest": manifest,
            "message": message,
            "upload_key": upload_key,
            "base_commit_id": base_commit_id,
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_vault_info(remote: str, vault_id: str, token: Optional[str] = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(
        _api_url(remote, f"/vaults/{vault_id}"),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def resolve_vault_by_path(
    remote: str,
    owner: str,
    vault_slug: str,
    token: Optional[str] = None,
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(
        _api_url(remote, f"/vaults/by-path/{owner}/{vault_slug}"),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_vault_tree_metadata(
    remote: str,
    vault_id: str,
    base_commit_id: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {}
    if base_commit_id:
        params["base_commit_id"] = base_commit_id

    resp = httpx.get(
        _api_url(remote, f"/vaults/{vault_id}/tree-metadata"),
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_push_run_status(remote: str, vault_id: str, run_id: str, token: Optional[str] = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(
        _api_url(remote, f"/vaults/{vault_id}/push/{run_id}"),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def download_vault_archive(remote: str, vault_id: str, token: Optional[str] = None) -> tuple[bytes, Optional[str]]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(
        _api_url(remote, f"/vaults/{vault_id}/archive"),
        headers=headers,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("X-Geode-Head-Commit") or None


def build_tar(files: list[tuple[str, str]], output_path: str):
    """files: list of (path_in_tar, local_filepath)"""
    with tarfile.open(output_path, "w") as tar:
        for arcname, local_path in files:
            tar.add(local_path, arcname=arcname)


def build_tar_stream(entries: list[tuple[str, bytes]]) -> bytes:
    """Create a tar in memory from (path, content) pairs."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for arcname, content in entries:
            info = tarfile.TarInfo(name=arcname)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()
