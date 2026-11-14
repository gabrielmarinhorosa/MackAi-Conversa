"""Erros da API no formato comum aos serviços: {"detail": "...", "code": "..."} (US 50)."""


class ErroApi(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status = status
        self.code = code
        self.detail = detail


def nao_autenticado() -> ErroApi:
    return ErroApi(401, "NAO_AUTENTICADO", "Token ausente, inválido ou expirado. Crie outro em POST /api/sessions.")


def conversa_nao_encontrada() -> ErroApi:
    return ErroApi(404, "CONVERSA_NAO_ENCONTRADA", "Conversa não encontrada.")


def mensagem_nao_encontrada() -> ErroApi:
    return ErroApi(404, "MENSAGEM_NAO_ENCONTRADA", "Mensagem não encontrada.")


def muitas_requisicoes() -> ErroApi:
    return ErroApi(429, "RATE_LIMITED", "Muitas requisições seguidas. Aguarde um minuto.")


def orquestrador_indisponivel() -> ErroApi:
    return ErroApi(503, "ORQUESTRADOR_INDISPONIVEL", "O assistente está indisponível no momento. Tente novamente em instantes.")
