"""Amazon S3: guarda as fotos dos itens em um bucket PRIVADO.

Segurança: o navegador nunca fala com o S3 nem recebe URL assinada (que carrega o ID da
credencial e o token de sessão). As fotos passam pela API: GET /api/items/{id}/image.
Na EC2 o boto3 usa as credenciais temporárias da IAM Role — não existe chave no código.

Localmente, S3_ENDPOINT_URL aponta para um emulador de S3 (Moto); o código é o mesmo.
"""
from typing import Optional, Tuple
import uuid

from botocore.exceptions import BotoCoreError, ClientError

from . import config, s3client

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


def upload_image(item_id: int, data: bytes, mime: str, ext: str) -> str:
    key = f"itens/{item_id}/{uuid.uuid4().hex}.{ext}"
    client = s3client.client()
    try:
        client.put_object(Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=mime)
    except (BotoCoreError, ClientError) as exc:
        raise s3client.trip(exc) from exc
    return key


def get_image(key: str) -> Tuple[bytes, str]:
    client = s3client.client()
    try:
        obj = client.get_object(Bucket=config.S3_BUCKET, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise FileNotFoundError(key) from exc
        raise s3client.trip(exc) from exc
    except BotoCoreError as exc:
        raise s3client.trip(exc) from exc


def delete_image(key: Optional[str]) -> bool:
    """Apaga sem derrubar a operação principal; devolve False se o S3 falhou."""
    if not key:
        return True
    try:
        s3client.client().delete_object(Bucket=config.S3_BUCKET, Key=key)
        return True
    except Exception:  # ServiceUnavailable (circuito aberto, sem bucket) ou erro do boto3
        return False


def image_url(item_id: int, key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    version = key.rsplit("/", 1)[-1].split(".")[0][:8]  # muda quando a foto muda (evita cache velho)
    return f"/api/items/{item_id}/image?v={version}"
