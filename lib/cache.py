"""
Geode CLI — Conversion cache.

Caches converted outputs in .geode/cache/.
Cache key: BLAKE3(source_path + source_hash + converter_version).
"""

import os
import shutil
from .hasher import hash_bytes

CACHE_DIR = os.path.join(".geode", "cache")
CONVERTER_VERSION = "1.0.0"


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def cache_key(source_path: str, source_hash: str) -> str:
    return hash_bytes(f"{source_path}:{source_hash}:{CONVERTER_VERSION}".encode())[:16]


def get_cached(source_path: str, source_hash: str) -> str | None:
    key = cache_key(source_path, source_hash)
    zarr_path = os.path.join(CACHE_DIR, f"{key}.zarr")
    arrow_path = os.path.join(CACHE_DIR, f"{key}.arrow")
    if os.path.exists(zarr_path):
        return zarr_path
    if os.path.exists(arrow_path):
        return arrow_path
    return None


def put_cache(source_path: str, source_hash: str, output_path: str):
    ensure_cache_dir()
    key = cache_key(source_path, source_hash)
    if os.path.isdir(output_path):
        dest = os.path.join(CACHE_DIR, f"{key}.zarr")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(output_path, dest)
        return dest
    else:
        dest = os.path.join(CACHE_DIR, f"{key}.arrow")
        shutil.copy2(output_path, dest)
        return dest
