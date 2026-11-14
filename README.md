# mackai-conversas

Porta de entrada pública do **MackAI** (Módulo 7). O serviço entrega o front e identifica cada pessoa
pela conta do **Módulo 1**. Ele guarda conversas, mensagens e feedback por pessoa e por projeto no
PostgreSQL e repassa as perguntas ao `mackai-orquestrador`.

**Não faz:** login próprio, montar prompt, chamar o Gemini, buscar trechos nem acessar o `busca_db`.

```text
                    Módulo 1 (Identidade e Projetos)
                      ▲ login, refresh        ▲ JWKS, /auth/me, /projects/{id}/access/v2
                      │                       │
Navegador ──HTTPS──► mackai-conversas ──► conversas_db (PostgreSQL)
Módulos 4, 5, 6, 8 ─►     │ POST /v1/answers (timeout de 60 s)
                          ▼
                    mackai-orquestrador ──► mackai-busca
```

Stack: Python 3.12, FastAPI, Pydantic v2, asyncpg (SQL puro, sem ORM), httpx e PyJWT. Front em React + Vite.

**Outros módulos:** leiam [docs/integracao-outros-modulos.md](docs/integracao-outros-modulos.md).

## Rodar localmente

### Com Docker (PostgreSQL + Orquestrador falso + Módulo 1 falso + serviço)

```bash
docker compose up --build
```

Abra http://localhost:8000 e entre com qualquer e-mail e senha: o Módulo 1 falso aceita todos. A
documentação interativa fica em http://localhost:8000/docs.

### Sem Docker

Pré-requisitos: Python 3.12+, Node 22 e um PostgreSQL com o banco `conversas_db`.

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # já aponta para o Módulo 1 falso
```

Em quatro terminais:

```bash
uvicorn dev.orquestrador_falso:app --port 8001      # ou o mackai-orquestrador real
uvicorn dev.modulo1_falso:app --port 8002           # ou apague MOD1_* do .env para usar o Módulo 1 real
uvicorn assistente_conversacional.main:app --port 8000 --reload
cd frontend && npm ci && npm run dev                # http://localhost:5173 (proxy de /api para 8000)
```

O orquestrador falso responde no mesmo contrato do real. Para testar a interface: uma pergunta com
"geral" volta sem fontes (`grounded=false`), "falha" gera 503 e "lento" estoura o timeout.

O Módulo 1 falso aceita qualquer e-mail e senha e oferece dois projetos. E-mail começando com `mfa`
pede o código `123456`. A chave RSA muda a cada início, então é preciso entrar de novo.

Para usar o Módulo 1 real no front local, apague `frontend/.env.development` e peça ao Módulo 1 para
liberar `http://localhost:5173` no CORS.

### Testes

Os testes usam um PostgreSQL de verdade (as tabelas são truncadas a cada teste) e um Orquestrador e
um Módulo 1 falsos (`httpx.MockTransport`, com chave RSA própria).

```bash
TEST_DATABASE_URL=postgresql://mackai:mackai@localhost:5432/conversas_test pytest
```

## API pública

Contrato completo: [contracts/mackai-conversas.openapi.json](contracts/mackai-conversas.openapi.json)
(gerado por `python scripts/exportar_openapi.py`) e coleção do Postman em [postman/](postman/).

Todas as rotas `/api/*` exigem `Authorization: Bearer <access_token do Módulo 1>`, exceto `/api/health`.

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/health` | Estado agregado do Orquestrador e da Busca (sem token) |
| `GET` | `/api/conversations?project_id=` | Conversas da pessoa no projeto (ou as gerais) que têm mensagens, da mais recente para a mais antiga |
| `POST` | `/api/conversations` | Cria uma conversa vazia (201). Corpo opcional `{"project_id": "..."}` |
| `GET` | `/api/conversations/{id}` | Conversa com as mensagens |
| `POST` | `/api/chat` | Envia a pergunta e devolve a resposta do assistente |
| `POST` | `/api/feedback` | Vota `up`, `down` ou `null` (remove) numa resposta |
| `GET` | `/api/projects/{project_id}/metrics` | Números de uso do projeto, somando todas as pessoas |
| `GET` | `/health` | Sonda de vida e prontidão (`{"status": "ok"}`) |

### Autenticação e projetos

O serviço não emite token. Em cada chamada ele:

1. valida o JWT do Módulo 1 (RS256, JWKS, issuer e audiência configurados);
2. confere em `GET /auth/me` que a sessão e a conta estão ativas;
3. quando há `project_id`, confere em `GET /projects/{id}/access/v2` a permissão `project:read`.

O resultado de 2 e 3 fica em cache por 60 segundos. Detalhes em
[contracts/modulo1-consumido.md](contracts/modulo1-consumido.md).

Cada conversa pertence a uma pessoa (`sub` do JWT) e, opcionalmente, a um projeto do Módulo 1. Numa
pergunta de acompanhamento vale o projeto da conversa. O `project_id` é repassado ao Orquestrador.

### Campos da resposta do chat

| Campo | Significado |
|---|---|
| `message.content` | Resposta em markdown |
| `message.sources[]` | `source` (módulo), `path`, `start_line`, `end_line`, `similarity` (0 a 1) e `excerpt` (300 caracteres) |
| `message.grounded` | `false` quando a resposta não veio de arquivos do projeto |
| `message.mode` | `gemini`, `offline` (sem chave) ou `fallback` (o Gemini falhou e a resposta é a mensagem amigável) |
| `message.feedback` | `up`, `down` ou `null` |

### Erros

Formato comum aos serviços: `{"detail": "mensagem legível", "code": "CODIGO"}`. Validação usa o 422 padrão do FastAPI.

| Status | `code` | Quando |
|---|---|---|
| 401 | `NAO_AUTENTICADO` | Sem token, token inválido ou expirado, ou sessão encerrada no Módulo 1 |
| 404 | `PROJETO_NAO_ENCONTRADO` | Projeto não existe ou a conta não tem `project:read` |
| 404 | `CONVERSA_NAO_ENCONTRADA` | Conversa não existe ou é de outra pessoa |
| 404 | `MENSAGEM_NAO_ENCONTRADA` | Mensagem não existe, é de outra pessoa ou não é do assistente |
| 422 | — | `message` vazia ou acima de 20.000 caracteres, perfil fora da lista, `temperature` fora de 0 a 1 |
| 429 | `RATE_LIMITED` | Mais de 10 perguntas por pessoa ou 60 no total, por minuto |
| 503 | `ORQUESTRADOR_INDISPONIVEL` | Orquestrador fora do ar, lento (> 60 s) ou com resposta fora do contrato. Nada é gravado |
| 503 | `MODULO1_INDISPONIVEL` | Módulo 1 fora do ar ou com resposta inesperada |

Perfis aceitos: `Desenvolvedor`, `Product Owner` e `Gerente de Projetos`. O perfil muda o foco da
resposta, não dá permissão.

## Dados

Tabelas `conversations` e `messages` em [schema.sql](assistente_conversacional/schema.sql), criadas na
inicialização com `CREATE TABLE IF NOT EXISTS`. A coluna `conversations.project_id` é adicionada com
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` nos bancos que já existiam.

