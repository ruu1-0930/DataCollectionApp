"""Operator-only GPS acceptance against one empty, disposable MySQL test schema.

No schema changes. No HTTP server. No production data. See the paired guide.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import os
from pathlib import Path
import secrets
import sys
from threading import Event, Thread, current_thread, local
from time import monotonic
from types import ModuleType
from uuid import uuid4


DATABASE = 'lanya_gps_verify_20261020'
TABLES = ('clinicians', 'patients', 'devices', 'device_raw_data',
          'collection_sessions', 'collection_insole_frames', 'collection_gps_raw')
TIMEOUT = 12
START = datetime(2026, 10, 19, 23, 59, 58, 123000)
CHECKPOINTS = frozenset(('startup', 'preflight', 'setup', 'create',
    'insole.accept_duplicate', 'insole.conflict', 'insole.atomic',
    'gps.accept_duplicate', 'gps.conflict', 'gps.atomic', 'service.counts',
    'gps.time_payload', 'gps.double_storage', 'insole.raw_clock', 'insole.raw_mapping', 'stop.boundary',
    'constraints', 'retry.wait', 'stop.wait', 'retry.writer', 'retry.contender',
    'stop.writer', 'stop.contender'))
_diagnostic = local()


class VerificationFailure(RuntimeError):
    pass


def require(condition):
    if not condition:
        raise VerificationFailure('acceptance condition failed')


def checkpoint(name):
    require(name in CHECKPOINTS)
    _diagnostic.checkpoint = name


def mysql_errno(error):
    # No import here: bootstrap may fail before SQLAlchemy is available.
    errors = sys.modules.get('sqlalchemy.exc')
    if errors is None or not isinstance(error, errors.DBAPIError):
        return None
    args = getattr(error.orig, 'args', ())
    code = args[0] if args else None
    return code if type(code) is int and 0 < code <= 65535 else None


def failure_detail(error):
    """Static enums and this helper's line number only; never exception content."""
    if isinstance(error, VerificationFailure):
        category = 'condition'
    elif isinstance(error, TimeoutError):
        category = 'timeout'
    elif type(error).__module__ == 'sqlalchemy.exc':
        category = 'database'
    elif isinstance(error, (KeyError, TypeError)):
        category = 'shape'
    elif isinstance(error, ValueError):
        category = 'request'
    else:
        category = 'unexpected'
    line, trace = 0, error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        if Path(code.co_filename).resolve() == Path(__file__).resolve() and code.co_name != 'require':
            line = trace.tb_lineno
        trace = trace.tb_next
    name = getattr(_diagnostic, 'checkpoint', 'startup')
    code = mysql_errno(error)
    errno = ', mysql_errno=' + str(code) if code is not None else ''
    return '[checkpoint=' + name + ', category=' + category + ', helper_line=' + str(line) + errno + ']'


def fixed_schema(connection):
    require(connection.exec_driver_sql('SELECT DATABASE()').scalar_one() == DATABASE)


def preflight(connection):
    fixed_schema(connection)
    version = connection.exec_driver_sql('SELECT VERSION()').scalar_one()
    require(version.startswith('8.') and 'mariadb' not in version.lower())
    tables = dict(connection.exec_driver_sql(
        'SELECT table_name, engine FROM information_schema.tables '
        'WHERE table_schema = DATABASE()').all())
    require(set(tables) == set(TABLES))
    require(all(tables[name] == 'InnoDB' for name in TABLES))
    empty_tables(connection)


def empty_tables(connection):
    for name in TABLES:  # identifiers are fixed constants, never operator input
        require(connection.exec_driver_sql('SELECT COUNT(*) FROM `' + name + '`').scalar_one() == 0)


def wait_for(gate, timeout=TIMEOUT):
    require(gate.wait(timeout))


def check_owned_capture(row, owned):
    require(row['capture_id'] in owned['captures'])
    for key in ('clinician_id', 'patient_id', 'device_id'):
        require(row[key] == owned[key])


