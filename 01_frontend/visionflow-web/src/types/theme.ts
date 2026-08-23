export const THEME_PREFERENCES = ["system", "light", "dark"] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number];
export type ResolvedTheme = Exclude<ThemePreference, "system">;

export interface StoredThemePreference {
  schemaVersion: 1;
  preference: ThemePreference;
  updatedAt: string;
}
