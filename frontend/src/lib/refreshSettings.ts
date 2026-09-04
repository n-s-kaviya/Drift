export type RefreshSettings = {
  enabled: boolean;
  intervalSeconds: number;
};

const STORAGE_KEY = "drift_refresh_settings";

export const REFRESH_INTERVAL_OPTIONS = [
  { value: 10, label: "Every 10 seconds" },
  { value: 30, label: "Every 30 seconds" },
  { value: 50, label: "Every 50 seconds" },
  { value: 60, label: "Every 1 minute" },
  { value: 90, label: "Every 90 seconds" },
  { value: 120, label: "Every 2 minutes" },
] as const;

const DEFAULT_SETTINGS: RefreshSettings = {
  enabled: true,
  intervalSeconds: 30,
};

export function loadRefreshSettings(): RefreshSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<RefreshSettings>;
    const intervalSeconds =
      REFRESH_INTERVAL_OPTIONS.find((o) => o.value === parsed.intervalSeconds)?.value ??
      DEFAULT_SETTINGS.intervalSeconds;
    return {
      enabled: parsed.enabled ?? DEFAULT_SETTINGS.enabled,
      intervalSeconds,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveRefreshSettings(settings: RefreshSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}
