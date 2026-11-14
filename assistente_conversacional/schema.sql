CREATE TABLE IF NOT EXISTS conversations (
  id          UUID PRIMARY KEY,
  owner_id    UUID NOT NULL,
  title       TEXT NOT NULL DEFAULT 'Nova conversa',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversations_owner_idx ON conversations (owner_id, created_at DESC);

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
