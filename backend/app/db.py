from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from . import config

if config.DATABASE_URL:
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True,
                           connect_args={"connect_timeout": 5} if config.DATABASE_URL.startswith("postgresql") else {})
elif config.DB_HOST:
    # Aurora PostgreSQL (dentro da VPC, sub-rede privada)
    url = URL.create(
        "postgresql+psycopg2",
        username=config.DB_USER,
        password=config.DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
    )
    # pool_pre_ping: reconecta se a conexão caiu. connect_timeout de 15 s cobre o Aurora
    # Serverless "acordando" e ainda permite mostrar a falha rápido se o banco cair.
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                           pool_timeout=10, connect_args={"connect_timeout": 15})
else:
    engine = create_engine(f"sqlite:///{config.BASE_DIR / 'estoque.db'}",
                           connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Conexão separada e rápida só para o /api/health (não espera 15 s se o banco cair)
probe_engine = (
    create_engine(engine.url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    if engine.dialect.name == "postgresql" else engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_label() -> str:
    if config.DB_HOST:
        return "Aurora PostgreSQL"
    return "PostgreSQL local" if engine.dialect.name == "postgresql" else "SQLite local"