def cleanup(connection, owned):
    """Validate all ownership before the first exact-key delete, in one transaction."""
    fixed_schema(connection)
    require(not any(t.is_alive() for t in owned.get('workers', [])))
    if 'clinician_id' not in owned:
        empty_tables(connection)
        return
    from sqlalchemy import delete, select
    from models.models import (Clinician, Patient, Device, DeviceRawData,
                               CollectionSession, CollectionInsoleFrame, CollectionGpsRaw)
    tables = {m.__tablename__: m.__table__ for m in
              (Clinician, Patient, Device, DeviceRawData, CollectionSession,
               CollectionInsoleFrame, CollectionGpsRaw)}
    actor, patient, device = owned['clinician_id'], owned['patient_id'], owned['device_id']
    owners = [('clinicians', actor, 'hospital', owned['marker']),
              ('patients', patient, 'subject_id', owned['subject']),
              ('devices', device, 'device_code', owned['marker'])]
    for name, identity, field, expected in owners:
        table = tables[name]
        row = connection.execute(select(table).where(table.c.id == identity)).mappings().first()
        if row is not None:
            require(row[field] == expected)
            if name != 'clinicians':
                require(row['clinician_id'] == actor)
    captures = tables['collection_sessions']
    rows = connection.execute(select(captures).where(
        captures.c.capture_id.in_(owned['captures']))).mappings().all()
    for row in rows:
        check_owned_capture(row, owned)
    raw = tables['device_raw_data']
    raw_rows = connection.execute(select(raw.c.id).where(
        raw.c.clinician_id == actor, raw.c.patient_id == patient,
        raw.c.device_id == device)).scalars().all()
    sidecar = tables['collection_insole_frames']
    side_rows = connection.execute(select(sidecar).where(
        sidecar.c.capture_id.in_(owned['captures']))).mappings().all()
    require(all(r['left_raw_id'] in raw_rows and r['right_raw_id'] in raw_rows for r in side_rows))
    # GPS and sidecars are selected and deleted by this run's exact capture UUIDs.
    for name in ('collection_gps_raw', 'collection_insole_frames'):
        table = tables[name]
        ids = connection.execute(select(table.c.id).where(
            table.c.capture_id.in_(owned['captures']))).scalars().all()
        if ids:
            connection.execute(delete(table).where(table.c.id.in_(ids),
                table.c.capture_id.in_(owned['captures'])))
    for row in rows:
        connection.execute(delete(captures).where(captures.c.capture_id == row['capture_id'],
            captures.c.clinician_id == actor, captures.c.patient_id == patient,
            captures.c.device_id == device))
    if raw_rows:
        connection.execute(delete(raw).where(raw.c.id.in_(raw_rows), raw.c.clinician_id == actor,
            raw.c.patient_id == patient, raw.c.device_id == device))
    for name, identity, field, expected in reversed(owners):
        table = tables[name]
        connection.execute(delete(table).where(table.c.id == identity, table.c[field] == expected))
    empty_tables(connection)  # unknown concurrent rows are failure; never delete them


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--env-file', required=True, type=Path,
                        help='Existing operator .env; only DB_HOST/PORT/USER/PASS are read')
    return parser.parse_args(argv)


def bootstrap(env_file):
    """Import this checkout's factory, with implicit dotenv and SVM disabled."""
    import dotenv
    from sqlalchemy.engine import URL
    require(env_file.is_file())
    values = dotenv.dotenv_values(env_file, interpolate=False)
    require(all(values.get(k) for k in ('DB_HOST', 'DB_USER', 'DB_PASS')))
    port = int(values.get('DB_PORT') or '3306')
    require(1 <= port <= 65535)
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    dotenv.load_dotenv = lambda *args, **kwargs: False  # also older python-dotenv
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    require('config' not in sys.modules and 'api.analysis' not in sys.modules)
    # The legacy factory eagerly loads/trains SVM while registering api.device.
    # Only that unrelated import is fenced; any attempted inference fails closed.
    blocked = ModuleType('api.analysis')
    def no_inference(*args, **kwargs):
        raise VerificationFailure('legacy inference forbidden')
    blocked.analyze = no_inference
    sys.modules['api.analysis'] = blocked
    import config
    import services.collection_ingest as service
    require(Path(config.__file__).resolve() == root / 'config.py')
    require(Path(service.__file__).resolve() == root / 'services/collection_ingest.py')
    uri = URL.create('mysql+pymysql', username=values['DB_USER'], password=values['DB_PASS'],
                     host=values['DB_HOST'], port=port, database=DATABASE)
    app = config.create_app({'SQLALCHEMY_DATABASE_URI': uri,
        'SECRET_KEY': secrets.token_hex(32), 'TESTING': True,
        'SQLALCHEMY_ENGINE_OPTIONS': {'pool_size': 3, 'max_overflow': 0,
            'pool_timeout': TIMEOUT, 'connect_args': {'connect_timeout': 5,
                'read_timeout': TIMEOUT, 'write_timeout': TIMEOUT}}})
    for name, relative in (('auth', 'auth.py'), ('models.models', 'models/models.py')):
        require(Path(sys.modules[name].__file__).resolve() == root / relative)
    return app, config.db, service


