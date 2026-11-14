"""Erros da API no formato comum aos serviços: {"detail": "...", "code": "..."} (US 50)."""


class ErroApi(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status = status
        self.code = code
        self.detail = detail


def nao_autenticado() -> ErroApi:
    return ErroApi(401, "NAO_AUTENTICADO",
                   "Token ausente, inválido, expirado ou de sessão encerrada. Faça login no Módulo 1 (POST /auth/token).")


def conversa_nao_encontrada() -> ErroApi:
    return ErroApi(404, "CONVERSA_NAO_ENCONTRADA", "Conversa não encontrada.")


def projeto_nao_encontrado() -> ErroApi:
    return ErroApi(404, "PROJETO_NAO_ENCONTRADO", "Projeto não encontrado ou sem acesso para esta conta no Módulo 1.")


def mensagem_nao_encontrada() -> ErroApi:
    return ErroApi(404, "MENSAGEM_NAO_ENCONTRADA", "Mensagem não encontrada.")


def muitas_requisicoes() -> ErroApi:
    return ErroApi(429, "RATE_LIMITED", "Muitas requisições seguidas. Aguarde um minuto.")


def orquestrador_indisponivel() -> ErroApi:
    return ErroApi(503, "ORQUESTRADOR_INDISPONIVEL", "O assistente está indisponível no momento. Tente novamente em instantes.")


def modulo1_indisponivel() -> ErroApi:
    return ErroApi(503, "MODULO1_INDISPONIVEL", "O serviço de identidade (Módulo 1) não respondeu. Tente novamente em instantes.")
