"""Integração com o Módulo 1 (identidade e projetos).

Segue o guia do Módulo 1 (docs/integracao-outros-modulos.md, release 0.5.0):

1. O JWT é validado aqui: RS256, `kid` do JWKS configurado, issuer e audiência configurados.
2. Assinatura válida não basta: `GET /auth/me` com o mesmo Bearer confirma que a sessão e a conta
   continuam ativas e que `id` == `sub`.
3. Papel no JWT não dá acesso a projeto: `GET /projects/{id}/access/v2` diz as permissões atuais.

As respostas de 2 e 3 ficam em cache por MOD1_CACHE_S segundos para não chamar o Módulo 1 em
toda requisição.
"""

import logging
import time
from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .erros import modulo1_indisponivel, nao_autenticado, projeto_nao_encontrado

log = logging.getLogger("mackai.conversas")

_bearer = HTTPBearer(auto_error=False, description="`access_token` obtido em `POST /auth/token` do Módulo 1.")

JWKS_VALIDADE_S = 300  # mesmo cache de 5 minutos do exemplo do Módulo 1
JWKS_RECARGA_MINIMA_S = 30  # kid desconhecido não pode virar uma chamada ao JWKS por requisição
CACHE_MAXIMO = 1000


@dataclass(frozen=True)
class Sessao:
    usuario: UUID  # `sub` do JWT do Módulo 1: dono das conversas
    token: str  # repassado ao Módulo 1 para consultar o acesso aos projetos
    jti: str


class ClienteModulo1:
    def __init__(self, auth_url: str, projects_url: str, jwks_url: str, issuer: str, audience: str,
                 timeout_s: float, cache_s: float, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(timeout=timeout_s, transport=transport)
        self._auth_url = auth_url.rstrip("/")
        self._projects_url = projects_url.rstrip("/")
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._cache_s = cache_s
        self._chaves: dict[str, jwt.PyJWK] = {}
        self._chaves_em = float("-inf")
        self._sessoes: dict[str, tuple[float, UUID]] = {}  # jti -> (vale até, usuário)
        self._acessos: dict[tuple[str, UUID], tuple[float, list[str]]] = {}  # (jti, projeto) -> permissões

    async def fechar(self) -> None:
        await self._http.aclose()

    # ---------- Token ----------

    async def validar(self, token: str) -> tuple[UUID, str]:
        """Devolve (usuário, jti). Token inválido ou sessão encerrada -> 401."""
        try:
            cabecalho = jwt.get_unverified_header(token)
            kid = cabecalho.get("kid")
            if cabecalho.get("alg") != "RS256" or cabecalho.get("typ") != "JWT" or not isinstance(kid, str) or not kid:
                raise ValueError("cabeçalho inválido")
            chave = await self._chave(kid)
            if chave is None:
                raise ValueError("kid desconhecido")
            claims = jwt.decode(
                token, chave, algorithms=["RS256"], issuer=self._issuer, audience=self._audience, leeway=5,
                options={"require": ["sub", "iss", "aud", "iat", "exp", "jti"], "strict_aud": True},
            )
            usuario, jti = UUID(claims["sub"]), str(UUID(claims["jti"]))
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
            raise nao_autenticado()

        agora = time.monotonic()
        em_cache = self._sessoes.get(jti)
        if em_cache and em_cache[0] > agora:
            return em_cache[1], jti

        corpo = await self._get(f"{self._auth_url}/auth/me", token)
        if corpo is None or str(corpo.get("id")) != str(usuario) or corpo.get("is_active") is not True:
            raise nao_autenticado()
        vale_ate = min(agora + self._cache_s, agora + max(0, claims["exp"] - time.time()))
        self._guardar(self._sessoes, jti, (vale_ate, usuario))
        return usuario, jti

    async def _chave(self, kid: str) -> jwt.PyJWK | None:
        agora = time.monotonic()
        vencido = agora - self._chaves_em > JWKS_VALIDADE_S
        if vencido or (kid not in self._chaves and agora - self._chaves_em > JWKS_RECARGA_MINIMA_S):
            try:
                resposta = await self._http.get(self._jwks_url)
                resposta.raise_for_status()
                self._chaves = {k["kid"]: jwt.PyJWK(k, algorithm="RS256")
                                for k in resposta.json()["keys"] if k.get("alg", "RS256") == "RS256"}
                self._chaves_em = agora
            except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError) as erro:
                log.warning("JWKS do Módulo 1 indisponível: %r", erro)
                if not self._chaves:
                    raise modulo1_indisponivel()
        return self._chaves.get(kid)

    # ---------- Projetos ----------

    async def exigir_acesso(self, sessao: Sessao, projeto: UUID) -> None:
        """Exige a permissão `project:read` no projeto. Sem acesso ou inexistente -> 404."""
        agora = time.monotonic()
        em_cache = self._acessos.get((sessao.jti, projeto))
        if em_cache and em_cache[0] > agora:
            permissoes = em_cache[1]
        else:
            corpo = await self._get(f"{self._projects_url}/projects/{projeto}/access/v2", sessao.token,
                                    sem_acesso=(403, 404))
            permissoes = None if corpo is None else list(corpo.get("permissions") or [])
        if not permissoes or "project:read" not in permissoes:
            raise projeto_nao_encontrado()  # negação não fica em cache: quem aceita um convite entra na hora
        self._guardar(self._acessos, (sessao.jti, projeto), (agora + self._cache_s, permissoes))

    # ---------- HTTP ----------

    async def _get(self, url: str, token: str, sem_acesso: tuple[int, ...] = ()) -> dict | None:
        """200 -> corpo; status em `sem_acesso` -> None; 401 -> 401; o resto -> 503."""
        try:
            resposta = await self._http.get(url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as erro:
            log.warning("Módulo 1 não respondeu em %s: %r", url, erro)
            raise modulo1_indisponivel()
        if resposta.status_code == 401:
            raise nao_autenticado()
        if resposta.status_code in sem_acesso:
            return None
        if resposta.status_code != 200:
            log.warning("Módulo 1 respondeu %d em %s", resposta.status_code, url)
            raise modulo1_indisponivel()
        try:
            corpo = resposta.json()
        except ValueError:
            raise modulo1_indisponivel()
        if not isinstance(corpo, dict):
            raise modulo1_indisponivel()
        return corpo

    @staticmethod
    def _guardar(cache: dict, chave, valor) -> None:
        if len(cache) >= CACHE_MAXIMO:
            agora = time.monotonic()
            for k in [k for k, v in cache.items() if v[0] <= agora]:
                del cache[k]
            if len(cache) >= CACHE_MAXIMO:
                cache.clear()
        cache[chave] = valor


async def sessao_atual(request: Request,
                       credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Sessao:
    """Dependência das rotas protegidas: valida o Bearer do Módulo 1."""
    if credenciais is None:
        raise nao_autenticado()
    usuario, jti = await request.app.state.modulo1.validar(credenciais.credentials)
    return Sessao(usuario, credenciais.credentials, jti)


async def exigir_acesso(request: Request, sessao: Sessao, projeto: UUID | None) -> None:
    """Sem projeto não há o que conferir (conversas gerais do usuário)."""
    if projeto is not None:
        await request.app.state.modulo1.exigir_acesso(sessao, projeto)