def stamp(milliseconds=0):
    return (START + timedelta(milliseconds=milliseconds)).isoformat(timespec='milliseconds') + 'Z'


def sample(service, stream='insole', seq=0, ms=1234):
    if stream == 'gps':
        payload = {'raw_line': 'GPS1,12,1,31.230123456789,121.470987654321,12.3456789,'
                   '1.23456789,8,1.123456789,100,2026-10-19T00:00:01Z,5000,0'}
    else:
        fields = sorted(set(service.LEFT_FIELDS.values()) | set(service.RIGHT_FIELDS.values()))
        require(len(fields) == 38)
        payload = {name: (i + 1) / 4 for i, name in enumerate(fields)}
    return dict(event_id=str(uuid4()), stream=stream, stream_sequence=seq,
                connection_epoch=0, mobile_received_at=stamp(ms), payload=payload)


def expect_conflict(service, operation):
    try:
        operation()
    except service.CollectionError as error:
        require(error.status == 409)
    else:
        raise VerificationFailure('expected service conflict')


def check_double_values(processed, driver_values, dialect):
    from models.models import CollectionGpsRaw
    for name, expected in [('lat', 31.230123456789), ('lon', 121.470987654321),
                           ('alt', 12.3456789), ('speed', 1.23456789), ('hdop', 1.123456789)]:
        # MySQL DOUBLE(asdecimal=True) rounds the ORM view to ten decimal places.
        # Storage precision is proved independently by the untyped driver result,
        # with exact comparison, not a relaxed tolerance on the rounded view.
        require(driver_values[name] == expected)
        implementation = CollectionGpsRaw.__table__.c[name].type.dialect_impl(dialect)
        processor = implementation.result_processor(dialect, None)
        require(processed[name] == (processor(expected) if processor else expected))


def check_raw_clock(frame, rows, connection):
    # Existing raw columns intentionally have different declared precision.
    metadata = connection.exec_driver_sql(
        'SELECT COLUMN_NAME, DATA_TYPE, DATETIME_PRECISION FROM information_schema.columns '
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'device_raw_data' "
        "AND COLUMN_NAME IN ('collected_at', 'uploaded_at')").all()
    require(len(metadata) == 2 and {name: (kind, fsp) for name, kind, fsp in metadata} ==
            {'collected_at': ('datetime', 3), 'uploaded_at': ('datetime', 0)})
    mode = connection.exec_driver_sql('SELECT @@SESSION.sql_mode').scalar_one()
    require(isinstance(mode, str))
    server = frame['server_received_at']
    require(type(server) is datetime and server.tzinfo is None and server.microsecond % 1000 == 0)
    collected = server + timedelta(hours=8)
    uploaded = collected.replace(microsecond=0)
    # MySQL INSERT rounds lower fsp by default; TIME_TRUNCATE_FRACTIONAL
    # truncates instead. Integer comparison handles .500 and day carry exactly.
    if 'TIME_TRUNCATE_FRACTIONAL' not in mode.split(',') and collected.microsecond >= 500000:
        uploaded += timedelta(seconds=1)
    require(len(rows) == 2)
    require(collected != frame['mobile_received_at'] and uploaded != frame['mobile_received_at'])
    require(all(row['collected_at'] == collected and row['uploaded_at'] == uploaded for row in rows))


