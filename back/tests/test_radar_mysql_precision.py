"""Exercise MySQL result processing offline; no engine, ML inference or socket use."""
import json
import math

import pytest
from sqlalchemy.dialects.mysql.pymysql import dialect
from sqlalchemy.schema import CreateTable

from models.models import CollectionRadarRaw, CollectionRadarTarget
from services.collection_ingest import CollectionError, normalized_event
from services.radar_query import _quality, _verified_payload


def reloaded_radar(age):
    payload = dict(frames=1,bytes=30,age_ms=age,stale=False,targets=[
        dict(slot=3,present=True,x_mm=10,y_mm=20,speed_cms=-2,resolution_mm=30)])
    event = dict(event_id='00000000-0000-4000-8000-000000000001',stream='radar',
        stream_sequence=0,connection_epoch=7,mobile_received_at='2026-10-23T00:00:01.000Z',payload=payload)
    accepted = normalized_event(event)
    mysql = dialect()
    processor = CollectionRadarRaw.__table__.c.age_ms.type.dialect_impl(mysql).result_processor(mysql,None)
    driver_value = None if age is None else float(age)
    loaded = processor(driver_value) if processor and driver_value is not None else driver_value
    row = CollectionRadarRaw(id=1,capture_id='00000000-0000-4000-8000-000000000002',
        event_id=event['event_id'],stream='radar',stream_sequence=0,connection_epoch=7,
        mobile_received_at=accepted['received'],server_received_at=accepted['received'],
        payload_hash=accepted['digest'],payload_json=json.dumps(payload),
        frames=1,bytes=30,age_ms=loaded,stale=False)
    row.targets = [CollectionRadarTarget(ordinal=0,**payload['targets'][0])]
    return row,payload


@pytest.mark.parametrize('age,label',[(0.1234567890123456,'fresh'),(1.1,'fresh'),
    (1e-30,'fresh'),(10**30+1,'stale'),(None,'stale'),(1500.0,'fresh')])
def test_mysql_age_result_processing_preserves_valid_audit_payload(age,label):
    row,payload = reloaded_radar(age)
    assert _verified_payload(row) == payload
    assert _quality(row)[0] == label


@pytest.mark.parametrize('fault',['double_ulp','payload_age','hash','target','null_age'])
def test_mysql_age_fix_keeps_exact_corruption_rejection(fault):
    row,payload = reloaded_radar(None if fault == 'null_age' else 0.1234567890123456)
    if fault == 'double_ulp':
        row.age_ms = math.nextafter(float(payload['age_ms']),math.inf)
    elif fault == 'payload_age':
        row.payload_json = json.dumps(dict(payload,age_ms=0.1234567891123456))
    elif fault == 'hash':
        row.payload_hash = '0'*64
    elif fault == 'target':
        row.targets[0].x_mm = 11
    else:
        row.age_ms = 0.0
    with pytest.raises(CollectionError) as rejected:
        _verified_payload(row)
    assert rejected.value.status == 503


def test_age_reader_configuration_keeps_mysql_double_ddl():
    mysql = dialect()
    assert CollectionRadarRaw.__table__.c.age_ms.type.compile(dialect=mysql) == 'DOUBLE'
    ddl = str(CreateTable(CollectionRadarRaw.__table__).compile(dialect=mysql))
    assert 'age_ms DOUBLE' in ddl
