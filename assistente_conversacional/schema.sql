CREATE TABLE IF NOT EXISTS conversations (
  id          UUID PRIMARY KEY,
  owner_id    UUID NOT NULL,              -- `sub` do JWT do Módulo 1
  project_id  UUID,                       -- projeto do Módulo 1; nulo = conversa geral
  title       TEXT NOT NULL DEFAULT 'Nova conversa',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Bancos criados antes da integração com o Módulo 1 não têm a coluna.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id UUID;
CREATE INDEX IF NOT EXISTS conversations_owner_idx ON conversations (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS conversations_project_idx ON conversations (project_id, owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id               UUID PRIMARY KEY,
  conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content          TEXT NOT NULL,
  sources          JSONB NOT NULL DEFAULT '[]',
  grounded         BOOLEAN,
  mode             TEXT,
  feedback         TEXT CHECK (feedback IN ('up', 'down')),
  feedback_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, created_at);
