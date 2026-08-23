"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  DEFAULT_THEME_PREFERENCE,
  getServerThemeSnapshot,
  isThemePreference,
  readThemeSnapshot,
  subscribeThemeSnapshot,
  writeThemePreference,
} from "@/lib/theme";
import type { ResolvedTheme, ThemePreference } from "@/types/theme";

interface ThemeContextValue {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

interface ThemeProviderProps {
  children: ReactNode;
}

function parseThemeSnapshot(snapshot: string): {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
} {
  const [preferenceValue, resolvedValue] = snapshot.split(":", 2);

  return {
    preference: isThemePreference(preferenceValue)
      ? preferenceValue
      : DEFAULT_THEME_PREFERENCE,
    resolvedTheme: resolvedValue === "dark" ? "dark" : "light",
  };
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const snapshot = useSyncExternalStore(
    subscribeThemeSnapshot,
    readThemeSnapshot,
    getServerThemeSnapshot,
  );
  const { preference, resolvedTheme } = useMemo(
    () => parseThemeSnapshot(snapshot),
    [snapshot],
  );

  const setPreference = useCallback((next: ThemePreference) => {
    writeThemePreference(next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      preference,
      resolvedTheme,
      setPreference,
    }),
    [preference, resolvedTheme, setPreference],
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemePreference(): ThemeContextValue {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error("useThemePreference must be used inside ThemeProvider.");
  }

  return value;
}
