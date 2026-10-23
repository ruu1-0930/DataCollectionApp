"""Operator-only radar verification on one pre-created empty disposable MySQL DB.

No schema/GRANT/server/model operations. Run in a fresh Python process with an
explicit --env-file; credentials never select the database or enter diagnostics.
"""
import argparse
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import secrets
import sys
from types import ModuleType
from uuid import uuid4


DATABASE = 'lanya_radar_verify_20261023'
TABLES = ('clinicians','patients','devices','device_raw_data','collection_sessions',
          'collection_insole_frames','collection_gps_raw','collection_radar_raw','collection_radar_targets')
CHECKPOINTS = frozenset(('startup','preflight','setup','service','constraints','cleanup'))
_stage = ContextVar('radar_verifier_stage',default='startup')


class VerificationFailure(RuntimeError):
    pass


def require(condition):
    if not condition:
        raise VerificationFailure('verification condition failed')


def checkpoint(name):
    require(name in CHECKPOINTS)
    _stage.set(name)


def mysql_errno(error):
    errors = sys.modules.get('sqlalchemy.exc')
    if errors is None or not isinstance(error,errors.DBAPIError):
        return None
    args = getattr(error.orig,'args',())
    code = args[0] if args else None
    return code if type(code) is int and 0 < code <= 65535 else None


def failure_detail(error):
    errors = sys.modules.get('sqlalchemy.exc')
    category = ('condition' if isinstance(error,VerificationFailure) else
                'database' if errors and isinstance(error,errors.DBAPIError) else 'unexpected')
    detail = 'checkpoint='+_stage.get()+' category='+category
    code = mysql_errno(error)
    return detail + (' mysql_errno='+str(code) if code is not None else '')


def fixed_schema(connection):
    require(connection.exec_driver_sql('SELECT DATABASE()').scalar_one() == DATABASE)


def empty_tables(connection):
    for table in TABLES:
        require(connection.exec_driver_sql('SELECT COUNT(*) FROM `'+table+'`').scalar_one() == 0)


def preflight(connection):
    fixed_schema(connection)
    version = connection.exec_driver_sql('SELECT VERSION()').scalar_one()
    require(isinstance(version,str) and 'mariadb' not in version.lower())
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:\D|$)',version)
    require(match is not None and tuple(map(int,match.groups())) >= (8,0,16))
    tables = dict(connection.exec_driver_sql('SELECT table_name, engine FROM information_schema.tables '
                                            'WHERE table_schema = DATABASE()').all())
    require(set(tables) == set(TABLES) and all(engine == 'InnoDB' for engine in tables.values()))
    empty_tables(connection)


def target_url(env_file):
    from dotenv import dotenv_values
    from sqlalchemy.engine import URL
    path = Path(env_file)
    require(path.is_file())
    values = dotenv_values(path,interpolate=False)
    require(all(values.get(key) for key in ('DB_HOST','DB_USER','DB_PASS')))
    port = int(values.get('DB_PORT') or '3306')
    require(1 <= port <= 65535)
    return URL.create('mysql+pymysql',username=values['DB_USER'],password=values['DB_PASS'],
                      host=values['DB_HOST'],port=port,database=DATABASE)


def bootstrap(env_file):
    """Factory/service from this tree; the unrelated eager legacy SVM is fenced."""
    import dotenv
    uri = target_url(env_file)
    root = Path(__file__).resolve().parents[1]
    require('config' not in sys.modules and 'api.analysis' not in sys.modules)
    sys.path.insert(0,str(root))
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    blocked = ModuleType('api.analysis')
    def no_inference(*_args,**_kwargs):
        raise VerificationFailure('model use forbidden')
    blocked.analyze = no_inference
    sys.modules['api.analysis'] = blocked
    original = dotenv.load_dotenv
    try:
        dotenv.load_dotenv = lambda *_args,**_kwargs:False
        import config
    finally:
        dotenv.load_dotenv = original
    import services.collection_ingest as service
    require(Path(config.__file__).resolve() == root/'config.py')
    require(Path(service.__file__).resolve() == root/'services/collection_ingest.py')
    app = config.create_app({'SQLALCHEMY_DATABASE_URI':uri,'SECRET_KEY':secrets.token_hex(32),
        'TESTING':True,'SQLALCHEMY_ENGINE_OPTIONS':{'pool_size':2,'max_overflow':0,'pool_timeout':12,
            'connect_args':{'connect_timeout':5,'read_timeout':12,'write_timeout':12}}})
    require(Path(sys.modules['models.models'].__file__).resolve() == root/'models/models.py')
    return app,config.db,service