def business_cases(db, service, owned):
    from sqlalchemy import select, func
    from models.models import CollectionInsoleFrame as Frame, CollectionGpsRaw as Gps, DeviceRawData as Raw
    actor, capture = owned['clinician_id'], owned['captures'][0]
    def submit(event_list):
        return service.ingest_batch(actor, capture, {'events': event_list})
    def counts():
        with db.engine.connect() as conn:
            return tuple(conn.execute(select(func.count()).select_from(m)).scalar_one()
                         for m in (Raw, Frame, Gps))
    for stream in ('insole', 'gps'):
        checkpoint(stream + '.accept_duplicate')
        event = sample(service, stream)
        first, second = submit([event]), submit([event])
        require(first['results'][0]['status'] == 'accepted')
        require(second['results'][0]['status'] == 'duplicate')
        require(first['results'][0]['server_received_at'] == second['results'][0]['server_received_at'])
        baseline = counts()
        changed = deepcopy(event)
        if stream == 'gps':
            changed['payload']['raw_line'] = changed['payload']['raw_line'].replace(',5000,0', ',5001,0')
        else:
            changed['payload']['left_speed'] = 99
        checkpoint(stream + '.conflict')
        expect_conflict(service, lambda: submit([changed]))
        require(counts() == baseline)
        checkpoint(stream + '.atomic')
        expect_conflict(service, lambda: submit([sample(service, stream, seq=1), changed]))
        require(counts() == baseline)
    checkpoint('service.counts')
    require(counts() == (2, 1, 1))
    with db.engine.connect() as conn:
        gps = conn.execute(select(Gps.__table__)).mappings().one()
        frame = conn.execute(select(Frame.__table__)).mappings().one()
        raw = conn.execute(select(Raw.__table__).order_by(Raw.id)).mappings().all()
        checkpoint('gps.time_payload')
        require(gps['mobile_received_at'] == START + timedelta(milliseconds=1234))
        require(frame['mobile_received_at'] == gps['mobile_received_at'])
        require(gps['utc'] == '2026-10-19T00:00:01Z')
        require(gps['raw_line'] == sample(service, 'gps')['payload']['raw_line'])
        require(tuple(gps[k] for k in ('seq', 'fix', 'sats', 'age', 'chars', 'errors')) ==
                (12, True, 8, 100, 5000, 0))
        require(service.time_string(gps['server_received_at']) == first['results'][0]['server_received_at'])
        checkpoint('gps.double_storage')
        driver_values = conn.exec_driver_sql(
            'SELECT lat, lon, alt, speed, hdop FROM collection_gps_raw WHERE id = %s',
            (gps['id'],)).mappings().one()
        check_double_values(gps, driver_values, conn.dialect)
        checkpoint('insole.raw_clock')
        check_raw_clock(frame, raw, conn)
        checkpoint('insole.raw_mapping')
        require({r['foot'] for r in raw} == {'L', 'R'})
        require({frame['left_raw_id'], frame['right_raw_id']} == {r['id'] for r in raw})
        # All 38 values survive the unchanged per-foot mapping (legacy FLOAT tolerance).
        event = sample(service)
        for row, fields in zip(raw, (service.LEFT_FIELDS, service.RIGHT_FIELDS)):
            for dest, source in fields.items():
                require(abs(row[dest] - event['payload'][source]) < 1e-5)
    checkpoint('stop.boundary')
    service.stop_capture(actor, capture, {'mobile_stopped_at': stamp(2000)})
    service.stop_capture(actor, capture, {'mobile_stopped_at': stamp(2000)})
    require(submit([sample(service, seq=2, ms=2000)])['results'][0]['status'] == 'accepted')
    require(submit([sample(service, 'gps', seq=2, ms=2000)])['results'][0]['status'] == 'accepted')
    with db.engine.connect() as conn:
        boundary = conn.execute(select(Gps.mobile_received_at).where(
            Gps.capture_id == capture, Gps.stream_sequence == 2)).scalar_one()
        require(boundary == datetime(2026, 10, 20, 0, 0, 0, 123000))
    expect_conflict(service, lambda: submit([sample(service, seq=3, ms=2001)]))
    print('OK service accepted/duplicate/conflict/atomic/time/38+13/stop')


def expect_db_rejection(expected_code, operation):
    from sqlalchemy.exc import DBAPIError
    require(type(expected_code) is int and expected_code in (1062, 1452, 3819))
    try:
        operation()
    except DBAPIError as error:
        if mysql_errno(error) != expected_code:
            raise
    else:
        raise VerificationFailure('constraint was not enforced')


