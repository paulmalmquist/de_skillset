import io,json,zipfile,sqlite3
from fastapi.testclient import TestClient
from flightcheck.server import create_app
from flightcheck.store import RunStore
from flightcheck.demo import demo_bundle
import pytest


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv("FLIGHTCHECK_TOKEN",raising=False)
    with TestClient(create_app(tmp_path/"runs.sqlite3"), base_url="http://127.0.0.1") as client:
        yield client


def test_app_demo_and_ledger(client):
    assert client.get("/").status_code==200
    boot=client.get("/api/bootstrap").json()
    assert len(boot["catalog"]["skills"])==19
    result=client.post("/api/demo/masked-loss",json={}).json()
    assert result["status"]=="mismatch"
    assert client.get(f"/api/runs/{result['id']}").json()==result
    assert "record witness" in client.get(f"/api/runs/{result['id']}/handoff").text
    assert len(client.get("/api/runs").json())==1


def test_api_errors_and_origin(client):
    assert client.post("/api/audit/sql",json={"sql":"SELECT 1","layer":"nonsense"}).status_code==422
    assert client.post("/api/demo/clean",json={},headers={"origin":"https://evil.example"}).status_code==403
    assert client.post("/api/audit/manifest",json={"nodes":{"x":None}}).status_code==422
    assert client.get("/api/runs/missing").status_code==404


def test_import_cannot_label_itself_executed(client):
    bundle=demo_bundle("clean").model_dump(mode="json")
    result=client.post("/api/evidence",json=bundle)
    assert result.status_code==200
    assert result.json()["provenance"]=="imported-unattested"


def test_model_zip_contains_expected_files(client):
    spec=client.get('/api/bootstrap').json()['model_example']
    response=client.post('/api/models',json=spec)
    assert response.status_code==200
    r=response.json();download=client.get(f"/api/runs/{r['id']}/scaffold.zip")
    with zipfile.ZipFile(io.BytesIO(download.content)) as z:
        assert "models/marts/fct_operation_event.sql" in z.namelist()


def test_token_required_for_evidence_api(tmp_path,monkeypatch):
    monkeypatch.setenv("FLIGHTCHECK_TOKEN","test-token")
    with TestClient(create_app(tmp_path/'token.sqlite3'), base_url="http://127.0.0.1") as c:
        assert c.get('/api/runs').status_code==401
        assert c.get('/api/runs',headers={'Authorization':'Bearer test-token'}).status_code==200


def test_checksum_detects_changed_payload(tmp_path):
    path=tmp_path/'runs.sqlite3';s=RunStore(path);r=s.save('test','test',{'status':'clear'})
    with sqlite3.connect(path) as conn:conn.execute("UPDATE runs SET payload='{}'")
    with pytest.raises(ValueError):s.get(r['id'])


def test_evaluations_endpoint_executes_cases(client):
    r=client.post('/api/evaluations',json={}).json()
    assert r['passed']==r['total']==13
