"""O que acontece quando cada serviço cai: a API responde 503 dizendo QUAL serviço falhou,
o resto do sistema continua funcionando, e nada de detalhe interno vaza para o usuário.

O S3 é o único armazenamento (fotos E dados): quando ele cai, tudo que depende de dados cai
junto — não existe mais um "banco" separado para continuar funcionando sozinho."""
import boto3
import pytest
from botocore.config import Config

from conftest import PNG_MIN, functions

LEAKS = ["Traceback", "Errno", "botocore", "127.0.0.1", "localhost", "Exception", "socket"]


def assert_safe(body: dict):
    text = str(body)
    for leak in LEAKS:
        assert leak not in text, f"vazou '{leak}' na resposta: {text}"
    assert body["request_id"]


@pytest.fixture
def break_s3(monkeypatch):
    """Devolve uma função: chame-a quando quiser simular o S3 fora do ar a partir daquele
    ponto do teste (assim dá para buscar dados ANTES de derrubar o serviço)."""
    from app import s3client

    def _break():
        dead = boto3.client("s3", endpoint_url="http://127.0.0.1:9", region_name="us-east-1",
                            config=Config(connect_timeout=0.5, read_timeout=0.5, retries={"max_attempts": 1}))
        monkeypatch.setattr(s3client, "_s3", dead)
        monkeypatch.setattr(s3client, "_probe_s3", dead)
        monkeypatch.setattr(s3client, "_circuit_open_until", 0.0)
    return _break


@pytest.fixture
def agent_down(monkeypatch, tmp_path):
    from app import agent_local
    flag = tmp_path / "agente"
    flag.touch()
    monkeypatch.setattr(agent_local, "FAILURE_FLAG", flag)


# ------------------------------------------------------------- S3 (fotos + dados)

def test_s3_fora_do_ar(api, item, break_s3):
    item_id = item("TC-003")["id"]  # busca ANTES de derrubar o S3
    break_s3()

    health = api.get("/api/health").json()
    assert health["status"] == "down" and health["services"]["s3"]["status"] == "down"

    # fotos
    res = api.post(f"/api/items/{item_id}/image", files={"file": ("f.png", PNG_MIN, "image/png")})
    assert res.status_code == 503
    body = res.json()
    assert body["service"] == "s3" and "S3" in body["message"]
    assert_safe(body)

    # dados: também vivem no S3, então caem junto (não há mais um "banco" à parte)
    res = api.get("/api/items")
    assert res.status_code == 503 and res.json()["service"] == "s3"
    assert_safe(res.json())

    res = api.post("/api/items", json={"name": "Sem S3", "unit_price": 1})
    assert res.status_code == 503 and res.json()["service"] == "s3"


def test_circuit_breaker_responde_rapido_depois_da_primeira_falha(api, item, break_s3):
    import time
    item_id = item("NB-001")["id"]
    break_s3()
    assert api.get(f"/api/items/{item_id}/image").status_code == 503   # tenta o S3 e falha
    start = time.perf_counter()
    res = api.get(f"/api/items/{item_id}/image")                         # circuito aberto
    assert res.status_code == 503 and res.json()["service"] == "s3"
    assert time.perf_counter() - start < 0.3


def test_agente_avisa_quando_o_s3_cai(api, chat, break_s3):
    break_s3()
    api.get("/api/items")  # primeira falha abre o circuito (mensagem fica estável a partir daqui)
    r = chat("Quais itens estão com estoque baixo?")
    assert functions(r) == ["itens_estoque_baixo"]
    assert "indisponível" in r["answer"]
    assert_safe({**r, "request_id": "-"})


# ------------------------------------------------------------- agente / Lambda

def test_agente_fora_do_ar(api, agent_down):
    assert api.get("/api/health").json()["services"]["agent"]["status"] == "down"
    res = api.post("/api/chat", json={"message": "oi"})
    assert res.status_code == 503 and res.json()["service"] == "agent"
    assert_safe(res.json())


def test_lambda_sem_rede_nao_vaza_endereco(monkeypatch):
    from app import agent_local
    monkeypatch.setenv("API_BASE_URL", "http://10.0.0.99:9")
    lam = agent_local.load_lambda()
    monkeypatch.setattr(lam.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("conn refused 10.0.0.99")))
    out = lam.lambda_handler({"actionGroup": "g", "function": "resumo_estoque", "parameters": []}, None)
    body = out["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    assert "não respondeu" in body and "10.0.0.99" not in body


# ------------------------------------------------------------- erros genéricos

def test_erro_de_validacao_amigavel(api):
    res = api.post("/api/items", json={"sku": "X"})
    assert res.status_code == 422
    assert res.json()["error"] == "validation_error" and "name" in res.json()["message"]