def constraint_cases(db, owned):
    from sqlalchemy import select
    from models.models import CollectionGpsRaw as Gps, CollectionInsoleFrame as Frame, CollectionSession as Capture
    checks = 0
    for model in (Gps, Frame):
        table = model.__table__
        with db.engine.connect() as conn:
            rows = conn.execute(select(table).where(table.c.capture_id == owned['captures'][0])
                                .order_by(table.c.id)).mappings().all()
        require(len(rows) == 2)
        first, second = rows
        changes = [({'event_id': first['event_id']}, 1062),
                   ({'stream_sequence': first['stream_sequence']}, 1062),
                   ({'connection_epoch': -1}, 3819),
                   ({'capture_id': str(uuid4())}, 1452)]
        if model is Frame:
            changes += [({'left_raw_id': first['left_raw_id']}, 1062),
                        ({'right_raw_id': first['right_raw_id']}, 1062),
                        ({'left_raw_id': -1}, 1452), ({'right_raw_id': -1}, 1452)]
        for change, expected_code in changes:
            with db.engine.connect() as conn:
                fixed_schema(conn)
                transaction = conn.get_transaction()
                try:
                    expect_db_rejection(expected_code, lambda: conn.execute(table.update().where(
                        table.c.id == second['id'], table.c.capture_id == owned['captures'][0]).values(**change)))
                    checks += 1
                finally:
                    transaction.rollback()
    # The three capture ownership FKs: each UPDATE must fail on this owned row.
    for column in ('clinician_id', 'patient_id', 'device_id'):
        with db.engine.connect() as conn:
            fixed_schema(conn)
            try:
                expect_db_rejection(1452, lambda: conn.execute(Capture.__table__.update().where(
                    Capture.capture_id == owned['captures'][0]).values(**{column: -1})))
                checks += 1
            finally:
                conn.rollback()
    print('OK constraint rejection cases=' + str(checks))


def lock_case(app, db, service, owned, capture, stopping=False):
    """Observe real service connections and server LOCK WAIT before writer commit."""
    from sqlalchemy import event as sql_event
    held, release, attempted = Event(), Event(), Event()
    outcomes, connection_ids, isolation = {}, {}, {}
    event_value = sample(service, ms=5000)
    prefix = 'stop' if stopping else 'retry'
    def before_execute(conn, cursor, statement, parameters, context, executemany):
        name = current_thread().name
        if name not in ('gps-writer', 'gps-contender'):
            return
        if name not in connection_ids:
            # Same DBAPI connection as the actual service Session, no separate default connection.
            cursor.execute('SELECT CONNECTION_ID(), @@transaction_isolation')
            identity, level = cursor.fetchone()
            connection_ids[name], isolation[name] = identity, level
            require(level.replace('-', ' ').upper() == 'READ COMMITTED')
        if name == 'gps-contender' and 'FOR UPDATE' in statement.upper() and 'collection_sessions' in statement:
            attempted.set()  # account read already completed inside _owned_capture
    def before_commit(conn):
        if current_thread().name == 'gps-writer':
            held.set()  # flush completed; real capture FOR UPDATE is still held
            wait_for(release)
    def worker(writer):
        checkpoint(prefix + ('.writer' if writer else '.contender'))
        try:
            with app.app_context():
                if not writer and stopping:
                    expect_conflict(service, lambda: service.stop_capture(owned['clinician_id'], capture,
                        {'mobile_stopped_at': stamp(4000)}))
                    outcomes['contender'] = 'conflict409'
                else:
                    response = service.ingest_batch(owned['clinician_id'], capture, {'events': [event_value]})
                    outcomes['writer' if writer else 'contender'] = response['results'][0]['status']
        except BaseException as error:
            print('FAIL worker ' + failure_detail(error) + ' (details suppressed)')
            outcomes['writer' if writer else 'contender'] = 'failed'
    sql_event.listen(db.engine, 'before_cursor_execute', before_execute)
    sql_event.listen(db.engine, 'commit', before_commit)
    writer = Thread(target=worker, args=(True,), name='gps-writer', daemon=True)
    contender = Thread(target=worker, args=(False,), name='gps-contender', daemon=True)
    owned['workers'] = [writer, contender]
    started = monotonic()
    try:
        writer.start()
        wait_for(held)
        contender.start()
        wait_for(attempted)
        deadline = monotonic() + TIMEOUT
        with db.engine.connect() as observer:
            fixed_schema(observer)
            # PROCESS visibility may be required; failure is evidence unavailable,
            # never permission to grant rights or substitute a simulated lock.
            while True:
                states = dict(observer.exec_driver_sql(
                    'SELECT trx_mysql_thread_id, trx_state FROM information_schema.innodb_trx '
                    'WHERE trx_mysql_thread_id IN (%s, %s)',
                    (connection_ids['gps-writer'], connection_ids['gps-contender'])).all())
                if states.get(connection_ids['gps-contender']) == 'LOCK WAIT':
                    require(connection_ids['gps-writer'] in states)
                    break
                require(monotonic() < deadline and 'contender' not in outcomes)
                # Bounded polling delay, not scheduling evidence or a sleep-based race.
                release.wait(0.02)
        require(isolation == {'gps-writer': 'READ-COMMITTED', 'gps-contender': 'READ-COMMITTED'})
        release.set()
    finally:
        release.set()
        writer.join(TIMEOUT + 2)
        if contender.ident is not None:
            contender.join(TIMEOUT + 2)
        # Do not remove a hook while a worker could still be executing it.
        if not writer.is_alive() and not contender.is_alive():
            sql_event.remove(db.engine, 'commit', before_commit)
            sql_event.remove(db.engine, 'before_cursor_execute', before_execute)
        require(not writer.is_alive() and not contender.is_alive())
    require(outcomes == {'writer': 'accepted', 'contender': 'conflict409' if stopping else 'duplicate'})
    print('OK InnoDB ' + prefix + ' LOCK WAIT; service READ COMMITTED; seconds=' +
          format(monotonic() - started, '.2f'))


