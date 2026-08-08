import {
  EVENT_TIME_RANGE_OPTIONS,
  STATISTICS_RANGE_OPTIONS,
  type EventTimeRange,
  type OperatorConsolePreferences,
  type StatisticsRangeDays,
  type StoredOperatorConsolePreferences,
} from "@/types/operator-console-settings";

export const OPERATOR_CONSOLE_SETTINGS_STORAGE_KEY =
  "visionflow.operator-console-settings.v1";

export const DEFAULT_OPERATOR_CONSOLE_PREFERENCES: OperatorConsolePreferences = {
  eventAutoRefresh: true,
  eventTimeRange: "24H",
  statisticsAutoRefresh: true,
  statisticsRangeDays: 30,
  aiModelAutoRefresh: true,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isEventTimeRange(value: unknown): value is EventTimeRange {
  return EVENT_TIME_RANGE_OPTIONS.some((option) => option === value);
}

function isStatisticsRangeDays(value: unknown): value is StatisticsRangeDays {
  return STATISTICS_RANGE_OPTIONS.some((option) => option === value);
}

export function parseOperatorConsolePreferences(
  value: unknown,
): OperatorConsolePreferences | null {
  if (!isRecord(value)) return null;
  const candidate = isRecord(value.preferences) ? value.preferences : value;
  if (
    typeof candidate.eventAutoRefresh !== "boolean" ||
    !isEventTimeRange(candidate.eventTimeRange) ||
    typeof candidate.statisticsAutoRefresh !== "boolean" ||
    !isStatisticsRangeDays(candidate.statisticsRangeDays) ||
    typeof candidate.aiModelAutoRefresh !== "boolean"
  ) {
    return null;
  }
  return {
    eventAutoRefresh: candidate.eventAutoRefresh,
    eventTimeRange: candidate.eventTimeRange,
    statisticsAutoRefresh: candidate.statisticsAutoRefresh,
    statisticsRangeDays: candidate.statisticsRangeDays,
    aiModelAutoRefresh: candidate.aiModelAutoRefresh,
  };
}

export function readOperatorConsolePreferences(): OperatorConsolePreferences {
  if (typeof window === "undefined") {
    return { ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES };
  }
  try {
    const serialized = window.localStorage.getItem(
      OPERATOR_CONSOLE_SETTINGS_STORAGE_KEY,
    );
    if (!serialized) return { ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES };
    return (
      parseOperatorConsolePreferences(JSON.parse(serialized)) ??
      { ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES }
    );
  } catch {
    return { ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES };
  }
}

export function writeOperatorConsolePreferences(
  preferences: OperatorConsolePreferences,
): string {
  const updatedAt = new Date().toISOString();
  const payload: StoredOperatorConsolePreferences = {
    schemaVersion: 1,
    updatedAt,
    preferences,
  };
  window.localStorage.setItem(
    OPERATOR_CONSOLE_SETTINGS_STORAGE_KEY,
    JSON.stringify(payload),
  );
  return updatedAt;
}

export function resetOperatorConsolePreferences(): OperatorConsolePreferences {
  window.localStorage.removeItem(OPERATOR_CONSOLE_SETTINGS_STORAGE_KEY);
  return { ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES };
}
