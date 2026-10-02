"""Agente SIMULADO: imita o Bedrock Agent localmente, sem LLM de verdade.

Serve para testar todo o caminho das ferramentas antes de subir para a AWS:

    API /api/chat -> agente simulado -> Lambda (mesmo código da AWS) -> API HTTP -> banco

O ciclo é o mesmo que o Bedrock Agents faz (chamado de "orquestração"):
  1. o "modelo" lê a pergunta + o que já foi feito e decide: chamar uma ferramenta OU responder;
  2. a chamada é validada contra bedrock/action_group.json (nome da função, obrigatórios, tipos);
  3. montamos o evento no MESMO formato JSON que o Bedrock envia para a Lambda e a executamos;
  4. o texto devolvido pela Lambda volta para o "modelo", que decide o próximo passo.

O "modelo" aqui é a classe RuleBasedLLM: regras simples com expressões regulares.
Na AWS ela é substituída por um LLM de verdade (Claude no Bedrock); o resto não muda.
"""
import importlib.util
import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from . import config
from .errors import ServiceUnavailable

REPO_ROOT = config.BASE_DIR.parent
SCHEMA_PATH = REPO_ROOT / "bedrock" / "action_group.json"
LAMBDA_PATH = REPO_ROOT / "lambda" / "agente_estoque" / "lambda_function.py"
# `python local/servicos.py derrubar agente` cria este arquivo para simular a Lambda fora do ar
FAILURE_FLAG = REPO_ROOT / ".local" / "falhas" / "agente"
MAX_STEPS = 6


# ------------------------------------------------------------------ estruturas

@dataclass
class ToolCall:
    function: str
    params: Dict[str, object]
    rationale: str = ""


@dataclass
class FinalAnswer:
    text: str


@dataclass
class Step:
    call: ToolCall
    observation: str


Decision = Union[ToolCall, FinalAnswer]


class SchemaError(ValueError):
    pass


# ------------------------------------------------------------------ schema + Lambda

def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_lambda():
    spec = importlib.util.spec_from_file_location("lambda_function", LAMBDA_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_call(call: ToolCall, schema: dict) -> None:
    """Mesmas regras que o Bedrock aplica antes de chamar a Lambda."""
    functions = {f["name"]: f for f in schema["functions"]}
    if call.function not in functions:
        raise SchemaError(f"função '{call.function}' não existe no action group")
    declared = functions[call.function]["parameters"]
    for name in call.params:
        if name not in declared:
            raise SchemaError(f"parâmetro '{name}' não declarado em {call.function}")
    for name, spec in declared.items():
        value = call.params.get(name)
        if spec.get("required") and value in (None, ""):
            raise SchemaError(f"parâmetro obrigatório '{name}' ausente em {call.function}")
        if value in (None, ""):
            continue
        try:
            if spec["type"] == "integer":
                int(str(value))
            elif spec["type"] == "number":
                float(str(value).replace(",", "."))
        except ValueError:
            raise SchemaError(f"'{name}' deveria ser {spec['type']}, recebeu '{value}'")


def build_event(call: ToolCall, schema: dict, session_id: str, input_text: str) -> dict:
    """Evento idêntico ao que o Bedrock Agents envia para a Lambda (valores sempre string)."""
    declared = {f["name"]: f for f in schema["functions"]}[call.function]["parameters"]
    return {
        "messageVersion": "1.0",
        "agent": {"name": "estoque-agente", "id": "LOCAL", "alias": "LOCAL", "version": "DRAFT"},
        "sessionId": session_id,
        "sessionAttributes": {},
        "promptSessionAttributes": {},
        "inputText": input_text,
        "actionGroup": schema["actionGroupName"],
        "function": call.function,
        "parameters": [
            {"name": k, "type": declared[k]["type"], "value": str(v)}
            for k, v in call.params.items() if v not in (None, "")
        ],
    }


def invoke_lambda(module, event: dict) -> str:
    # ida e volta em JSON, como acontece entre o Bedrock e a Lambda
    response = module.lambda_handler(json.loads(json.dumps(event)), None)
    response = json.loads(json.dumps(response))
    try:
        assert response["messageVersion"] == "1.0"
        assert response["response"]["function"] == event["function"]
        return response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    except (KeyError, AssertionError):
        raise RuntimeError(f"resposta da Lambda fora do formato do Bedrock: {response}")


# ------------------------------------------------------------------ "LLM" de regras

STOPWORDS = set("""
a o as os um uma uns umas e de da do das dos em no na nos nas para pra por com sem que se
qual quais quanto quantos quanta quantas tem temos ha existe existem estoque item itens produto
produtos unidade unidades un preco precos valor valores custa custam cada me mostre mostra mostrar
liste lista listar busque buscar procure procurar sobre informe informacoes info ver veja saber
quero gostaria pode poderia favor voce nosso nossa meu minha ainda agora hoje dia dias vai vao
acabar acaba previsao prever preveja demanda durar dura quando registre registrar registra venda
vendi vendemos vendas vendeu saida saidas entrada entradas chegaram chegou recebemos recebi
compramos comprei comprar reposicao repor retirada retirei retirar fornecedor cliente clientes
foram foi sairam saiu altere alterar mude mudar atualize atualizar troque trocar ajuste ajustar
defina definir novo nova minimo nome sku categoria total isso este esse esta essa dele dela mais
menos estao ele ela tudo todos todas baixo r$ reais real ok oi ola por favor obrigado ja
""".split())

SKU_RE = re.compile(r"\b([A-Za-z]{2,}-\d{2,})\b")
NUMBER = r"(\d+(?:[.,]\d+)?)"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def singular(word: str) -> str:
    if len(word) > 5 and word.endswith("res"):
        return word[:-2]  # monitores -> monitor
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]  # mouses -> mouse
    return word


