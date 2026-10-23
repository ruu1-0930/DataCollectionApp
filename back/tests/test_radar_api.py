import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from tests.test_collection_ingest import capture, batch
from tests.test_radar_ingest import radar_event
from tests.test_radar_query import window, radar_get, radar_path


def test_radar_response_strict_schema(client,capture):
    window(client,capture)
    sample = radar_event()
    assert batch(client,capture,[sample]).status_code == 200
    data = radar_get(client,capture)
    for filename,value in [('radar_session_v1.schema.json',data),('collection_radar_v1.schema.json',sample['payload'])]:
        schema = json.loads((Path(__file__).parents[1]/'contracts'/filename).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)


def test_radar_read_permissions_and_errors(client,capture,admin_scope):
    window(client,capture)
    path = radar_path(capture)
    assert client.get(path).status_code == 401
    assert client.get(path,headers=admin_scope['doctor_b']['headers']).status_code == 403
    assert client.get(path,headers=admin_scope['admin']['headers']).status_code == 200
    assert client.get(path.replace('/radar','x/radar'),headers=capture['headers']).status_code == 422
    assert client.get(path.replace('/patients/1/','/patients/99999/'),headers=capture['headers']).status_code == 404
    assert client.get(path.replace('202610','202510'),headers=capture['headers']).status_code == 404


@pytest.mark.parametrize('query',[{'page':0},{'page_size':501},{'extra':1},{'page':'1.0'},[('page','1'),('page','2')]])
def test_radar_pagination_rejected(client,capture,query):
    window(client,capture)
    assert client.get(radar_path(capture),headers=capture['headers'],query_string=query).status_code == 400
