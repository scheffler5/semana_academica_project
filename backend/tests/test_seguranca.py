"""Nenhuma chave/segredo no repositório nem nas respostas da API."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS = {
    "Access Key da AWS": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Secret Key da AWS": re.compile(r"aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+]{30,}", re.I),
    "Chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Senha com valor literal: em arquivos KEY=valor (.env, .sh...) e em código (password="...")
ENV_PASSWORD = re.compile(r"^[ \t]*[A-Z_]*PASSWORD=[^\s#]+", re.M)
CODE_PASSWORD = re.compile(r"password\w*\s*[=:]\s*[\"'][^\"']{4,}[\"']", re.I)
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts"}


def repo_files():
    """Arquivos que iriam para o git (respeita o .gitignore)."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for name in out.splitlines():
        path = ROOT / name
        if path.is_file() and path.stat().st_size < 2_000_000:
            yield path


def test_nenhum_segredo_no_repositorio():
    found = []
    for path in repo_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                found.append(f"{label} em {path.relative_to(ROOT)}")
        if path.suffix in CODE_SUFFIXES:
            if CODE_PASSWORD.search(content):
                found.append(f"Senha no código em {path.relative_to(ROOT)}")
        elif path.suffix != ".md" and ENV_PASSWORD.search(content):
            found.append(f"Senha preenchida em {path.relative_to(ROOT)}")
    assert not found, found


def test_repositorio_so_tem_codigo():
    """Imagens e bancos de dados nunca vão para o git (os dados são criados pelo seed.py)."""
    proibidos = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico", ".db", ".sqlite", ".sqlite3", ".sql", ".dump")
    permitidos = {"deploy/schema.sql"}  # código de criação das tabelas (sem dados)
    encontrados = [str(p.relative_to(ROOT)) for p in repo_files()
                   if p.suffix.lower() in proibidos and str(p.relative_to(ROOT)) not in permitidos]
    assert not encontrados, encontrados


def test_arquivos_sensiveis_ignorados_pelo_git():
    for sensitive in ["backend/.env", ".local/credenciais-locais.env", ".pgdata/PG_VERSION"]:
        result = subprocess.run(["git", "check-ignore", "-q", sensitive], cwd=ROOT)
        assert result.returncode == 0, f"{sensitive} NÃO está no .gitignore"


def test_health_nao_expoe_configuracao(api):
    text = api.get("/api/health").text
    from conftest import BUCKET
    for secret_ish in [BUCKET, "AWS_", "password", "DATABASE_URL", "private_ip", "endpoint_url", "127.0.0.1"]:
        assert secret_ish not in text, secret_ish


def test_nenhuma_resposta_traz_credenciais(api, item):
    import os
    key_id = os.environ["AWS_ACCESS_KEY_ID"]
    for path in ["/api/health", "/api/dashboard", "/api/items", f"/api/items/{item('NB-001')['id']}"]:
        text = api.get(path).text
        assert key_id not in text and "X-Amz-Credential" not in text and "X-Amz-Signature" not in text
