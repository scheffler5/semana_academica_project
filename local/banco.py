"""PostgreSQL 16 local (mesmo motor do Aurora PostgreSQL), sem Docker e sem instalar nada no sistema.

Usa o pacote `pgserver`, que traz os binários do PostgreSQL dentro do ambiente virtual.
Os dados ficam em .pgdata/ na raiz do projeto.

    python local/banco.py iniciar   # sobe o banco e mostra a DATABASE_URL
    python local/banco.py parar
    python local/banco.py zerar     # apaga o banco "estoque" e cria de novo (vazio)
    python local/banco.py psql "select sku, name, quantity from items"
"""
import sys
from pathlib import Path

import pgserver

ROOT = Path(__file__).resolve().parent.parent
PGDATA = ROOT / ".pgdata"
DB_NAME = "estoque"


def server():
    # cleanup_mode=None: o banco continua rodando depois que este script termina
    return pgserver.get_server(PGDATA, cleanup_mode=None)


def database_url(srv) -> str:
    # ex.: postgresql://postgres:@/postgres?host=/caminho/.pgdata  ->  banco "estoque"
    return srv.get_uri().replace("/postgres?", f"/{DB_NAME}?", 1)


def ensure_database(srv) -> None:
    exists = srv.psql(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}';")
    if "1 row" not in exists:
        srv.psql(f"CREATE DATABASE {DB_NAME};")


def start() -> str:
    srv = server()
    ensure_database(srv)
    return database_url(srv)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "iniciar"
    if command == "iniciar":
        print(f"PostgreSQL rodando. DATABASE_URL={start()}")
    elif command == "parar":
        srv = server()
        srv.cleanup_mode = "stop"
        srv.cleanup()
        print("PostgreSQL parado.")
    elif command == "zerar":
        srv = server()
        srv.psql(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE);")
        srv.psql(f"CREATE DATABASE {DB_NAME};")
        print("Banco 'estoque' recriado vazio. Os dados de exemplo voltam quando a API iniciar.")
    elif command == "psql":
        srv = server()
        sql = sys.argv[2] if len(sys.argv) > 2 else "\\dt"
        print(srv.psql(f"\\c {DB_NAME}\n{sql};" if not sql.startswith("\\") else f"\\c {DB_NAME}\n{sql}"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
