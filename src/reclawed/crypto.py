"""Cryptographic primitives for E2E relay encryption and local DB encryption."""

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Envelope version — bump if the format changes.
_ENVELOPE_VERSION = 1
_ENVELOPE_PREFIX = '{"v":1,'

# PBKDF2 iterations for room key derivation.
_PBKDF2_ITERATIONS = 100_000


def generate_passphrase() -> str:
    """Generate a 32-character hex passphrase for room encryption."""
    return secrets.token_hex(16)


def derive_room_key(passphrase: str, room_id: str) -> bytes:
    """Derive a 256-bit AES key from a passphrase and room ID.

    Uses PBKDF2-HMAC-SHA256 with the room_id as the salt.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=room_id.encode("utf-8"),
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_content(plaintext: str, key: bytes) -> str:
    """Encrypt a string with AES-256-GCM, returning a JSON envelope string.

    The envelope format is::

        {"v":1,"ct":"<base64>","iv":"<base64>"}
    """
    aesgcm = AESGCM(key)
    iv = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return json.dumps(
        {
            "v": _ENVELOPE_VERSION,
            "ct": base64.b64encode(ciphertext).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
        },
        separators=(",", ":"),
    )


def decrypt_content(envelope: str, key: bytes) -> str:
    """Decrypt a JSON envelope string back to plaintext.

    Raises ``ValueError`` on invalid envelope format.
    Raises ``cryptography.exceptions.InvalidTag`` on wrong key or tampered data.
    """
    try:
        data = json.loads(envelope)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid encryption envelope") from exc

    if data.get("v") != _ENVELOPE_VERSION:
        raise ValueError(f"Unsupported envelope version: {data.get('v')}")

    ciphertext = base64.b64decode(data["ct"])
    iv = base64.b64decode(data["iv"])

    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext_bytes.decode("utf-8")


def is_encrypted(content: str) -> bool:
    """Quick check whether a content string is an encrypted envelope."""
    return content.startswith(_ENVELOPE_PREFIX)


def generate_local_key() -> bytes:
    """Generate a random 256-bit key for local database encryption."""
    return os.urandom(32)


def load_or_create_local_key(data_dir: Path) -> bytes:
    """Load the local encryption key from disk, creating it if it doesn't exist.

    The key file is stored at ``{data_dir}/local.key`` with 0600 permissions.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / "local.key"

    if key_path.exists():
        return key_path.read_bytes()

    key = generate_local_key()
    key_path.write_bytes(key)
    key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return key
