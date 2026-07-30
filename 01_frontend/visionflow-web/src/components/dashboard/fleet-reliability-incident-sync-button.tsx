"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { parseFlightQualityIncidentSyncResponse } from "@/types/flight-quality-incident";

function errorMessage(body: unknown, fallback: string): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string"
  ) {
    return body.message;
  }
  return fallback;
}

export function FleetReliabilityIncidentSyncButton() {
  const router = useRouter();
  const { canOperate, operateDeniedReason } = useOperatorAccess();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function synchronize() {
    if (!canOperate || busy) {
      return;
    }

    setBusy(true);
    setMessage(null);
    setFailed(false);

    try {
      const response = await fetch(
        "/api/flight-quality/fleet-reliability/" +
          "incidents/synchronize?limitPerDrone=20",
        {
          method: "POST",
          headers: { Accept: "application/json" },
          cache: "no-store",
        },
      );
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // JSON이 아니면 HTTP 상태 기반 오류 문구를 사용합니다.
      }

      if (!response.ok) {
        throw new Error(
          errorMessage(
            body,
            `Incident 동기화 실패: HTTP ${response.status}`,
          ),
        );
      }

      const result = parseFlightQualityIncidentSyncResponse(body);
      if (!result) {
        throw new Error("Incident 동기화 응답 형식이 올바르지 않습니다.");
      }

      setMessage(
        `생성 ${result.createdCount} · 갱신 ${result.updatedCount} · ` +
          `중복 억제 ${result.deduplicatedCount} · ` +
          `재개 ${result.reopenedCount} · 해결 ${result.resolvedCount}`,
      );
      router.refresh();
    } catch (error) {
      setFailed(true);
      setMessage(
        error instanceof Error
          ? error.message
          : "기체 신뢰도 Incident 동기화에 실패했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => void synchronize()}
        disabled={!canOperate || busy}
        title={!canOperate ? (operateDeniedReason ?? undefined) : undefined}
        className="rounded-lg border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm font-bold text-cyan-900 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Incident 동기화 중" : "Incident 동기화"}
      </button>
      {message && (
        <p
          role={failed ? "alert" : "status"}
          className={`max-w-xs text-right text-xs ${
            failed ? "text-red-700" : "text-emerald-700"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
