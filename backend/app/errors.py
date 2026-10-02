"""Tratamento de erros padronizado.

Toda resposta de erro tem o MESMO formato, para o site mostrar uma mensagem clara
dizendo QUAL serviço falhou (ótimo para demonstrar falhas em aula):

    {"error": "service_unavailable", "service": "s3",
     "message": "Armazenamento (Amazon S3) indisponível...", "request_id": "a1b2c3d4"}

Segurança: detalhes técnicos (exceções, hosts, ARNs, IDs de conta) vão SÓ para o log do
servidor, junto com o request_id. O cliente nunca recebe texto de exceção.
"""
import logging
import uuid
from contextvars import ContextVar

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("estoque")
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

SERVICES = {
    "s3": "Armazenamento (Amazon S3)",
    "agent": "Assistente de IA (Amazon Bedrock + Lambda)",
}


class ServiceUnavailable(Exception):
    """Um serviço de que a API depende está fora do ar ou recusou o acesso."""

    def __init__(self, service: str, message: str = ""):
        self.service = service
        self.message = message or f"{SERVICES[service]} está indisponível no momento."
        super().__init__(self.message)


def aws_error_message(service: str, exc: Exception) -> str:
    """Traduz erros do boto3 em mensagens seguras (sem ARN, conta ou endpoint)."""
    name = SERVICES[service]
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("AccessDenied", "AccessDeniedException", "403", "UnauthorizedOperation"):
            return f"{name}: a aplicação não tem permissão (verifique a IAM Role da EC2)."
        if code in ("NoSuchBucket", "ResourceNotFoundException", "ValidationException", "404"):
            return f"{name}: recurso não encontrado (verifique a configuração no .env)."
        if code in ("ThrottlingException", "SlowDown", "TooManyRequestsException"):
            return f"{name}: muitas requisições, tente novamente em instantes."
    return f"{name} não respondeu. O serviço pode estar fora do ar."


def _body(error: str, message: str, service: str = None) -> dict:
    body = {"error": error, "message": message, "request_id": request_id_var.get()}
    if service:
        body["service"] = service
    return body


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        rid = uuid.uuid4().hex[:8]
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(ServiceUnavailable)
    async def service_unavailable(request: Request, exc: ServiceUnavailable):
        log.warning("[%s] %s indisponível: %s", request_id_var.get(), exc.service, exc.__cause__ or exc.message)
        return JSONResponse(_body("service_unavailable", exc.message, exc.service), status_code=503)

    @app.exception_handler(BotoCoreError)
    @app.exception_handler(ClientError)
    async def aws_error(request: Request, exc: Exception):
        log.error("[%s] erro AWS não tratado: %s", request_id_var.get(), exc)
        return JSONResponse(_body("aws_error", "Um serviço da AWS falhou. Tente novamente."), status_code=503)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        problems = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
            problems.append(f"{field}: {err['msg']}" if field else err["msg"])
        return JSONResponse(_body("validation_error", "Dados inválidos — " + "; ".join(problems)), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("[%s] erro inesperado", request_id_var.get())
        return JSONResponse(
            _body("internal_error", f"Erro interno. Informe o código {request_id_var.get()} ao administrador."),
            status_code=500,
        )
