"""Geração automática do SKU (código interno do produto).

Formato: 3 letras da categoria + sequência de 3 dígitos. Ex.: Áudio -> AUD-001, AUD-002...
O usuário não precisa inventar código: o sistema garante que é único.
"""
import re
import unicodedata


def prefix(category: str) -> str:
    text = unicodedata.normalize("NFKD", category or "")
    letters = "".join(c for c in text if c.isascii() and c.isalpha()).upper()
    return (letters[:3] or "GER").ljust(3, "X")


def next_sku(items: list, category: str) -> str:
    p = prefix(category)
    pattern = re.compile(rf"^{p}-(\d+)$")
    numbers = [int(m.group(1)) for it in items if (m := pattern.match(it["sku"]))]
    return f"{p}-{max(numbers, default=0) + 1:03d}"
