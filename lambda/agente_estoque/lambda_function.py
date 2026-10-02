"""AWS Lambda: ferramentas (Action Group) do agente de estoque do Bedrock.

Fluxo:  Usuário -> Bedrock Agent -> ESTA Lambda -> API na EC2 (IP privado, dentro da VPC)

O agente decide qual função chamar (ex.: "cadastrar_item") e com quais
parâmetros. Aqui só traduzimos isso em chamadas HTTP para a API do sistema.
Usa apenas a biblioteca padrão do Python: dá para colar direto no console.

As funções e parâmetros precisam bater com bedrock/action_group.json.

Variáveis de ambiente:
    API_BASE_URL       = http://<IP-PRIVADO-DA-EC2>   (obrigatória, ex.: http://10.0.0.25)
    PERMISSOES_AGENTE  = leitura,escrita              (opcional; "leitura" = agente só consulta)

Segurança (camada de software):
  - a Lambda só fala com a API do estoque: não tem acesso a banco, arquivos, segredos nem AWS;
  - cada ferramenta tem um nível de permissão (leitura/escrita) e não existe ferramenta de apagar;
  - todo parâmetro é validado (formato, tamanho, caracteres, limites) ANTES de chamar a API.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

# ------------------------------------------------------------- permissões e limites (software)

PERMISSOES = {
    "consultar_estoque": "leitura",
    "itens_estoque_baixo": "leitura",
    "resumo_estoque": "leitura",
    "prever_demanda": "leitura",
    "cadastrar_item": "escrita",
    "atualizar_item": "escrita",
    "registrar_movimentacao": "escrita",
}
LIMITE_QUANTIDADE = 1000      # o agente não movimenta mais que isso de uma vez
LIMITE_PRECO = 100_000.0

SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,39}$")
TEXTO_RE = re.compile(r"^[0-9A-Za-zÀ-ÿ .,'\"/()+&-]+$")
SUSPEITO_RE = re.compile(
    r"(--|;|/\*|\*/|<\s*script|\$\(|`|\b(drop|delete|insert|update|select|union|truncate|alter|exec)\b)",
    re.IGNORECASE,
)


def permissoes_ativas():
    return {p.strip() for p in os.environ.get("PERMISSOES_AGENTE", "leitura,escrita").split(",") if p.strip()}


def validar_sku(valor):
    sku = str(valor).strip().upper()
    if not SKU_RE.match(sku):
        raise ValueError("SKU inválido: use só letras, números e hífen (ex.: MS-002)")
    return sku


def validar_texto(valor, campo, maximo):
    texto = " ".join(str(valor).split())  # remove quebras de linha e espaços extras
    if not texto or len(texto) > maximo:
        raise ValueError(f"{campo} deve ter entre 1 e {maximo} caracteres")
    if not TEXTO_RE.match(texto) or SUSPEITO_RE.search(texto):
        raise ValueError(f"{campo} contém caracteres ou comandos não permitidos")
    return texto


def call_api(method, path, body=None):
    api = os.environ.get("API_BASE_URL", "").rstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{api}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as err:
        # A API devolve {"message": "..."} já pronto para o usuário (sem detalhes internos)
        try:
            body = json.loads(err.read() or "{}")
        except ValueError:
            body = {}
        raise ValueError(body.get("message") or body.get("detail") or f"a API respondeu {err.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        # O detalhe (IP privado, porta) fica só no CloudWatch; o agente recebe uma frase segura
        print(f"Falha de rede ao chamar a API: {err}")
        raise ValueError("a API do estoque (EC2) não respondeu; o servidor pode estar fora do ar")


# O Bedrock envia TODOS os valores como texto: convertemos e checamos os limites aqui
def to_int(value, minimo=0, maximo=LIMITE_QUANTIDADE, campo="quantidade"):
    try:
        number = int(float(str(value).replace(",", ".")))
    except ValueError:
        raise ValueError(f"{campo} deve ser um número inteiro")
    if not minimo <= number <= maximo:
        raise ValueError(f"{campo} deve estar entre {minimo} e {maximo}")
    return number


def to_float(value, campo="preço"):
    text = str(value).replace("R$", "").strip()
    if "," in text:  # formato brasileiro: 1.299,90
        text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{campo} deve ser um número")
    if not 0 < number <= LIMITE_PRECO:
        raise ValueError(f"{campo} deve estar entre 0,01 e {LIMITE_PRECO:,.2f}")
    return round(number, 2)


def get_by_sku(sku):
    return call_api("GET", f"/api/items/by-sku/{urllib.parse.quote(validar_sku(sku))}")


def resumo_item(i):
    status = "ESTOQUE BAIXO" if i["low_stock"] else "ok"
    return (f"{i['sku']} | {i['name']} | categoria {i['category']} | "
            f"{i['quantity']} un. (mínimo {i['min_quantity']}) | R$ {i['unit_price']:.2f} | {status}")


# ------------------------------------------------------------- ferramentas

def consultar_estoque(termo=""):
    termo = validar_texto(termo, "termo de busca", 60) if str(termo).strip() else ""
    query = f"?search={urllib.parse.quote(termo)}" if termo else ""
    items = call_api("GET", f"/api/items{query}")
    if not items:
        return f"Nenhum item encontrado para '{termo}'."
    return "\n".join(resumo_item(i) for i in items)


def itens_estoque_baixo():
    items = call_api("GET", "/api/items?low_stock=true")
    if not items:
        return "Nenhum item está abaixo do estoque mínimo."
    return "Itens no estoque mínimo ou abaixo:\n" + "\n".join(resumo_item(i) for i in items)


def resumo_estoque():
    d = call_api("GET", "/api/dashboard")
    return (f"{d['total_items']} itens cadastrados, {d['total_units']} unidades no total, "
            f"valor total em estoque R$ {d['total_value']:.2f}. "
            f"{len(d['low_stock'])} item(ns) com estoque baixo.")


def cadastrar_item(nome, preco, quantidade=0, categoria="Geral", estoque_minimo=5):
    # O SKU não é enviado: a API gera o código (ex.: AUD-001)
    item = call_api("POST", "/api/items", {
        "name": validar_texto(nome, "nome", 120), "unit_price": to_float(preco),
        "quantity": to_int(quantidade, 0), "category": validar_texto(categoria or "Geral", "categoria", 60),
        "min_quantity": to_int(estoque_minimo, 0, campo="estoque mínimo"),
    })
    return f"Item cadastrado com o código {item['sku']}: " + resumo_item(item)


def atualizar_item(sku, preco=None, estoque_minimo=None, nome=None):
    changes = {}
    if preco not in (None, ""):
        changes["unit_price"] = to_float(preco)
    if estoque_minimo not in (None, ""):
        changes["min_quantity"] = to_int(estoque_minimo, 0, campo="estoque mínimo")
    if nome:
        changes["name"] = validar_texto(nome, "nome", 120)
    if not changes:
        raise ValueError("informe ao menos um campo para alterar (preco, estoque_minimo ou nome)")
    item = get_by_sku(sku)
    updated = call_api("PUT", f"/api/items/{item['id']}", changes)
    return "Item atualizado: " + resumo_item(updated)


def registrar_movimentacao(sku, tipo, quantidade, observacao="Registrado pelo assistente de IA"):
    tipo = str(tipo).strip().lower().replace("í", "i")
    if tipo not in ("entrada", "saida"):
        raise ValueError("tipo deve ser 'entrada' ou 'saida'")
    observacao = validar_texto(observacao, "observação", 200)
    quantidade = to_int(quantidade, 1)
    item = get_by_sku(sku)
    atualizado = call_api("POST", f"/api/items/{item['id']}/movements",
                          {"type": tipo, "quantity": quantidade, "note": observacao})
    return (f"Movimentação registrada: {tipo} de {quantidade} un. de {item['name']} ({item['sku']}). "
            f"Estoque atual: {atualizado['quantity']} un.")


def prever_demanda(sku):
    item = get_by_sku(sku)
    f = call_api("GET", f"/api/items/{item['id']}/forecast")
    return (f"Previsão para {f['name']} ({f['sku']}), calculada pela média móvel das saídas: "
            f"saída de {f['predicted_next_7_days']} un. nos próximos 7 dias "
            f"(~{f['predicted_daily']}/dia). Estoque atual {f['quantity']} un. {f['recommendation']}")


TOOLS = {
    "consultar_estoque": consultar_estoque,
    "itens_estoque_baixo": itens_estoque_baixo,
    "resumo_estoque": resumo_estoque,
    "cadastrar_item": cadastrar_item,
    "atualizar_item": atualizar_item,
    "registrar_movimentacao": registrar_movimentacao,
    "prever_demanda": prever_demanda,
}


def lambda_handler(event, context):
    print(json.dumps(event, ensure_ascii=False))  # aparece no CloudWatch Logs
    function = event["function"]
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}

    tool = TOOLS.get(function)
    if tool is None:
        text = f"Erro: a função {function} não existe nesta Lambda."
    elif PERMISSOES[function] not in permissoes_ativas():
        text = f"Erro ao executar {function}: o assistente não tem permissão de {PERMISSOES[function]} neste sistema."
    else:
        try:
            text = tool(**params)
        except Exception as exc:
            text = f"Erro ao executar {function}: {exc}"

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event["actionGroup"],
            "function": function,
            "functionResponse": {"responseBody": {"TEXT": {"body": text}}},
        },
    }
