"""SQL de conversas e mensagens (conversas_db). Todas as consultas filtram pelo dono."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import asyncpg

from . import config

SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")

_COLUNAS_MENSAGEM = "id, role, content, sources, grounded, mode, feedback, created_at"


async def _configurar_conexao(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def abrir_pool(url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5, init=_configurar_conexao)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
    return pool


async def criar_conversa(pool: asyncpg.Pool, dono: UUID) -> dict:
    linha = await pool.fetchrow(
        "INSERT INTO conversations (id, owner_id) VALUES ($1, $2) RETURNING id, title, created_at",
        uuid.uuid4(), dono,
    )
    return dict(linha)


async def listar_conversas(pool: asyncpg.Pool, dono: UUID) -> list[dict]:
    linhas = await pool.fetch(
        """
        SELECT c.id, c.title, c.created_at
        FROM conversations c
        WHERE c.owner_id = $1
          AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
        ORDER BY c.created_at DESC
        """,
        dono,
    )
    return [dict(l) for l in linhas]


async def buscar_conversa(pool: asyncpg.Pool, dono: UUID, conversa_id: UUID) -> dict | None:
    linha = await pool.fetchrow(
        "SELECT id, title, created_at FROM conversations WHERE id = $1 AND owner_id = $2",
        conversa_id, dono,
    )
    return dict(linha) if linha else None


async def listar_mensagens(pool: asyncpg.Pool, conversa_id: UUID) -> list[dict]:
    linhas = await pool.fetch(
        f"SELECT {_COLUNAS_MENSAGEM} FROM messages WHERE conversation_id = $1 ORDER BY created_at",
        conversa_id,
    )
    return [dict(l) for l in linhas]


async def ultimas_mensagens(pool: asyncpg.Pool, conversa_id: UUID) -> list[dict]:
    """Histórico para o Orquestrador: as 10 últimas, em ordem cronológica, cada uma com até 4.000 caracteres."""
    linhas = await pool.fetch(
        """
        SELECT role, left(content, $2) AS content FROM (
          SELECT role, content, created_at FROM messages
          WHERE conversation_id = $1
          ORDER BY created_at DESC
          LIMIT $3
        ) ultimas
        ORDER BY created_at
        """,
        conversa_id, config.HISTORY_MAX_CHARS, config.HISTORY_MAX_MESSAGES,
    )
    return [dict(l) for l in linhas]


async def gravar_troca(
    pool: asyncpg.Pool,
    dono: UUID,
    conversa_id: UUID | None,
    pergunta: str,
    perguntada_em: datetime,
    resposta: dict,
) -> tuple[UUID, dict]:
    """Grava pergunta e resposta na mesma transação, depois que o Orquestrador respondeu.

    Se `conversa_id` for nulo, a conversa também nasce aqui; assim uma falha do
    Orquestrador não deixa conversa vazia no banco.
    """
    async with pool.acquire() as conn, conn.transaction():
        if conversa_id is None:
            conversa_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO conversations (id, owner_id, created_at) VALUES ($1, $2, $3)",
                conversa_id, dono, perguntada_em,
            )

        # Título = primeiros 60 caracteres da primeira pergunta.
        await conn.execute(
            """
            UPDATE conversations SET title = $2
            WHERE id = $1 AND NOT EXISTS (SELECT 1 FROM messages WHERE conversation_id = $1)
            """,
            conversa_id, pergunta[: config.TITLE_MAX_CHARS],
        )

        await conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES ($1, $2, 'user', $3, $4)",
            uuid.uuid4(), conversa_id, pergunta, perguntada_em,
        )
        mensagem = await conn.fetchrow(
            f"""
            INSERT INTO messages (id, conversation_id, role, content, sources, grounded, mode, created_at)
            VALUES ($1, $2, 'assistant', $3, $4, $5, $6, $7)
            RETURNING {_COLUNAS_MENSAGEM}
            """,
            uuid.uuid4(), conversa_id, resposta["content"], resposta["sources"],
            resposta["grounded"], resposta["mode"], datetime.now(timezone.utc),
        )
    return conversa_id, dict(mensagem)


async def votar(pool: asyncpg.Pool, dono: UUID, mensagem_id: UUID, valor: str | None) -> bool:
    """Grava o voto só se a mensagem for do assistente e de uma conversa do dono."""
    resultado = await pool.execute(
        """
        UPDATE messages m
        SET feedback = $3, feedback_at = CASE WHEN $3::text IS NULL THEN NULL ELSE now() END
        FROM conversations c
        WHERE m.id = $1 AND m.role = 'assistant' AND m.conversation_id = c.id AND c.owner_id = $2
        """,
        mensagem_id, dono, valor,
    )
    return resultado != "UPDATE 0"
