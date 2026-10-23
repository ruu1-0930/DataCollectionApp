"""Strict device observations; presentation policy lives in radar_query."""

from decimal import Decimal
import math


def parse_radar_payload(payload):
    # Imported lazily to keep the collection error boundary shared without a cycle.
    from services.collection_ingest import CollectionError, exact, integer
    exact(payload, {'frames','bytes','age_ms','stale','targets'})
    integer(payload['frames'])
    integer(payload['bytes'])
    age = payload['age_ms']
    try:
        valid_age = age is None or (type(age) in (int,float) and age >= 0 and math.isfinite(age))
    except OverflowError:
        valid_age = False
    if not valid_age or type(payload['stale']) is not bool:
        raise CollectionError()
    targets = payload['targets']
    if not isinstance(targets,list) or len(targets) > 3:
        raise CollectionError()
    slots = set()
    for target in targets:
        exact(target, {'slot','present','x_mm','y_mm','speed_cms','resolution_mm'})
        slot = target['slot']
        if type(slot) is not int or slot not in (1,2,3) or slot in slots or type(target['present']) is not bool:
            raise CollectionError()
        slots.add(slot)
        for key,low,high in (('x_mm',-32767,32767),('y_mm',-32767,32767),('speed_cms',-32767,32767),('resolution_mm',0,65535)):
            if type(target[key]) is not int or not low <= target[key] <= high:
                raise CollectionError()
    return dict(payload,targets=[dict(target) for target in targets])


def canonical_radar_payload(payload):
    result = parse_radar_payload(payload)
    age = result['age_ms']
    if age is not None:
        result['age_ms'] = (Decimal(age) if type(age) is int else Decimal(str(age)).normalize()) if age else Decimal(0)
    return result
