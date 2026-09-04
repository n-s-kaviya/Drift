import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Fundamentals, getStockDetails, MarketQuote, PriceBar } from "../lib/api";
import { Loader2, X } from "lucide-react";

function formatCap(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

function formatPct(n: number | null, signed = false): string {
  if (n == null) return "—";
  const prefix = signed && n > 0 ? "+" : "";
  return `${prefix}${n.toFixed(2)}%`;
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]">{label}</p>
      <p className="mt-0.5 text-sm font-semibold">{value}</p>
      {hint && <p className="text-[10px] text-[var(--muted-foreground)]">{hint}</p>}
    </div>
  );
}

function PriceTooltip({ active, payload }: { active?: boolean; payload?: { payload: PriceBar }[] }) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border bg-white px-3 py-2 text-xs shadow-md">
      <p className="font-medium">{d.date}</p>
      <p>Close: ${d.close.toFixed(2)}</p>
      <p className="text-[var(--muted-foreground)]">Vol: {(d.volume / 1e6).toFixed(2)}M</p>
    </div>
  );
}

function VolumeTooltip({ active, payload }: { active?: boolean; payload?: { payload: PriceBar }[] }) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border bg-white px-3 py-2 text-xs shadow-md">
      <p className="font-medium">{d.date}</p>
      <p>Volume: {(d.volume / 1e6).toFixed(2)}M shares</p>
    </div>
  );
}

export function StockDetailModal({
  quote,
  token,
  onClose,
}: {
  quote: MarketQuote;
  token: string;
  onClose: () => void;
}) {
  const [period, setPeriod] = useState("1m");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<PriceBar[]>([]);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getStockDetails(token, quote.symbol, period)
      .then((data) => {
        if (cancelled) return;
        setHistory(data.history);
        setFundamentals(data.fundamentals);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load stock details.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, quote.symbol, period]);

  const priceStart = history[0]?.close;
  const priceEnd = history[history.length - 1]?.close;
  const periodChange =
    priceStart && priceEnd ? ((priceEnd - priceStart) / priceStart) * 100 : quote.change_pct;

  const chartData = history.map((b) => ({
    ...b,
    label: b.date.slice(5),
    volM: Math.round(b.volume / 1e6),
  }));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-2 sm:items-center sm:p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-[var(--border)] bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-start justify-between border-b border-[var(--border)] bg-white px-4 py-3">
          <div>
            <h2 className="text-lg font-semibold">{quote.symbol}</h2>
            <p className="text-sm text-[var(--muted-foreground)]">
              {fundamentals?.company_name ?? "Loading…"}
              {fundamentals?.sector && ` · ${fundamentals.sector}`}
            </p>
            <p className="mt-1 text-2xl font-bold">
              ${quote.price.toFixed(2)}{" "}
              <span className={`text-base font-medium ${quote.change_pct >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {quote.change_pct >= 0 ? "+" : ""}
                {quote.change_pct.toFixed(2)}% today
              </span>
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 hover:bg-[var(--muted)]">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div className="flex flex-wrap gap-2">
            {(["1w", "1m", "3m", "6m", "1y"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPeriod(p)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  period === p ? "bg-[var(--primary)] text-white" : "border border-[var(--border)]"
                }`}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading charts…
            </div>
          ) : error ? (
            <p className="py-8 text-center text-sm text-[var(--destructive)]">{error}</p>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-[var(--border)] p-3">
                  <div className="mb-2 flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold">Price trend</h3>
                    <span className={`text-xs font-medium ${periodChange >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {periodChange >= 0 ? "+" : ""}
                      {periodChange.toFixed(1)}% over period
                    </span>
                  </div>
                  <p className="mb-2 text-[10px] text-[var(--muted-foreground)]">
                    How the stock price moved — up means gains, down means losses.
                  </p>
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} width={48} tickFormatter={(v) => `$${v}`} />
                      <Tooltip content={<PriceTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="close"
                        stroke={periodChange >= 0 ? "#059669" : "#dc2626"}
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="rounded-xl border border-[var(--border)] p-3">
                  <h3 className="mb-2 text-sm font-semibold">Trading volume</h3>
                  <p className="mb-2 text-[10px] text-[var(--muted-foreground)]">
                    Taller bars = more shares traded that day. Spikes often mean news or heavy interest.
                  </p>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 10 }} width={40} tickFormatter={(v) => `${v}M`} />
                      <Tooltip content={<VolumeTooltip />} />
                      <Bar dataKey="volM" fill="#6366f1" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {fundamentals && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Key fundamentals</h3>
                  <p className="mb-3 text-xs text-[var(--muted-foreground)]">
                    Financial health metrics that help explain how the company is performing.
                  </p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                    <MetricCard label="ROE" value={formatPct(fundamentals.roe)} hint="Return on equity — profitability" />
                    <MetricCard
                      label="Debt / Equity"
                      value={fundamentals.debt_to_equity != null ? fundamentals.debt_to_equity.toFixed(2) : "—"}
                      hint="Lower = less debt risk"
                    />
                    <MetricCard label="Div. Yield" value={formatPct(fundamentals.dividend_yield)} hint="Annual dividend %" />
                    <MetricCard label="P/E Ratio" value={fundamentals.pe_ratio?.toFixed(1) ?? "—"} hint="Price vs earnings" />
                    <MetricCard label="Profit Margin" value={formatPct(fundamentals.profit_margin)} hint="How much revenue becomes profit" />
                    <MetricCard label="Beta" value={fundamentals.beta?.toFixed(2) ?? "—"} hint="Volatility vs market (1 = average)" />
                    <MetricCard label="Market Cap" value={formatCap(fundamentals.market_cap)} hint="Total company value" />
                    <MetricCard label="Revenue Growth" value={formatPct(fundamentals.revenue_growth, true)} hint="Year-over-year sales change" />
                  </div>
                  {fundamentals.industry && (
                    <p className="mt-2 text-xs text-[var(--muted-foreground)]">Industry: {fundamentals.industry}</p>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div className="rounded-lg bg-[var(--muted)]/40 px-2 py-1.5">
                  <span className="text-[var(--muted-foreground)]">Day high </span>
                  <span className="font-medium">${quote.high.toFixed(2)}</span>
                </div>
                <div className="rounded-lg bg-[var(--muted)]/40 px-2 py-1.5">
                  <span className="text-[var(--muted-foreground)]">Day low </span>
                  <span className="font-medium">${quote.low.toFixed(2)}</span>
                </div>
                <div className="rounded-lg bg-[var(--muted)]/40 px-2 py-1.5">
                  <span className="text-[var(--muted-foreground)]">Volume </span>
                  <span className="font-medium">{(quote.volume / 1e6).toFixed(2)}M</span>
                </div>
                <div className="rounded-lg bg-[var(--muted)]/40 px-2 py-1.5">
                  <span className="text-[var(--muted-foreground)]">Status </span>
                  <span className="font-medium">{quote.abnormality_label}</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
