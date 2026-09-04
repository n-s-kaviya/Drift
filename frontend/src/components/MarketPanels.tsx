import { useMemo, useState } from "react";
import { ChangeEvent, FeedItem, MarketQuote, WatchlistItem } from "../lib/api";
import { StockDetailModal } from "./StockDetailModal";
import { Layers, Search, Trash2, ThumbsDown, ThumbsUp, VolumeX, X } from "lucide-react";

const EVENT_LABELS: Record<string, string> = {
  regime_shift: "Trading pattern change",
  price_move: "Price change",
  outlier: "Unusual move",
  anomaly: "Unusual activity",
  corporate_action: "Corporate action",
  trading_halted: "Trading paused",
  volume_anomaly: "High volume",
};

function normalizeQuery(q: string) {
  return q.trim().toLowerCase();
}

function textMatchesQuery(text: string | null | undefined, query: string) {
  if (!query) return true;
  return (text ?? "").toLowerCase().includes(query);
}

function eventMatchesQuery(event: ChangeEvent, query: string) {
  if (!query) return true;
  return [
    event.symbol,
    event.title,
    event.summary,
    event.why_plain,
    EVENT_LABELS[event.event_type] || event.event_type,
  ].some((part) => textMatchesQuery(part, query));
}

function feedItemMatches(item: FeedItem, query: string): boolean {
  if (!query) return true;
  if (item.kind === "bundle") {
    return (
      textMatchesQuery(item.title, query) ||
      textMatchesQuery(item.summary, query) ||
      textMatchesQuery(item.why_plain, query) ||
      item.events.some((e) => eventMatchesQuery(e, query))
    );
  }
  return eventMatchesQuery(item.events[0], query);
}

function filterFeed(feed: FeedItem[], query: string): FeedItem[] {
  const q = normalizeQuery(query);
  if (!q) return feed;

  return feed
    .filter((item) => feedItemMatches(item, q))
    .map((item) => {
      if (item.kind !== "bundle") return item;
      const events = item.events.filter((e) => eventMatchesQuery(e, q));
      return events.length > 0 ? { ...item, events } : item;
    });
}

function SectionSearch({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative w-full sm:w-52">
      <Search className="absolute left-2.5 top-2 h-4 w-4 text-[var(--muted-foreground)]" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-[var(--border)] bg-white py-1.5 pl-8 pr-8 text-sm"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          className="absolute right-2 top-1.5 rounded p-0.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
          aria-label="Clear search"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function formatTime(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function EventCard({
  event,
  onFeedback,
  onMute,
  feedbackPending,
  compact = false,
}: {
  event: ChangeEvent;
  onFeedback: (eventId: number, engaged: boolean) => void;
  onMute: (symbol: string, eventType: string) => void;
  feedbackPending?: number | null;
  compact?: boolean;
}) {
  const muteType =
    event.event_type === "anomaly" && event.summary.toLowerCase().includes("volume")
      ? "volume_anomaly"
      : event.event_type;

  const detail = !compact ? event.why_plain || event.summary : null;

  return (
    <div
      className={`flex h-full min-h-[9.5rem] flex-col rounded-lg border bg-white p-2.5 ${
        event.is_new ? "border-[var(--primary)]/40 ring-1 ring-[var(--primary)]/20" : "border-[var(--border)]"
      }`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-sm font-bold">{event.symbol}</span>
        {event.is_new && (
          <span className="rounded-full bg-[var(--primary)] px-1.5 py-0.5 text-[9px] font-medium text-white">
            New
          </span>
        )}
      </div>

      <span className="mt-1 w-fit rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] text-indigo-800">
        {EVENT_LABELS[event.event_type] || event.event_type}
      </span>

      <p className="mt-1.5 line-clamp-2 text-xs font-medium leading-snug">{event.title}</p>

      {detail && (
        <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-[var(--muted-foreground)]">{detail}</p>
      )}

      <p className="mt-auto pt-1.5 text-[10px] text-[var(--muted-foreground)]">{formatTime(event.created_at)}</p>

      <div className="mt-1.5 flex gap-1">
        <button
          type="button"
          title="Useful"
          disabled={feedbackPending === event.id}
          onClick={() => onFeedback(event.id, true)}
          className={`flex flex-1 items-center justify-center rounded border py-1 ${event.user_engaged === true ? "bg-[var(--primary)] text-white" : "hover:bg-[var(--muted)]"}`}
        >
          <ThumbsUp className="h-3 w-3" />
        </button>
        <button
          type="button"
          title="Not useful"
          disabled={feedbackPending === event.id}
          onClick={() => onFeedback(event.id, false)}
          className={`flex flex-1 items-center justify-center rounded border py-1 ${event.user_engaged === false ? "bg-red-100 text-red-800" : "hover:bg-[var(--muted)]"}`}
        >
          <ThumbsDown className="h-3 w-3" />
        </button>
        <button
          type="button"
          title="Mute this alert type"
          onClick={() => onMute(event.symbol, muteType)}
          className="flex flex-1 items-center justify-center rounded border border-amber-200 bg-amber-50 py-1 text-amber-900 hover:bg-amber-100"
        >
          <VolumeX className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

export function ChangeFeed({
  feed,
  onFeedback,
  onMute,
  feedbackPending,
}: {
  feed: FeedItem[];
  onFeedback: (eventId: number, engaged: boolean) => void;
  onMute: (symbol: string, eventType: string) => void;
  feedbackPending?: number | null;
}) {
  const [search, setSearch] = useState("");
  const filteredFeed = useMemo(() => filterFeed(feed, search), [feed, search]);
  const query = normalizeQuery(search);

  if (feed.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] py-10 text-center">
        <p className="font-medium">No recent alerts</p>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          Price moves, trading-pattern changes, and volume spikes from the last 24 hours appear here.
          Click Refresh to check for new activity.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-[var(--muted-foreground)]">
          {query
            ? `${filteredFeed.length} of ${feed.length} alert${feed.length !== 1 ? "s" : ""}`
            : `${feed.length} alert${feed.length !== 1 ? "s" : ""}`}
        </p>
        <SectionSearch
          value={search}
          onChange={setSearch}
          placeholder="Filter by symbol or keyword…"
        />
      </div>

      {filteredFeed.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--card)] py-8 text-center">
          <p className="font-medium">No alerts match &ldquo;{search}&rdquo;</p>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">Try a ticker like NVDA or a word from the alert.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredFeed.map((item) =>
            item.kind === "bundle" ? (
              <div
                key={item.bundle_id}
                className="col-span-full rounded-xl border border-amber-200 bg-amber-50/40 p-3"
              >
                <div className="mb-2 flex items-center gap-1 text-xs font-medium text-amber-900">
                  <Layers className="h-3.5 w-3.5" /> {item.title}
                </div>
                <p className="mb-2 line-clamp-2 text-xs text-[var(--muted-foreground)]">
                  {item.why_plain || item.summary}
                </p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {item.events.map((event) => (
                    <EventCard
                      key={event.id}
                      event={event}
                      onFeedback={onFeedback}
                      onMute={onMute}
                      feedbackPending={feedbackPending}
                      compact
                    />
                  ))}
                </div>
              </div>
            ) : (
              <EventCard
                key={item.events[0]?.id}
                event={item.events[0]}
                onFeedback={onFeedback}
                onMute={onMute}
                feedbackPending={feedbackPending}
              />
            )
          )}
        </div>
      )}
    </div>
  );
}

