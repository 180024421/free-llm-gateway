"""Protocol tests for the run-jane encrypted transport."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gateway.crypto_transport import create_envelope, decrypt_response


@pytest.fixture()
def protocol_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, {"keyId": "test-key", "publicKey": base64.b64encode(public_der).decode()}


def _aad(envelope):
    return (
        f"{envelope['version']}|{envelope['keyId']}|{envelope['timestamp']}|"
        f"{envelope['requestId']}|{envelope['scope']}"
    ).encode()


def test_request_and_response_round_trip(protocol_keys):
    private_key, public_document = protocol_keys
    payload = {"cardCode": "fixture-only", "nested": {"ok": True}}
    envelope, response_key = create_envelope(
        public_document,
        "gateway-license.redeem",
        payload,
        now_ms=1_725_000_000_000,
        request_id="fixture-request",
        aes_key=b"K" * 32,
        iv=b"I" * 12,
    )
    assert envelope["version"] == "v1"

    aes_key = private_key.decrypt(
        base64.b64decode(envelope["encryptedKey"]),
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    plaintext = AESGCM(aes_key).decrypt(
        base64.b64decode(envelope["iv"]),
        base64.b64decode(envelope["ciphertext"]),
        _aad(envelope),
    )
    assert json.loads(plaintext) == payload

    response_iv = b"R" * 12
    response_plaintext = json.dumps({"valid": True}, separators=(",", ":")).encode()
    response_ciphertext = AESGCM(aes_key).encrypt(
        response_iv,
        response_plaintext,
        _aad(envelope) + b"|response",
    )
    encrypted_response = {
        "iv": base64.b64encode(response_iv).decode(),
        "ciphertext": base64.b64encode(response_ciphertext).decode(),
    }
    assert decrypt_response(encrypted_response, envelope, response_key) == {"valid": True}


def test_response_rejects_wrong_aad(protocol_keys):
    _, public_document = protocol_keys
    envelope, key = create_envelope(public_document, "user.login", {})
    with pytest.raises(Exception):
        decrypt_response(
            {"iv": base64.b64encode(b"R" * 12).decode(), "ciphertext": base64.b64encode(b"x" * 32).decode()},
            envelope,
            key,
        )


def test_pem_public_key_remains_compatible(protocol_keys):
    private_key, _ = protocol_keys
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    envelope, _ = create_envelope(
        {"keyId": "pem-key", "publicKey": public_pem},
        "user.register",
        {"fixture": True},
    )
    assert envelope["keyId"] == "pem-key"
