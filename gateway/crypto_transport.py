"""run-jane application-layer encrypted transport primitives."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROTOCOL_VERSION = "v1"


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _aad(version: str, key_id: str, timestamp: int, request_id: str, scope: str) -> bytes:
    return f"{version}|{key_id}|{timestamp}|{request_id}|{scope}".encode("utf-8")


def _public_key_fields(document: dict[str, Any]) -> tuple[str, str]:
    data = document.get("data") if isinstance(document.get("data"), dict) else document
    key_id = str(data.get("keyId") or "").strip()
    public_key = str(data.get("publicKey") or data.get("publicKeyPem") or "").strip()
    if not key_id or not public_key:
        raise ValueError("授权服务公钥响应缺少 keyId/publicKey")
    return key_id, public_key


def _load_public_key(value: str) -> Any:
    encoded = value.strip()
    if encoded.startswith("-----BEGIN"):
        return serialization.load_pem_public_key(encoded.encode("ascii"))
    try:
        der = _b64decode(encoded)
    except Exception as exc:
        raise ValueError("授权服务 publicKey 不是有效的 Base64 DER SPKI 或 PEM") from exc
    return serialization.load_der_public_key(der)


def create_envelope(
    public_key_document: dict[str, Any],
    scope: str,
    payload: Any,
    *,
    now_ms: int | None = None,
    request_id: str | None = None,
    aes_key: bytes | None = None,
    iv: bytes | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Encrypt JSON payload and return the wire envelope plus response AES key."""
    key_id, public_key_value = _public_key_fields(public_key_document)
    timestamp = int(now_ms if now_ms is not None else time.time() * 1000)
    rid = request_id or str(uuid.uuid4())
    key = aes_key or os.urandom(32)
    nonce = iv or os.urandom(12)
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("AES-256-GCM requires a 32-byte key and 12-byte IV")
    aad = _aad(PROTOCOL_VERSION, key_id, timestamp, rid, scope)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    public_key = _load_public_key(public_key_value)
    encrypted_key = public_key.encrypt(
        key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return (
        {
            "version": PROTOCOL_VERSION,
            "keyId": key_id,
            "timestamp": timestamp,
            "requestId": rid,
            "scope": scope,
            "iv": _b64encode(nonce),
            "encryptedKey": _b64encode(encrypted_key),
            "ciphertext": _b64encode(ciphertext),
        },
        key,
    )


def decrypt_response(response: dict[str, Any], request: dict[str, Any], aes_key: bytes) -> Any:
    """Decrypt a response using the request key and response-specific AAD."""
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    iv = str(data.get("iv") or "").strip()
    ciphertext = str(data.get("ciphertext") or "").strip()
    if not iv or not ciphertext:
        raise ValueError("敏感接口未返回加密响应")
    aad = _aad(
        str(request["version"]),
        str(request["keyId"]),
        int(request["timestamp"]),
        str(request["requestId"]),
        str(request["scope"]),
    ) + b"|response"
    plaintext = AESGCM(aes_key).decrypt(_b64decode(iv), _b64decode(ciphertext), aad)
    return json.loads(plaintext.decode("utf-8"))
