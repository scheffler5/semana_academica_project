"""API do Sistema de Estoque Inteligente (roda na EC2, atrás do nginx).

"Banco de dados": não existe um — os produtos e movimentações vivem em dois arquivos JSON
dentro do mesmo bucket S3 das fotos (veja app/store.py). Cada rota lê o que precisa do S3,
mexe nas listas em Python e grava de volta quando muda algo.
"""
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from . import agent, config, errors, forecast, instance, s3client, skus, storage, store
from .schemas import ChatIn, ChatOut, ItemIn, ItemOut, ItemUpdate, MovementIn, MovementOut
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("estoque")

app = FastAPI(title="Estoque Inteligente", version="3.0")
errors.install(app)


# ---------------------------------------------------------------- dados de exemplo

_seed_lock = threading.Lock()
_seeded = False


def ensure_seeded() -> None:
    """Cria os produtos de exemplo na primeira vez que o S3 responder. Se o S3 estiver fora
    do ar no startup, a API sobe mesmo assim e tenta nas próximas requisições."""
    global _seeded
    if _seeded or not config.SEED_DATA:
        return
    with _seed_lock:
        if _seeded:
            return
        seed()
        _seeded = True
        log.info("Dados de exemplo prontos (S3)")


@app.on_event("startup")
def startup() -> None:
    try:
        ensure_seeded()
    except Exception:
        log.warning("Não foi possível popular os dados de exemplo no startup; tentará de novo na próxima requisição")


def all_items() -> list:
    ensure_seeded()
    return store.load_items()


def all_movements() -> list:
    ensure_seeded()
    return store.load_movements()


# ---------------------------------------------------------------- utilidades

def to_out(item: dict) -> ItemOut:
    return ItemOut(
        id=item["id"], sku=item["sku"], name=item["name"], category=item["category"],
        quantity=item["quantity"], min_quantity=item["min_quantity"],
        unit_price=float(item["unit_price"]), image_url=storage.image_url(item["id"], item.get("image_key")),
        low_stock=item["quantity"] <= item["min_quantity"], created_at=item["created_at"],
    )


def find_item(items: list, item_id: int) -> dict:
    for it in items:
        if it["id"] == item_id:
            return it
    raise HTTPException(404, "Item não encontrado")


def match(item: dict, term: str) -> bool:
    return term in item["name"].lower() or term in item["sku"].lower() or term in item["category"].lower()


# ---------------------------------------------------------------- status

@app.get("/api/health")
def health():
    """Situação de cada serviço. Sempre responde 200 (mesmo com serviços fora do ar)
    para o site conseguir mostrar QUAL parte falhou. Não expõe hosts, IPs nem nomes de recursos."""
    probes = {"s3": s3client.probe, "agent": agent.probe}
    with ThreadPoolExecutor(max_workers=len(probes)) as pool:  # em paralelo: o health nunca demora mais que a sonda mais lenta
        futures = {name: pool.submit(fn) for name, fn in probes.items()}
        services = {"api": {"status": "ok"}, **{name: f.result() for name, f in futures.items()}}
    critical_down = services["s3"]["status"] == "down"  # S3 guarda fotos E dados: sem ele, nada funciona
    any_down = any(v["status"] == "down" for v in services.values())
    ec2 = instance.metadata()
    return {
        "status": "down" if critical_down else ("degraded" if any_down else "ok"),
        "services": services,
        "agent_mode": agent.mode(),
        "ec2": {k: v for k, v in ec2.items() if k != "private_ip"} if ec2 else None,
        "environment": "aws" if ec2 else "local",
        "region": config.AWS_REGION,
    }


