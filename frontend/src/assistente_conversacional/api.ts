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

export type ConversationSummary = { id: string; project_id: string | null; title: string; created_at: string };
export type Health = {
  status: "ok" | "degraded";
  llm: string;
  documents: number;
  chunks: number;
  indexed_at: string | null;
};
export type User = { id: string; email: string; display_name: string };
export type Project = { id: string; name: string };
export type LoginResult = { status: "ok" } | { status: "mfa"; challenge: string };

// Mesmo valor de MAX_MESSAGE_CHARS no backend (US 39).
export const MAX_MESSAGE_CHARS = 20000;
export const COUNTER_FROM_CHARS = 18000;

/** Erro com o status HTTP e o `code` da API, para a tela diferenciar 401, 404, 429 e 503. */
export class ApiError extends Error {
  constructor(public status: number, public code: string | null, message: string) {
    super(message);
  }
}

// Sem VITE_API_URL, usa a mesma origem da página: em produção o serviço entrega o front,
// e em desenvolvimento o proxy do Vite (vite.config.ts) encaminha /api para o localhost:8000.
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Módulo 1 (identidade e projetos), chamado direto pelo navegador. O Módulo 1 precisa liberar a
// origem deste front no CORS. Sem as variáveis, usa os endereços publicados do Módulo 1.
const MOD1_AUTH_URL = import.meta.env.VITE_MOD1_AUTH_URL || "https://mod1-auth.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io";
const MOD1_PROJECTS_URL = import.meta.env.VITE_MOD1_PROJECTS_URL || "https://mod1-projects.whitemeadow-deba1090.brazilsouth.azurecontainerapps.io";
export const MOD1_FRONTEND_URL = import.meta.env.VITE_MOD1_FRONTEND_URL || "https://green-river-02e44e810.2.azurestaticapps.net";

type Tokens = { access_token: string; refresh_token: string | null };
const TOKENS_KEY = "mackai.auth";

function readTokens(): Tokens | null {
  try { return JSON.parse(localStorage.getItem(TOKENS_KEY) ?? "null"); } catch { return null; }
}

function saveTokens(next: Tokens | null) {
  tokens = next;
  try {
    if (next) localStorage.setItem(TOKENS_KEY, JSON.stringify(next));
    else localStorage.removeItem(TOKENS_KEY);
  } catch { /* sem storage: o login vale só nesta aba */ }
}

let tokens: Tokens | null = readTokens();
let pendingRefresh: Promise<boolean> | null = null;
let onSessionEnded: () => void = () => undefined;

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

/** Troca o refresh_token por tokens novos. Requisições simultâneas compartilham a mesma troca. */
function refresh(): Promise<boolean> {
  const current = tokens?.refresh_token;
  if (!current) return Promise.resolve(false);
  pendingRefresh ??= fetch(`${MOD1_AUTH_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current }),
  })
    .then(async (response) => {
      if (!response.ok) return false;
      const body = await response.json();
      if (!body.access_token) return false;
      saveTokens({ access_token: body.access_token, refresh_token: body.refresh_token ?? null });
      return true;
    })
    .catch(() => false)
    .finally(() => { pendingRefresh = null; });
  return pendingRefresh;
}

/** Envia o Bearer do Módulo 1. Em 401, renova o token uma vez; se não der, encerra a sessão. */
async function authed<T>(url: string, init?: RequestInit, retried = false): Promise<T> {
  if (!tokens) {
    onSessionEnded();
    throw new ApiError(401, "NAO_AUTENTICADO", "Faça login.");
  }
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens.access_token}`, ...init?.headers },
  });
  if (response.status === 401) {
    if (!retried && (await refresh())) return authed<T>(url, init, true);
    saveTokens(null);
    onSessionEnded();
  }
  if (!response.ok) throw await toError(response);
  return response.json();
}

function tokensFrom(body: { access_token: string; refresh_token?: string | null }): LoginResult {
  saveTokens({ access_token: body.access_token, refresh_token: body.refresh_token ?? null });
  return { status: "ok" };
}

export const auth = {
  isLoggedIn: () => tokens !== null,
  onSessionEnded: (callback: () => void) => { onSessionEnded = callback; },

  /** POST /auth/token do Módulo 1: formulário com username = e-mail e a senha literal. */
  login: async (email: string, password: string): Promise<LoginResult> => {
    const response = await fetch(`${MOD1_AUTH_URL}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email.trim(), password }),
    });
    if (!response.ok) throw await toError(response);
    const body = await response.json();
    if (body.mfa_required) return { status: "mfa", challenge: body.challenge_token };
    return tokensFrom(body);
  },

  verifyMfa: async (challenge: string, code: string): Promise<LoginResult> => {
    const response = await fetch(`${MOD1_AUTH_URL}/auth/mfa/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challenge, code: code.trim() }),
    });
    if (!response.ok) throw await toError(response);
    return tokensFrom(await response.json());
  },

  logout: async () => {
    const current = tokens;
    saveTokens(null);
    if (!current) return;
    // Encerra a sessão no Módulo 1; se falhar, o token local já foi apagado.
    await fetch(`${MOD1_AUTH_URL}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${current.access_token}` },
      body: "{}",
    }).catch(() => undefined);
  },
};

export const api = {
  health: async (): Promise<Health> => {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    if (!response.ok) throw await toError(response);
    return response.json();
  },
  me: () => authed<User>(`${MOD1_AUTH_URL}/auth/me`),
  projects: async (): Promise<Project[]> =>
    (await authed<{ items: Project[] }>(`${MOD1_PROJECTS_URL}/projects?limit=100`)).items,

  conversations: (projectId: string | null) =>
    authed<ConversationSummary[]>(`${API_BASE_URL}/api/conversations${projectId ? `?project_id=${projectId}` : ""}`),
  conversation: (id: string) =>
    authed<ConversationSummary & { messages: Message[] }>(`${API_BASE_URL}/api/conversations/${id}`),
  chat: (body: { message: string; conversation_id: string | null; project_id: string | null; profile: string; temperature: number }) =>
    authed<{ conversation_id: string; message: Message }>(`${API_BASE_URL}/api/chat`, { method: "POST", body: JSON.stringify(body) }),
  feedback: (message_id: string, value: "up" | "down" | null) =>
    authed<{ ok: boolean }>(`${API_BASE_URL}/api/feedback`, { method: "POST", body: JSON.stringify({ message_id, value }) }),
};
