from decimal import Decimal
import hashlib
import math

import pytest

from services.canonical_json import CanonicalJSONError, canonical_json_bytes, sha256_hex


def test_canonical_json_sorts_keys_and_uses_compact_utf8_nfc():
    payload = {"z": "e\u0301", "a": ["鞋垫", None]}

    assert canonical_json_bytes(payload) == '{"a":["鞋垫",null],"z":"é"}'.encode("utf-8")


def test_canonical_json_keeps_decimal_scale_as_a_json_string():
    assert canonical_json_bytes({"value": Decimal("1.2300")}) == b'{"value":"1.2300"}'


def test_sha256_hex_is_lowercase_hex():
    payload = canonical_json_bytes({"value": Decimal("1.2300")})

    assert sha256_hex(payload) == hashlib.sha256(payload).hexdigest()
    assert sha256_hex(payload).islower()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 1.25])
def test_canonical_json_rejects_float_numeric_inputs(value):
    with pytest.raises(CanonicalJSONError):
        canonical_json_bytes({"value": value})


def test_canonical_json_preserves_boolean_as_boolean_not_a_numeric_value():
    assert canonical_json_bytes({"value": True}) == b'{"value":true}'
