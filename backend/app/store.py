"""O "banco de dados" do estoque: dois documentos JSON dentro do mesmo bucket S3 das fotos.

    s3://bucket/data/items.json       lista de produtos
    s3://bucket/data/movements.json   lista de movimentações

Cada escrita lê o documento inteiro, modifica a lista **em memória** e grava ela de volta
inteira (PutObject). Para o tamanho de um laboratório (dezenas/centenas de produtos) isso é
rápido e simples de entender — é literalmente "abrir o JSON, mudar, salvar de novo".

Isso NÃO é como um banco de verdade trata muitos acessos ao mesmo tempo: não há transação
nem bloqueio entre processos, só um `Lock` que serializa as escritas dentro deste mesmo
processo Python. Está aqui para ensinar o S3 como armazenamento central da aplicação, não
como referência de arquitetura para produção com muitos usuários simultâneos.

Importante para quem for mexer no código: `transaction()` devolve as DUAS listas e grava as
duas de volta quando o bloco `with` termina sem erro. Para a gravação funcionar, o código
dentro do `with` precisa ALTERAR as listas (append, remove, atribuir um campo do dict) e
nunca trocar a variável por uma lista nova (isso quebraria a referência que será salva).
"""
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from . import config, s3client

ITEMS_KEY = "data/items.json"
MOVEMENTS_KEY = "data/movements.json"

# Serializa leitura-modificação-escrita DENTRO deste processo (uma instância EC2 = um processo).
# Não protege contra duas instâncias da API escrevendo ao mesmo tempo — não é o caso aqui.
_lock = threading.Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_iso() -> str:
    return utcnow().isoformat()


def _get_json(key: str) -> list:
    client = s3client.client()
    try:
        obj = client.get_object(Bucket=config.S3_BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return []  # documento ainda não existe: é como uma tabela vazia
        raise s3client.trip(exc) from exc
    except BotoCoreError as exc:
        raise s3client.trip(exc) from exc


def _put_json(key: str, data: list) -> None:
    client = s3client.client()
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    try:
        client.put_object(Bucket=config.S3_BUCKET, Key=key, Body=body, ContentType="application/json")
    except (BotoCoreError, ClientError) as exc:
        raise s3client.trip(exc) from exc


def load_items() -> list:
    return _get_json(ITEMS_KEY)


def load_movements() -> list:
    return _get_json(MOVEMENTS_KEY)


def save_items(items: list) -> None:
    _put_json(ITEMS_KEY, items)


def save_movements(movements: list) -> None:
    _put_json(MOVEMENTS_KEY, movements)


def next_id(rows: list) -> int:
    return max((r["id"] for r in rows), default=0) + 1


@contextmanager
def transaction() -> Iterator[Tuple[list, list]]:
    """`with store.transaction() as (items, movements):` — altere as listas em memória;
    elas são gravadas de volta no S3 ao sair do bloco sem erro. Se o código dentro do `with`
    levantar uma exceção (ex.: HTTPException de validação), NADA é gravado."""
    with _lock:
        items = load_items()
        movements = load_movements()
        yield items, movements
        save_items(items)
        save_movements(movements)
