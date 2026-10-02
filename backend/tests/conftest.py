"""Sobe a API de verdade (uvicorn) numa porta livre, com um bucket S3 de TESTE (emulador Moto).

O S3 é o único armazenamento do sistema (fotos E dados). A Lambda do agente chama essa API
por HTTP, exatamente como faz na AWS.
"""
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"
S3_PORT = _free_port()
BUCKET = "estoque-teste"

# Emulador de S3 (Moto) em processo, com credenciais aleatórias e falsas
from moto.server import ThreadedMotoServer  # noqa: E402

_moto = ThreadedMotoServer(ip_address="127.0.0.1", port=S3_PORT, verbose=False)
_moto.start()

# Precisa ser definido ANTES de importar o app (config lê o ambiente na importação)
os.environ.update({
    "AGENT_MODE": "simulado",
    "LOCAL_API_URL": BASE_URL,
    "API_BASE_URL": BASE_URL,   # variável que a Lambda lê
    "S3_BUCKET": BUCKET,
    "S3_ENDPOINT_URL": f"http://127.0.0.1:{S3_PORT}",
    "AWS_ACCESS_KEY_ID": "teste" + secrets.token_hex(6),
    "AWS_SECRET_ACCESS_KEY": secrets.token_urlsafe(24),
    "AWS_DEFAULT_REGION": "us-east-1",
    "SEED_DATA": "true",
})


@pytest.fixture(scope="session")
def server():
    import uvicorn
    from app import s3client
    from app.main import app

    s3client._s3.create_bucket(Bucket=BUCKET)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("API não subiu")
    yield BASE_URL
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def api(server):
    import httpx

    with httpx.Client(base_url=server, timeout=30) as client:
        yield client


@pytest.fixture
def chat(api):
    """chat("mensagem") -> resposta do POST /api/chat (mantém a sessão entre chamadas do mesmo teste)."""
    state = {"session_id": None}

    def send(message: str) -> dict:
        res = api.post("/api/chat", json={"message": message, "session_id": state["session_id"]})
        assert res.status_code == 200, res.text
        body = res.json()
        state["session_id"] = body["session_id"]
        return body

    return send


@pytest.fixture
def item(api):
    """item("SKU") -> item atual lido pela API."""
    def get(sku: str) -> dict:
        res = api.get(f"/api/items/by-sku/{sku}")
        assert res.status_code == 200, res.text
        return res.json()

    return get


PNG_MIN = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def functions(result: dict) -> list:
    return [t["function"] for t in result["tools_used"]]
