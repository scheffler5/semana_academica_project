"""Geração automática do SKU (código interno do produto).

Formato: 3 letras da categoria + sequência de 3 dígitos. Ex.: Áudio -> AUD-001, AUD-002...
O usuário não precisa inventar código: o sistema garante que é único.
"""
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item


def prefix(category: str) -> str:
    text = unicodedata.normalize("NFKD", category or "")
    letters = "".join(c for c in text if c.isascii() and c.isalpha()).upper()
    return (letters[:3] or "GER").ljust(3, "X")


def next_sku(db: Session, category: str) -> str:
    p = prefix(category)
    pattern = re.compile(rf"^{p}-(\d+)$")
    existing = db.scalars(select(Item.sku).where(Item.sku.like(f"{p}-%")))
    numbers = [int(m.group(1)) for sku in existing if (m := pattern.match(sku))]
    return f"{p}-{max(numbers, default=0) + 1:03d}"
