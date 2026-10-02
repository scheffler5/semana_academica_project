"""Gera o SQL de criação das tabelas (DDL) a partir dos modelos, para criar o banco "na mão".

    cd backend && python -m app.schema_sql > ../deploy/schema.sql

Não é obrigatório: a API cria as tabelas sozinha ao iniciar. O arquivo existe para mostrar
na aula (Query Editor do RDS ou psql) e é gerado do código para nunca ficar desatualizado.
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from .db import Base
from . import models  # noqa: F401  (registra as tabelas no Base)

HEADER = """-- Estoque Inteligente: criação das tabelas no Aurora PostgreSQL
-- Gerado automaticamente por backend/app/schema_sql.py a partir de backend/app/models.py.
-- Não edite à mão: rode `python -m app.schema_sql > ../deploy/schema.sql` dentro de backend/.
--
-- Pode rodar mais de uma vez (IF NOT EXISTS). Os produtos de exemplo NÃO estão aqui:
-- a API os cria na primeira execução (backend/app/seed.py), se a tabela estiver vazia.
"""


def render() -> str:
    dialect = postgresql.dialect()
    parts = [HEADER]
    for table in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip() + ";\n")
        for index in sorted(table.indexes, key=lambda i: i.name):
            parts.append(str(CreateIndex(index, if_not_exists=True).compile(dialect=dialect)).strip() + ";\n")
    sql = "\n".join(parts)
    return "\n".join(line.rstrip().replace("\t", "    ") for line in sql.splitlines()) + "\n"


if __name__ == "__main__":
    print(render(), end="")
