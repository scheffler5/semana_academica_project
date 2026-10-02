"""Proteções do assistente de IA (camada de SOFTWARE, independente da infraestrutura).

Camadas de defesa, da entrada à saída:

  1. ENTRADA (este arquivo): antes de qualquer LLM ou ferramenta, a mensagem é verificada.
     Bloqueia SQL injection, prompt injection ("ignore suas instruções"), pedidos de
     segredos (.env, senhas, chaves), comandos de sistema e pedidos sobre infraestrutura.
  2. FERRAMENTAS (lambda_function.py): cada parâmetro é validado (formato do SKU, tamanho,
     caracteres permitidos, limites de quantidade/preço) e cada ferramenta tem um nível de
     permissão (leitura/escrita). O agente NÃO tem ferramenta de apagar nem acesso a banco,
     AWS ou arquivos: só chama a API do estoque.
  3. API: o banco é acessado só pelo ORM com parâmetros (nunca SQL montado com texto),
     então mesmo um texto malicioso vira um valor comum, nunca um comando.
  4. SAÍDA (este arquivo): a resposta do agente passa por um filtro que remove qualquer coisa
     com cara de segredo (chaves AWS, URLs de banco, IPs privados) antes de chegar à tela.

Vale para os dois modos (simulado e Bedrock). No Bedrock, recomenda-se também ligar um
Bedrock Guardrail (filtro de "prompt attack") — ver docs/FALHAS_E_SEGURANCA.md.
"""
import logging
import re
import unicodedata
from typing import Optional

log = logging.getLogger("estoque")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


# categoria -> padrões (aplicados no texto em minúsculas e sem acentos)
BLOCKED = {
    "sql_injection": [
        r"\b(drop|truncate|alter)\s+(table|database|schema|user)\b",
        r"\bdelete\s+from\b", r"\binsert\s+into\b", r"\bupdate\s+\w+\s+set\b",
        r"\bunion\s+(all\s+)?select\b", r"\bselect\b[\s\S]{0,80}\bfrom\b",
        r"'\s*(or|and)\s*'?\w+'?\s*=\s*'?\w+", r";\s*--", r"--\s*$", r"/\*[\s\S]*\*/",
        r"\b(pg_sleep|pg_catalog|information_schema|xp_cmdshell|sqlite_master)\b",
        r"\b(exec|execute)\s*\(", r"\bsql\b",
    ],
    "prompt_injection": [
        r"\b(ignore|ignora|ignorar|esqueca|esquecer|desconsidere|desconsiderar)\b.{0,40}\b(instruc|regra|orientac|prompt|anterior)",
        r"\bignore (all |the )?(previous|prior|above)\b",
        r"\b(system prompt|prompt do sistema|prompt de sistema|suas instrucoes|your instructions)\b",
        r"\b(modo desenvolvedor|developer mode|jailbreak|modo deus|sem restric)",
        r"\b(finja|aja como|act as|pretend|voce agora e|you are now)\b",
    ],
    "secrets": [
        r"(^|[\s/])\.env\b", r"\bvariave(l|is) de ambiente\b", r"\benviron(ment)?\b",
        r"\bsenhas?\b", r"\bpassword", r"\bcredenciai?s?\b", r"\bsecret",
        r"\bapi[\s_-]?keys?\b", r"\bchaves? (de )?(api|acesso|secreta|privada|aws)\b", r"\baccess[\s_-]?key",
        r"\btoken\b", r"\bdatabase_url\b", r"\bstring de conexao\b", r"\bconnection string\b",
        r"\baws_\w+", r"\b(akia|asia)[0-9a-z]{16}\b", r"/etc/(passwd|shadow)", r"\bid_rsa\b", r"\.pem\b",
    ],
    "system_commands": [
        r"\b(rm\s+-rf|sudo|chmod|chown|curl|wget|bash|powershell|cmd\.exe|ssh|scp|eval|os\.system|subprocess)\b",
        r"\b(cat|ls|cd)\s+[/~.]", r"\$\(|`[^`]+`",
    ],
    "infrastructure": [
        r"\b(ec2|iam|vpc|security group|grupo de seguranca|bucket|s3|rds|aurora|cloudformation|"
        r"lambda|bedrock|sagemaker|instancias?|servidor(es)?|firewall|porta \d+|endereco ip|ip privado|"
        r"banco de dados|tabelas? do banco|schema|logs? do servidor)\b",
    ],
}

REFUSALS = {
    "sql_injection": "Não executo comandos de banco de dados. Posso consultar e alterar o estoque usando as ferramentas do sistema.",
    "prompt_injection": "Não posso mudar minhas instruções nem minhas regras de segurança.",
    "secrets": "Não tenho acesso a senhas, chaves, tokens ou configurações do sistema, e não posso ajudar com isso.",
    "system_commands": "Não executo comandos de sistema.",
    "infrastructure": "Não tenho acesso à infraestrutura (servidores, rede, banco, serviços da AWS). Só trabalho com produtos e movimentações do estoque.",
}

MAX_MESSAGE_CHARS = 500


def check_input(message: str) -> Optional[dict]:
    """Devolve None se a mensagem é segura; senão {"category", "answer"} com a recusa."""
    if len(message) > MAX_MESSAGE_CHARS:
        return {"category": "too_long",
                "answer": f"Mensagem muito longa. Escreva até {MAX_MESSAGE_CHARS} caracteres."}
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in message):
        return {"category": "control_chars", "answer": "A mensagem contém caracteres inválidos."}
    text = _normalize(message)
    for category, patterns in BLOCKED.items():
        if any(re.search(p, text) for p in patterns):
            log.warning("Guardrail bloqueou mensagem (categoria=%s)", category)  # não registra o conteúdo
            return {
                "category": category,
                "answer": f"🛡️ {REFUSALS[category]} Exemplos do que posso fazer: consultar quantidade e "
                          "preço, cadastrar e atualizar produtos, registrar entradas e saídas e prever demanda.",
            }
    return None


# ------------------------------------------------------------------ saída

REDACT = [
    re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),                                   # access key AWS
    re.compile(r"(?i)aws_(secret_access_key|session_token|access_key_id)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\b(postgres(ql)?(\+\w+)?|mysql|sqlite)://\S+"),             # URL de banco
    re.compile(r"(?i)\b(password|senha|db_password)\s*[=:]\s*\S+"),
    re.compile(r"\barn:aws:[\w:/.\-*]+"),                                         # ARNs (revelam conta)
    re.compile(r"\b(10\.\d{1,3}|192\.168|172\.(1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),  # IPs privados
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]


def redact(text: str) -> str:
    for pattern in REDACT:
        text = pattern.sub("[removido]", text)
    return text