@app.get("/api/dashboard")
def dashboard():
    items = all_items()
    movements = all_movements()
    items_by_id = {i["id"]: i for i in items}

    today = store.utcnow().date()
    start = today - timedelta(days=13)
    daily = {start + timedelta(days=i): {"entradas": 0, "saidas": 0} for i in range(14)}
    for m in movements:
        d = datetime.fromisoformat(m["created_at"]).date()
        bucket = daily.get(d)
        if bucket is not None:
            bucket["entradas" if m["type"] == "entrada" else "saidas"] += m["quantity"]
    series = [{"date": d.isoformat(), **v} for d, v in sorted(daily.items())]
    sold_7d = sum(d["saidas"] for d in series[7:])
    sold_prev_7d = sum(d["saidas"] for d in series[:7])

    categories = defaultdict(lambda: {"value": 0.0, "units": 0, "items": 0})
    for i in items:
        c = categories[i["category"]]
        c["value"] += i["quantity"] * float(i["unit_price"])
        c["units"] += i["quantity"]
        c["items"] += 1

    recent = sorted(movements, key=lambda m: m["created_at"], reverse=True)[:8]
    low = sorted((i for i in items if i["quantity"] <= i["min_quantity"]),
                 key=lambda i: i["quantity"] / max(i["min_quantity"], 1))
    return {
        "total_items": len(items),
        "total_units": sum(i["quantity"] for i in items),
        "total_value": round(sum(i["quantity"] * float(i["unit_price"]) for i in items), 2),
        "out_of_stock": sum(1 for i in items if i["quantity"] == 0),
        "sold_7d": sold_7d,
        "sold_prev_7d": sold_prev_7d,
        "daily": series,
        "by_category": sorted(({"category": k, **{**v, "value": round(v["value"], 2)}}
                               for k, v in categories.items()), key=lambda c: -c["value"]),
        "low_stock": [to_out(i) for i in low],
        "top_value": [to_out(i) for i in sorted(items, key=lambda i: -i["quantity"] * float(i["unit_price"]))[:4]],
        "recent_movements": [
            {"id": m["id"], "item_id": m["item_id"],
             "item": items_by_id.get(m["item_id"], {}).get("name", "?"),
             "sku": items_by_id.get(m["item_id"], {}).get("sku", "?"),
             "type": m["type"], "quantity": m["quantity"], "note": m.get("note"), "created_at": m["created_at"]}
            for m in recent
        ],
    }


# ---------------------------------------------------------------- itens

@app.get("/api/items", response_model=List[ItemOut])
def list_items(search: Optional[str] = None, low_stock: bool = False, category: Optional[str] = None):
    items = all_items()
    if search:
        term = search.strip().lower()[:60]
        items = [i for i in items if match(i, term)]
    if low_stock:
        items = [i for i in items if i["quantity"] <= i["min_quantity"]]
    if category:
        items = [i for i in items if i["category"] == category]
    items = sorted(items, key=lambda i: i["name"])
    return [to_out(i) for i in items]


@app.get("/api/categories", response_model=List[str])
def list_categories():
    return sorted({i["category"] for i in all_items()})


@app.get("/api/items/next-sku")
def preview_sku(category: str = "Geral"):
    """Prévia do código que será gerado (mostrada na tela de cadastro)."""
    return {"sku": skus.next_sku(all_items(), category)}


@app.get("/api/items/by-sku/{sku}", response_model=ItemOut)
def get_item_by_sku(sku: str):
    for i in all_items():
        if i["sku"].upper() == sku.upper():
            return to_out(i)
    raise HTTPException(404, f"Nenhum item com SKU {sku}")


@app.post("/api/items", response_model=ItemOut, status_code=201)
def create_item(data: ItemIn):
    fields = data.model_dump()
    fields["name"] = fields["name"].strip()
    fields["category"] = fields["category"].strip() or "Geral"
    manual_sku = (fields.pop("sku") or "").strip().upper()

    with store.transaction() as (items, movements):
        sku = manual_sku or skus.next_sku(items, fields["category"])
        if any(i["sku"] == sku for i in items):
            raise HTTPException(409, f"Já existe um item com SKU {sku}")
        item = {
            "id": store.next_id(items), "sku": sku, "name": fields["name"], "category": fields["category"],
            "quantity": fields["quantity"], "min_quantity": fields["min_quantity"],
            "unit_price": fields["unit_price"], "image_key": None, "created_at": store.now_iso(),
        }
        items.append(item)
        if item["quantity"]:
            movements.append({"id": store.next_id(movements), "item_id": item["id"], "type": "entrada",
                              "quantity": item["quantity"], "note": "Estoque inicial", "created_at": store.now_iso()})
    return to_out(item)


@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    return to_out(find_item(all_items(), item_id))