- Pergunta e resposta são gravadas na mesma transação, só depois que o Orquestrador responde.
- O título da conversa é formado pelos primeiros 60 caracteres da primeira pergunta.
- Conversas criadas com a sessão anônima da versão 1 continuam no banco, mas nenhum usuário do
  Módulo 1 as enxerga.

## Configuração

| Variável | Padrão | Observação |
|---|---|---|
| `DATABASE_URL` | `postgresql://mackai:mackai@localhost:5432/conversas_db` | Secret no Azure |
| `ORQUESTRADOR_URL` | `http://localhost:8001` | `http://mackai-orquestrador` no Azure |
| `ORQUESTRADOR_TIMEOUT_S` | `60` | |
| `MOD1_AUTH_URL` | Identidade publicada do Módulo 1 | |
| `MOD1_PROJECTS_URL` | Projetos publicado do Módulo 1 | |
| `MOD1_JWT_ISSUER` | igual a `MOD1_AUTH_URL` | `mod1-auth-local` com o Módulo 1 falso |
| `MOD1_JWT_AUDIENCE` | `engenharia-software-api` | |
| `MOD1_JWKS_URL` | `MOD1_AUTH_URL` + `/.well-known/jwks.json` | |
| `MOD1_TIMEOUT_S` | `5` | |
| `MOD1_CACHE_S` | `60` | Tempo de cache de `/auth/me` e do acesso ao projeto |
| `CHAT_LIMIT_PER_USER` | `10` | Por minuto |
| `CHAT_LIMIT_GLOBAL` | `60` | Por minuto |
| `MAX_MESSAGE_CHARS` | `20000` | Mesmo valor de `MAX_MESSAGE_CHARS` em `frontend/src/assistente_conversacional/api.ts` |
| `CORS_ORIGINS` | vazio | Origens dos fronts de outros módulos que chamam esta API pelo navegador |

O front lê, no build, `VITE_MOD1_AUTH_URL`, `VITE_MOD1_PROJECTS_URL` e `VITE_MOD1_FRONTEND_URL`. Vazias,
valem os endereços publicados do Módulo 1. No Docker, passe-as como `--build-arg`.

## Estrutura

```text
assistente_conversacional/
  main.py                   # app, handler de erros, X-Request-ID e montagem do front
  rotas.py                  # rotas /api/*
  modelos.py                # contrato público e contrato do Orquestrador (Pydantic)
  modulo1.py                # validação do JWT, sessão e acesso a projetos no Módulo 1
  limites.py                # limites por minuto em memória
  repositorio.py            # SQL de conversas, mensagens e métricas
  cliente_orquestrador.py   # httpx.AsyncClient reutilizado
  erros.py                  # erros no formato {detail, code}
  config.py                 # variáveis de ambiente
  schema.sql
frontend/                   # React + Vite, identidade visual do Módulo 6, login pelo Módulo 1
dev/orquestrador_falso.py   # Orquestrador falso para desenvolvimento
dev/modulo1_falso.py        # Módulo 1 falso (login, JWKS, projetos) para desenvolvimento
docs/                       # guia de integração para os outros módulos
contracts/                  # OpenAPI exportado e contratos consumidos (Orquestrador e Módulo 1)
postman/                    # coleção e ambientes (gerados por scripts/gerar_postman.py)
tests/
```

## Deploy (Azure Container Apps)

Passo a passo pelo portal, incluindo o acesso dos colegas: [docs/deploy-azure.md](docs/deploy-azure.md).

- Container App `mackai-conversas`, ingress **externo**, porta 8000, 0,25 vCPU e 0,5 GiB.
- Réplicas: mínimo 0 e máximo 1 (os limites ficam em memória). No dia da apresentação, mínimo 1.
- Secret: `DATABASE_URL`.
- Sondas de vida e de prontidão em `/health`.
- Peça ao Módulo 1 para liberar a URL pública do front no CORS de Identidade e Projetos.

## Limitações

- O `project_id` chega ao Orquestrador, mas a Busca ainda indexa um único conjunto de arquivos.
- Os contadores de limite zeram quando o serviço reinicia e não funcionam com mais de uma réplica.
- Uma sessão encerrada no Módulo 1 continua aceita aqui por até `MOD1_CACHE_S` segundos.
- Sem streaming de resposta e sem exportação de feedback pela interface.
