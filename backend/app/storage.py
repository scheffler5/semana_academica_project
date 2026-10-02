"""Amazon S3: guarda as fotos dos itens em um bucket PRIVADO.

Segurança: o navegador nunca fala com o S3 nem recebe URL assinada (que carrega o ID da
credencial e o token de sessão). As fotos passam pela API: GET /api/items/{id}/image.
Na EC2 o boto3 usa as credenciais temporárias da IAM Role — não existe chave no código.

Localmente, S3_ENDPOINT_URL aponta para um emulador de S3 (Moto); o código é o mesmo.
"""
import time
import uuid
from typing import Optional, Tuple

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

# Tipo detectado pelos primeiros bytes do arquivo (não confiamos no Content-Type do navegador)
SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
]


def detect_image(data: bytes) -> Optional[Tuple[str, str]]:
    for magic, mime, ext in SIGNATURES:
        if data.startswith(magic):
            return mime, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def enabled() -> bool:
    return _s3 is not None


# ---------------------------------------------------------------- circuit breaker
# Depois de uma falha, por 15 s respondemos "S3 indisponível" NA HORA, sem chamar o S3.
# Sem isso, cada foto da tela ficaria presa esperando timeout e ocuparia as conexões
# do navegador (e threads da API). O health check (probe) fecha o circuito quando o S3 volta.
CIRCUIT_SECONDS = 15
_circuit_open_until = 0.0


def _trip(exc: Exception) -> ServiceUnavailable:
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + CIRCUIT_SECONDS
    return ServiceUnavailable("s3", aws_error_message("s3", exc))


def _require():
    if _s3 is None:
        raise ServiceUnavailable("s3", "Armazenamento de fotos não configurado (defina S3_BUCKET).")
    if time.monotonic() < _circuit_open_until:
        raise ServiceUnavailable("s3", "Armazenamento de fotos (Amazon S3) indisponível no momento.")
    return _s3


def upload_image(item_id: int, data: bytes, mime: str, ext: str) -> str:
    key = f"itens/{item_id}/{uuid.uuid4().hex}.{ext}"
    client = _require()
    try:
        client.put_object(Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=mime)
    except (BotoCoreError, ClientError) as exc:
        raise _trip(exc) from exc
    return key


def get_image(key: str) -> Tuple[bytes, str]:
    client = _require()
    try:
        obj = client.get_object(Bucket=config.S3_BUCKET, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise FileNotFoundError(key) from exc
        raise _trip(exc) from exc
    except BotoCoreError as exc:
        raise _trip(exc) from exc


def delete_image(key: Optional[str]) -> bool:
    """Apaga sem derrubar a operação principal; devolve False se o S3 falhou."""
    if not (key and _s3):
        return True
    try:
        _s3.delete_object(Bucket=config.S3_BUCKET, Key=key)
        return True
    except (BotoCoreError, ClientError):
        return False


def image_url(item_id: int, key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    version = key.rsplit("/", 1)[-1].split(".")[0][:8]  # muda quando a foto muda (evita cache velho)
    return f"/api/items/{item_id}/image?v={version}"


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
