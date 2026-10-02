"""Chat de terminal com o agente, falando SÓ com a API (POST /api/chat), como o site faz.

    python local/chat.py                          # API local
    python local/chat.py http://IP-DA-EC2         # API na AWS

Mostra a resposta e, abaixo, cada ferramenta que o agente chamou (função, parâmetros, retorno).
"""
import json
import sys
import urllib.error
import urllib.request

API = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def post(message, session_id):
    body = json.dumps({"message": message, "session_id": session_id}).encode()
    req = urllib.request.Request(f"{API}/api/chat", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main():
    print(f"Agente de estoque em {API}. Digite 'sair' para encerrar, 'nova' para nova sessão.\n")
    session_id = None
    while True:
        try:
            message = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            continue
        if message.lower() == "sair":
            break
        if message.lower() == "nova":
            session_id = None
            print("(nova sessão)\n")
            continue
        try:
            result = post(message, session_id)
        except urllib.error.HTTPError as err:
            print(f"erro {err.code}: {err.read().decode()}\n")
            continue
        except urllib.error.URLError as err:
            print(f"API indisponível em {API}: {err.reason}\n")
            continue
        session_id = result["session_id"]
        for tool in result["tools_used"]:
            params = ", ".join(f"{k}={v!r}" for k, v in tool["parameters"].items())
            print(f"  🔧 {tool['function']}({params})")
            if tool.get("rationale"):
                print(f"     raciocínio: {tool['rationale']}")
            for line in (tool.get("result") or "").splitlines()[:4]:
                print(f"     ↳ {line}")
        print(f"agente [{result['mode']}]> {result['answer']}\n")


if __name__ == "__main__":
    main()