def cleanup(connection,owned):
    """Caller owns one transaction. Validate every scope before the first DELETE."""
    from sqlalchemy import delete,select
    from models.models import (Clinician,Patient,Device,DeviceRawData,CollectionSession,
        CollectionInsoleFrame,CollectionGpsRaw,CollectionRadarRaw,CollectionRadarTarget)
    fixed_schema(connection)
    if 'clinician_id' not in owned:
        empty_tables(connection)
        return
    actor,patient,device = (owned[key] for key in ('clinician_id','patient_id','device_id'))
    owners = ((Clinician,actor,'hospital',owned['marker']),
              (Patient,patient,'subject_id',owned['subject']),(Device,device,'device_code',owned['marker']))
    present = []
    for model,identity,field,value in owners:
        row = connection.execute(select(model.__table__).where(model.id == identity)).mappings().first()
        present.append(row is not None)
        if row is not None:
            require(row[field] == value and (model is Clinician or row['clinician_id'] == actor))
    if not any(present):
        empty_tables(connection)
        return
    require(all(present))
    capture = owned['capture_id']
    session_row = connection.execute(select(CollectionSession.__table__).where(CollectionSession.capture_id == capture)).mappings().first()
    if session_row is not None:
        require(all(session_row[key] == owned[key] for key in ('capture_id','clinician_id','patient_id','device_id')))
    raw = DeviceRawData.__table__
    raw_ids = connection.execute(select(raw.c.id).where(raw.c.clinician_id == actor,raw.c.patient_id == patient,raw.c.device_id == device)).scalars().all()
    by_model = {}
    for model in (CollectionInsoleFrame,CollectionGpsRaw,CollectionRadarRaw):
        by_model[model] = connection.execute(select(model.__table__).where(model.capture_id == capture)).mappings().all()
    expected_raw = {row[key] for row in by_model[CollectionInsoleFrame] for key in ('left_raw_id','right_raw_id')}
    require(expected_raw == set(raw_ids))
    radar_ids = [row['id'] for row in by_model[CollectionRadarRaw]]
    children = CollectionRadarTarget.__table__
    child_ids = connection.execute(select(children.c.id).where(children.c.parent_id.in_(radar_ids))).scalars().all()
    if child_ids:
        connection.execute(delete(children).where(children.c.id.in_(child_ids),children.c.parent_id.in_(radar_ids)))
    for model in (CollectionRadarRaw,CollectionGpsRaw,CollectionInsoleFrame):
        ids = [row['id'] for row in by_model[model]]
        if ids:
            connection.execute(delete(model.__table__).where(model.id.in_(ids),model.capture_id == capture))
    connection.execute(delete(CollectionSession.__table__).where(CollectionSession.capture_id == capture,
        CollectionSession.clinician_id == actor,CollectionSession.patient_id == patient,CollectionSession.device_id == device))
    if raw_ids:
        connection.execute(delete(raw).where(raw.c.id.in_(raw_ids),raw.c.clinician_id == actor,raw.c.patient_id == patient,raw.c.device_id == device))
    for model,identity,field,value in reversed(owners):
        conditions = [model.id == identity,getattr(model,field) == value]
        if model is not Clinician:
            conditions.append(model.clinician_id == actor)
        connection.execute(delete(model.__table__).where(*conditions))
    empty_tables(connection)  # Unknown rows cause rollback; never broaden cleanup.


def expect_rejection(expected,operation):
    from sqlalchemy.exc import DBAPIError
    require(type(expected) is int and expected in (1062,1452,3819))
    try:
        operation()
    except DBAPIError as error:
        if mysql_errno(error) != expected:
            raise
    else:
        raise VerificationFailure('expected rejection absent')


def expect_conflict(service,operation):
    try:
        operation()
    except service.CollectionError as error:
        require(error.status == 409)
    else:
        raise VerificationFailure('expected conflict absent')


def stamp(ms=0):
    return (datetime(2026,10,23)+timedelta(milliseconds=ms)).isoformat(timespec='milliseconds')+'Z'


def business_cases(db,service,owned):
    from sqlalchemy.orm import Session
    from models.models import CollectionRadarRaw,CollectionRadarTarget,DeviceRawData,Patient
    from services.radar_query import _verified_payload
    actor,capture = owned['clinician_id'],owned['capture_id']
    def event(stream,seq,ms,payload):
        return dict(event_id=str(uuid4()),stream=stream,stream_sequence=seq,connection_epoch=7 if stream == 'radar' else 2,
                    mobile_received_at=stamp(ms),payload=payload)
    def submit(events):
        return service.ingest_batch(actor,capture,{'events':events})['results']
    fields = sorted(set(service.LEFT_FIELDS.values())|set(service.RIGHT_FIELDS.values()))
    require(len(fields) == 38)
    target = dict(slot=3,present=True,x_mm=-32767,y_mm=32767,speed_cms=-2,resolution_mm=65535)
    radar = dict(frames=1,bytes=30,age_ms=10**30+1,stale=False,targets=[target,dict(target,slot=1)])
    samples = [event('insole',0,1000,{key:index+1 for index,key in enumerate(fields)}),
        event('gps',0,2000,{'raw_line':'GPS1,1,1,31.23,121.47,12,1.2,8,1.1,100,,5000,0'}),
        event('radar',0,2500,radar),event('radar',1,3000,dict(radar,frames=2,age_ms=0.1234567890123456,targets=[dict(target,slot=2)]))]
    last_collected = None
    for sample in samples:
        accepted,duplicate = submit([sample])[0],submit([sample])[0]
        require(accepted['status'] == 'accepted' and duplicate['status'] == 'duplicate')
        require(accepted['server_received_at'] == duplicate['server_received_at'])
        with Session(db.engine) as session:
            require(session.query(DeviceRawData).count() == 2)
            current = session.get(Patient,owned['patient_id']).last_collected_at
            if last_collected is not None:
                require(current == last_collected)
            last_collected = current
    changed = deepcopy(samples[2])
    changed['payload']['age_ms'] += 1
    expect_conflict(service,lambda:submit([event('radar',2,2800,radar),changed]))
    with Session(db.engine) as session:  # Force driver reload, not cached Python inputs.
        rows = session.query(CollectionRadarRaw).order_by(CollectionRadarRaw.id).all()
        require(len(rows) == 2 and session.query(CollectionRadarTarget).count() == 3)
        require([_verified_payload(row) for row in rows] == [sample['payload'] for sample in samples[2:]])
        require([target.slot for target in rows[0].targets] == [3,1])
    expect_conflict(service,lambda:service.stop_capture(actor,capture,{'mobile_stopped_at':stamp(2999)}))
    service.stop_capture(actor,capture,{'mobile_stopped_at':stamp(3000)})
    expect_conflict(service,lambda:submit([event('radar',2,3001,radar)]))