def search_terms(message: str) -> List[str]:
    """Palavras que provavelmente identificam o item (ex.: 'mouses' -> ['mouse', 'mouses'])."""
    terms = []
    for word in re.findall(r"[\wÀ-ÿ]+", SKU_RE.sub(" ", message.lower())):
        if word.isdigit() or normalize(word) in STOPWORDS or len(word) < 3:
            continue
        for candidate in (singular(word), word):
            if candidate not in terms:
                terms.append(candidate)
    return terms


def parse_item_lines(observation: str) -> List[dict]:
    """Converte as linhas 'SKU | nome | categoria | qtd | preço | status' da Lambda."""
    items = []
    for line in observation.splitlines():
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) == 6:
            items.append({"sku": parts[0], "name": parts[1], "category": parts[2],
                          "stock": parts[3], "price": parts[4], "low": parts[5] != "ok"})
    return items


def format_items(items: List[dict]) -> str:
    return "\n".join(
        f"- {i['sku']} · {i['name']}: {i['stock']}, {i['price']}"
        + (" ⚠️ estoque baixo" if i["low"] else "")
        for i in items
    )


HELP = (
    "Posso ajudar com o estoque. Exemplos:\n"
    "- Quantos mouses temos? / Qual o preço do monitor?\n"
    "- Quais itens estão com estoque baixo?\n"
    "- Qual o valor total do estoque?\n"
    "- Cadastre o produto Fone Bluetooth JBL, preço 199,90, 30 unidades, categoria Áudio\n"
    "- Altere o preço do MS-002 para 99,90 / Mude o estoque mínimo do SSD para 10\n"
    "- Registre a venda de 2 headsets / Chegaram 50 cabos HDMI\n"
    "- Em quantos dias o SSD vai acabar?"
)


