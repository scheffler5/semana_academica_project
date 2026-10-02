"""Sobe o sistema inteiro localmente, montado como em produção:

    emulador de S3 (Moto, guarda fotos E dados) + API FastAPI (como na EC2)
    + build de produção do React servido com proxy /api (como o nginx)

    python local/rodar.py            # http://localhost:4173
    python local/rodar.py --dev      # React em modo desenvolvimento (recarrega ao salvar)

Ctrl+C para tudo. Para simular falhas durante a aula, em outro terminal:
    python local/servicos.py derrubar s3      (e depois: restaurar s3)
"""
import functools
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
print = functools.partial(print, flush=True)  # noqa: A001 (mensagens aparecem na hora)
VENV_BIN = Path(sys.executable).parent
sys.path.insert(0, str(ROOT / "local"))
import servicos  # noqa: E402

DEV = "--dev" in sys.argv


def wait_http(url: str, seconds: int = 30) -> bool:
    for _ in range(seconds * 5):
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    npm = VENV_BIN / "npm"
    if not npm.exists():
        npm = shutil.which("npm")
    if not npm:
        sys.exit("npm não encontrado. Veja a instalação do Node no README (nodeenv).")
    node_env = {**os.environ, "PATH": f"{VENV_BIN}{os.pathsep}{os.environ['PATH']}"}

    print("▶ Serviço (S3 local)…")
    servicos.start_s3()

    env = {**os.environ, **servicos.api_env()}
    env.pop("BEDROCK_AGENT_ID", None)
    env["PYTHONWARNINGS"] = "ignore"  # esconde aviso de fim de suporte do boto3 ao Python 3.9 (só local)
    print("▶ API (FastAPI) em http://127.0.0.1:8000 …")
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000",
         "--no-access-log"] + (["--reload"] if DEV else []),
        cwd=ROOT / "backend", env=env,
    )

    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "node_modules").exists():
        print("▶ Instalando dependências do frontend…")
        subprocess.run([str(npm), "install", "--no-audit", "--no-fund", "--loglevel=error"],
                       cwd=frontend_dir, env=node_env, check=True)
    if DEV:
        web = subprocess.Popen([str(npm), "run", "dev", "--", "--port", "4173", "--strictPort"],
                               cwd=frontend_dir, env=node_env)
    else:
        print("▶ Build de produção do React…")
        subprocess.run([str(npm), "run", "build"], cwd=frontend_dir, env=node_env, check=True,
                       stdout=subprocess.DEVNULL)
        web = subprocess.Popen([str(npm), "run", "preview", "--", "--port", "4173", "--strictPort"],
                               cwd=frontend_dir, env=node_env, stdout=subprocess.DEVNULL)

    ok = wait_http("http://127.0.0.1:8000/api/health") and wait_http("http://localhost:4173")
    if ok:
        import enviar_fotos
        try:
            if enviar_fotos.main(quiet=True):
                print("▶ Fotos de exemplo enviadas ao S3 local pela API")
        except Exception:
            print("⚠ Não foi possível enviar as fotos de exemplo (veja python local/servicos.py status)")
    print()
    servicos.status()
    print("\n  ➜  Site: http://localhost:4173" if ok else "\n  ⚠ Algo não subiu; veja as mensagens acima.")
    print("     Falhas para a aula: python local/servicos.py derrubar s3|agente\n     Ctrl+C para encerrar.\n")
    try:
        while api.poll() is None and web.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (web, api):
            proc.terminate()
        for proc in (web, api):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("\nAPI e site encerrados. O S3 local continua ligado (python local/servicos.py encerrar).")


if __name__ == "__main__":
    main()
