from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ItemIn(BaseModel):
    # Opcional: se não vier, o sistema gera (ex.: AUD-001). O site e o agente não enviam.
    sku: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=120)
    category: str = "Geral"
    quantity: int = Field(default=0, ge=0)
    min_quantity: int = Field(default=5, ge=0)
    unit_price: float = Field(default=0, ge=0)


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    min_quantity: Optional[int] = Field(default=None, ge=0)
    unit_price: Optional[float] = Field(default=None, ge=0)


class ItemOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    quantity: int
    min_quantity: int
    unit_price: float
    image_url: Optional[str]
    low_stock: bool
    created_at: datetime


class MovementIn(BaseModel):
    type: Literal["entrada", "saida"]
    quantity: int = Field(gt=0)
    note: Optional[str] = None


class MovementOut(BaseModel):
    id: int
    type: str
    quantity: int
    note: Optional[str]
    created_at: datetime


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


class ToolUse(BaseModel):
    function: str
    parameters: Dict[str, str]
    rationale: str = ""
    result: Optional[str] = None


class ChatOut(BaseModel):
    answer: str
    session_id: str
    mode: str
    tools_used: List[ToolUse]
    blocked: Optional[str] = None  # categoria bloqueada pelos guardrails (ex.: "sql_injection")
