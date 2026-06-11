const API_PREFIX = "/api/v1";

export type AuthUser = {
  id: number;
  email?: string | null;
  phone?: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type ChatMessage = {
  id: number;
  session_id: number;
  role: "user" | "assistant" | string;
  content: string;
  intent?: string | null;
  feedback?: FeedbackRating | null;
  created_at: string;
};

export type FeedbackRating = "like" | "dislike";

export type ChatSession = {
  id: number;
  title?: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatSessionDetail = ChatSession & {
  messages: ChatMessage[];
};

type StreamChatOptions = {
  question: string;
  sessionId?: number | null;
  onSession?: (sessionId: number) => void;
  onDelta: (text: string) => void;
  onSaved?: (messageId: number) => void;
  onDone: () => void;
  onError?: (message: string) => void;
};

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function normalizeErrorMessage(message: string): string {
  if (message.includes("String should have at least 6 characters")) {
    return "\u5bc6\u7801\u81f3\u5c11 6 \u4f4d";
  }
  if (message.includes("String should have at most 64 characters")) {
    return "\u5bc6\u7801\u4e0d\u80fd\u8d85\u8fc7 64 \u4f4d";
  }
  if (message.includes("Field required")) {
    return "\u8bf7\u586b\u5199\u5fc5\u586b\u9879";
  }
  return message;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    let message = text || "Request failed";
    try {
      const data = JSON.parse(text);
      if (Array.isArray(data.detail)) {
        message = data.detail[0]?.msg || message;
      } else {
        message = data.detail || message;
      }
    } catch {
      // Keep original response text when the server does not return JSON.
    }
    throw new Error(normalizeErrorMessage(message));
  }
  return response.json();
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: authHeaders()
  });
  return parseResponse<T>(response);
}

export async function postJson<T>(path: string, data: unknown): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders()
    },
    body: JSON.stringify(data)
  });
  return parseResponse<T>(response);
}

export async function deleteJson(path: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "DELETE",
    headers: authHeaders()
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export function login(account: string, password: string) {
  return postJson<AuthResponse>("/auth/login", { account, password });
}

export function register(data: { email?: string; phone?: string; password: string }) {
  return postJson<AuthResponse>("/auth/register", data);
}

export function createSession(title = "\u65b0\u5efa\u5bf9\u8bdd") {
  return postJson<ChatSessionDetail>("/sessions", { title });
}

export async function listSessions() {
  const data = await getJson<{ items: ChatSession[] }>("/sessions");
  return data.items;
}

export function getSession(sessionId: number) {
  return getJson<ChatSessionDetail>(`/sessions/${sessionId}`);
}

export function deleteSession(sessionId: number) {
  return deleteJson(`/sessions/${sessionId}`);
}

export function submitFeedback(data: { message_id: number; rating: FeedbackRating; comment?: string }) {
  return postJson<{ id: number; message_id: number; rating: FeedbackRating; comment?: string | null }>(
    "/feedback",
    data
  );
}

export async function streamChat(options: StreamChatOptions) {
  try {
    const response = await fetch(`${API_PREFIX}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders()
      },
      body: JSON.stringify({
        question: options.question,
        session_id: options.sessionId || undefined
      })
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || "Send failed");
    }

    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        const eventLine = block.split("\n").find((line) => line.startsWith("event: "));
        const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
        if (!dataLine) continue;

        const event = eventLine?.replace("event: ", "") || "message";
        const data = JSON.parse(dataLine.replace("data: ", ""));

        if (event === "session" && typeof data.session_id === "number") {
          options.onSession?.(data.session_id);
        }

        if (event === "message" && data.type === "delta") {
          options.onDelta(data.content || "");
        }

        if (event === "saved" && typeof data.message_id === "number") {
          options.onSaved?.(data.message_id);
        }
      }
    }

    options.onDone();
  } catch (error) {
    options.onError?.(error instanceof Error ? error.message : "Send failed");
    options.onDone();
  }
}