class RuleBasedLLM:
    """Faz o papel do LLM: decide a próxima ação a partir da mensagem e dos passos anteriores."""

    def decide(self, message: str, steps: List[Step], memory: dict) -> Decision:
        # Ferramenta falhou: explica ao usuário em vez de seguir (como um LLM faria)
        if steps and steps[-1].observation.startswith("Erro ao executar"):
            reason = steps[-1].observation.split(": ", 1)[-1]
            return FinalAnswer(f"Desculpe, não consegui concluir agora. {reason[0].upper() + reason[1:]}")
        intent = self.intent(message)
        return getattr(self, f"_{intent}")(message, steps, memory)

    # ---------------------------------------------------------- intenção

    @staticmethod
    def intent(message: str) -> str:
        t = normalize(message)
        has_qty = re.search(r"\d", SKU_RE.sub(" ", t)) is not None
        if re.search(r"\b(ajuda|help|o que voce (faz|sabe)|como funciona)\b", t) or \
                re.fullmatch(r"\s*(oi|ola|bom dia|boa tarde|boa noite)\W*", t):
            return "ajuda"
        if re.search(r"cadastr|adicion|inclu|novo item|nova item|crie|criar", t):
            return "cadastrar"
        if re.search(r"(alter|mud|atualiz|troc|ajust|defin)\w*\b.*(preco|minimo|nome)", t):
            return "atualizar"
        if re.search(r"previs|prever|preveja|quantos dias|vai acabar|acaba quando|quando .*acab|demanda|durar|dura ", t):
            return "prever"
        if has_qty and re.search(r"vend|saida|saiu|sairam|retir|entrada|cheg|receb|compr|repus|repor|reposicao|abastec|registr", t):
            return "movimentar"
        if re.search(r"estoque baixo|repor|reposicao|acabando|em falta|faltando|abaixo do minimo|precis\w* compr", t):
            return "baixo"
        if re.search(r"valor total|resumo|total do estoque|quantos itens|quanto vale", t):
            return "resumo"
        if re.search(r"quant|preco|custa|valor|\btem\b|temos|estoque|list|mostr|busc|procur|qual|quais|informac|dados", t):
            return "consultar"
        return "consultar" if search_terms(message) else "ajuda"

    # ---------------------------------------------------------- utilidades

    @staticmethod
    def _last_error(steps: List[Step]) -> Optional[str]:
        if steps and steps[-1].observation.startswith("Erro"):
            return f"Não consegui concluir a operação. {steps[-1].observation}"
        return None

    def _resolve_sku(self, message: str, steps: List[Step], memory: dict) -> Union[str, Decision]:
        """Descobre o SKU: direto da mensagem, de uma busca anterior ou da memória da sessão.
        Se ainda não sabe, devolve uma chamada a consultar_estoque (como um LLM faria)."""
        match = SKU_RE.search(message)
        if match:
            return match.group(1).upper()

        lookups = [s for s in steps if s.call.function == "consultar_estoque"]
        tried = [s.call.params.get("termo") for s in lookups]
        if lookups and not lookups[-1].observation.startswith("Nenhum"):
            found = parse_item_lines(lookups[-1].observation)
            if len(found) == 1:
                return found[0]["sku"]
            if len(found) > 1:
                return FinalAnswer("Encontrei mais de um item. Qual deles? Informe o SKU:\n" + format_items(found))

        remaining = [t for t in search_terms(message) if t not in tried]
        if remaining:
            return ToolCall("consultar_estoque", {"termo": remaining[0]},
                            f"Preciso do SKU; vou buscar itens com '{remaining[0]}'.")
        if not tried and memory.get("last_sku"):
            return memory["last_sku"]
        if tried:
            return FinalAnswer(f"Não encontrei nenhum item com '{tried[0]}'. Pode informar o SKU?")
        return FinalAnswer("De qual item você está falando? Informe o nome ou o SKU.")

    # ---------------------------------------------------------- intenções

    def _ajuda(self, message, steps, memory):
        return FinalAnswer(HELP)

    def _baixo(self, message, steps, memory):
        if not steps:
            return ToolCall("itens_estoque_baixo", {}, "Pergunta sobre reposição: listar itens abaixo do mínimo.")
        items = parse_item_lines(steps[-1].observation)
        if not items:
            return FinalAnswer(steps[-1].observation)
        return FinalAnswer(f"{len(items)} item(ns) precisam de reposição:\n" + format_items(items))

    def _resumo(self, message, steps, memory):
        if not steps:
            return ToolCall("resumo_estoque", {}, "Pergunta sobre totais: usar o resumo do estoque.")
        return FinalAnswer(steps[-1].observation)

    def _consultar(self, message, steps, memory):
        if steps:
            last = steps[-1]
            if last.observation.startswith("Nenhum item"):
                tried = [s.call.params.get("termo") for s in steps]
                remaining = [t for t in search_terms(message) if t not in tried]
                if remaining:
                    return ToolCall("consultar_estoque", {"termo": remaining[0]},
                                    f"Nada com '{tried[-1]}'; tentar '{remaining[0]}'.")
                return FinalAnswer(f"Não encontrei nenhum item com '{tried[0]}'.")
            items = parse_item_lines(last.observation)
            if not items:
                return FinalAnswer(last.observation)
            if len(items) == 1:
                memory["last_sku"] = items[0]["sku"]
            return FinalAnswer(f"Encontrei {len(items)} item(ns):\n" + format_items(items))

        terms = search_terms(message)
        wants_all = re.search(r"\btod[oa]s\b|\blist", normalize(message))
        if not terms and not wants_all and memory.get("last_sku"):
            sku = memory["last_sku"]
            return ToolCall("consultar_estoque", {"termo": sku}, f"Pergunta sobre o item da conversa ({sku}).")
        if not terms or wants_all:
            return ToolCall("consultar_estoque", {}, "Listar todos os itens.")
        return ToolCall("consultar_estoque", {"termo": terms[0]}, f"Buscar itens com '{terms[0]}'.")

    def _cadastrar(self, message, steps, memory):
        if steps:
            created = re.search(r"código ([A-Z0-9-]+)", steps[-1].observation)
            if created:
                memory["last_sku"] = created.group(1)
            return FinalAnswer(self._last_error(steps) or steps[-1].observation)

        def find(pattern):
            m = re.search(pattern, message, re.IGNORECASE)
            return m.group(1).strip() if m else None

        # nome: 'nome "X"' / 'nome X' / ou o texto logo após "cadastre o produto ..."
        name_after_verb = (
            r"(?:cadastr\w*|adicion\w*|inclu\w*|crie|criar)\s+(?:(?:o|a|um|uma)\s+)?(?:(?:novo|nova)\s+)?"
            r"(?:(?:item|produto)\s+)?(?:chamad[oa]\s+)?\"?([^\",;\n]+?)\"?\s*(?:,|;|$|\s+(?:com|por|pre[çc]o|R\$))"
        )
        params = {
            "nome": find(r'\bnome\s*[:=]?\s*"([^"]+)"') or find(r"\bnome\s*[:=]?\s*([^,;\n]+)") or find(name_after_verb),
            "preco": find(r"(?:pre[çc]o\s*(?:de|:|=)?\s*(?:R\$)?|R\$)\s*" + NUMBER),
            "quantidade": find(r"\bquantidade\s*(?:de|:|=)?\s*(\d+)") or find(r"\b(\d+)\s*(?:unidades|un\b|pe[çc]as)"),
            "categoria": find(r'\bcategoria\s*[:=]?\s*"?([^",;\n]+)"?'),
            "estoque_minimo": find(r"\bm[íi]nimo\s*(?:de|:|=)?\s*(\d+)"),
        }
        missing = [label for key, label in (("nome", "nome"), ("preco", "preço")) if not params[key]]
        if missing:
            return FinalAnswer(
                f"Para cadastrar preciso de: {' e '.join(missing)}. O código (SKU) é gerado automaticamente. Exemplo:\n"
                "Cadastre o produto Fone Bluetooth JBL, preço 199,90, 30 unidades, categoria Áudio"
            )
        return ToolCall("cadastrar_item", {k: v for k, v in params.items() if v},
                        "Pedido de cadastro com nome e preço; o sistema gera o código.")

    def _atualizar(self, message, steps, memory):
        if steps and steps[-1].call.function == "atualizar_item":
            return FinalAnswer(self._last_error(steps) or steps[-1].observation)
        sku = self._resolve_sku(message, steps, memory)
        if not isinstance(sku, str):
            return sku
        t = message
        params = {"sku": sku}
        m = re.search(r"pre[çc]o.*?(?:para|=|:|por)\s*(?:R\$)?\s*" + NUMBER, t, re.IGNORECASE)
        if m:
            params["preco"] = m.group(1)
        m = re.search(r"m[íi]nimo.*?(?:para|=|:|de)\s*(\d+)", t, re.IGNORECASE)
        if m:
            params["estoque_minimo"] = m.group(1)
        m = re.search(r'\bnome\b.*?para\s*"?([^"\n]+)"?', t, re.IGNORECASE)
        if m:
            params["nome"] = m.group(1).strip()
        if len(params) == 1:
            return FinalAnswer('O que devo alterar? Ex.: "altere o preço do MS-002 para 99,90".')
        memory["last_sku"] = sku
        return ToolCall("atualizar_item", params, f"Atualizar {', '.join(list(params)[1:])} do item {sku}.")

    def _movimentar(self, message, steps, memory):
        if steps and steps[-1].call.function == "registrar_movimentacao":
            return FinalAnswer(self._last_error(steps) or steps[-1].observation)
        sku = self._resolve_sku(message, steps, memory)
        if not isinstance(sku, str):
            return sku
        t = normalize(message)
        tipo = "entrada" if re.search(r"entrada|cheg|receb|compr|repus|repor|reposicao|abastec", t) else "saida"
        quantity = re.search(r"\b(\d+)\b", SKU_RE.sub(" ", t)).group(1)
        memory["last_sku"] = sku
        return ToolCall("registrar_movimentacao",
                        {"sku": sku, "tipo": tipo, "quantidade": quantity,
                         "observacao": "Registrado pelo assistente (simulado)"},
                        f"Registrar {tipo} de {quantity} un. do item {sku}.")

    def _prever(self, message, steps, memory):
        if steps and steps[-1].call.function == "prever_demanda":
            return FinalAnswer(self._last_error(steps) or steps[-1].observation)
        sku = self._resolve_sku(message, steps, memory)
        if not isinstance(sku, str):
            return sku
        memory["last_sku"] = sku
        return ToolCall("prever_demanda", {"sku": sku}, f"Pedir ao modelo de previsão os dados do item {sku}.")


