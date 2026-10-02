"""deploy/schema.sql precisa bater com os modelos e funcionar num PostgreSQL vazio."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app import schema_sql
from app.db import Base
from app.models import Item
from app.seed import seed

SCHEMA = Path(__file__).resolve().parents[2] / "deploy" / "schema.sql"


def test_schema_sql_esta_atualizado():
    assert SCHEMA.read_text(encoding="utf-8") == schema_sql.render(), (
        "deploy/schema.sql desatualizado: rode `python -m app.schema_sql > ../deploy/schema.sql` em backend/"
    )


def test_schema_sql_cria_o_banco_e_a_api_usa_ele():
    pgserver = pytest.importorskip("pgserver")
    root = Path(__file__).resolve().parents[2]
    srv = pgserver.get_server(root / ".pgdata", cleanup_mode=None)
    srv.psql("DROP DATABASE IF EXISTS estoque_schema WITH (FORCE);")
    srv.psql("CREATE DATABASE estoque_schema;")
    engine = create_engine(srv.get_uri().replace("/postgres?", "/estoque_schema?", 1))

    # 1. cria as tabelas SÓ com o SQL (como no Query Editor / psql), duas vezes (idempotente)
    with engine.begin() as conn:
        conn.execute(text(SCHEMA.read_text(encoding="utf-8")))
        conn.execute(text(SCHEMA.read_text(encoding="utf-8")))

    # 2. a API sobe por cima: create_all não muda nada e o seed preenche os exemplos
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        assert db.scalar(select(func.count(Item.id))) == 10
    engine.dispose()
    srv.psql("DROP DATABASE IF EXISTS estoque_schema WITH (FORCE);")
