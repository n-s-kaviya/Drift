import { useEffect, useState } from "react";
import { addWatchlistItem, AlertMute, formatApiError, searchSymbols, SymbolSearchResult, WatchlistItem } from "../lib/api";
import { STOCK_CATEGORIES } from "../lib/stockSuggestions";
import { Loader2, Plus, Search, VolumeX } from "lucide-react";

export function WatchlistManager({
  items,
  mutes,
  token,
  onChange,
  onUnmute,
  unmutePending,
}: {
  items: WatchlistItem[];
  mutes: AlertMute[];
  token: string;
  onChange: () => void | Promise<void>;
  onUnmute: (muteId: number) => void;
  unmutePending?: Set<number>;
}) {
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [addingSymbol, setAddingSymbol] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState(STOCK_CATEGORIES[0]?.id ?? "");
  const [searchQuery, setSearchQuery] = useState("");
  const [pendingSymbols, setPendingSymbols] = useState<Set<string>>(new Set());
  const [apiResults, setApiResults] = useState<SymbolSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const watchlistSymbols = new Set([...items.map((i) => i.symbol), ...pendingSymbols]);
  const activeCat = STOCK_CATEGORIES.find((c) => c.id === activeCategory);
  const isSearching = searchQuery.trim().length > 0;

  useEffect(() => {
    setPendingSymbols((prev) => {
      const next = new Set(prev);
      for (const sym of prev) {
        if (items.some((i) => i.symbol === sym)) next.delete(sym);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [items]);

  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      setApiResults([]);
      setSearchLoading(false);
      return;
    }

    setSearchLoading(true);
    const timer = setTimeout(() => {
      searchSymbols(token, q)
        .then(setApiResults)
        .catch(() => setApiResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, token]);

  async function addSymbol(sym: string) {
    const upper = sym.trim().toUpperCase();
    if (!upper || watchlistSymbols.has(upper)) {
      if (upper && items.some((i) => i.symbol === upper)) {
        setError(`${upper} is already on your watchlist.`);
      }
      return;
    }
    setAddingSymbol(upper);
    setError(null);
    try {
      await addWatchlistItem(token, upper);
      setPendingSymbols((prev) => new Set(prev).add(upper));
      setSymbol("");
      setSearchQuery("");
      await onChange();
    } catch (err) {
      setError(formatApiError(err, `Could not add ${upper}. Check the ticker and try again.`));
    } finally {
      setAddingSymbol(null);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim()) return;
    setLoading(true);
    await addSymbol(symbol);
    setLoading(false);
  }

  function renderResultChip(stock: { symbol: string; name: string; type?: string | null }) {
    const alreadyAdded = watchlistSymbols.has(stock.symbol);
    const isAdding = addingSymbol === stock.symbol;
    return (
      <button
        key={stock.symbol}
        type="button"
        disabled={alreadyAdded || isAdding}
        onClick={() => addSymbol(stock.symbol)}
        title={stock.name}
        className={`rounded-lg border px-2 py-2 text-left transition-colors ${
          alreadyAdded
            ? "cursor-default border-emerald-200 bg-emerald-50"
            : "border-[var(--border)] bg-white hover:border-[var(--primary)] hover:bg-indigo-50/60"
        } disabled:opacity-60`}
      >
        <span className="block text-xs font-bold leading-tight">{stock.symbol}</span>
        <span className="mt-0.5 block truncate text-[10px] leading-tight text-[var(--muted-foreground)]">
          {stock.name}
        </span>
        {stock.type && (
          <span className="mt-0.5 block truncate text-[10px] text-[var(--muted-foreground)]">{stock.type}</span>
        )}
        {alreadyAdded && <span className="mt-0.5 block text-[10px] text-emerald-700">✓</span>}
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] px-4 py-3">
        <h2 className="font-semibold">Add stocks</h2>
        <span className="rounded-full bg-[var(--muted)] px-2.5 py-0.5 text-xs font-medium">
          {items.length} in watchlist
        </span>
      </div>

      <div className="space-y-3 p-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <form onSubmit={handleAdd} className="flex min-w-0 flex-1 gap-2">
            <input
              placeholder="Type exact ticker (e.g. TCS.NS, INFY)"
              className="min-w-0 flex-1 rounded-lg border border-[var(--border)] px-3 py-2 text-sm uppercase"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            />
            <button
              type="submit"
              disabled={loading}
              className="shrink-0 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm text-white"
            >
              <Plus className="h-4 w-4" />
            </button>
          </form>
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[var(--muted-foreground)]" />
            <input
              placeholder="Search any company worldwide (TCS, Infosys, Apple…)"
              className="w-full rounded-lg border border-[var(--border)] py-2 pl-9 pr-3 text-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {error && <p className="text-sm text-[var(--destructive)]">{error}</p>}

        {!isSearching && (
          <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-7">
            {STOCK_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setActiveCategory(cat.id)}
                className={`rounded-lg border px-2 py-1.5 text-xs font-medium leading-tight transition-colors ${
                  activeCategory === cat.id
                    ? "border-[var(--primary)] bg-indigo-50 text-indigo-900"
                    : "border-[var(--border)] hover:bg-[var(--muted)]"
                }`}
              >
                <span className="mr-0.5">{cat.icon}</span>
                {cat.name}
              </button>
            ))}
          </div>
        )}

        <div>
          {isSearching ? (
            <>
              {searchLoading ? (
                <p className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching global markets…
                </p>
              ) : (
                <p className="mb-2 text-xs text-[var(--muted-foreground)]">
                  {apiResults.length} result{apiResults.length !== 1 ? "s" : ""} for &ldquo;{searchQuery}&rdquo;
                </p>
              )}

              {!searchLoading && apiResults.length > 0 && (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
                  {apiResults.map((stock) => renderResultChip(stock))}
                </div>
              )}

              {!searchLoading && apiResults.length === 0 && (
                <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--muted)]/20 px-4 py-3 text-sm">
                  <p className="text-[var(--muted-foreground)]">
                    No matches found. You can still add it if you know the exact ticker.
                  </p>
                  <button
                    type="button"
                    onClick={() => addSymbol(searchQuery)}
                    className="mt-2 rounded-lg border border-[var(--primary)] bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-900 hover:bg-indigo-100"
                  >
                    Add &ldquo;{searchQuery.trim().toUpperCase()}&rdquo; anyway
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              {activeCat && (
                <p className="mb-2 text-xs text-[var(--muted-foreground)]">{activeCat.description}</p>
              )}
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10">
                {(activeCat?.stocks ?? []).map((stock) => renderResultChip(stock))}
              </div>
            </>
          )}
        </div>

        {mutes.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2">
            <VolumeX className="h-4 w-4 shrink-0 text-amber-800" />
            <span className="text-xs font-medium text-amber-900">Muted:</span>
            {mutes.map((m) => (
              <span key={m.id} className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs">
                {m.symbol} ({m.event_type.replace(/_/g, " ")})
                <button
                  type="button"
                  disabled={unmutePending?.has(m.id)}
                  onClick={() => onUnmute(m.id)}
                  className="text-amber-800 underline disabled:opacity-50"
                >
                  unmute
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
