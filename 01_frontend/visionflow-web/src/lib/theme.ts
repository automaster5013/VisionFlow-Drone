import {
  THEME_PREFERENCES,
  type ResolvedTheme,
  type StoredThemePreference,
  type ThemePreference,
} from "@/types/theme";

export const THEME_STORAGE_KEY = "visionflow.theme-preference.v1";
export const THEME_COOKIE_NAME = "vf-theme";
export const THEME_CHANGE_EVENT = "visionflow:theme-change";
export const DEFAULT_THEME_PREFERENCE: ThemePreference = "system";
export const SERVER_THEME_SNAPSHOT = "system:light";

export function isThemePreference(
  value: unknown,
): value is ThemePreference {
  return THEME_PREFERENCES.some((candidate) => candidate === value);
}

export function parseThemePreference(value: unknown): ThemePreference | null {
  if (isThemePreference(value)) {
    return value;
  }

  if (
    typeof value === "object" &&
    value !== null &&
    "preference" in value &&
    isThemePreference(value.preference)
  ) {
    return value.preference;
  }

  return null;
}

export function resolveThemePreference(
  preference: ThemePreference,
  prefersDark: boolean,
): ResolvedTheme {
  if (preference === "system") {
    return prefersDark ? "dark" : "light";
  }

  return preference;
}

export function readThemePreference(): ThemePreference {
  if (typeof window === "undefined") {
    return DEFAULT_THEME_PREFERENCE;
  }

  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_THEME_PREFERENCE;
    }

    try {
      return (
        parseThemePreference(JSON.parse(raw)) ??
        parseThemePreference(raw) ??
        DEFAULT_THEME_PREFERENCE
      );
    } catch {
      return parseThemePreference(raw) ?? DEFAULT_THEME_PREFERENCE;
    }
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

export function applyThemePreference(
  preference: ThemePreference,
): ResolvedTheme {
  if (typeof window === "undefined") {
    return "light";
  }

  const prefersDark = window.matchMedia(
    "(prefers-color-scheme: dark)",
  ).matches;
  const resolved = resolveThemePreference(preference, prefersDark);
  const root = window.document.documentElement;

  root.dataset.theme = preference;
  root.dataset.resolvedTheme = resolved;
  root.style.colorScheme = resolved;

  return resolved;
}

export function readThemeSnapshot(): string {
  if (typeof window === "undefined") {
    return SERVER_THEME_SNAPSHOT;
  }

  const preference = readThemePreference();
  const resolved = resolveThemePreference(
    preference,
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  return `${preference}:${resolved}`;
}

export function getServerThemeSnapshot(): string {
  return SERVER_THEME_SNAPSHOT;
}

export function subscribeThemeSnapshot(
  onStoreChange: () => void,
): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const media = window.matchMedia("(prefers-color-scheme: dark)");

  const synchronize = () => {
    applyThemePreference(readThemePreference());
    onStoreChange();
  };

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== THEME_STORAGE_KEY) return;
    synchronize();
  };

  const handleThemeChange = () => synchronize();

  const handleMediaChange = () => {
    if (readThemePreference() !== "system") return;
    synchronize();
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange);
  media.addEventListener("change", handleMediaChange);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange);
    media.removeEventListener("change", handleMediaChange);
  };
}

export function writeThemePreference(
  preference: ThemePreference,
): string {
  const updatedAt = new Date().toISOString();

  if (typeof window === "undefined") {
    return updatedAt;
  }

  const payload: StoredThemePreference = {
    schemaVersion: 1,
    preference,
    updatedAt,
  };

  try {
    window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify(payload),
    );
  } catch {
    // Theme still applies for the current page when storage is unavailable.
  }

  try {
    window.document.cookie = [
      `${THEME_COOKIE_NAME}=${preference}`,
      "Path=/",
      "Max-Age=31536000",
      "SameSite=Lax",
    ].join("; ");
  } catch {
    // Cookie persistence is optional; local visual state remains available.
  }

  applyThemePreference(preference);
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
  return updatedAt;
}
