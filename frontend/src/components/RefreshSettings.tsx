import { useEffect, useRef, useState } from "react";
import { Settings2 } from "lucide-react";
import {
  loadRefreshSettings,
  REFRESH_INTERVAL_OPTIONS,
  RefreshSettings,
  saveRefreshSettings,
} from "../lib/refreshSettings";

export function RefreshSettingsMenu({
  settings,
  onChange,
}: {
  settings: RefreshSettings;
  onChange: (next: RefreshSettings) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  function update(partial: Partial<RefreshSettings>) {
    const next = { ...settings, ...partial };
    saveRefreshSettings(next);
    onChange(next);
  }

  const label = settings.enabled ? `Auto ${settings.intervalSeconds}s` : "Auto off";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs sm:text-sm ${
          settings.enabled ? "border-indigo-200 bg-indigo-50 text-indigo-900" : "border-[var(--border)]"
        }`}
        title="Auto-refresh settings"
      >
        <Settings2 className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{label}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border border-[var(--border)] bg-white p-3 shadow-lg">
          <p className="mb-2 text-xs font-semibold">Auto-refresh prices</p>
          <label className="flex cursor-pointer items-center justify-between gap-2 text-sm">
            <span>Enabled</span>
            <input
              type="checkbox"
              checked={settings.enabled}
              onChange={(e) => update({ enabled: e.target.checked })}
              className="h-4 w-4 accent-[var(--primary)]"
            />
          </label>
          {settings.enabled && (
            <select
              value={settings.intervalSeconds}
              onChange={(e) => update({ intervalSeconds: Number(e.target.value) })}
              className="mt-2 w-full rounded border border-[var(--border)] px-2 py-1.5 text-xs"
            >
              {REFRESH_INTERVAL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          )}
          <p className="mt-2 text-[10px] leading-snug text-[var(--muted-foreground)]">
            Updates prices only. Use Refresh for alerts too.
          </p>
        </div>
      )}
    </div>
  );
}

export { loadRefreshSettings };
