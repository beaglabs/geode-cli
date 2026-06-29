"""
Hematite CLI — BLAKE3 file hashing.
"""

import os
import blake3


def hash_file(filepath: str) -> str:
    hasher = blake3.blake3()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_bytes(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()