import { useCallback, useEffect, useRef, useState } from "react";
import { getDashboard, markVisit, submitFeedback, clearFeedback, createMute, deleteMute, removeWatchlistItem, Dashboard } from "./lib/api";
import { clearToken, getToken } from "./lib/auth";
import { AuthForm } from "./components/AuthForm";
import { ChangeFeed, QuotesTable } from "./components/MarketPanels";
import { WatchlistManager } from "./components/WatchlistManager";
import { loadRefreshSettings, RefreshSettingsMenu } from "./components/RefreshSettings";
import type { RefreshSettings } from "./lib/refreshSettings";
import { CheckCheck, LogOut, RefreshCw, Sparkles } from "lucide-react";

export default function App() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [feedbackPending, setFeedbackPending] = useState<number | null>(null);
  const [unmutePending, setUnmutePending] = useState<Set<number>>(new Set());
  const [refreshSettings, setRefreshSettings] = useState<RefreshSettings>(loadRefreshSettings);
  const initialLoadDone = useRef(false);
  const loadRequestId = useRef(0);

  const load = useCallback(async (options?: { light?: boolean }) => {
    const t = getToken();
    if (!t) return;

    const requestId = ++loadRequestId.current;
    const light = options?.light ?? false;

    if (light) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const dashboard = await getDashboard(t, light);
      if (requestId !== loadRequestId.current) return;

      setData((prev) => {
        if (light && prev) {
          return { ...prev, quotes: dashboard.quotes, quotes_updated_at: dashboard.quotes_updated_at };
        }
        return dashboard;
      });
    } catch {
      if (requestId !== loadRequestId.current) return;
      clearToken();
      setTokenState(null);
      setError("Session expired. Please sign in again.");
    } finally {
      if (requestId === loadRequestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!token) {
      initialLoadDone.current = false;
      return;
    }
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    load();
  }, [token, load]);

  // Auto-refresh prices on user-chosen interval (light mode — quotes only).
  useEffect(() => {
    if (!token || !refreshSettings.enabled) return;
    const id = setInterval(() => load({ light: true }), refreshSettings.intervalSeconds * 1000);
    return () => clearInterval(id);
  }, [token, load, refreshSettings.enabled, refreshSettings.intervalSeconds]);

  async function handleFeedback(eventId: number, engaged: boolean) {
    const t = getToken();
    if (!t) return;

    const current = data?.feed
      .flatMap((item) => item.events)
      .find((e) => e.id === eventId)?.user_engaged;

    setFeedbackPending(eventId);
    try {
      if (current === engaged) {
        await clearFeedback(t, eventId);
        setData((prev) =>
          prev
            ? {
                ...prev,
                feed: prev.feed.map((item) => ({
                  ...item,
                  events: item.events.map((e) =>
                    e.id === eventId ? { ...e, user_engaged: null } : e
                  ),
                })),
              }
            : prev
        );
      } else {
        await submitFeedback(t, eventId, engaged);
        setData((prev) =>
          prev
            ? {
                ...prev,
                feed: prev.feed.map((item) => ({
                  ...item,
                  events: item.events.map((e) =>
                    e.id === eventId ? { ...e, user_engaged: engaged } : e
                  ),
                })),
              }
            : prev
        );
      }
    } catch {
      setError("Could not save feedback. Try again.");
    } finally {
      setFeedbackPending(null);
    }
  }

  async function handleMute(symbol: string, eventType: string) {
    const t = getToken();
    if (!t) return;
    try {
      await createMute(t, symbol, eventType);
      load();
    } catch {
      setError("Could not save mute preference.");
    }
  }

  async function handleUnmute(muteId: number) {
    const t = getToken();
    if (!t || unmutePending.has(muteId)) return;
    setUnmutePending((s) => new Set(s).add(muteId));
    setData((prev) =>
      prev ? { ...prev, mutes: prev.mutes.filter((m) => m.id !== muteId) } : prev
    );
    try {
      await deleteMute(t, muteId);
    } catch {
      setError("Could not remove mute.");
      load();
    } finally {
      setUnmutePending((s) => {
        const next = new Set(s);
        next.delete(muteId);
        return next;
      });
    }
  }

  async function handleMarkRead() {
    const t = getToken();
    if (!t) return;
    try {
      await markVisit(t);
      setData((prev) =>
        prev
          ? {
              ...prev,
              last_visit_at: new Date().toISOString(),
              unread_event_count: 0,
              feed: prev.feed.map((item) => ({
                ...item,
                events: item.events.map((e) => ({ ...e, is_new: false })),
              })),
            }
          : prev
      );
    } catch {
      setError("Could not mark alerts as read.");
    }
  }

  async function handleRemoveStock(itemId: number) {
    const t = getToken();
    if (!t) return;
    await removeWatchlistItem(t, itemId);
    await load();
  }

  function handleSignOut() {
    clearToken();
    setTokenState(null);
    setData(null);
    initialLoadDone.current = false;
  }

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100 p-4">
        <AuthForm onSuccess={() => setTokenState(getToken())} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <header className="border-b border-[var(--border)] bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              <Sparkles className="h-5 w-5 text-[var(--primary)]" />
              Smart Market Watchlist
            </h1>
            <p className="text-sm text-[var(--muted-foreground)]">Recent alerts and live prices</p>
          </div>
          <div className="flex items-center gap-2">
            {data && data.unread_event_count > 0 && (
              <span className="rounded-full bg-[var(--primary)] px-2 py-0.5 text-xs text-white">
                {data.unread_event_count} new
              </span>
            )}
            {data && data.unread_event_count > 0 && (
              <button
                type="button"
                onClick={handleMarkRead}
                className="flex items-center gap-1 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm"
              >
                <CheckCheck className="h-4 w-4" /> Mark read
              </button>
            )}
            <RefreshSettingsMenu settings={refreshSettings} onChange={setRefreshSettings} />
            <button
              type="button"
              onClick={() => load()}
              className="flex items-center gap-1 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm"
            >
              <RefreshCw className={`h-4 w-4 ${loading || refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={handleSignOut}
              className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-[var(--muted-foreground)]"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        {error && <p className="text-sm text-[var(--destructive)]">{error}</p>}

        {data && token && (
          <WatchlistManager
            items={data.watchlist}
            mutes={data.mutes}
            token={token}
            onChange={load}
            onUnmute={handleUnmute}
            unmutePending={unmutePending}
          />
        )}

        {data && token && (
          <QuotesTable
            quotes={data.quotes}
            watchlist={data.watchlist}
            token={token}
            onRemove={handleRemoveStock}
          />
        )}

        <section>
          <h2 className="mb-3 text-lg font-semibold">Recent alerts</h2>
          {data ? (
            <ChangeFeed
              feed={data.feed}
              onFeedback={handleFeedback}
              onMute={handleMute}
              feedbackPending={feedbackPending}
            />
          ) : (
            <p className="text-[var(--muted-foreground)]">Loading…</p>
          )}
        </section>

        <details className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 p-4 text-xs text-[var(--muted-foreground)]">
          <summary className="cursor-pointer font-medium text-[var(--foreground)]">How this works</summary>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>Alerts show price moves, pattern changes, and volume spikes from the last 24 hours</li>
            <li>Volume spikes appear as separate alerts when trading volume is unusually high</li>
            <li>Price changes appear in the table; small moves are not duplicated as alerts</li>
            <li>Click Mark read to clear the new badge — signing out no longer hides alerts</li>
            <li>Click any price card for charts and fundamentals (ROE, P/E, dividend yield, etc.)</li>
            <li>Hover a price card and click the trash icon to remove a stock</li>
            <li>Auto-refresh is in the header next to Refresh — click it to change the interval</li>
          </ul>
        </details>
      </main>
    </div>
  );
}
