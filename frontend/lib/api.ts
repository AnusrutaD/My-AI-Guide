const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type HealthResponse = {
  status: string;
  checkpointer?: string;
};

export type StartSessionRequest = {
  user_id: string;
  thread_id?: string;
};

export type StartSessionResponse = {
  thread_id: string;
  question_text: string;
  topic: string;
  subtopic: string;
  difficulty: string;
  question_type?: string;
  test_cases?: Array<{ input: string; expected: string }>;
};

export type ExecuteRequest = {
  language: string;
  code: string;
  stdin: string;
};

export type ExecuteResponse = {
  stdout: string;
  stderr: string;
  code: number | null;
  signal: string | null;
  run_error?: string | null;
};

export type RespondSessionRequest = {
  user_id: string;
  thread_id: string;
  response: string;
};

export type RespondSessionResponse = {
  feedback: string;
  verdict: string;
  score_delta: number;
  next_action: string;
};

export type SessionStateResponse = {
  thread_id: string;
  interview_stage: string;
  current_topic?: string | null;
  current_subtopic?: string | null;
  knowledge_gap_score?: number | null;
  messages: Array<{ role?: string; content?: string }>;
};

export type DailyStatusResponse = {
  user_id: string;
  window_hours: number;
  attempts: number;
  average_score_delta: number;
  latest_topic?: string | null;
  latest_verdict?: string | null;
  last_activity_at?: string | null;
  message?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorText = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) errorText = String(body.detail);
    } catch {
      // keep fallback text
    }
    throw new Error(errorText);
  }
  return (await res.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  return readJson<HealthResponse>(res);
}

export async function startSession(body: StartSessionRequest): Promise<StartSessionResponse> {
  const res = await fetch(`${API_BASE_URL}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<StartSessionResponse>(res);
}

export async function respondSession(body: RespondSessionRequest): Promise<RespondSessionResponse> {
  const res = await fetch(`${API_BASE_URL}/session/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<RespondSessionResponse>(res);
}

export async function fetchSessionState(
  threadId: string,
  userId: string,
): Promise<SessionStateResponse> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${API_BASE_URL}/session/${encodeURIComponent(threadId)}?${params}`, {
    cache: "no-store",
  });
  return readJson<SessionStateResponse>(res);
}

export async function fetchDailyStatus(
  userId: string,
  hours = 24,
): Promise<DailyStatusResponse> {
  const params = new URLSearchParams({ hours: String(hours) });
  const res = await fetch(
    `${API_BASE_URL}/status/daily/${encodeURIComponent(userId)}?${params}`,
    { cache: "no-store" },
  );
  return readJson<DailyStatusResponse>(res);
}

export async function executeCode(body: ExecuteRequest): Promise<ExecuteResponse> {
  const res = await fetch(`${API_BASE_URL}/execute/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<ExecuteResponse>(res);
}

export { API_BASE_URL };
