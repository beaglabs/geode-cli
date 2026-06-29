import io
import os
import shutil
import tarfile
from pathlib import PurePosixPath


def _safe_archive_path(name: str) -> str:
    normalized = name.lstrip("/")
    parts = PurePosixPath(normalized).parts
    if not normalized or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe archive member path: {name}")
    return str(PurePosixPath(*parts))


def extract_archive_bytes(archive_bytes: bytes, destination: str) -> None:
    os.makedirs(destination, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tar:
        for member in tar.getmembers():
            safe_name = _safe_archive_path(member.name)
            if member.isdir():
                os.makedirs(os.path.join(destination, safe_name), exist_ok=True)
                continue

            if member.issym() or member.islnk():
                raise ValueError(f"Unsupported archive member type: {member.name}")

            source = tar.extractfile(member)
            if source is None:
                continue

            target_path = os.path.join(destination, safe_name)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "wb") as handle:
                shutil.copyfileobj(source, handle)


def replace_directory_from_archive(
    archive_bytes: bytes,
    destination: str,
    preserve_names: set[str] | None = None,
) -> None:
    preserve_names = preserve_names or set()

    for name in os.listdir(destination):
        if name in preserve_names:
            continue

        path = os.path.join(destination, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)

    extract_archive_bytes(archive_bytes, destination)
