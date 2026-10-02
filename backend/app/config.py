"""Configurações lidas de variáveis de ambiente (arquivo backend/.env na EC2)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BASE_DIR = Path(__file__).resolve().parent.parent  # pasta backend/

# S3: bucket PRIVADO onde ficam as fotos E os dados (items.json/movements.json).
# É o ÚNICO armazenamento do sistema — não existe banco de dados separado.
# S3_ENDPOINT_URL só é usado localmente (emulador de S3); na AWS fica vazio.
# Credenciais: NUNCA no código ou no .env da EC2 — na AWS vêm da IAM Role da instância.
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Agente de IA:
#   - "bedrock": Bedrock Agent de verdade (IDs do console do Bedrock)
#   - "simulado": LLM falso baseado em regras que usa as MESMAS ferramentas (Lambda) localmente
BEDROCK_AGENT_ID = os.getenv("BEDROCK_AGENT_ID", "")
BEDROCK_AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID", "")
AGENT_MODE = os.getenv("AGENT_MODE") or ("bedrock" if BEDROCK_AGENT_ID else "simulado")

# No modo simulado, a Lambda roda localmente e chama a API neste endereço
# (na AWS ela usa o IP privado da EC2)
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://127.0.0.1:8000")

# Popular o estoque com itens de exemplo na primeira execução
SEED_DATA = os.getenv("SEED_DATA", "true").lower() == "true"
