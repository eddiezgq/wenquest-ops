"""File store for the document library (ADR-0014 item 1): the bytes of every imported file, kept once under their
SHA-256 on the company's own server. ``WQO_FILES_DIR`` (default /data/files) is the hub's file volume; backups
include it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024


def root() -> Path:
    return Path(os.environ.get("WQO_FILES_DIR", "/data/files"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def path(sha: str) -> Path:
    if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
        raise ValueError("not a SHA-256")
    return root() / sha[:2] / sha


def put(data: bytes) -> str:
    """Store the bytes (once) and return their SHA-256."""
    sha = digest(data)
    p = path(sha)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{sha}.{os.getpid()}.{secrets.token_hex(4)}.part")   # two uploads of one file: no clash
        tmp.write_bytes(data)
        tmp.replace(p)
    return sha


def get(sha: str) -> bytes:
    data = path(sha).read_bytes()
    if digest(data) != sha:
        raise OSError(f"stored file {sha} does not match its fingerprint")
    return data
