export const EVENT_TIME_RANGE_OPTIONS = ["1H", "6H", "24H", "7D", "ALL"] as const;
export const STATISTICS_RANGE_OPTIONS = [7, 30, 90] as const;

export type EventTimeRange = (typeof EVENT_TIME_RANGE_OPTIONS)[number];
export type StatisticsRangeDays = (typeof STATISTICS_RANGE_OPTIONS)[number];

export interface OperatorConsolePreferences {
  eventAutoRefresh: boolean;
  eventTimeRange: EventTimeRange;
  statisticsAutoRefresh: boolean;
  statisticsRangeDays: StatisticsRangeDays;
  aiModelAutoRefresh: boolean;
}

export interface StoredOperatorConsolePreferences {
  schemaVersion: 1;
  updatedAt: string;
  preferences: OperatorConsolePreferences;
}
