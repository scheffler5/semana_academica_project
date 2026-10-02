"""Assistente de IA do estoque. Dois modos (variável AGENT_MODE):

- "bedrock":  Amazon Bedrock Agents. O LLM decide quais ferramentas usar e o Bedrock
              invoca a função Lambda, que consulta esta API pela rede privada da VPC.
- "simulado": desenvolvimento local. Um "LLM" de regras (agent_local.py) faz o papel do
              Bedrock e chama o MESMO código da Lambda com o MESMO formato de evento.

Nos dois casos a resposta inclui `tools_used`: as ferramentas chamadas e o que retornaram.
"""
import logging
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from . import agent_local, config, guardrails
from .errors import ServiceUnavailable, aws_error_message

log = logging.getLogger("estoque")

_client = (
    boto3.client("bedrock-agent-runtime", region_name=config.AWS_REGION,
                 config=Config(connect_timeout=3, read_timeout=90, retries={"max_attempts": 1}))
    if config.AGENT_MODE == "bedrock" and config.BEDROCK_AGENT_ID and config.BEDROCK_AGENT_ALIAS_ID
    else None
)


def mode() -> str:
    return config.AGENT_MODE


def enabled() -> bool:
    return config.AGENT_MODE == "simulado" or _client is not None


def ask(message: str, session_id: str = None) -> dict:
    if not enabled():
        raise ServiceUnavailable("agent", "Assistente não configurado (defina BEDROCK_AGENT_ID e BEDROCK_AGENT_ALIAS_ID).")

    # Camada 1: a mensagem nem chega ao LLM/ferramentas se for maliciosa
    blocked = guardrails.check_input(message)
    if blocked:
        return {"answer": blocked["answer"], "session_id": session_id or uuid.uuid4().hex,
                "tools_used": [], "mode": config.AGENT_MODE, "blocked": blocked["category"]}

    if config.AGENT_MODE == "simulado":
        result = agent_local.run(message, session_id)
    else:
        try:
            result = _ask_bedrock(message, session_id)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailable("agent", aws_error_message("agent", exc)) from exc
    # Camada 4: nada com cara de segredo sai para a tela, nem na resposta nem no rastro das ferramentas
    result["answer"] = guardrails.redact(result["answer"])
    for tool in result["tools_used"]:
        if tool.get("result"):
            tool["result"] = guardrails.redact(tool["result"])
    result["mode"] = config.AGENT_MODE
    result["blocked"] = None
    return result


def probe() -> dict:
    if config.AGENT_MODE == "simulado":
        return agent_local.probe()
    if _client is None:
        return {"status": "disabled", "message": "BEDROCK_AGENT_ID não definido"}
    # Não chamamos o agente no health (custaria tokens); só confirmamos a configuração
    return {"status": "ok", "message": "Bedrock Agent configurado"}


def _ask_bedrock(message: str, session_id: str = None) -> dict:
    session_id = session_id or uuid.uuid4().hex
    response = _client.invoke_agent(
        agentId=config.BEDROCK_AGENT_ID,
        agentAliasId=config.BEDROCK_AGENT_ALIAS_ID,
        sessionId=session_id,  # mesma sessão = o agente lembra da conversa
        inputText=message,
        enableTrace=True,      # devolve o "raciocínio" e as chamadas de ferramenta
    )
    # A resposta chega em partes (streaming): texto ("chunk") e rastros ("trace")
    answer = ""
    tools_used = []
    rationale = ""
    for event in response["completion"]:
        if "chunk" in event:
            answer += event["chunk"]["bytes"].decode("utf-8")
        trace = event.get("trace", {}).get("trace", {}).get("orchestrationTrace", {})
        rationale = trace.get("rationale", {}).get("text", rationale)
        call = trace.get("invocationInput", {}).get("actionGroupInvocationInput")
        if call:
            tools_used.append({
                "function": call.get("function"),
                "parameters": {p["name"]: p["value"] for p in call.get("parameters", [])},
                "rationale": rationale,
                "result": None,
            })
            rationale = ""
        output = trace.get("observation", {}).get("actionGroupInvocationOutput")
        if output and tools_used:
            tools_used[-1]["result"] = output.get("text")
    return {"answer": answer.strip(), "session_id": session_id, "tools_used": tools_used}
