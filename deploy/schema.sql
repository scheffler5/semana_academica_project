-- Estoque Inteligente: criação das tabelas no Aurora PostgreSQL
-- Gerado automaticamente por backend/app/schema_sql.py a partir de backend/app/models.py.
-- Não edite à mão: rode `python -m app.schema_sql > ../deploy/schema.sql` dentro de backend/.
--
-- Pode rodar mais de uma vez (IF NOT EXISTS). Os produtos de exemplo NÃO estão aqui:
-- a API os cria na primeira execução (backend/app/seed.py), se a tabela estiver vazia.

CREATE TABLE IF NOT EXISTS items (
    id SERIAL NOT NULL,
    sku VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    category VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    min_quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    image_key VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_items_sku ON items (sku);

CREATE TABLE IF NOT EXISTS movements (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    type VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    note VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_movements_created_at ON movements (created_at);

CREATE INDEX IF NOT EXISTS ix_movements_item_id ON movements (item_id);