# ------------------------------------------------------------------ orquestração

_sessions: Dict[str, dict] = {}  # memória por sessão (o Bedrock também guarda o histórico da sessão)


def probe() -> dict:
    if FAILURE_FLAG.exists():
        return {"status": "down", "message": "Lambda de ferramentas fora do ar (falha simulada)"}
    try:
        schema = load_schema()
        tools = load_lambda().TOOLS
    except Exception:
        return {"status": "down", "message": "Não foi possível carregar a Lambda ou o action group"}
    if {f["name"] for f in schema["functions"]} != set(tools):
        return {"status": "down", "message": "action_group.json e Lambda não combinam"}
    return {"status": "simulated", "message": f"Agente simulado com {len(tools)} ferramentas"}


def run(message: str, session_id: Optional[str] = None, llm: Optional[RuleBasedLLM] = None) -> dict:
    if FAILURE_FLAG.exists():
        raise ServiceUnavailable("agent", "A Lambda de ferramentas do assistente não respondeu (falha simulada).")
    os.environ.setdefault("API_BASE_URL", config.LOCAL_API_URL)
    session_id = session_id or uuid.uuid4().hex
    memory = _sessions.setdefault(session_id, {})
    schema = load_schema()
    lambda_module = load_lambda()
    llm = llm or RuleBasedLLM()

    steps: List[Step] = []
    tools_used = []
    for _ in range(MAX_STEPS):
        decision = llm.decide(message, steps, memory)
        if isinstance(decision, FinalAnswer):
            return {"answer": decision.text, "session_id": session_id, "tools_used": tools_used}

        validate_call(decision, schema)
        event = build_event(decision, schema, session_id, message)
        observation = invoke_lambda(lambda_module, event)
        steps.append(Step(decision, observation))
        tools_used.append({
            "function": decision.function,
            "parameters": {p["name"]: p["value"] for p in event["parameters"]},
            "rationale": decision.rationale,
            "result": observation,
        })

    return {"answer": "Não consegui concluir em poucos passos. Tente reformular a pergunta.",
            "session_id": session_id, "tools_used": tools_used}
