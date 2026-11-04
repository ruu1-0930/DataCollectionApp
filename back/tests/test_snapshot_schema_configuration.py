"""The deployed HTTP factory can explicitly select V2 while V1 stays default."""

import pytest

from .test_snapshot_api import scope, auth, ensure_url, snapshot_url, NOW
from services.analysis_snapshot import AnalysisSnapshotService


def test_default_factory_uses_v1(app):
    from api.snapshot import _service
    with app.app_context():
        assert _service().versions.snapshot_schema_version == '1'


def test_configured_factory_publishes_full_and_projection_v2(app, client, scope, monkeypatch):
    app.config.pop('SNAPSHOT_SERVICE_FACTORY')
    app.config['GAIT_SNAPSHOT_SCHEMA_VERSION'] = '2'
    monkeypatch.setattr('api.snapshot.AnalysisSnapshotService',
                        lambda **kwargs: AnalysisSnapshotService(clock=lambda: NOW, **kwargs))
    result = client.post(ensure_url(scope), headers=auth(scope))
    assert result.status_code == 201, result.json
    assert result.json['schema_version'] == '2'
    snapshot_id = result.json['snapshot_id']
    full = client.get(snapshot_url(scope, snapshot_id), headers=auth(scope))
    projection = client.get(snapshot_url(scope, snapshot_id, '/agent-projection'), headers=auth(scope))
    for response, version_key in ((full, 'schema_version'), (projection, 'projection_schema_version')):
        assert response.status_code == 200, response.json
        assert response.json[version_key] == '2'
        assert response.json['derivation_quality']['version'] == 1


@pytest.mark.parametrize('version', ['3', '', 2])
def test_invalid_writer_configuration_fails_at_startup(version):
    from config import create_app
    with pytest.raises(ValueError, match='unsupported_snapshot_schema_configuration'):
        create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                    'SECRET_KEY': 'synthetic', 'GAIT_SNAPSHOT_SCHEMA_VERSION': version})
