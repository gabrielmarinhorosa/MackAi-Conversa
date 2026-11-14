# Contrato consumido do Módulo 1

Fonte: guia de integração do Módulo 1, release 0.5.0 (Identidade 0.4.0, Projetos 0.5.0). Se o Módulo 1
mudar estas rotas, `assistente_conversacional/modulo1.py`, o Módulo 1 falso em `dev/modulo1_falso.py`
e o falso dos testes em `tests/conftest.py` precisam mudar junto.

| Variável | Valor publicado |
| --- | --- |
| `MOD1_AUTH_URL` | `https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io` |
| `MOD1_PROJECTS_URL` | `https://mod1-projects.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io` |
| `MOD1_JWT_ISSUER` | igual a `MOD1_AUTH_URL` |
| `MOD1_JWT_AUDIENCE` | `engenharia-software-api` |
| `MOD1_JWKS_URL` | `MOD1_AUTH_URL` + `/.well-known/jwks.json` |

## Chamadas do backend (timeout de 5 s)

| Rota | Uso | Tratamento |
| --- | --- | --- |
| `GET /.well-known/jwks.json` | Chaves públicas RS256 | Cache de 5 min. `kid` desconhecido recarrega no máximo a cada 30 s |
| `GET /auth/me` | Sessão e conta ativas | 200 com `id` == `sub` e `is_active` true. 401 vira 401. Outros status ou falha de rede viram 503 `MODULO1_INDISPONIVEL`. Cache de 60 s por `jti` |
| `GET /projects/{id}/access/v2` | Permissões atuais no projeto | Exige `project:read` em `permissions`. 403 e 404 viram 404 `PROJETO_NAO_ENCONTRADO`. Só o acesso concedido fica em cache (60 s) |

O JWT precisa de `sub`, `iss`, `aud`, `iat`, `exp` e `jti`, cabeçalho `alg: RS256`, `typ: JWT` e
`kid`. A tolerância de relógio é de 5 s.

## Chamadas do navegador (front do Módulo 7)

Dependem de o Módulo 1 liberar a origem do front no CORS.

| Rota | Uso |
| --- | --- |
| `POST /auth/token` | Login: formulário `username` (e-mail) e `password`. Pode devolver o desafio de MFA |
| `POST /auth/mfa/verify` | `{challenge_token, code}` quando a conta tem MFA |
| `POST /auth/refresh` | `{refresh_token}` quando a API responde 401 |
| `POST /auth/logout` | Corpo `{}`. Encerra a sessão no Módulo 1 |
| `GET /auth/me` | Nome exibido na barra lateral |
| `GET /projects?limit=100` | Projetos do seletor |
