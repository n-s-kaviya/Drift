// Empty string = same origin; Vite dev server proxies /api → backend (port 8765).
const API_BASE = import.meta.env.VITE_API_URL ?? "";

export type User = {
  id: number;
  email: string;
  created_at: string;
  last_visit_at: string | null;
};

export type WatchlistItem = {
  id: number;
  symbol: string;
  notes: string | null;
  added_at: string;
};

export type MarketQuote = {
  symbol: string;
  price: number;
  change_pct: number;
  volume: number;
  high: number;
  low: number;
  open_price: number;
  is_stale: boolean;
  source: string;
  fetched_at: string;
  trading_status: string;
  trust_label: string;
  abnormality_score: number;
  abnormality_label: string;
};

export type ChangeEvent = {
  id: number;
  symbol: string;
  event_type: string;
  title: string;
  summary: string;
  why_plain: string;
  severity: number;
  cluster_id: number | null;
  prev_cluster_id: number | null;
  detection_method: string;
  is_stale_context: boolean;
  is_out_of_order: boolean;
  created_at: string;
  relevance_score: number | null;
  user_engaged: boolean | null;
  personalization_forced?: boolean;
  is_new?: boolean;
};

export type FeedItem = {
  kind: "single" | "bundle";
  bundle_id: string | null;
  title: string;
  summary: string;
  why_plain: string | null;
  events: ChangeEvent[];
  created_at: string;
};

export type AlertMute = {
  id: number;
  symbol: string;
  event_type: string;
  created_at: string;
};

export type Dashboard = {
  last_visit_at: string | null;
  feed: FeedItem[];
  watchlist: WatchlistItem[];
  quotes: MarketQuote[];
  mutes: AlertMute[];
  unread_event_count: number;
  in_bootstrap_phase: boolean;
  quotes_updated_at?: string | null;
};

export type PriceBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Fundamentals = {
  symbol: string;
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  roe: number | null;
  debt_to_equity: number | null;
  dividend_yield: number | null;
  pe_ratio: number | null;
  profit_margin: number | null;
  beta: number | null;
  market_cap: number | null;
  revenue_growth: number | null;
  source: string;
};

export type StockDetails = {
  symbol: string;
  history: PriceBar[];
  fundamentals: Fundamentals;
};

export type SymbolSearchResult = {
  symbol: string;
  name: string;
  type: string | null;
};

export function formatApiError(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  const msg = err.message;

  if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
    return "Cannot reach the server. Make sure the backend is running (port 8765).";
  }
  if (msg.includes("already in watchlist")) {
    return "That symbol is already on your watchlist.";
  }
  if (msg.includes("401") || msg.toLowerCase().includes("unauthorized")) {
    return "Session expired. Please sign out and sign back in.";
  }
  if (msg.includes("Symbol required")) {
    return "Please enter a stock ticker.";
  }

  try {
    const parsed = JSON.parse(msg) as { detail?: string };
    if (parsed.detail) return parsed.detail;
  } catch {
    // not JSON — use raw message if it's readable
  }

  return msg.length > 0 && msg.length < 200 ? msg : fallback;
}

async function request<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    let detail = text || res.statusText;
    try {
      const body = JSON.parse(text) as { detail?: string | { msg: string }[] };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep raw text
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function register(email: string, password: string) {
  return request<User>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();
  return data.access_token as string;
}

export async function getDashboard(token: string, light = false) {
  const query = light ? "?light=true" : "";
  return request<Dashboard>(`/api/dashboard${query}`, {}, token);
}

export async function markVisit(token: string) {
  return request<{ ok: boolean }>("/api/visit", { method: "POST" }, token);
}

export async function addWatchlistItem(token: string, symbol: string, notes?: string) {
  return request<WatchlistItem>("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol, notes }),
  }, token);
}

export async function removeWatchlistItem(token: string, itemId: number) {
  return request<void>(`/api/watchlist/${itemId}`, { method: "DELETE" }, token);
}

export async function submitFeedback(token: string, eventId: number, engaged: boolean) {
  return request<{ ok: boolean }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify({ event_id: eventId, engaged }),
  }, token);
}

export async function clearFeedback(token: string, eventId: number) {
  return request<void>(`/api/feedback/${eventId}`, { method: "DELETE" }, token);
}

export async function createMute(token: string, symbol: string, eventType: string) {
  return request<AlertMute>("/api/mutes", {
    method: "POST",
    body: JSON.stringify({ symbol, event_type: eventType }),
  }, token);
}

export async function deleteMute(token: string, muteId: number) {
  const res = await fetch(`${API_BASE}/api/mutes/${muteId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 204 || res.status === 404) return;
  throw new Error(await res.text() || res.statusText);
}

export async function listMutes(token: string) {
  return request<AlertMute[]>("/api/mutes", {}, token);
}

export async function getStockDetails(token: string, symbol: string, period = "1m") {
  return request<StockDetails>(`/api/symbols/${encodeURIComponent(symbol)}/details?period=${period}`, {}, token);
}

export async function searchSymbols(token: string, query: string) {
  return request<SymbolSearchResult[]>(
    `/api/symbols/search?q=${encodeURIComponent(query)}`,
    {},
    token
  );
}
