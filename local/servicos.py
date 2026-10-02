"""Serviço local que imita a AWS, e comandos para SIMULAR FALHAS na aula.

O S3 (emulador Moto) é o ÚNICO armazenamento do sistema: guarda as fotos E os dados
(items.json / movements.json). Por isso só existem dois "interruptores": s3 e agente.

    python local/servicos.py status
    python local/servicos.py iniciar            # sobe o S3 (emulador Moto)
    python local/servicos.py derrubar s3        # congela o S3 (requisições dão timeout, como rede bloqueada)
    python local/servicos.py derrubar agente    # a "Lambda" de ferramentas deixa de responder
    python local/servicos.py restaurar s3|agente|todos
    python local/servicos.py encerrar           # desliga tudo (fotos e dados do S3 local são perdidos)

Segurança: o emulador de S3 recebe credenciais FALSAS geradas aleatoriamente e guardadas em
.local/credenciais-locais.env (fora do git, permissão 600). Elas nunca são exibidas.
Na AWS não existe arquivo de credenciais: a EC2 usa a IAM Role.
"""
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
FAILURES = LOCAL / "falhas"
CREDENTIALS = LOCAL / "credenciais-locais.env"
S3_PID = LOCAL / "s3.pid"
S3_LOG = LOCAL / "s3.log"
S3_PORT = 4566
S3_URL = f"http://127.0.0.1:{S3_PORT}"
BUCKET = "estoque-imagens-local"
VENV_BIN = Path(sys.executable).parent


# ------------------------------------------------------------------ credenciais falsas

def credentials() -> dict:
    """Credenciais aleatórias SÓ para o emulador local. Não valem em nenhuma conta AWS."""
    LOCAL.mkdir(exist_ok=True)
    if not CREDENTIALS.exists():
        CREDENTIALS.write_text(
            "# Credenciais FALSAS do emulador local de S3. Não são chaves da AWS. Não compartilhe.\n"
            f"AWS_ACCESS_KEY_ID=local{secrets.token_hex(8)}\n"
            f"AWS_SECRET_ACCESS_KEY={secrets.token_urlsafe(30)}\n"
        )
        CREDENTIALS.chmod(0o600)
    values = {}
    for line in CREDENTIALS.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def api_env() -> dict:
    """Variáveis para a API rodar localmente como na AWS (sem imprimir nenhum segredo)."""
    return {
        "S3_BUCKET": BUCKET,
        "S3_ENDPOINT_URL": S3_URL,
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AGENT_MODE": "simulado",
        "LOCAL_API_URL": "http://127.0.0.1:8000",
        **credentials(),
    }


# ------------------------------------------------------------------ S3 (Moto)

def _s3_pid():
    try:
        pid = int(S3_PID.read_text())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _s3_client():
    import boto3
    from botocore.config import Config

    creds = credentials()
    return boto3.client("s3", endpoint_url=S3_URL, region_name="us-east-1",
                        aws_access_key_id=creds["AWS_ACCESS_KEY_ID"],
                        aws_secret_access_key=creds["AWS_SECRET_ACCESS_KEY"],
                        config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 1}))


def start_s3() -> None:
    if _s3_pid() is None:
        if _port_open(S3_PORT):
            sys.exit(f"A porta {S3_PORT} já está em uso por outro programa.")
        LOCAL.mkdir(exist_ok=True)
        log = open(S3_LOG, "ab")
        proc = subprocess.Popen([str(VENV_BIN / "moto_server"), "-H", "127.0.0.1", "-p", str(S3_PORT)],
                                stdout=log, stderr=log, start_new_session=True)
        S3_PID.write_text(str(proc.pid))
        for _ in range(50):
            if _port_open(S3_PORT):
                break
            time.sleep(0.2)
    # Bucket privado, igual ao da AWS (Block Public Access ligado)
    s3 = _s3_client()
    if BUCKET not in [b["Name"] for b in s3.list_buckets()["Buckets"]]:
        s3.create_bucket(Bucket=BUCKET)
        s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True})


def freeze_s3() -> None:
    pid = _s3_pid()
    if pid:
        os.kill(pid, signal.SIGSTOP)  # congela: conexões ficam penduradas até o timeout


def resume_s3() -> None:
    pid = _s3_pid()
    if pid:
        os.kill(pid, signal.SIGCONT)
    else:
        start_s3()


def stop_s3() -> None:
    pid = _s3_pid()
    if pid:
        os.kill(pid, signal.SIGCONT)
        os.kill(pid, signal.SIGTERM)
    S3_PID.unlink(missing_ok=True)


def s3_status() -> str:
    pid = _s3_pid()
    if not pid:
        return "parado"
    try:
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
    except OSError:
        state = ""
    return "DERRUBADO (congelado)" if state.strip().startswith("T") else f"rodando em {S3_URL}"


# ------------------------------------------------------------------ agente

def agent_down(down: bool) -> None:
    FAILURES.mkdir(parents=True, exist_ok=True)
    flag = FAILURES / "agente"
    if down:
        flag.touch()
    else:
        flag.unlink(missing_ok=True)


def api_status() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3) as r:
            return "rodando em http://127.0.0.1:8000" if r.status == 200 else f"erro {r.status}"
    except Exception:
        return "parada"


def status() -> None:
    print(f"  S3 (fotos + dados, → emulador Moto): {s3_status()}")
    print(f"  Agente (Bedrock+Lambda → simulado):  {'DERRUBADO' if (FAILURES / 'agente').exists() else 'ok'}")
    print(f"  API (EC2 → uvicorn local):           {api_status()}")


# ------------------------------------------------------------------ comandos

def main() -> None:
    args = sys.argv[1:] or ["status"]
    command, target = args[0], (args[1] if len(args) > 1 else "todos")

    if command == "iniciar":
        start_s3()
        agent_down(False)
    elif command == "derrubar":
        if target == "s3":
            freeze_s3()
        elif target == "agente":
            agent_down(True)
        else:
            sys.exit("Use: derrubar s3 | agente")
        print(f"💥 {target} derrubado. Veja o efeito no site (barra de status e telas).")
    elif command == "restaurar":
        if target in ("s3", "todos"):
            resume_s3()
        if target in ("agente", "todos"):
            agent_down(False)
        print(f"✅ {target} restaurado.")
    elif command == "encerrar":
        stop_s3()
        agent_down(False)
    elif command != "status":
        print(__doc__)
        return
    status()


if __name__ == "__main__":
    main()
