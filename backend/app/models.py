from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="Geral")
    quantity: Mapped[int] = mapped_column(default=0)
    min_quantity: Mapped[int] = mapped_column(default=5)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    image_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    movements: Mapped[List["Movement"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Movement.created_at.desc()"
    )


class Movement(Base):
    __tablename__ = "movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(10))  # "entrada" ou "saida"
    quantity: Mapped[int]
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    item: Mapped[Item] = relationship(back_populates="movements")
