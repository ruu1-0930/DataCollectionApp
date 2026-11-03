"""GPS numeric JSON boundary through MySQL's actual result processors, offline."""
import json

import pytest
from flask import Flask
from sqlalchemy.dialects.mysql.pymysql import dialect

from models.models import CollectionGpsRaw


@pytest.mark.parametrize('name,value', [
    ('lat', 31.2304567), ('lon', 121.4737654), ('alt', 12.5),
    ('speed', 1.2), ('hdop', 99.99),
])
def test_mysql_gps_results_remain_json_numbers_and_preserve_seven_decimals(name, value):
    mysql = dialect()
    column_type = CollectionGpsRaw.__table__.c[name].type.dialect_impl(mysql)
    processor = column_type.result_processor(mysql, None)
    loaded = processor(value) if processor else value
    wire = json.loads(Flask(__name__).json.dumps({name: loaded}))
    assert type(wire[name]) is float
    assert wire[name] == value
    assert column_type.compile(dialect=mysql) == 'DOUBLE'
    missing = processor(None) if processor else None
    assert json.loads(Flask(__name__).json.dumps({name: missing}))[name] is None
