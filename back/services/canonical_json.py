"""Strict canonical JSON for immutable clinical evidence inputs."""

import hashlib
import json
import unicodedata
from decimal import Decimal


class CanonicalJSONError(ValueError):
    """Raised when a value cannot be represented without ambiguous JSON coercion."""


def _canonical_value(value):
    if value is None or isinstance(value, str):
        return None if value is None else unicodedata.normalize("NFC", value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalJSONError("non-finite decimal")
        # Decimal JSON values are strings so their scale is never lost to a float.
        return format(value, "f")
    if isinstance(value, float):
        raise CanonicalJSONError("float values require an explicit Decimal conversion")
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError("object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise CanonicalJSONError("duplicate object key after NFC normalization")
            normalized[normalized_key] = _canonical_value(item)
        return {key: normalized[key] for key in sorted(normalized)}
    raise CanonicalJSONError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical UTF-8 JSON without using Python float serialization."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    """Return the lowercase SHA-256 hex digest for canonical bytes."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return hashlib.sha256(payload).hexdigest()