export function QuotesTable({
  quotes,
  watchlist,
  token,
  onRemove,
}: {
  quotes: MarketQuote[];
  watchlist: WatchlistItem[];
  token: string;
  onRemove: (itemId: number) => void | Promise<void>;
}) {
  const [selectedQuote, setSelectedQuote] = useState<MarketQuote | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");

  const itemBySymbol = new Map(watchlist.map((i) => [i.symbol, i]));
  const query = normalizeQuery(search);
  const filteredQuotes = useMemo(() => {
    if (!query) return quotes;
    return quotes.filter((q) =>
      [q.symbol, q.trust_label, q.abnormality_label, q.source].some((part) =>
        textMatchesQuery(part, query)
      )
    );
  }, [quotes, query]);

  async function handleRemove(e: React.MouseEvent, itemId: number) {
    e.stopPropagation();
    if (removingId) return;
    setRemovingId(itemId);
    try {
      await onRemove(itemId);
    } finally {
      setRemovingId(null);
    }
  }

  if (quotes.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] py-8 text-center text-[var(--muted-foreground)]">
        Add symbols to your watchlist to see live quotes.
      </div>
    );
  }

  return (
    <>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)]">
        <div className="flex flex-col gap-3 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold">Latest prices</h2>
            <p className="text-xs text-[var(--muted-foreground)]">
              {query
                ? `${filteredQuotes.length} of ${quotes.length} stocks`
                : `${quotes.length} stocks`}{" "}
              · click a card for charts & fundamentals
            </p>
          </div>
          <SectionSearch
            value={search}
            onChange={setSearch}
            placeholder="Search your stocks…"
          />
        </div>
        {filteredQuotes.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
            No stocks match &ldquo;{search}&rdquo;
          </div>
        ) : (
        <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8">
          {filteredQuotes.map((q) => {
            const item = itemBySymbol.get(q.symbol);
            const up = q.change_pct >= 0;
            return (
              <div
                key={q.symbol}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedQuote(q)}
                onKeyDown={(e) => e.key === "Enter" && setSelectedQuote(q)}
                className="group relative cursor-pointer rounded-lg border border-[var(--border)] bg-white p-2.5 text-left transition-colors hover:border-[var(--primary)] hover:bg-indigo-50/50"
              >
                {item && (
                  <button
                    type="button"
                    title={`Remove ${q.symbol}`}
                    disabled={removingId === item.id}
                    onClick={(e) => handleRemove(e, item.id)}
                    className="absolute right-1 top-1 z-10 rounded p-0.5 text-[var(--muted-foreground)] opacity-0 transition-opacity hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
                <p className="truncate pr-4 text-sm font-bold">{q.symbol}</p>
                <p className="mt-0.5 text-base font-semibold tabular-nums">${q.price.toFixed(2)}</p>
                <p className={`text-xs font-medium tabular-nums ${up ? "text-emerald-600" : "text-red-600"}`}>
                  {up ? "+" : ""}
                  {q.change_pct.toFixed(2)}%
                </p>
                <p className="mt-1 truncate text-[10px] text-[var(--muted-foreground)]">
                  Vol {(q.volume / 1e6).toFixed(1)}M
                  {q.is_stale && <span className="ml-1 text-amber-700">· stale</span>}
                </p>
              </div>
            );
          })}
        </div>
        )}
      </div>

      {selectedQuote && (
        <StockDetailModal quote={selectedQuote} token={token} onClose={() => setSelectedQuote(null)} />
      )}
    </>
  );
}
