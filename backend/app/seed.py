"""Itens de exemplo + 30 dias de movimentações para o laboratório já começar com dados."""
import random
from datetime import timedelta

from . import store

# sku, nome, categoria, estoque atual, mínimo, preço, saída média por dia
SAMPLE_ITEMS = [
    ("NB-001", "Notebook Dell Inspiron 15", "Informática", 38, 5, 3899.90, 1.2),
    ("MS-002", "Mouse sem fio Logitech", "Informática", 12, 20, 89.90, 5.0),
    ("TC-003", "Teclado mecânico Redragon", "Informática", 57, 10, 249.90, 2.5),
    ("MN-004", "Monitor LG 24\"", "Informática", 21, 5, 899.00, 1.0),
    ("CB-005", "Cabo HDMI 2m", "Acessórios", 184, 30, 29.90, 9.0),
    ("HD-006", "Headset Gamer HyperX", "Áudio", 44, 8, 399.90, 2.2),
    ("PD-007", "Pendrive 64GB Kingston", "Armazenamento", 160, 25, 49.90, 7.5),
    ("SS-008", "SSD NVMe 1TB Samsung", "Armazenamento", 4, 6, 549.90, 1.8),
    ("WC-009", "Webcam Full HD", "Acessórios", 47, 10, 199.90, 3.0),
    ("CD-010", "Cadeira ergonômica", "Mobiliário", 2, 4, 1299.00, 0.6),
]


def seed() -> None:
    if store.load_items():
        return  # já tem dados (seja de exemplo ou cadastrados pela turma): não mexe

    rng = random.Random(42)
    now = store.utcnow()
    items, movements = [], []
    next_item_id, next_mov_id = 1, 1

    for sku, name, category, current_qty, min_qty, price, daily in SAMPLE_ITEMS:
        item_id = next_item_id
        next_item_id += 1
        items.append({
            "id": item_id, "sku": sku, "name": name, "category": category,
            "quantity": current_qty, "min_quantity": min_qty, "unit_price": price,
            "image_key": None, "created_at": (now - timedelta(days=31)).isoformat(),
        })

        for days_ago in range(30, -1, -1):
            day = now - timedelta(days=days_ago, hours=rng.randint(0, 8))
            weekend = day.weekday() >= 5
            out = max(0, round(rng.gauss(daily * (0.4 if weekend else 1.15), daily * 0.4)))
            if out:
                movements.append({"id": next_mov_id, "item_id": item_id, "type": "saida",
                                  "quantity": out, "note": "Venda", "created_at": day.isoformat()})
                next_mov_id += 1
            # reposição semanal do fornecedor
            if days_ago % 7 == 3:
                movements.append({"id": next_mov_id, "item_id": item_id, "type": "entrada",
                                  "quantity": round(daily * 7), "note": "Reposição do fornecedor",
                                  "created_at": (day + timedelta(hours=1)).isoformat()})
                next_mov_id += 1

    store.save_items(items)
    store.save_movements(movements)
