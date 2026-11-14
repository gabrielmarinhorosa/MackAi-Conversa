export type Source = {
  source: string;
  path: string;
  start_line: number;
  end_line: number;
  similarity: number;
  excerpt: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources?: Source[];
  // Opcionais para o front não quebrar se o campo faltar (seção 15).
  grounded?: boolean | null;
  mode?: "gemini" | "offline" | "fallback" | string | null;
  feedback?: "up" | "down" | null;
};

export type ConversationSummary = { id: string; title: string; created_at: string };
export type Health = {
  status: "ok" | "degraded";
  llm: string;
  documents: number;
  chunks: number;
  indexed_at: string | null;
};

// Mesmo valor de MAX_MESSAGE_CHARS no backend (US 39).
export const MAX_MESSAGE_CHARS = 20000;
export const COUNTER_FROM_CHARS = 18000;

/** Erro com o status HTTP e o `code` da API, para a tela diferenciar 401, 429 e 503. */
export class ApiError extends Error {
  constructor(public status: number, public code: string | null, message: string) {
    super(message);
  }
}

// Sem VITE_API_URL, usa a mesma origem da página: em produção o serviço entrega o front,
// e em desenvolvimento o proxy do Vite (vite.config.ts) encaminha /api para o localhost:8000.
const API_BASE_URL = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "mackai.token";

function readToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function saveToken(token: string) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* sem storage: o token vale só nesta aba */ }
}

let memoryToken: string | null = readToken();
let pendingSession: Promise<string> | null = null;

async function newSession(): Promise<string> {
  // Requisições simultâneas compartilham a mesma criação de sessão.
  pendingSession ??= fetch(`${API_BASE_URL}/api/sessions`, { method: "POST" })
    .then(async (response) => {
      if (!response.ok) throw await toError(response);
      const { token } = (await response.json()) as { token: string };
      memoryToken = token;
      saveToken(token);
      return token;
    })
    .finally(() => { pendingSession = null; });
  return pendingSession;
}

async function toError(response: Response): Promise<ApiError> {
  let code: string | null = null;
  let detail = `Erro ${response.status}`;
  try {
    const body = await response.json();
    code = body.code ?? null;
    if (typeof body.detail === "string") detail = body.detail;
  } catch { /* corpo não é JSON */ }
  return new ApiError(response.status, code, detail);
}

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const token = memoryToken ?? (await newSession());
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init?.headers },
  });
  // Token expirado ou inválido: pede um novo e repete uma vez.
  if (response.status === 401 && !retried) {
    memoryToken = null;
    await newSession();
    return request<T>(path, init, true);
  }
  if (!response.ok) throw await toError(response);
  return response.json();
}

export const api = {
  health: async (): Promise<Health> => {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    if (!response.ok) throw await toError(response);
    return response.json();
  },
  conversations: () => request<ConversationSummary[]>("/api/conversations"),
  conversation: (id: string) => request<ConversationSummary & { messages: Message[] }>(`/api/conversations/${id}`),
  chat: (body: { message: string; conversation_id: string | null; profile: string; temperature: number }) =>
    request<{ conversation_id: string; message: Message }>("/api/chat", { method: "POST", body: JSON.stringify(body) }),
  feedback: (message_id: string, value: "up" | "down" | null) =>
    request<{ ok: boolean }>("/api/feedback", { method: "POST", body: JSON.stringify({ message_id, value }) }),
};
