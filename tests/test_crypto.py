"""Tests for the crypto module."""

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from clawdia.crypto import (
    decrypt_content,
    derive_room_key,
    encrypt_content,
    generate_local_key,
    generate_passphrase,
    is_encrypted,
    load_or_create_local_key,
)


# ---------------------------------------------------------------------------
# generate_passphrase
# ---------------------------------------------------------------------------

def test_generate_passphrase_length():
    pp = generate_passphrase()
    assert len(pp) == 32


def test_generate_passphrase_is_hex():
    pp = generate_passphrase()
    int(pp, 16)  # raises if not valid hex


def test_generate_passphrase_unique():
    assert generate_passphrase() != generate_passphrase()


# ---------------------------------------------------------------------------
# derive_room_key
# ---------------------------------------------------------------------------

def test_derive_room_key_deterministic():
    k1 = derive_room_key("secret", "room-123")
    k2 = derive_room_key("secret", "room-123")
    assert k1 == k2


def test_derive_room_key_length():
    key = derive_room_key("pass", "room")
    assert len(key) == 32


def test_derive_room_key_different_passphrase():
    k1 = derive_room_key("alpha", "room")
    k2 = derive_room_key("beta", "room")
    assert k1 != k2


def test_derive_room_key_different_room():
    k1 = derive_room_key("pass", "room-a")
    k2 = derive_room_key("pass", "room-b")
    assert k1 != k2


# ---------------------------------------------------------------------------
# encrypt_content / decrypt_content round-trip
# ---------------------------------------------------------------------------

def test_round_trip_short():
    key = generate_local_key()
    plaintext = "Hello, world!"
    envelope = encrypt_content(plaintext, key)
    assert decrypt_content(envelope, key) == plaintext


def test_round_trip_long():
    key = generate_local_key()
    plaintext = "Line {}\n" * 1000
    envelope = encrypt_content(plaintext, key)
    assert decrypt_content(envelope, key) == plaintext


def test_round_trip_unicode():
    key = generate_local_key()
    plaintext = "Emoji: \U0001f600 CJK: \u4e16\u754c Accents: caf\u00e9"
    envelope = encrypt_content(plaintext, key)
    assert decrypt_content(envelope, key) == plaintext


def test_round_trip_empty():
    key = generate_local_key()
    envelope = encrypt_content("", key)
    assert decrypt_content(envelope, key) == ""


def test_wrong_key_raises():
    key1 = generate_local_key()
    key2 = generate_local_key()
    envelope = encrypt_content("secret message", key1)
    with pytest.raises(InvalidTag):
        decrypt_content(envelope, key2)


def test_tampered_ciphertext_raises():
    key = generate_local_key()
    envelope = encrypt_content("test", key)
    # Flip a character in the ciphertext
    import json
    data = json.loads(envelope)
    ct = data["ct"]
    data["ct"] = ct[:-1] + ("A" if ct[-1] != "A" else "B")
    tampered = json.dumps(data)
    with pytest.raises(InvalidTag):
        decrypt_content(tampered, key)


def test_decrypt_invalid_json():
    key = generate_local_key()
    with pytest.raises(ValueError, match="Invalid encryption envelope"):
        decrypt_content("not json at all", key)


def test_decrypt_wrong_version():
    key = generate_local_key()
    with pytest.raises(ValueError, match="Unsupported envelope version"):
        decrypt_content('{"v":99,"ct":"aa","iv":"bb"}', key)


def test_each_encryption_uses_unique_nonce():
    key = generate_local_key()
    e1 = encrypt_content("same", key)
    e2 = encrypt_content("same", key)
    # Same plaintext + same key should produce different ciphertexts (random nonce)
    assert e1 != e2


# ---------------------------------------------------------------------------
# is_encrypted
# ---------------------------------------------------------------------------

def test_is_encrypted_true():
    key = generate_local_key()
    envelope = encrypt_content("test", key)
    assert is_encrypted(envelope) is True


def test_is_encrypted_false_plaintext():
    assert is_encrypted("Hello, world!") is False


def test_is_encrypted_false_other_json():
    assert is_encrypted('{"type":"message"}') is False


def test_is_encrypted_false_empty():
    assert is_encrypted("") is False


# ---------------------------------------------------------------------------
# generate_local_key
# ---------------------------------------------------------------------------

def test_generate_local_key_length():
    assert len(generate_local_key()) == 32


def test_generate_local_key_unique():
    assert generate_local_key() != generate_local_key()


# ---------------------------------------------------------------------------
# load_or_create_local_key
# ---------------------------------------------------------------------------

def test_load_or_create_creates_key(tmp_path):
    key = load_or_create_local_key(tmp_path)
    assert len(key) == 32
    assert (tmp_path / "local.key").exists()


def test_load_or_create_returns_same_key(tmp_path):
    k1 = load_or_create_local_key(tmp_path)
    k2 = load_or_create_local_key(tmp_path)
    assert k1 == k2


def test_load_or_create_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    key = load_or_create_local_key(nested)
    assert len(key) == 32
    assert nested.exists()


def test_load_or_create_file_permissions(tmp_path):
    load_or_create_local_key(tmp_path)
    key_path = tmp_path / "local.key"
    import stat
    mode = key_path.stat().st_mode
    assert mode & stat.S_IRUSR  # owner read
    assert mode & stat.S_IWUSR  # owner write
    assert not (mode & stat.S_IRGRP)  # no group read
    assert not (mode & stat.S_IROTH)  # no other read


# ---------------------------------------------------------------------------
# Integration: derive_room_key + encrypt/decrypt
# ---------------------------------------------------------------------------

def test_room_key_encrypt_decrypt():
    """Full flow: passphrase -> key derivation -> encrypt -> decrypt."""
    passphrase = generate_passphrase()
    room_id = "test-room-uuid"

    key = derive_room_key(passphrase, room_id)
    plaintext = "Hello from the encrypted group chat!"

    envelope = encrypt_content(plaintext, key)
    assert is_encrypted(envelope)

    # A second participant deriving the same key can decrypt
    key2 = derive_room_key(passphrase, room_id)
    assert decrypt_content(envelope, key2) == plaintext
