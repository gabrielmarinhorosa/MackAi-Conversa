"""Gera a coleção e os ambientes do Postman em postman/ (rode depois de mudar o contrato).

    python scripts/gerar_postman.py
    npx newman run postman/mackai-conversas.postman_collection.json -e postman/mackai-local.postman_environment.json
"""

import json
from pathlib import Path

POSTMAN = Path(__file__).resolve().parent.parent / "postman"


def req(nome, metodo, rota, corpo=None, testes=(), auth=True, prerequest=None, base="{{baseUrl}}"):
    caminho = rota.split("?")[0]
    item = {
        "name": nome,
        "request": {
            "method": metodo,
            "header": [{"key": "Content-Type", "value": "application/json"}] if corpo is not None else [],
            "url": {"raw": base + rota, "host": [base], "path": [p for p in caminho.split("/") if p]},
        },
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": list(testes)}}],
    }
    if corpo is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(corpo, ensure_ascii=False, indent=2),
                                   "options": {"raw": {"language": "json"}}}
    if not auth:
        item["request"]["auth"] = {"type": "noauth"}
    if prerequest:
        item["event"].append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": prerequest}})
    return item


def status(n):
    return [f'pm.test("status {n}", () => pm.response.to.have.status({n}));']


def erro(n, code):
    return status(n) + [f'pm.test("code {code}", () => pm.expect(pm.response.json().code).to.eql("{code}"));']


MENSAGEM_NO_CONTRATO = [
    "const m = pm.response.json().message;",
    'pm.test("mensagem no contrato", () => {',
    '  pm.expect(m).to.include.keys("id", "role", "content", "sources", "grounded", "mode", "feedback", "created_at");',
    '  pm.expect(m.role).to.eql("assistant");',
    '  m.sources.forEach(s => pm.expect(s).to.include.keys("source", "path", "start_line", "end_line", "similarity", "excerpt"));',
    "});",
]

LOGIN_MODULO1 = [
    "pm.sendRequest({",
    "  url: pm.variables.get('mod1AuthUrl') + '/auth/token', method: 'POST',",
    "  header: { 'Content-Type': 'application/x-www-form-urlencoded' },",
    "  body: { mode: 'urlencoded', urlencoded: [",
    "    { key: 'username', value: pm.variables.get('email') },",
    "    { key: 'password', value: pm.variables.get('password') },",
    "  ] },",
    "}, (err, res) => {",
]

