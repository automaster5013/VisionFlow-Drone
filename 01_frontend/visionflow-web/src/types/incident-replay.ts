import type { IncidentSourceType } from "@/types/incident";

export interface IncidentReplayFocus {
  incidentId: number;
  sourceType: IncidentSourceType;
  occurredAt: string;
  latitude: number | null;
  longitude: number | null;
  altitude: number | null;
}
