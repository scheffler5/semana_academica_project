"""Cliente S3 compartilhado — usado tanto para as fotos (storage.py) quanto para os
"documentos" JSON que fazem o papel de banco de dados (store.py). É o ÚNICO serviço de
armazenamento do sistema: se o bucket cair, fotos E dados ficam indisponíveis juntos.

Circuit breaker: depois de uma falha, por alguns segundos todo pedido ao S3 falha na
hora, sem esperar o timeout de novo. Sem isso, uma falha do S3 deixaria cada requisição
(imagem ou dado) pendurada esperando a rede, travando a tela inteira.
"""
import time

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from . import config
from .errors import ServiceUnavailable, aws_error_message

# Timeouts curtos: se o S3 cair, a tela mostra o erro em segundos (e não trava)
_cfg = Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 1})
_probe_cfg = Config(connect_timeout=1, read_timeout=2, retries={"max_attempts": 1})


def _client(cfg: Config):
    if not config.S3_BUCKET:
        return None
    kwargs = {"region_name": config.AWS_REGION, "config": cfg}
    if config.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = config.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


_s3 = _client(_cfg)
_probe_s3 = _client(_probe_cfg)  # health: falha em ~2 s em vez de esperar as novas tentativas

CIRCUIT_SECONDS = 15
_circuit_open_until = 0.0


def enabled() -> bool:
    return _s3 is not None


def trip(exc: Exception) -> ServiceUnavailable:
    """Chame no except de ClientError/BotoCoreError: abre o circuito e devolve o erro certo."""
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + CIRCUIT_SECONDS
    return ServiceUnavailable("s3", aws_error_message("s3", exc))


def client():
    """Devolve o client do S3, ou levanta ServiceUnavailable (sem bucket, ou circuito aberto)."""
    if _s3 is None:
        raise ServiceUnavailable("s3", "Armazenamento (S3) não configurado (defina S3_BUCKET).")
    if time.monotonic() < _circuit_open_until:
        raise ServiceUnavailable("s3", "Armazenamento (Amazon S3) indisponível no momento.")
    return _s3


def probe() -> dict:
    """Usado pelo /api/health: confirma que o bucket existe e responde."""
    if _probe_s3 is None:
        return {"status": "disabled", "message": "S3_BUCKET não definido"}
    start = time.perf_counter()
    global _circuit_open_until
    try:
        _probe_s3.head_bucket(Bucket=config.S3_BUCKET)
        _circuit_open_until = 0.0  # S3 respondeu: fecha o circuito
        return {"status": "ok", "latency_ms": round((time.perf_counter() - start) * 1000)}
    except (BotoCoreError, ClientError) as exc:
        return {"status": "down", "message": aws_error_message("s3", exc)}
