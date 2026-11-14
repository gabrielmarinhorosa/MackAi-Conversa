"""Cenários da seção 12 do documento do serviço, o contrato de cada rota e a integração com o Módulo 1."""

import time
import uuid

import jwt

from assistente_conversacional import config
from tests.conftest import perguntar, token, usuario_de


# ---------- Autenticação pelo Módulo 1 ----------

def test_requisicao_sem_token_retorna_401(client):
    for metodo, rota in [("get", "/api/conversations"), ("post", "/api/conversations"),
                         ("post", "/api/chat"), ("post", "/api/feedback")]:
        resposta = getattr(client, metodo)(rota)
        assert resposta.status_code == 401, rota
        assert resposta.json()["code"] == "NAO_AUTENTICADO"


def test_token_invalido_retorna_401(client):
    resposta = client.get("/api/conversations", headers={"Authorization": "Bearer abc.def.ghi"})
    assert resposta.status_code == 401


def test_token_de_outro_emissor_audiencia_ou_algoritmo_retorna_401(client, modulo1):
    hs256 = jwt.encode({"sub": str(uuid.uuid4()), "iss": "mod1-auth-teste", "aud": "engenharia-software-api",
                        "iat": int(time.time()), "exp": int(time.time()) + 60, "jti": str(uuid.uuid4())},
                       "segredo-hs256-com-mais-de-32-caracteres", algorithm="HS256")
    for tok in [modulo1.emitir(iss="outro-emissor"), modulo1.emitir(aud="outra-api"), hs256]:
        resposta = client.get("/api/conversations", headers={"Authorization": f"Bearer {tok}"})
        assert resposta.status_code == 401
        assert resposta.json()["code"] == "NAO_AUTENTICADO"


