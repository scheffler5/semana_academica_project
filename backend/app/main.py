"""API do Sistema de Estoque Inteligente (roda na EC2, atrás do nginx)."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from collections import defaultdict
from datetime import timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from . import agent, config, errors, forecast, instance, skus, storage
from .db import Base, SessionLocal, database_label, engine, probe_engine
from .models import Item, Movement, utcnow
from .schemas import ChatIn, ChatOut, ItemIn, ItemOut, ItemUpdate, MovementIn, MovementOut
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("estoque")

app = FastAPI(title="Estoque Inteligente", version="2.0")
errors.install(app)


# ---------------------------------------------------------------- banco

_db_ready = False
_db_lock = threading.Lock()


def init_database() -> None:
    """Cria as tabelas e os dados de exemplo. Se o banco estiver fora do ar, a API sobe
    mesmo assim e tenta de novo na próxima requisição (o health mostra o banco como "down")."""
    global _db_ready
    if _db_ready:
        return
    with _db_lock:
        if _db_ready:
            return
        Base.metadata.create_all(engine)
        if config.SEED_DATA:
            with SessionLocal() as db:
                seed(db)
        _db_ready = True
        log.info("Banco pronto: %s", database_label())


@app.on_event("startup")
def startup() -> None:
    try:
        init_database()
    except OperationalError:
        log.error("Banco indisponível na inicialização; nova tentativa na próxima requisição")


def get_db():
    init_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------- utilidades

def to_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id, sku=item.sku, name=item.name, category=item.category,
        quantity=item.quantity, min_quantity=item.min_quantity,
        unit_price=float(item.unit_price), image_url=storage.image_url(item.id, item.image_key),
        low_stock=item.quantity <= item.min_quantity, created_at=item.created_at,
    )


def get_item_or_404(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item não encontrado")
    return item


def _probe_database() -> dict:
    start = time.perf_counter()
    try:
        with probe_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.perf_counter() - start) * 1000)}
    except Exception:
        return {"status": "down", "message": "Sem conexão com o banco de dados"}


# ---------------------------------------------------------------- status

@app.get("/api/health")
def health():
    """Situação de cada serviço. Sempre responde 200 (mesmo com serviços fora do ar)
    para o site conseguir mostrar QUAL parte falhou. Não expõe hosts, IPs nem nomes de recursos."""
    probes = {"database": _probe_database, "s3": storage.probe, "agent": agent.probe}
    with ThreadPoolExecutor(max_workers=len(probes)) as pool:  # em paralelo: o health nunca demora mais que a sonda mais lenta
        futures = {name: pool.submit(fn) for name, fn in probes.items()}
        services = {"api": {"status": "ok"}, **{name: f.result() for name, f in futures.items()}}
    services["database"]["label"] = database_label()
    critical_down = any(services[s]["status"] == "down" for s in ("database",))
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
def dashboard(db: Session = Depends(get_db)):
    items = db.scalars(select(Item)).all()
    today = utcnow().date()
    start = today - timedelta(days=13)
    movements = db.scalars(select(Movement).where(Movement.created_at >= start)).all()

    daily = {start + timedelta(days=i): {"entradas": 0, "saidas": 0} for i in range(14)}
    for m in movements:
        bucket = daily.get(m.created_at.date())
        if bucket is not None:
            bucket["entradas" if m.type == "entrada" else "saidas"] += m.quantity
    series = [{"date": d.isoformat(), **v} for d, v in sorted(daily.items())]
    sold_7d = sum(d["saidas"] for d in series[7:])
    sold_prev_7d = sum(d["saidas"] for d in series[:7])

    categories = defaultdict(lambda: {"value": 0.0, "units": 0, "items": 0})
    for i in items:
        c = categories[i.category]
        c["value"] += i.quantity * float(i.unit_price)
        c["units"] += i.quantity
        c["items"] += 1

    recent = db.scalars(select(Movement).order_by(Movement.created_at.desc()).limit(8)).all()
    low = sorted((i for i in items if i.quantity <= i.min_quantity),
                 key=lambda i: i.quantity / max(i.min_quantity, 1))
    return {
        "total_items": len(items),
        "total_units": sum(i.quantity for i in items),
        "total_value": round(sum(i.quantity * float(i.unit_price) for i in items), 2),
        "out_of_stock": sum(1 for i in items if i.quantity == 0),
        "sold_7d": sold_7d,
        "sold_prev_7d": sold_prev_7d,
        "daily": series,
        "by_category": sorted(({"category": k, **{**v, "value": round(v["value"], 2)}}
                               for k, v in categories.items()), key=lambda c: -c["value"]),
        "low_stock": [to_out(i) for i in low],
        "top_value": [to_out(i) for i in sorted(items, key=lambda i: -i.quantity * float(i.unit_price))[:4]],
        "recent_movements": [
            {"id": m.id, "item_id": m.item_id, "item": m.item.name, "sku": m.item.sku, "type": m.type,
             "quantity": m.quantity, "note": m.note, "created_at": m.created_at}
            for m in recent
        ],
    }


# ---------------------------------------------------------------- itens

@app.get("/api/items", response_model=List[ItemOut])
def list_items(search: Optional[str] = None, low_stock: bool = False, category: Optional[str] = None,
               db: Session = Depends(get_db)):
    query = select(Item).order_by(Item.name)
    if search:
        # % e _ digitados pelo usuário são tratados como texto, não como curinga do LIKE
        safe = search.lower()[:60].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{safe}%"
        query = query.where(or_(func.lower(Item.name).like(term, escape="\\"),
                                func.lower(Item.sku).like(term, escape="\\"),
                                func.lower(Item.category).like(term, escape="\\")))
    if low_stock:
        query = query.where(Item.quantity <= Item.min_quantity)
    if category:
        query = query.where(Item.category == category)
    return [to_out(i) for i in db.scalars(query)]


@app.get("/api/categories", response_model=List[str])
def list_categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Item.category).distinct().order_by(Item.category)))


@app.get("/api/items/next-sku")
def preview_sku(category: str = "Geral", db: Session = Depends(get_db)):
    """Prévia do código que será gerado (mostrada na tela de cadastro)."""
    return {"sku": skus.next_sku(db, category)}


@app.get("/api/items/by-sku/{sku}", response_model=ItemOut)
def get_item_by_sku(sku: str, db: Session = Depends(get_db)):
    item = db.scalar(select(Item).where(func.upper(Item.sku) == sku.upper()))
    if not item:
        raise HTTPException(404, f"Nenhum item com SKU {sku}")
    return to_out(item)


@app.post("/api/items", response_model=ItemOut, status_code=201)
def create_item(data: ItemIn, db: Session = Depends(get_db)):
    fields = data.model_dump()
    fields["name"] = fields["name"].strip()
    fields["category"] = fields["category"].strip() or "Geral"
    manual_sku = (fields.pop("sku") or "").strip().upper()

    for _ in range(5):  # se dois cadastros gerarem o mesmo código ao mesmo tempo, tenta o próximo
        item = Item(**fields, sku=manual_sku or skus.next_sku(db, fields["category"]))
        db.add(item)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if manual_sku:
                raise HTTPException(409, f"Já existe um item com SKU {manual_sku}")
    else:
        raise HTTPException(409, "Não foi possível gerar um código único. Tente novamente.")
    if item.quantity:
        db.add(Movement(item_id=item.id, type="entrada", quantity=item.quantity, note="Estoque inicial"))
        db.commit()
    return to_out(item)


@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    return to_out(get_item_or_404(db, item_id))


@app.put("/api/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, data: ItemUpdate, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    return to_out(item)


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    key = item.image_key
    db.delete(item)
    db.commit()
    if not storage.delete_image(key):
        log.warning("Item %s apagado, mas a foto ficou no S3 (S3 indisponível)", item_id)


@app.post("/api/items/{item_id}/image", response_model=ItemOut)
async def upload_image(item_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read(config.MAX_IMAGE_BYTES + 1)
    if len(data) > config.MAX_IMAGE_BYTES:
        raise HTTPException(413, "Imagem maior que 5 MB")
    detected = storage.detect_image(data)
    if not detected:
        raise HTTPException(400, "Arquivo não é uma imagem JPG, PNG, WEBP ou GIF válida")

    item = get_item_or_404(db, item_id)
    old_key = item.image_key
    item.image_key = storage.upload_image(item.id, data, *detected)  # 503 se o S3 cair
    db.commit()
    storage.delete_image(old_key)
    return to_out(item)


@app.get("/api/items/{item_id}/image")
def get_image(item_id: int, db: Session = Depends(get_db)):
    """A foto passa pela API: o navegador nunca recebe credenciais nem acessa o bucket."""
    item = get_item_or_404(db, item_id)
    if not item.image_key:
        raise HTTPException(404, "Item sem foto")
    try:
        data, content_type = storage.get_image(item.image_key)
    except FileNotFoundError:
        raise HTTPException(404, "Foto não encontrada no S3")
    return Response(data, media_type=content_type,
                    headers={"Cache-Control": "private, max-age=30", "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- movimentações

@app.get("/api/movements")
def recent_movements(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.scalars(select(Movement).order_by(Movement.created_at.desc()).limit(min(limit, 200)))
    return [{"id": m.id, "item_id": m.item_id, "item": m.item.name, "sku": m.item.sku, "type": m.type,
             "quantity": m.quantity, "note": m.note, "created_at": m.created_at} for m in rows]


@app.get("/api/items/{item_id}/movements", response_model=List[MovementOut])
def list_movements(item_id: int, limit: int = 50, db: Session = Depends(get_db)):
    get_item_or_404(db, item_id)
    rows = db.scalars(select(Movement).where(Movement.item_id == item_id)
                      .order_by(Movement.created_at.desc()).limit(min(limit, 200)))
    return list(rows)


@app.post("/api/items/{item_id}/movements", response_model=ItemOut, status_code=201)
def add_movement(item_id: int, data: MovementIn, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    if data.type == "saida" and data.quantity > item.quantity:
        raise HTTPException(400, f"Estoque insuficiente: há apenas {item.quantity} unidade(s) de {item.name}")
    item.quantity += data.quantity if data.type == "entrada" else -data.quantity
    db.add(Movement(item_id=item.id, **data.model_dump()))
    db.commit()
    return to_out(item)


# ---------------------------------------------------------------- IA

@app.get("/api/items/{item_id}/forecast")
def item_forecast(item_id: int, db: Session = Depends(get_db)):
    return forecast.forecast_item(db, get_item_or_404(db, item_id))


@app.post("/api/chat", response_model=ChatOut)
def chat(data: ChatIn):
    result = agent.ask(data.message, data.session_id)  # ServiceUnavailable -> 503 tratado
    result["answer"] = result["answer"] or "(o agente não retornou texto)"
    return ChatOut(**result)