def verify(env_file):
    app, db, service = bootstrap(env_file)
    from sqlalchemy.orm import Session
    from models.models import Clinician, Patient, Device
    marker = 'gps-verify-' + uuid4().hex
    owned = {'marker': marker, 'subject': 'gpsv-' + uuid4().hex[:15],
             'captures': [str(uuid4()) for _ in range(3)]}
    with app.app_context():
        stage = 'preflight'
        checkpoint('preflight')
        try:
            with db.engine.connect() as connection:
                preflight(connection)
            print('OK fixed empty MySQL8/InnoDB schema')
            stage = 'synthetic setup/create'
            checkpoint('setup')
            with Session(db.engine, expire_on_commit=False) as session:
                clinician = Clinician(hospital=marker, dept='synthetic', name='synthetic',
                    phone='00000000000', passcode_hash='!synthetic-not-login', role='clinician')
                session.add(clinician)
                session.flush()
                patient = Patient(clinician_id=clinician.id, subject_id=owned['subject'])
                device = Device(clinician_id=clinician.id, device_code=marker, device_name='synthetic')
                session.add_all([patient, device])
                session.flush()
                owned.update(clinician_id=clinician.id, patient_id=patient.id, device_id=device.id)
                session.commit()  # cross-session service calls must see setup rows
            for capture in owned['captures']:
                checkpoint('create')
                payload = dict(capture_id=capture, patient_id=owned['patient_id'],
                    device_code=marker, mobile_started_at=stamp())
                require(service.create_capture(owned['clinician_id'], payload) == {'capture_id': capture})
                require(service.create_capture(owned['clinician_id'], payload) == {'capture_id': capture})
            stage = 'service cases'
            business_cases(db, service, owned)
            stage = 'constraint rejection'
            checkpoint('constraints')
            constraint_cases(db, owned)
            stage = 'InnoDB retry wait'
            checkpoint('retry.wait')
            lock_case(app, db, service, owned, owned['captures'][1])
            stage = 'InnoDB stop wait'
            checkpoint('stop.wait')
            lock_case(app, db, service, owned, owned['captures'][2], stopping=True)
        except BaseException as error:
            print('FAIL ' + stage + ' ' + failure_detail(error) + ' (details suppressed)')
            raise
        finally:
            db.session.remove()
            try:
                with db.engine.begin() as connection:
                    cleanup(connection, owned)
                print('OK cleanup own synthetic rows; all seven tables empty')
            except BaseException as error:
                print('FAIL cleanup ' + failure_detail(error) + ' (preserve test schema for inspection)')
                raise
            finally:
                db.engine.dispose()
    print('MYSQL_GPS_VERIFY_OK')


def run_safely(operation, output=None):
    try:
        operation()
        return 0
    except BaseException as error:
        print('FAIL verification ' + failure_detail(error) + ' (details suppressed)', file=output or sys.stdout)
        return 1


if __name__ == '__main__':
    options = arguments()
    sys.exit(run_safely(lambda: verify(options.env_file)))
