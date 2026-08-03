"""
VOIDLINK — Cryptographic primitives.

Provides:
  * Ed25519 identity keypairs  — sign / verify messages (authenticity)
  * X25519 ECDH key exchange   — derive per-peer session keys (confidentiality)
  * AES-256-GCM                — encrypt / decrypt payloads
  * HKDF-SHA256                — stretch raw ECDH output into a 32-byte key
  * Key fingerprinting         — short human-readable node identity

Wire format for encrypted payloads
  [12-byte IV] + [ciphertext] + [16-byte GCM tag]  → base64url string
"""

from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature


# ─────────────────────────────────────────────────────────────────────────────
# Ed25519 identity
# ─────────────────────────────────────────────────────────────────────────────

def generate_identity() -> Tuple[bytes, bytes]:
    """
    Generate a fresh Ed25519 keypair.

    Returns:
        (private_key_bytes, public_key_bytes)  — both as raw 32-byte sequences.
    """
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return priv_bytes, pub_bytes


def sign(data: bytes, private_key_bytes: bytes) -> bytes:
    """Sign *data* with an Ed25519 private key.  Returns 64-byte signature."""
    priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return priv.sign(data)


def verify(data: bytes, signature: bytes, public_key_bytes: bytes) -> bool:
    """Verify an Ed25519 signature.  Returns True if valid, False otherwise."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub.verify(signature, data)
        return True
    except (InvalidSignature, ValueError):
        return False


def fingerprint(public_key_bytes: bytes, length: int = 16) -> str:
    """
    Return a short hex fingerprint of a public key for display.

    Example: ``a3f2 91bc 04de 77aa``
    """
    hex_str = public_key_bytes.hex()[:length]
    return " ".join(hex_str[i:i+4] for i in range(0, len(hex_str), 4))


# ─────────────────────────────────────────────────────────────────────────────
# X25519 ECDH + HKDF
# ─────────────────────────────────────────────────────────────────────────────

def generate_x25519_keypair() -> Tuple[X25519PrivateKey, bytes]:
    """
    Generate an ephemeral X25519 keypair.

    Returns:
        (private_key_object, public_key_bytes)
    """
    priv = X25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return priv, pub_bytes


def derive_session_key(
    our_private_key: X25519PrivateKey,
    their_public_key_bytes: bytes,
    info: bytes = b"voidlink-session-v1",
) -> bytes:
    """
    Perform X25519 ECDH and stretch the shared secret to a 32-byte AES key
    using HKDF-SHA256.

    Returns:
        32-byte symmetric key suitable for AES-256-GCM.
    """
    their_pub = X25519PublicKey.from_public_bytes(their_public_key_bytes)
    raw_secret = our_private_key.exchange(their_pub)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(raw_secret)
    return key


# ─────────────────────────────────────────────────────────────────────────────
# AES-256-GCM
# ─────────────────────────────────────────────────────────────────────────────

_IV_LEN = 12  # 96-bit nonce recommended for GCM


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Wire format: [12-byte IV] + [ciphertext + 16-byte GCM tag]
    """
    iv = os.urandom(_IV_LEN)
    aesgcm = AESGCM(key)
    ciphertext_tag = aesgcm.encrypt(iv, plaintext, None)
    return iv + ciphertext_tag


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Decrypt AES-256-GCM data produced by :func:`encrypt`.

    Raises:
        cryptography.exceptions.InvalidTag if authentication fails.
        ValueError if the data is too short.
    """
    if len(data) < _IV_LEN + 16:
        raise ValueError(f"Encrypted payload too short ({len(data)} bytes)")
    iv = data[:_IV_LEN]
    ciphertext_tag = data[_IV_LEN:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext_tag, None)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: base64url helpers
# ─────────────────────────────────────────────────────────────────────────────

def b64enc(data: bytes) -> str:
    """URL-safe base64 encode bytes → str."""
    return base64.urlsafe_b64encode(data).decode()


def b64dec(s: str) -> bytes:
    """URL-safe base64 decode str → bytes."""
    # Add padding if missing
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)
