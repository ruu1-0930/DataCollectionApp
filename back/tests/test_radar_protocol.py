from copy import deepcopy
import importlib

import pytest

from services.collection_ingest import CollectionError


def radar_payload(**over):
    value = dict(frames=1, bytes=30, age_ms=0, stale=False, targets=[
        dict(slot=3, present=True, x_mm=-32767, y_mm=32767, speed_cms=-2, resolution_mm=65535)])
    value.update(over)
    return value


def test_radar_payload_limits_and_sparse_slots():
    protocol = importlib.import_module('services.radar_protocol')
    for targets in ([], radar_payload()['targets'], [dict(radar_payload()['targets'][0],slot=i) for i in (3,1,2)]):
        payload = radar_payload(targets=targets)
        assert protocol.parse_radar_payload(payload) == payload
    invalid = [dict(frames=True), dict(bytes=9007199254740992), dict(age_ms=float('nan')),
               dict(age_ms=-1),dict(stale=0),dict(extra=1)]
    for over in invalid:
        with pytest.raises(CollectionError):
            protocol.parse_radar_payload(radar_payload(**over))
    for over in (dict(slot=True),dict(x_mm=32768),dict(resolution_mm=65536),dict(present=1),dict(speed_cms=1.0)):
        with pytest.raises(CollectionError):
            protocol.parse_radar_payload(radar_payload(targets=[dict(radar_payload()['targets'][0],**over)]))
    with pytest.raises(CollectionError):
        protocol.parse_radar_payload(radar_payload(targets=radar_payload()['targets']*2))
    original = radar_payload(age_ms=1.0)
    assert protocol.canonical_radar_payload(original) == protocol.canonical_radar_payload(dict(original,age_ms=1))
    assert original == deepcopy(original)


def test_canonical_age_retains_large_integer_distinctions():
    from services.radar_protocol import canonical_radar_payload
    from services.canonical_json import canonical_json_bytes
    first = canonical_json_bytes(canonical_radar_payload(radar_payload(age_ms=10**30+1)))
    second = canonical_json_bytes(canonical_radar_payload(radar_payload(age_ms=10**30+2)))
    assert first != second
    decimal = canonical_json_bytes(canonical_radar_payload(radar_payload(age_ms=0.1234567890123456)))
    assert b'"age_ms":"0.1234567890123456"' in decimal
    assert b'"age_ms":"0.000000000000000000000000000001"' in canonical_json_bytes(canonical_radar_payload(radar_payload(age_ms=1e-30)))
