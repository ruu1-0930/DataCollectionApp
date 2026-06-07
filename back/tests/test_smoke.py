def test_app_and_db_ready(client):
    # 应用能起、SQLite 内存库能建表
    resp = client.get('/__nonexistent__')
    assert resp.status_code == 404
