"""Security and cryptography utilities: password hashing and JWT token processing."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
import bcrypt
from cryptography.fernet import Fernet, InvalidToken

from config.settings import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a secure bcrypt hash for a plaintext password."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return str(encoded_jwt)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT refresh token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return str(encoded_jwt)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed JWT token. Raises PyJWT exceptions on invalid/expired tokens."""
    payload: Dict[str, Any] = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return payload


def _get_fernet_cipher() -> Fernet:
    """Derive a deterministic 32-byte Fernet key from application secret key."""
    raw_key = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", None) or settings.JWT_SECRET_KEY
    key_bytes = hashlib.sha256(raw_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a sensitive string (e.g. API key, Secret key) using symmetric Fernet encryption."""
    if not plaintext:
        return plaintext
    # If already encrypted token, avoid double encrypting
    if plaintext.startswith("gAAAAA"):
        try:
            _get_fernet_cipher().decrypt(plaintext.encode("utf-8"))
            return plaintext
        except Exception:
            pass
    cipher = _get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_secret(ciphertext_or_plaintext: Optional[str]) -> Optional[str]:
    """Decrypt a ciphertext secret. If ciphertext is plaintext or invalid token, fallback gracefully."""
    if not ciphertext_or_plaintext:
        return ciphertext_or_plaintext
    try:
        cipher = _get_fernet_cipher()
        decrypted_bytes = cipher.decrypt(ciphertext_or_plaintext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except (InvalidToken, Exception):
        # Fallback to returning the raw value (e.g., legacy unencrypted string)
        return ciphertext_or_plaintext