def constraint_cases(db,owned):
    from sqlalchemy import select
    from models.models import CollectionRadarRaw as Radar,CollectionRadarTarget as Target
    with db.engine.connect() as connection:
        rows = connection.execute(select(Radar.__table__).where(Radar.capture_id == owned['capture_id']).order_by(Radar.id)).mappings().all()
        child = connection.execute(select(Target.id).where(Target.parent_id == rows[0]['id']).order_by(Target.ordinal)).scalars().first()
    checks = ((1062,Radar.__table__.update().where(Radar.id == rows[1]['id'],Radar.capture_id == owned['capture_id']).values(event_id=rows[0]['event_id'])),
              (1452,Target.__table__.update().where(Target.id == child,Target.parent_id == rows[0]['id']).values(parent_id=-1)),
              (3819,Target.__table__.update().where(Target.id == child,Target.parent_id == rows[0]['id']).values(slot=4)))
    for expected,statement in checks:
        with db.engine.connect() as connection:
            try:
                fixed_schema(connection)
                expect_rejection(expected,lambda:connection.execute(statement))
            finally:
                connection.rollback()
        print('OK checkpoint=constraints mysql_errno='+str(expected))


def verify(env_file):
    checkpoint('startup')
    app,db,service = bootstrap(env_file)
    from sqlalchemy.orm import Session
    from models.models import Clinician,Patient,Device
    owned = dict(marker='radar-verify-'+uuid4().hex,subject='rv-'+uuid4().hex[:16],capture_id=str(uuid4()))
    with app.app_context():
        ready = False
        try:
            checkpoint('preflight')
            with db.engine.connect() as connection:
                preflight(connection)
            ready = True
            print('OK checkpoint=preflight')
            checkpoint('setup')
            with Session(db.engine) as session,session.begin():
                actor = Clinician(hospital=owned['marker'],dept='synthetic',name='synthetic',phone='00000000000',passcode_hash='!not-login',role='clinician')
                session.add(actor)
                session.flush()
                patient = Patient(clinician_id=actor.id,subject_id=owned['subject'])
                device = Device(clinician_id=actor.id,device_code=owned['marker'])
                session.add_all([patient,device])
                session.flush()
                owned.update(clinician_id=actor.id,patient_id=patient.id,device_id=device.id)
            checkpoint('service')
            service.create_capture(owned['clinician_id'],dict(capture_id=owned['capture_id'],patient_id=owned['patient_id'],device_code=owned['marker'],mobile_started_at=stamp()))
            business_cases(db,service,owned)
            print('OK checkpoint=service')
            checkpoint('constraints')
            constraint_cases(db,owned)
        except BaseException as error:
            print('FAIL '+failure_detail(error))
            raise
        finally:
            db.session.remove()
            try:
                if ready:
                    checkpoint('cleanup')
                    with db.engine.begin() as connection:
                        cleanup(connection,owned)
                    print('OK checkpoint=cleanup')
            except BaseException as error:
                print('FAIL '+failure_detail(error))
                raise
            finally:
                db.engine.dispose()
    print('MYSQL_RADAR_VERIFY_OK')


class SafeParser(argparse.ArgumentParser):
    def error(self,_message):
        raise VerificationFailure('invalid command arguments')


def arguments(argv=None):
    parser = SafeParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--env-file',required=True,type=Path,help='Explicit credential file; DB_NAME is ignored')
    return parser.parse_args(argv)


def run_safely(operation,output=None):
    try:
        operation()
        return 0
    except SystemExit as error:
        if error.code == 0:
            return 0
        print('FAIL '+failure_detail(error),file=output or sys.stdout)
        return 1
    except BaseException as error:
        print('FAIL '+failure_detail(error),file=output or sys.stdout)
        return 1


def main(argv=None,output=None):
    return run_safely(lambda:verify(arguments(argv).env_file),output)


if __name__ == '__main__':
    sys.exit(main())
