"use client";

import { useThemePreference } from "@/components/theme/theme-provider";
import type { ThemePreference } from "@/types/theme";

const OPTIONS: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  glyph: string;
  title: string;
}> = [
  {
    value: "system",
    label: "자동",
    glyph: "◐",
    title: "시스템 설정에 맞춰 자동 전환",
  },
  {
    value: "light",
    label: "주간",
    glyph: "☀",
    title: "주간 모드",
  },
  {
    value: "dark",
    label: "야간",
    glyph: "◒",
    title: "야간 모드",
  },
];

export function ThemeSelector() {
  const { preference, resolvedTheme, setPreference } =
    useThemePreference();

  return (
    <div
      role="group"
      aria-label="화면 테마"
      className="vf-theme-selector"
      data-theme-preference={preference}
      data-resolved-theme={resolvedTheme}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={preference === option.value}
          title={option.title}
          className="vf-theme-selector__button"
          onClick={() => setPreference(option.value)}
        >
          <span aria-hidden="true">{option.glyph}</span>
          <span className="vf-theme-selector__label">
            {option.label}
          </span>
        </button>
      ))}
      <span className="sr-only" aria-live="polite">
        현재 화면 테마: {preference}, 실제 표시: {resolvedTheme}
      </span>
    </div>
  );
}