COLECAO = {
    "info": {
        "_postman_id": "6f1d8a7e-3c2b-4e59-9a0d-5b7c1e2f4a60",
        "name": "mackai-conversas",
        "description": "API pública do mackai-conversas (Módulo 7). O pre-request da coleção faz login no "
                       "Módulo 1 (POST {{mod1AuthUrl}}/auth/token com {{email}} e {{password}} do ambiente) e "
                       "guarda o access_token em {{token}}.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
    "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": [
        "// Faz login no Módulo 1 uma vez e reaproveita o token nas outras requisições.",
        "if (pm.request.url.getPath() === '/auth/token' || pm.collectionVariables.get('token')) return;",
        *LOGIN_MODULO1,
        "  if (err || res.code !== 200) { console.error('login no Módulo 1 falhou', err || res.code); return; }",
        "  pm.collectionVariables.set('token', res.json().access_token);",
        "});",
    ]}}],
    "variable": [
        {"key": "token", "value": ""},
        {"key": "conversationId", "value": ""},
        {"key": "messageId", "value": ""},
    ],
    "item": [
        {"name": "Módulo 1", "item": [
            {**req("Login (POST /auth/token)", "POST", "/auth/token", auth=False, base="{{mod1AuthUrl}}",
                   testes=status(200) + [
                       "const body = pm.response.json();",
                       'pm.test("access_token", () => pm.expect(body).to.include.keys("access_token"));',
                       'pm.collectionVariables.set("token", body.access_token);',
                   ]),
             "request": {
                 "method": "POST",
                 "header": [{"key": "Content-Type", "value": "application/x-www-form-urlencoded"}],
                 "url": {"raw": "{{mod1AuthUrl}}/auth/token", "host": ["{{mod1AuthUrl}}"], "path": ["auth", "token"]},
                 "auth": {"type": "noauth"},
                 "body": {"mode": "urlencoded", "urlencoded": [
                     {"key": "username", "value": "{{email}}"}, {"key": "password", "value": "{{password}}"}]},
             }},
        ]},
        {"name": "Saúde", "item": [
            req("Health da API", "GET", "/api/health", auth=False, testes=status(200) + [
                'pm.test("formato do health", () => pm.expect(pm.response.json())'
                '.to.have.keys("status", "llm", "documents", "chunks", "indexed_at"));',
            ]),
            req("Sonda /health", "GET", "/health", auth=False, testes=status(200) + [
                'pm.test("status ok", () => pm.expect(pm.response.json().status).to.eql("ok"));',
            ]),
        ]},
        {"name": "Chat", "item": [
            req("Pergunta em conversa nova", "POST", "/api/chat",
                corpo={"message": "Como funciona a busca?", "conversation_id": None,
                       "profile": "Desenvolvedor", "temperature": 0.4},
                testes=status(200) + MENSAGEM_NO_CONTRATO + [
                    'pm.collectionVariables.set("conversationId", pm.response.json().conversation_id);',
                    'pm.collectionVariables.set("messageId", m.id);',
                ]),
            req("Pergunta de acompanhamento", "POST", "/api/chat",
                corpo={"message": "E para o PO?", "conversation_id": "{{conversationId}}",
                       "profile": "Product Owner", "temperature": 0.4},
                testes=status(200) + MENSAGEM_NO_CONTRATO + [
                    'pm.test("mesma conversa", () => pm.expect(pm.response.json().conversation_id)'
                    '.to.eql(pm.collectionVariables.get("conversationId")));',
                ]),
            req("Mensagem acima de 20.000 caracteres (422)", "POST", "/api/chat",
                corpo={"message": "{{mensagemGrande}}", "conversation_id": None,
                       "profile": "Desenvolvedor", "temperature": 0.4},
                testes=status(422), prerequest=['pm.variables.set("mensagemGrande", "a".repeat(20001));']),
            req("Perfil inválido (422)", "POST", "/api/chat", corpo={"message": "Oi", "profile": "Estagiário"},
                testes=status(422)),
            req("Temperatura fora de 0 a 1 (422)", "POST", "/api/chat", corpo={"message": "Oi", "temperature": 1.5},
                testes=status(422)),
            req("Sem token (401)", "POST", "/api/chat", corpo={"message": "Oi"}, auth=False,
                testes=erro(401, "NAO_AUTENTICADO")),
            req("Pergunta em projeto do Módulo 1", "POST", "/api/chat",
                corpo={"message": "Como funciona a busca?", "conversation_id": None, "project_id": "{{projectId}}",
                       "profile": "Desenvolvedor", "temperature": 0.4},
                testes=status(200) + MENSAGEM_NO_CONTRATO),
            req("Projeto sem acesso (404)", "POST", "/api/chat",
                corpo={"message": "Oi", "project_id": "00000000-0000-0000-0000-000000000000"},
                testes=erro(404, "PROJETO_NAO_ENCONTRADO")),
        ]},
        {"name": "Conversas", "item": [
            req("Listar conversas", "GET", "/api/conversations", testes=status(200) + [
                'pm.test("contém a conversa criada", () => pm.expect(pm.response.json().map(c => c.id))'
                '.to.include(pm.collectionVariables.get("conversationId")));',
            ]),
            req("Buscar conversa", "GET", "/api/conversations/{{conversationId}}", testes=status(200) + [
                "const c = pm.response.json();",
                'pm.test("mensagens em ordem", () => pm.expect(c.messages.map(m => m.role))'
                '.to.eql(["user", "assistant", "user", "assistant"]));',
            ]),
            req("Conversas do projeto", "GET", "/api/conversations?project_id={{projectId}}", testes=status(200) + [
                'pm.test("todas do projeto", () => pm.response.json().forEach(c => '
                'pm.expect(c.project_id).to.eql(pm.environment.get("projectId"))));',
            ]),
            req("Conversa inexistente (404)", "GET", "/api/conversations/00000000-0000-0000-0000-000000000000",
                testes=erro(404, "CONVERSA_NAO_ENCONTRADA")),
            req("Criar conversa vazia", "POST", "/api/conversations", testes=status(201) + [
                'pm.test("título padrão", () => pm.expect(pm.response.json().title).to.eql("Nova conversa"));',
            ]),
        ]},
        {"name": "Feedback", "item": [
            req("Votar útil", "POST", "/api/feedback", corpo={"message_id": "{{messageId}}", "value": "up"},
                testes=status(200) + ['pm.test("ok", () => pm.expect(pm.response.json().ok).to.eql(true));']),
            req("Remover voto", "POST", "/api/feedback", corpo={"message_id": "{{messageId}}", "value": None},
                testes=status(200)),
            req("Mensagem inexistente (404)", "POST", "/api/feedback",
                corpo={"message_id": "00000000-0000-0000-0000-000000000000", "value": "up"},
                testes=erro(404, "MENSAGEM_NAO_ENCONTRADA")),
        ]},
        {"name": "Integração", "item": [
            req("Métricas do projeto", "GET", "/api/projects/{{projectId}}/metrics", testes=status(200) + [
                'pm.test("formato das métricas", () => pm.expect(pm.response.json()).to.have.keys('
                '"project_id", "conversations", "users", "questions", "answers_up", "answers_down", '
                '"answers_not_grounded", "last_question_at"));',
            ]),
        ]},
    ],
}

MOD1_AUTH_PUBLICADO = "https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io"

# local: Módulo 1 falso (dev/modulo1_falso.py), que aceita qualquer e-mail e senha.
# azure: preencha email, password e projectId no Postman com a sua conta do Módulo 1. Nunca faça commit deles.
AMBIENTES = {
    "local": ("0b7e4c1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d", "http://localhost:8000", "http://localhost:8002",
              "dev@mackai.test", "senha-local", "7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01"),
    "azure": ("1c8f5d2b-3e4a-4b6c-9d7e-8f9a0b1c2d3e", "https://<url-publica-do-mackai-conversas>",
              MOD1_AUTH_PUBLICADO, "", "", ""),
}


def salvar(nome: str, conteudo: dict) -> None:
    (POSTMAN / nome).write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    POSTMAN.mkdir(exist_ok=True)
    salvar("mackai-conversas.postman_collection.json", COLECAO)
    for nome, (id_, url, mod1, email, senha, projeto) in AMBIENTES.items():
        salvar(f"mackai-{nome}.postman_environment.json", {
            "id": id_, "name": f"mackai-{nome}",
            "values": [
                {"key": "baseUrl", "value": url, "type": "default", "enabled": True},
                {"key": "mod1AuthUrl", "value": mod1, "type": "default", "enabled": True},
                {"key": "email", "value": email, "type": "default", "enabled": True},
                {"key": "password", "value": senha, "type": "secret", "enabled": True},
                {"key": "projectId", "value": projeto, "type": "default", "enabled": True},
            ],
            "_postman_variable_scope": "environment",
        })
    print("Coleção e ambientes gerados em postman/")