def test_token_expirado_retorna_401(client, modulo1):
    agora = int(time.time())
    tok = modulo1.emitir(iat=agora - 3600, exp=agora - 60)
    assert client.get("/api/conversations", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_sessao_encerrada_no_modulo1_retorna_401(client, modulo1):
    a = token(modulo1)
    modulo1.revogados.add(usuario_de(a))
    resposta = client.get("/api/conversations", headers=a)
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "NAO_AUTENTICADO"


def test_jwks_e_auth_me_sao_reaproveitados_entre_requisicoes(client, modulo1):
    a = token(modulo1)
    for _ in range(3):
        assert client.get("/api/conversations", headers=a).status_code == 200
    assert modulo1.chamadas.count("/.well-known/jwks.json") == 1
    assert modulo1.chamadas.count("/auth/me") == 1


def test_modulo1_fora_do_ar_retorna_503(client, modulo1):
    modulo1.fora = True
    resposta = client.get("/api/conversations", headers=token(modulo1))
    assert resposta.status_code == 503
    assert resposta.json()["code"] == "MODULO1_INDISPONIVEL"


def test_health_nao_exige_token(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


# ---------- Isolamento entre usuários ----------

def test_token_b_nao_ve_lista_le_nem_vota_na_conversa_de_a(client, modulo1):
    a, b = token(modulo1), token(modulo1)
    resposta = perguntar(client, a).json()
    conversa_id, mensagem_id = resposta["conversation_id"], resposta["message"]["id"]

    assert client.get("/api/conversations", headers=b).json() == []
    assert client.get(f"/api/conversations/{conversa_id}", headers=b).status_code == 404
    voto = client.post("/api/feedback", headers=b, json={"message_id": mensagem_id, "value": "up"})
    assert voto.status_code == 404
    assert voto.json()["code"] == "MENSAGEM_NAO_ENCONTRADA"
    assert perguntar(client, b, conversation_id=conversa_id).status_code == 404


# ---------- Projetos do Módulo 1 ----------

def test_pergunta_em_projeto_sem_acesso_retorna_404_e_nao_chega_ao_orquestrador(client, modulo1, orquestrador):
    resposta = perguntar(client, token(modulo1), project_id=str(uuid.uuid4()))
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "PROJETO_NAO_ENCONTRADO"
    assert orquestrador.pedidos == []


def test_conversa_de_projeto_fica_separada_das_gerais(client, modulo1, orquestrador):
    a, projeto = token(modulo1), str(uuid.uuid4())
    modulo1.acessos[(usuario_de(a), projeto)] = ["project:read"]

    corpo = perguntar(client, a, project_id=projeto).json()
    assert orquestrador.pedidos[-1]["project_id"] == projeto
    lista = client.get("/api/conversations", headers=a, params={"project_id": projeto}).json()
    assert [c["id"] for c in lista] == [corpo["conversation_id"]]
    assert client.get("/api/conversations", headers=a).json() == []
    assert client.get(f"/api/conversations/{corpo['conversation_id']}", headers=a).json()["project_id"] == projeto


def test_conversa_geral_nao_envia_project_id_ao_orquestrador(client, modulo1, orquestrador):
    perguntar(client, token(modulo1))
    assert "project_id" not in orquestrador.pedidos[-1]


def test_acompanhamento_usa_o_projeto_da_conversa(client, modulo1, orquestrador):
    a, projeto = token(modulo1), str(uuid.uuid4())
    modulo1.acessos[(usuario_de(a), projeto)] = ["project:read"]
    conversa_id = perguntar(client, a, project_id=projeto).json()["conversation_id"]

    perguntar(client, a, "E agora?", conversation_id=conversa_id, project_id=str(uuid.uuid4()))
    assert orquestrador.pedidos[-1]["project_id"] == projeto


def test_quem_perde_o_acesso_ao_projeto_nao_le_mais_a_conversa(novo_cliente, modulo1, monkeypatch):
    monkeypatch.setattr(config, "MOD1_CACHE_S", 0)
    client = novo_cliente()
    a, projeto = token(modulo1), str(uuid.uuid4())
    modulo1.acessos[(usuario_de(a), projeto)] = ["project:read"]
    conversa_id = perguntar(client, a, project_id=projeto).json()["conversation_id"]

    del modulo1.acessos[(usuario_de(a), projeto)]
    resposta = client.get(f"/api/conversations/{conversa_id}", headers=a)
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "PROJETO_NAO_ENCONTRADO"


def test_permissao_sem_project_read_nao_da_acesso(client, modulo1):
    a, projeto = token(modulo1), str(uuid.uuid4())
    modulo1.acessos[(usuario_de(a), projeto)] = ["backlog:read"]
    assert perguntar(client, a, project_id=projeto).status_code == 404


def test_post_conversations_com_projeto_exige_acesso(client, modulo1):
    a, projeto = token(modulo1), str(uuid.uuid4())
    assert client.post("/api/conversations", headers=a, json={"project_id": projeto}).status_code == 404
    modulo1.acessos[(usuario_de(a), projeto)] = ["project:read"]
    criada = client.post("/api/conversations", headers=a, json={"project_id": projeto})
    assert criada.status_code == 201
    assert criada.json()["project_id"] == projeto


def test_metricas_do_projeto_somam_todas_as_pessoas_com_acesso(client, modulo1, orquestrador):
    a, b, projeto = token(modulo1), token(modulo1), str(uuid.uuid4())
    for auth in (a, b):
        modulo1.acessos[(usuario_de(auth), projeto)] = ["project:read"]
    resposta = perguntar(client, a, project_id=projeto).json()
    perguntar(client, a, "Outra", conversation_id=resposta["conversation_id"])
    client.post("/api/feedback", headers=a, json={"message_id": resposta["message"]["id"], "value": "up"})
    orquestrador.resposta = {**orquestrador.resposta, "grounded": False, "sources": []}
    perguntar(client, b, project_id=projeto)
    perguntar(client, b)  # conversa geral não entra nas métricas do projeto

    metricas = client.get(f"/api/projects/{projeto}/metrics", headers=b).json()
    assert {k: v for k, v in metricas.items() if k != "last_question_at"} == {
        "project_id": projeto, "conversations": 2, "users": 2, "questions": 3,
        "answers_up": 1, "answers_down": 0, "answers_not_grounded": 1}
    assert metricas["last_question_at"] is not None
    assert client.get(f"/api/projects/{projeto}/metrics", headers=token(modulo1)).status_code == 404


# ---------- Persistência ----------

def test_conversa_continua_depois_de_reiniciar_o_app(novo_cliente, modulo1):
    primeiro = novo_cliente()
    a = token(modulo1)
    conversa_id = perguntar(primeiro, a).json()["conversation_id"]

    reiniciado = novo_cliente()
    assert [c["id"] for c in reiniciado.get("/api/conversations", headers=a).json()] == [conversa_id]
    conversa = reiniciado.get(f"/api/conversations/{conversa_id}", headers=a).json()
    assert [m["role"] for m in conversa["messages"]] == ["user", "assistant"]


def test_post_conversations_cria_vazia_que_so_aparece_na_lista_com_mensagens(client, modulo1):
    a = token(modulo1)
    criada = client.post("/api/conversations", headers=a)
    assert criada.status_code == 201
    assert criada.json()["title"] == "Nova conversa"
    assert client.get("/api/conversations", headers=a).json() == []

    perguntar(client, a, conversation_id=criada.json()["id"])
    assert [c["id"] for c in client.get("/api/conversations", headers=a).json()] == [criada.json()["id"]]


def test_titulo_sao_os_60_primeiros_caracteres_da_primeira_pergunta(client, modulo1):
    a = token(modulo1)
    pergunta = "x" * 100
    conversa_id = perguntar(client, a, pergunta).json()["conversation_id"]
    perguntar(client, a, "segunda pergunta", conversation_id=conversa_id)
    assert client.get(f"/api/conversations/{conversa_id}", headers=a).json()["title"] == "x" * 60


# ---------- Contrato do chat ----------

def test_resposta_do_chat_segue_o_contrato(client, modulo1):
    a = token(modulo1)
    corpo = perguntar(client, a, profile="Product Owner", temperature=0.9).json()
    mensagem = corpo["message"]
    assert mensagem["role"] == "assistant"
    assert mensagem["content"] == "Resposta **markdown**"
    assert mensagem["grounded"] is True and mensagem["mode"] == "gemini" and mensagem["feedback"] is None
    assert mensagem["sources"][0]["source"] == "modulo-7"
    assert set(mensagem["sources"][0]) == {"source", "path", "start_line", "end_line", "similarity", "excerpt"}


def test_perfil_e_temperatura_chegam_ao_orquestrador(client, orquestrador, modulo1):
    perguntar(client, token(modulo1), "  Oi  ", profile="Gerente de Projetos", temperature=1)
    assert orquestrador.pedidos[-1] == {"question": "Oi", "profile": "Gerente de Projetos",
                                        "temperature": 1.0, "history": []}


def test_resposta_geral_guarda_grounded_false(client, orquestrador, modulo1):
    orquestrador.resposta = {**orquestrador.resposta, "grounded": False, "sources": []}
    a = token(modulo1)
    conversa_id = perguntar(client, a).json()["conversation_id"]
    mensagens = client.get(f"/api/conversations/{conversa_id}", headers=a).json()["messages"]
    assert mensagens[1]["grounded"] is False and mensagens[1]["sources"] == []


def test_x_request_id_e_repassado_ao_orquestrador(client, orquestrador, modulo1):
    resposta = client.post("/api/chat", headers={**token(modulo1), "X-Request-ID": "abc-123"},
                           json={"message": "Oi"})
    assert resposta.headers["X-Request-ID"] == "abc-123"
    assert orquestrador.cabecalhos[-1]["X-Request-ID"] == "abc-123"


# ---------- Histórico ----------

def test_primeira_pergunta_depois_de_nova_conversa_vai_sem_historico(client, orquestrador, modulo1):
    a = token(modulo1)
    conversa_id = perguntar(client, a, "Primeira").json()["conversation_id"]
    perguntar(client, a, "Segunda", conversation_id=conversa_id)
    assert len(orquestrador.pedidos[-1]["history"]) == 2

    perguntar(client, a, "Nova conversa", conversation_id=None)
    assert orquestrador.pedidos[-1]["history"] == []


def test_conversa_com_14_mensagens_envia_so_as_10_ultimas_cortadas_em_4000(client, orquestrador, modulo1):
    a = token(modulo1)
    conversa_id = perguntar(client, a, "pergunta 0").json()["conversation_id"]
    for i in range(1, 6):
        perguntar(client, a, f"pergunta {i}", conversation_id=conversa_id)
    perguntar(client, a, "y" * 5000, conversation_id=conversa_id)  # 7ª troca = 14 mensagens

    perguntar(client, a, "pergunta final", conversation_id=conversa_id)
    historico = orquestrador.pedidos[-1]["history"]
    assert len(historico) == 10
    assert [h["role"] for h in historico] == ["user", "assistant"] * 5
    assert historico[0]["content"] == "pergunta 2"
    assert historico[-2]["content"] == "y" * 4000


# ---------- Validação ----------

def test_mensagem_acima_de_20000_e_perfil_invalido_retornam_422(client, modulo1):
    a = token(modulo1)
    assert perguntar(client, a, "a" * (config.MAX_MESSAGE_CHARS + 1)).status_code == 422
    assert perguntar(client, a, profile="Estagiário").status_code == 422
    assert perguntar(client, a, temperature=1.5).status_code == 422
    assert perguntar(client, a, "   ").status_code == 422


def test_stack_trace_de_15000_caracteres_e_aceito(client, modulo1):
    assert perguntar(client, token(modulo1), "Traceback\n" * 1500).status_code == 200


# ---------- Limites ----------

def test_11a_pergunta_no_mesmo_minuto_retorna_429(client, modulo1):
    a = token(modulo1)
    for _ in range(10):
        assert perguntar(client, a).status_code == 200
    resposta = perguntar(client, a)
    assert resposta.status_code == 429
    assert resposta.json()["code"] == "RATE_LIMITED"
    assert perguntar(client, token(modulo1)).status_code == 200  # outro usuário segue livre


def test_limite_global_protege_a_cota_mesmo_com_muitos_usuarios(novo_cliente, monkeypatch, modulo1):
    monkeypatch.setattr(config, "CHAT_LIMIT_GLOBAL", 3)
    client = novo_cliente()
    for _ in range(3):
        assert perguntar(client, token(modulo1)).status_code == 200
    assert perguntar(client, token(modulo1)).status_code == 429


# ---------- Falhas do Orquestrador ----------

def test_orquestrador_em_timeout_retorna_503_e_nada_e_gravado(client, orquestrador, modulo1):
    a = token(modulo1)
    conversa_id = perguntar(client, a, "antes").json()["conversation_id"]

    orquestrador.modo = "timeout"
    resposta = perguntar(client, a, "depois", conversation_id=conversa_id)
    assert resposta.status_code == 503
    assert resposta.json()["code"] == "ORQUESTRADOR_INDISPONIVEL"
    assert perguntar(client, a, "conversa nova").status_code == 503

    assert len(client.get("/api/conversations", headers=a).json()) == 1
    assert len(client.get(f"/api/conversations/{conversa_id}", headers=a).json()["messages"]) == 2


def test_orquestrador_com_erro_500_retorna_503(client, orquestrador, modulo1):
    orquestrador.modo = "erro"
    assert perguntar(client, token(modulo1)).status_code == 503


# ---------- Feedback ----------

def test_voto_e_remocao_do_voto(client, modulo1):
    a = token(modulo1)
    resposta = perguntar(client, a).json()
    conversa_id, mensagem_id = resposta["conversation_id"], resposta["message"]["id"]

    def voto_salvo():
        return client.get(f"/api/conversations/{conversa_id}", headers=a).json()["messages"][1]["feedback"]

    assert client.post("/api/feedback", headers=a, json={"message_id": mensagem_id, "value": "up"}).json() == {"ok": True}
    assert voto_salvo() == "up"
    client.post("/api/feedback", headers=a, json={"message_id": mensagem_id, "value": None})
    assert voto_salvo() is None


def test_voto_em_mensagem_do_usuario_retorna_404(client, modulo1):
    a = token(modulo1)
    conversa_id = perguntar(client, a).json()["conversation_id"]
    pergunta_id = client.get(f"/api/conversations/{conversa_id}", headers=a).json()["messages"][0]["id"]
    assert client.post("/api/feedback", headers=a, json={"message_id": pergunta_id, "value": "up"}).status_code == 404


# ---------- Health ----------

def test_health_agrega_o_status_do_orquestrador(client):
    assert client.get("/api/health").json() == {
        "status": "ok", "llm": "gemini", "documents": 42, "chunks": 380, "indexed_at": "2026-11-12T10:00:00Z"}


def test_health_degradado_quando_orquestrador_nao_responde(client, orquestrador):
    orquestrador.status_modo = "fora"
    assert client.get("/api/health").json() == {
        "status": "degraded", "llm": "offline", "documents": 0, "chunks": 0, "indexed_at": None}


def test_health_degradado_quando_busca_nao_responde(client, orquestrador):
    orquestrador.status_modo = "sem_busca"
    corpo = client.get("/api/health").json()
    assert corpo["status"] == "degraded" and corpo["llm"] == "gemini" and corpo["documents"] == 0


def test_rota_inexistente_usa_o_formato_de_erro_comum(client):
    resposta = client.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "HTTP_404"