@app.put("/api/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, data: ItemUpdate):
    with store.transaction() as (items, movements):
        item = find_item(items, item_id)
        for field, value in data.model_dump(exclude_none=True).items():
            item[field] = value
    return to_out(item)


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int):
    with store.transaction() as (items, movements):
        item = find_item(items, item_id)
        items.remove(item)
        movements[:] = [m for m in movements if m["item_id"] != item_id]
        key = item.get("image_key")
    if not storage.delete_image(key):
        log.warning("Item %s apagado, mas a foto ficou no S3 (S3 indisponível)", item_id)


@app.post("/api/items/{item_id}/image", response_model=ItemOut)
async def upload_image(item_id: int, file: UploadFile = File(...)):
    data = await file.read(config.MAX_IMAGE_BYTES + 1)
    if len(data) > config.MAX_IMAGE_BYTES:
        raise HTTPException(413, "Imagem maior que 5 MB")
    detected = storage.detect_image(data)
    if not detected:
        raise HTTPException(400, "Arquivo não é uma imagem JPG, PNG, WEBP ou GIF válida")

    find_item(all_items(), item_id)  # 404 cedo, antes de gastar uma chamada ao S3
    new_key = storage.upload_image(item_id, data, *detected)  # 503 se o S3 cair

    with store.transaction() as (items, movements):
        item = find_item(items, item_id)
        old_key = item.get("image_key")
        item["image_key"] = new_key
    storage.delete_image(old_key)
    return to_out(item)


@app.get("/api/items/{item_id}/image")
def get_image(item_id: int):
    """A foto passa pela API: o navegador nunca recebe credenciais nem acessa o bucket."""
    item = find_item(all_items(), item_id)
    if not item.get("image_key"):
        raise HTTPException(404, "Item sem foto")
    try:
        data, content_type = storage.get_image(item["image_key"])
    except FileNotFoundError:
        raise HTTPException(404, "Foto não encontrada no S3")
    return Response(data, media_type=content_type,
                    headers={"Cache-Control": "private, max-age=30", "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- movimentações

@app.get("/api/movements")
def recent_movements(limit: int = 30):
    items_by_id = {i["id"]: i for i in all_items()}
    movements = sorted(all_movements(), key=lambda m: m["created_at"], reverse=True)[:min(limit, 200)]
    return [
        {"id": m["id"], "item_id": m["item_id"],
         "item": items_by_id.get(m["item_id"], {}).get("name", "?"),
         "sku": items_by_id.get(m["item_id"], {}).get("sku", "?"),
         "type": m["type"], "quantity": m["quantity"], "note": m.get("note"), "created_at": m["created_at"]}
        for m in movements
    ]


@app.get("/api/items/{item_id}/movements", response_model=List[MovementOut])
def list_movements(item_id: int, limit: int = 50):
    find_item(all_items(), item_id)
    rows = sorted((m for m in all_movements() if m["item_id"] == item_id),
                  key=lambda m: m["created_at"], reverse=True)
    return rows[:min(limit, 200)]


@app.post("/api/items/{item_id}/movements", response_model=ItemOut, status_code=201)
def add_movement(item_id: int, data: MovementIn):
    with store.transaction() as (items, movements):
        item = find_item(items, item_id)
        if data.type == "saida" and data.quantity > item["quantity"]:
            raise HTTPException(400, f"Estoque insuficiente: há apenas {item['quantity']} unidade(s) de {item['name']}")
        item["quantity"] += data.quantity if data.type == "entrada" else -data.quantity
        movements.append({"id": store.next_id(movements), "item_id": item_id,
                          "created_at": store.now_iso(), **data.model_dump()})
    return to_out(item)


# ---------------------------------------------------------------- IA

@app.get("/api/items/{item_id}/forecast")
def item_forecast(item_id: int):
    items = all_items()
    item = find_item(items, item_id)
    movements = [m for m in all_movements() if m["item_id"] == item_id]
    return forecast.forecast_item(item, movements)


@app.post("/api/chat", response_model=ChatOut)
def chat(data: ChatIn):
    result = agent.ask(data.message, data.session_id)  # ServiceUnavailable -> 503 tratado
    result["answer"] = result["answer"] or "(o agente não retornou texto)"
    return ChatOut(**result)
